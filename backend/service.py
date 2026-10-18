"""VERA staff authentication, catalogue and current project-operation API."""
import os, json, secrets, hashlib, hmac, time, base64, binascii, re, sys
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from contextlib import nullcontext
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from database import connect, BACKEND, SCHEMA
from image_storage import put_image,get_image,MAX_BYTES,MODE as STORAGE_MODE,MEDIA_DIR,StorageError

DB_PATH=os.environ.get('VERA_DB',str(Path(__file__).with_name('vera.db')))
app=FastAPI(title='VERA Project Operations API')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['*'],allow_headers=['*'])
security=HTTPBearer(auto_error=False)
BUSINESS_TZ=ZoneInfo(os.getenv('VERA_TIMEZONE','Pacific/Auckland'))


def business_now():return datetime.now(BUSINESS_TZ)

def now():
    return datetime.now(timezone.utc).isoformat()

def db():
    return connect(DB_PATH)

def dump(value):
    return json.dumps(value, ensure_ascii=False)

def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 120_000).hex()
    return f'{salt}${digest}'

def password_ok(password: str, stored: str) -> bool:
    salt, digest = stored.split('$', 1)
    check = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 120_000).hex()
    return hmac.compare_digest(check, digest)

def init_db(connection=None,seed_admin=True,seed_catalog=True):
    if BACKEND=='sqlite': Path(DB_PATH).parent.mkdir(parents=True,exist_ok=True)
    with (nullcontext(connection) if connection else db()) as c:
        if BACKEND=='postgres':
            c.ensure_schema();c.execute('BEGIN IMMEDIATE')
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY,company TEXT NOT NULL,locale TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,name TEXT NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,expires_at REAL NOT NULL,username TEXT NOT NULL);
        """)
        from operations import migrate
        migrate(c)
        if 'notes' not in {r['name'] for r in c.execute('PRAGMA table_info(customers)')}:
            c.execute("ALTER TABLE customers ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
        if 'username' not in {r['name'] for r in c.execute('PRAGMA table_info(sessions)')}:
            c.execute("ALTER TABLE sessions ADD COLUMN username TEXT NOT NULL DEFAULT 'dylan'")
        if seed_admin and not c.execute('SELECT 1 FROM users WHERE username=?',('dylan',)).fetchone():
            if BACKEND=='postgres' and len(os.getenv('VERA_DEMO_PASSWORD',''))<8: raise RuntimeError('Set VERA_DEMO_PASSWORD before initializing a PostgreSQL administrator')
            c.execute('INSERT INTO users(username,name,password_hash,role,active) VALUES(?,?,?,?,1)',('dylan','Dylan',password_hash(os.environ.get('VERA_DEMO_PASSWORD','vera-demo')),'admin'))
        for p in ([
            {'id':1,'name_zh':'铝百叶（示例）','name_en':'Aluminium Blinds (Sample)','material_zh':'铝合金','material_en':'Aluminium','description_zh':'轻盈的叶片与灵活的光线控制。产品及规格待客户确认。','description_en':'Lightweight slats and versatile light control. Product and specifications await confirmation.','category':'aluminium','sample':True},
            {'id':2,'name_zh':'木百叶（示例）','name_en':'Timber Blinds (Sample)','material_zh':'木材','material_en':'Timber','description_zh':'温暖质感，适合自然风格空间。产品及规格待客户确认。','description_en':'Warm texture for natural interiors. Product and specifications await confirmation.','category':'timber','sample':True},
            {'id':3,'name_zh':'复合百叶（示例）','name_en':'Composite Blinds (Sample)','material_zh':'复合材料','material_en':'Composite','description_zh':'简洁耐用的示例系列，实际选项待确认。','description_en':'A simple sample collection. Actual options await confirmation.','category':'composite','sample':True}
        ] if seed_catalog else []):
            c.execute('INSERT OR IGNORE INTO products VALUES(?,?)',(p['id'],dump(p)))

if BACKEND=='sqlite' or os.getenv('VERA_AUTO_INIT')=='1':init_db()


def auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Please sign in')
    key = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    with db() as c:
        row = c.execute('SELECT expires_at, username FROM sessions WHERE token_hash=?',(key,)).fetchone()
        user = c.execute('SELECT active FROM users WHERE username=?',(row['username'],)).fetchone() if row else None
        username = row['username'] if row else ''
        expires = row['expires_at'] if row else 0
        active = bool(user and user['active'])
    if not username or expires < time.time() or not active:
        raise HTTPException(401, 'Session expired')
    return username

class Login(BaseModel):
    username: str
    password: str

@app.get('/api/health')
def health():
    return {'ok':True,'status':'ok','demo':True,'database':BACKEND}

@app.post('/api/auth/login')
def login(body: Login):
    with db() as c:
        user = c.execute('SELECT * FROM users WHERE username=?',(body.username,)).fetchone()
        if not user or not user['active'] or not password_ok(body.password, user['password_hash']):
            raise HTTPException(401, 'Invalid credentials')
        profile = {'username': user['username'], 'name': user['name'], 'role': user['role']}
        token = secrets.token_urlsafe(32)
        c.execute('DELETE FROM sessions WHERE expires_at<?',(time.time(),))
        c.execute('INSERT INTO sessions(token_hash,expires_at,username) VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),time.time()+28800,profile['username']))
    return {'token':token, 'token_type':'bearer', 'expires_in':28800, 'user':profile}

@app.get('/api/auth/me')
def me(username: str = Depends(auth)):
    with db() as c:
        user = c.execute('SELECT username,name,role FROM users WHERE username=? AND active=1',(username,)).fetchone()
        profile = dict(user) if user else None
    if not profile:
        raise HTTPException(401, 'Session expired')
    return profile

class PasswordChange(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=80)

@app.post('/api/auth/password')
def change_password(body: PasswordChange, username: str = Depends(auth)):
    with db() as c:
        user = c.execute('SELECT password_hash FROM users WHERE username=? AND active=1',(username,)).fetchone()
        if not user or not password_ok(body.current, user['password_hash']):
            raise HTTPException(400, 'Current password is wrong')
        c.execute('UPDATE users SET password_hash=? WHERE username=?',(password_hash(body.new), username))
        c.execute('DELETE FROM sessions WHERE username=?',(username,))
    return {'ok': True}

def require_admin(username: str = Depends(auth)) -> str:
    with db() as c:
        user = c.execute('SELECT role FROM users WHERE username=? AND active=1',(username,)).fetchone()
        role = user['role'] if user else ''
    if role != 'admin':
        raise HTTPException(403, 'Admin only')
    return username

class NewUser(BaseModel):
    username: str = Field(min_length=2, max_length=40, pattern=r'^[a-z0-9._-]+$')
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=80)
    role: Literal['admin', 'staff']

    @model_validator(mode='after')
    def clean_name(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError('Name is required')
        return self

class RoleChange(BaseModel):
    role: Literal['admin', 'staff']

@app.get('/api/users')
def list_users(_admin: str = Depends(require_admin)):
    with db() as c:
        return [dict(r) for r in c.execute('SELECT username,name,role,active FROM users ORDER BY username')]

@app.post('/api/users')
def create_user(body: NewUser, _admin: str = Depends(require_admin)):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM users WHERE username=?',(body.username,)).fetchone():
            raise HTTPException(409, 'That username already exists')
        c.execute('INSERT INTO users(username,name,password_hash,role,active) VALUES(?,?,?,?,1)',(body.username, body.name.strip(), password_hash(body.password), body.role))
    return {'ok': True}

@app.post('/api/users/{username}/role')
def set_role(username: str, body: RoleChange, actor: str = Depends(require_admin)):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        target = c.execute('SELECT role FROM users WHERE username=? AND active=1',(username,)).fetchone()
        if not target:
            raise HTTPException(404, 'User not found')
        if target['role'] == 'admin' and body.role != 'admin':
            admins = c.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND active=1").fetchone()['n']
            if admins <= 1:
                raise HTTPException(409, 'Keep at least one administrator')
        c.execute('UPDATE users SET role=? WHERE username=?',(body.role, username))
    return {'ok': True, 'by': actor}

@app.post('/api/auth/logout')
def logout(credentials: HTTPAuthorizationCredentials = Depends(security), actor=Depends(auth)):
    with db() as c:
        c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(credentials.credentials.encode()).hexdigest(),))
    return {'ok':True}

def is_authenticated_user(credentials: HTTPAuthorizationCredentials | None) -> bool:
    """Check if user is authenticated (staff or portal customer)."""
    if not credentials or credentials.scheme.lower() != 'bearer':
        return False
    
    token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    
    # Try staff session
    with db() as c:
        row = c.execute('SELECT expires_at, username FROM sessions WHERE token_hash=?', (token_hash,)).fetchone()
        if row:
            user = c.execute('SELECT active FROM users WHERE username=?', (row['username'],)).fetchone()
            if user and user['active'] and row['expires_at'] >= time.time():
                return True
        
        # Try portal customer session
        row = c.execute('SELECT * FROM portal_sessions WHERE token_hash=?', (token_hash,)).fetchone()
        if row and row['expires_at'] >= time.time():
            return True
    
    return False


@app.get('/api/products')
def products(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    # Check if user is authenticated (staff or portal customer)
    is_authenticated = is_authenticated_user(credentials)
    
    with db() as c:
        result = []
        for r in c.execute('SELECT data FROM products ORDER BY id'):
            d = json.loads(r['data'])
            if not d.get('published', True) or d.get('portal_only', False):
                continue
            # Hide non-sample aluminium products for non-authenticated users
            # Sample products (demo/placeholder) remain visible
            if not is_authenticated and d.get('category') == 'aluminium' and not d.get('sample', False):
                continue
            result.append(catalog_product(d))
        return result

@app.get('/api/products/{pid}')
def product(pid:int, credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    # Check if user is authenticated (staff or portal customer)
    is_authenticated = is_authenticated_user(credentials)
    
    with db() as c:
        r=c.execute('SELECT data FROM products WHERE id=?',(pid,)).fetchone()
        if not r: raise HTTPException(404,'Product not found')
        d=json.loads(r['data'])
        if not d.get('published',True) or d.get('portal_only'): 
            raise HTTPException(404,'Product not found')
        # Block non-sample aluminium products for non-authenticated users
        if not is_authenticated and d.get('category') == 'aluminium' and not d.get('sample', False):
            raise HTTPException(403,'Authentication required to view aluminium products')
        return catalog_product(d)

@app.get('/api/admin/image-upload-config',dependencies=[Depends(auth)])
def image_upload_config():return {'max_bytes':MAX_BYTES,'max_images':12,'storage':STORAGE_MODE}

@app.get('/api/media/{filename}')
def product_image(filename:str,credentials=Depends(security)):
    if credentials:auth(credentials)
    else:
        url='/api/media/'+filename
        with db() as c:
            visible=any(d.get('published',True) and not d.get('portal_only') and url in (d.get('image_urls') or [d.get('image_url')]) for d in (json.loads(r['data']) for r in c.execute('SELECT data FROM products')))
        if not visible:raise HTTPException(404,'Image not found')
    try:raw=get_image(filename)
    except (FileNotFoundError,StorageError):raise HTTPException(404,'Image not found')
    mime='image/png' if filename.endswith('.png') else 'image/webp' if filename.endswith('.webp') else 'image/jpeg'
    return Response(raw,media_type=mime,headers={'Cache-Control':'private, max-age=3600' if credentials else 'public, max-age=86400','Vary':'Authorization'})

def catalog_product(d):
    defaults={1:['/images/vera-aluminium-room-v2.png','/images/vera-aluminium-detail-v2.png'],2:['/images/vera-timber-room-v2.png','/images/vera-timber-detail.png'],3:['/images/vera-composite-room-v2.png','/images/vera-composite-detail-v2.png']}.get(d['id'],[])
    images=d.get('image_urls') if 'image_urls' in d else ([d['image_url']] if d.get('image_url') else defaults)
    images=images or []
    result={'published':True,'unit':'mm','width_min':None,'width_max':None,'height_min':None,'height_max':None,'colors':[],'controls':[],**d}
    result.update(image_urls=images,image_url=images[0] if images else '')
    return result

class ProductEdit(BaseModel):
    name_zh:str=Field(min_length=1,max_length=160)
    name_en:str=Field(min_length=1,max_length=160)
    material_zh:str=Field(min_length=1,max_length=100)
    material_en:str=Field(min_length=1,max_length=100)
    description_zh:str=Field(default='',max_length=3000)
    description_en:str=Field(default='',max_length=3000)
    category:str=Field(min_length=1,max_length=80)
    sample:bool=True
    published:bool=False
    image_url:str=Field(default='',max_length=300)
    image_urls:list[str]=Field(default_factory=list,max_length=12)
    unit:Literal['mm','inch']='mm'
    width_min:float|None=Field(default=None,gt=0)
    width_max:float|None=Field(default=None,gt=0)
    height_min:float|None=Field(default=None,gt=0)
    height_max:float|None=Field(default=None,gt=0)
    colors:list[str]=Field(default_factory=list,max_length=50)
    controls:list[str]=Field(default_factory=list,max_length=30)
    @model_validator(mode='after')
    def clean_product(self):
        for key in ['name_zh','name_en','material_zh','material_en','category']:
            setattr(self,key,getattr(self,key).strip())
            if not getattr(self,key):raise ValueError('Product names, material and category are required')
        images=self.image_urls or ([self.image_url] if self.image_url else [])
        if any(not re.fullmatch(r'/(?:images|api/media)/[a-zA-Z0-9_.-]+\.(?:png|jpg|jpeg|webp)',x) for x in images+([self.image_url] if self.image_url else [])):raise ValueError('Choose local PNG, JPEG or WebP product images')
        self.image_urls=list(dict.fromkeys(images));self.image_url=self.image_urls[0] if self.image_urls else ''
        if self.published and not self.image_url:raise ValueError('Choose a cover image before showing the product on the website')
        for low,high in [(self.width_min,self.width_max),(self.height_min,self.height_max)]:
            if low is not None and high is not None and low>high:raise ValueError('Minimum dimensions cannot exceed maximum')
        self.colors=[x.strip() for x in self.colors if x.strip()]
        self.controls=[x.strip() for x in self.controls if x.strip()]
        if any(len(x)>100 for x in self.colors+self.controls):raise ValueError('Option text is too long')
        return self

@app.get('/api/admin/products',dependencies=[Depends(auth)])
def admin_products():
    with db() as c:return [catalog_product(json.loads(r['data'])) for r in c.execute('SELECT data FROM products ORDER BY id')]

@app.post('/api/admin/products',dependencies=[Depends(require_admin)])
def create_product(body:ProductEdit):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        pid=c.execute('SELECT COALESCE(MAX(id),0)+1 FROM products').fetchone()[0]
        d={'id':pid,**body.model_dump()};c.execute('INSERT INTO products VALUES(?,?)',(pid,dump(d)))
        return d

@app.post('/api/admin/products/{pid}',dependencies=[Depends(require_admin)])
def edit_product(pid:int,body:ProductEdit):
    with db() as c:
        existing=c.execute('SELECT data FROM products WHERE id=?',(pid,)).fetchone()
        if not existing:raise HTTPException(404,'Product not found')
        d={**json.loads(existing['data']),'id':pid,**body.model_dump()};c.execute('UPDATE products SET data=? WHERE id=?',(dump(d),pid));return d

class ImageUpload(BaseModel):
    data:str=Field(min_length=1,max_length=7_000_000)
    content_type:Literal['image/png','image/jpeg','image/webp']

@app.post('/api/admin/product-images',dependencies=[Depends(require_admin)])
def upload_product_image(body:ImageUpload):
    try:raw=base64.b64decode(body.data,validate=True)
    except (ValueError,binascii.Error):raise HTTPException(422,'Invalid image encoding')
    if len(raw)>MAX_BYTES:raise HTTPException(413,f'Image must be {MAX_BYTES//1024//1024} MB or smaller')
    mime=body.content_type
    valid=(mime=='image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n') and b'IEND' in raw[-16:]) or (mime=='image/jpeg' and raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9')) or (mime=='image/webp' and raw[:4]==b'RIFF' and raw[8:12]==b'WEBP')
    if not valid:raise HTTPException(422,'Image content does not match PNG, JPEG or WebP')
    ext={'image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[mime]
    name=secrets.token_hex(16)+'.'+ext
    try:put_image(name,raw,mime)
    except (StorageError,RuntimeError):raise HTTPException(503,'Product image storage is unavailable')
    return {'image_url':'/api/media/'+name}

from operations import register as register_operations
register_operations(app,sys.modules[__name__])
