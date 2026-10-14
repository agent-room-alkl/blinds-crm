"""VERA local demonstration API. SQLite writes are transactional."""
import os
import json
import sqlite3
import secrets
import hashlib
import hmac
import time
from pathlib import Path
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from typing import Literal
from contextlib import contextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

DB_PATH = os.environ.get('VERA_DB', str(Path(__file__).with_name('vera.db')))
app = FastAPI(title='VERA Demo API')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['*'], allow_headers=['*'])
security = HTTPBearer(auto_error=False)

def now():
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        with con:
            yield con
    finally:
        con.close()

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

def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, company TEXT NOT NULL, locale TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), name TEXT, channel TEXT);
        CREATE TABLE IF NOT EXISTS inquiries(id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), data TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT, submission_key TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS followups(id INTEGER PRIMARY KEY, inquiry_id INTEGER REFERENCES inquiries(id), note TEXT NOT NULL, next_at TEXT, created_at TEXT, actor TEXT);
        CREATE TABLE IF NOT EXISTS quotes(id INTEGER PRIMARY KEY, inquiry_id INTEGER REFERENCES inquiries(id), created_at TEXT);
        CREATE TABLE IF NOT EXISTS quote_versions(id INTEGER PRIMARY KEY, quote_id INTEGER REFERENCES quotes(id), version INTEGER NOT NULL, data TEXT NOT NULL, created_at TEXT, UNIQUE(quote_id,version));
        CREATE TABLE IF NOT EXISTS quote_lines(id INTEGER PRIMARY KEY, version_id INTEGER REFERENCES quote_versions(id), data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, version_id INTEGER UNIQUE REFERENCES quote_versions(id), snapshot TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT);
        CREATE TABLE IF NOT EXISTS status_history(id INTEGER PRIMARY KEY, entity TEXT, entity_id INTEGER, old_status TEXT, new_status TEXT, note TEXT, actor TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        ''')
        if 'notes' not in {row['name'] for row in c.execute('PRAGMA table_info(customers)')}:
            c.execute("ALTER TABLE customers ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
        if 'username' not in {row['name'] for row in c.execute('PRAGMA table_info(sessions)')}:
            c.execute("ALTER TABLE sessions ADD COLUMN username TEXT NOT NULL DEFAULT 'dylan'")
        if not c.execute('SELECT 1 FROM users WHERE username=?',('dylan',)).fetchone():
            c.execute('INSERT INTO users(username,name,password_hash,role,active) VALUES(?,?,?,?,1)',('dylan','Dylan',password_hash(os.environ.get('VERA_DEMO_PASSWORD','vera-demo')),'admin'))
        for p in [
            {'id':1,'name_zh':'铝百叶（示例）','name_en':'Aluminium Blinds (Sample)','material_zh':'铝合金','material_en':'Aluminium','description_zh':'轻盈的叶片与灵活的光线控制。产品及规格待客户确认。','description_en':'Lightweight slats and versatile light control. Product and specifications await confirmation.','category':'aluminium','sample':True},
            {'id':2,'name_zh':'木百叶（示例）','name_en':'Timber Blinds (Sample)','material_zh':'木材','material_en':'Timber','description_zh':'温暖质感，适合自然风格空间。产品及规格待客户确认。','description_en':'Warm texture for natural interiors. Product and specifications await confirmation.','category':'timber','sample':True},
            {'id':3,'name_zh':'复合百叶（示例）','name_en':'Composite Blinds (Sample)','material_zh':'复合材料','material_en':'Composite','description_zh':'简洁耐用的示例系列，实际选项待确认。','description_en':'A simple sample collection. Actual options await confirmation.','category':'composite','sample':True}
        ]:
            c.execute('INSERT OR IGNORE INTO products VALUES(?,?)',(p['id'],dump(p)))

init_db()

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
    return {'ok':True, 'status':'ok', 'demo':True}

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
        if c.execute('SELECT 1 FROM users WHERE username=?',(body.username,)).fetchone():
            raise HTTPException(409, 'That username already exists')
        c.execute('INSERT INTO users(username,name,password_hash,role,active) VALUES(?,?,?,?,1)',(body.username, body.name.strip(), password_hash(body.password), body.role))
    return {'ok': True}

@app.post('/api/users/{username}/role')
def set_role(username: str, body: RoleChange, actor: str = Depends(require_admin)):
    with db() as c:
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

@app.get('/api/products')
def products():
    with db() as c:
        return [catalog_product(json.loads(r['data'])) for r in c.execute('SELECT data FROM products ORDER BY id') if json.loads(r['data']).get('published',True)]

@app.get('/api/products/{pid}')
def product(pid:int):
    with db() as c:
        r=c.execute('SELECT data FROM products WHERE id=?',(pid,)).fetchone()
        if not r: raise HTTPException(404,'Product not found')
        d=json.loads(r['data'])
        if not d.get('published',True): raise HTTPException(404,'Product not found')
        return catalog_product(d)

class Inquiry(BaseModel):
    company: str = Field(min_length=1,max_length=150)
    contact_name: str = Field(min_length=1,max_length=100)
    channel: str = Field(min_length=3,max_length=200)
    locale: Literal['zh','en'] = 'en'
    product_id: int | None = None
    quantity: int | None = Field(default=None,gt=0)
    width: float | None = Field(default=None,gt=0)
    height: float | None = Field(default=None,gt=0)
    unit: Literal['mm','inch'] | None = None
    expected_date: str = ''
    notes: str = Field(default='',max_length=4000)
    submission_key: str | None = Field(default=None,max_length=100)
    source: str = 'website'
    @model_validator(mode='after')
    def validate_spec(self):
        if (self.width or self.height) and not self.unit: raise ValueError('Dimensions require a unit')
        if not self.company.strip() or not self.contact_name.strip() or not self.channel.strip(): raise ValueError('Contact fields cannot be blank')
        return self

def insert_inquiry(body:Inquiry):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if body.submission_key:
            prior=c.execute('SELECT * FROM inquiries WHERE submission_key=?',(body.submission_key,)).fetchone()
            if prior: return inquiry_dict(c,prior)
        if body.product_id and not c.execute('SELECT id FROM products WHERE id=?',(body.product_id,)).fetchone(): raise HTTPException(422,'Unknown product')
        cid=c.execute('INSERT INTO customers(company,locale) VALUES(?,?)',(body.company.strip(),body.locale)).lastrowid
        c.execute('INSERT INTO contacts(customer_id,name,channel) VALUES(?,?,?)',(cid,body.contact_name.strip(),body.channel.strip()))
        iid=c.execute('INSERT INTO inquiries(customer_id,data,status,created_at,submission_key) VALUES(?,?,?,?,?)',(cid,dump(body.model_dump()),'new',now(),body.submission_key)).lastrowid
        return inquiry_dict(c,c.execute('SELECT * FROM inquiries WHERE id=?',(iid,)).fetchone())

def inquiry_dict(c,r):
    d=json.loads(r['data']); d.update(id=r['id'],customer_id=r['customer_id'],status=r['status'],created_at=r['created_at'])
    d['followups']=[dict(x) for x in c.execute('SELECT * FROM followups WHERE inquiry_id=? ORDER BY id DESC',(r['id'],))]
    return d

@app.post('/api/inquiries')
def new_inquiry(body:Inquiry):
    d=insert_inquiry(body)
    return {'id':d['id'],'reference':f"INQ-{d['id']:05d}",'status':d['status']}

class Conversation(BaseModel):
    company: str = Field(default='Other',min_length=1,max_length=150)
    contact_name: str = Field(min_length=1,max_length=100)
    channel: str = Field(min_length=3,max_length=200)
    locale: Literal['zh','en'] = 'en'
    weekday_slot: str = Field(min_length=1,max_length=200)
    notes: str = Field(default='',max_length=3000)
    submission_key: str | None = None

@app.post('/api/conversations')
def conversation(body:Conversation):
    return new_inquiry(Inquiry(company=body.company,contact_name=body.contact_name,channel=body.channel,locale=body.locale,notes=f'Conversation preference: {body.weekday_slot}\n{body.notes}',source='conversation',submission_key=body.submission_key))

@app.get('/api/inquiries',dependencies=[Depends(auth)])
def inquiries():
    with db() as c: return [inquiry_dict(c,r) for r in c.execute('SELECT * FROM inquiries ORDER BY id DESC')]

@app.get('/api/inquiries/{iid}',dependencies=[Depends(auth)])
def inquiry(iid:int):
    with db() as c:
        r=c.execute('SELECT * FROM inquiries WHERE id=?',(iid,)).fetchone()
        if not r: raise HTTPException(404,'Inquiry not found')
        return inquiry_dict(c,r)

def _suggest_at(agreed):
    for extra in range(2,9):
        stamp=(datetime.now()+timedelta(days=extra)).replace(hour=10,minute=0,second=0,microsecond=0).strftime('%Y-%m-%dT%H:%M')
        if not any(str(a).startswith(stamp) for a in agreed): return stamp
    return (datetime.now()+timedelta(days=9)).strftime('%Y-%m-%dT%H:%M')

@app.post('/api/inquiries/{iid}/assistant')
def inquiry_assistant(iid:int,_actor=Depends(auth)):
    with db() as c:
        r=c.execute('SELECT * FROM inquiries WHERE id=?',(iid,)).fetchone()
        if not r: raise HTTPException(404,'Inquiry not found')
        def marks():
            return (c.execute('SELECT COUNT(*) n FROM inquiries').fetchone()['n'],c.execute('SELECT COUNT(*) n FROM followups').fetchone()['n'],c.execute('SELECT COUNT(*) n FROM quotes').fetchone()['n'],c.execute('SELECT COUNT(*) n FROM orders').fetchone()['n'],[x['snapshot'] for x in c.execute('SELECT snapshot FROM orders ORDER BY id')],c.execute('SELECT status FROM inquiries WHERE id=?',(iid,)).fetchone()['status'])
        before=marks()
        item=inquiry_dict(c,r)
        cust=c.execute('SELECT * FROM customers WHERE id=?',(r['customer_id'],)).fetchone()
        locale=(cust['locale'] if cust and cust['locale'] in ('zh','en') else item.get('locale')) or 'en'
        zh=locale=='zh'
        facts=[]
        if cust and (cust['notes'] or '').strip(): facts.append({'source':'customer.notes','text':cust['notes'].strip()})
        if (item.get('notes') or '').strip(): facts.append({'source':'inquiry.notes','text':item['notes'].strip()})
        agreed=[]
        for fup in item['followups']:
            facts.append({'source':f"followup:{fup['id']}",'text':fup['note']})
            if fup.get('next_at'): agreed.append(fup['next_at'])
        quote=c.execute('SELECT q.id quote_id,v.version,v.data,v.id version_id FROM quotes q JOIN quote_versions v ON v.quote_id=q.id WHERE q.inquiry_id=? ORDER BY q.id DESC,v.version DESC LIMIT 1',(iid,)).fetchone()
        if quote:
            data=json.loads(quote['data'])
            facts.append({'source':f"quote:{quote['quote_id']}/v{quote['version']}",'text':f"{data.get('currency')} {data.get('total')}"})
        order=c.execute('SELECT o.id,o.status FROM orders o JOIN quote_versions v ON v.id=o.version_id JOIN quotes q ON q.id=v.quote_id WHERE q.inquiry_id=? ORDER BY o.id DESC LIMIT 1',(iid,)).fetchone()
        if order: facts.append({'source':f"order:{order['id']}",'text':order['status']})
        gaps=[]
        if not item.get('width') or not item.get('height'): gaps.append('尺寸' if zh else 'size')
        if not item.get('expected_date'): gaps.append('交期' if zh else 'timing')
        if not item.get('product_id'): gaps.append('产品' if zh else 'product')
        suggested=_suggest_at(agreed)
        recorded='\n'.join(f"{n}. {fact['text']} [{fact['source']}]" for n,fact in enumerate(facts,1)) or ('无' if zh else 'None')
        missing='、'.join(gaps) if zh else ', '.join(gaps)
        nxt=(f'先补齐：{missing}。补齐前不写价格。' if gaps else '规格已齐，可以整理报价草稿。单价仍由人工填写。') if zh else (f'First confirm: {missing}. Do not write a price before that.' if gaps else 'The specification is complete enough to draft a quote. A person still enters the unit price.')
        name=item.get('contact_name') or ''
        if zh:
            summary=f"沟通摘要（尚未保存）\n询价 #{iid}\n已记录：\n{recorded}\n建议下一步：{nxt}\n建议跟进时间：{suggested}（建议，不是已约定时间）"
            ask=f"为准备报价，还请补充：{missing}。" if gaps else '目前记下的规格已经够我们开始整理报价。'
            reply=f"{name}，您好。\n\n我们已收到您的询价 #{iid}。{ask}\n价格会在规格确认后单独说明，这封回复不含报价。"
        else:
            summary=f"Conversation summary (not saved)\nInquiry #{iid}\nRecorded:\n{recorded}\nSuggested next step: {nxt}\nSuggested follow-up: {suggested} (a suggestion, not an agreed time)"
            ask=f"To prepare a quote, please confirm: {missing}." if gaps else 'The specifications we have are enough to start preparing a quote.'
            reply=f"Hello {name},\n\nWe have received inquiry #{iid}. {ask}\nPricing will be set out separately once the specification is confirmed. This reply does not include a price."
        if marks()!=before: raise HTTPException(500,'Assistant changed stored records')
        return {'mode':'rules','connected':False,'locale':'zh' if zh else 'en','summary':summary,'reply':reply,'facts':facts,'gaps':gaps,'suggested_next_at':suggested,'agreed':False}

def customer_dict(c,r):
    d=dict(r)
    d['notes']=d.get('notes') or ''
    d['contacts']=[dict(x) for x in c.execute('SELECT * FROM contacts WHERE customer_id=?',(r['id'],))]
    d['inquiries']=[{'id':x['id'],'status':x['status'],'created_at':x['created_at'],'contact_name':json.loads(x['data']).get('contact_name','')} for x in c.execute('SELECT * FROM inquiries WHERE customer_id=? ORDER BY id DESC',(r['id'],))]
    d['orders']=[{'id':o['id'],'status':o['status'],'created_at':o['created_at']} for o in c.execute('SELECT o.id,o.status,o.created_at FROM orders o JOIN quote_versions v ON v.id=o.version_id JOIN quotes q ON q.id=v.quote_id JOIN inquiries i ON i.id=q.inquiry_id WHERE i.customer_id=? ORDER BY o.id DESC',(r['id'],))]
    return d

@app.get('/api/customers',dependencies=[Depends(auth)])
def customers():
    with db() as c:
        return [customer_dict(c,r) for r in c.execute('SELECT * FROM customers ORDER BY id DESC')]

class CustomerEdit(BaseModel):
    company:str=Field(min_length=1,max_length=200)
    contact_name:str=Field(min_length=1,max_length=200)
    channel:str=Field(min_length=1,max_length=200)
    locale:Literal['zh','en']
    notes:str=Field(default='',max_length=4000)
    contact_id:int|None=None
    @model_validator(mode='after')
    def reject_blank(self):
        self.company=self.company.strip(); self.contact_name=self.contact_name.strip(); self.channel=self.channel.strip(); self.notes=self.notes.strip()
        if not self.company or not self.contact_name or not self.channel: raise ValueError('Company, contact and channel cannot be blank')
        return self

@app.post('/api/customers/{cid}')
def update_customer(cid:int,body:CustomerEdit,_actor=Depends(auth)):
    with db() as c:
        row=c.execute('SELECT * FROM customers WHERE id=?',(cid,)).fetchone()
        if not row: raise HTTPException(404,'Customer not found')
        before=[x['snapshot'] for x in c.execute('SELECT snapshot FROM orders ORDER BY id')]
        c.execute('UPDATE customers SET company=?,locale=?,notes=? WHERE id=?',(body.company.strip(),body.locale,body.notes.strip(),cid))
        contact=c.execute('SELECT * FROM contacts WHERE id=? AND customer_id=?',(body.contact_id,cid)).fetchone() if body.contact_id else c.execute('SELECT * FROM contacts WHERE customer_id=? ORDER BY id LIMIT 1',(cid,)).fetchone()
        if contact: c.execute('UPDATE contacts SET name=?,channel=? WHERE id=?',(body.contact_name.strip(),body.channel.strip(),contact['id']))
        else: c.execute('INSERT INTO contacts(customer_id,name,channel) VALUES(?,?,?)',(cid,body.contact_name.strip(),body.channel.strip()))
        after=[x['snapshot'] for x in c.execute('SELECT snapshot FROM orders ORDER BY id')]
        if before!=after: raise HTTPException(500,'Customer edit changed an order snapshot')
        return customer_dict(c,c.execute('SELECT * FROM customers WHERE id=?',(cid,)).fetchone())

class FollowUp(BaseModel):
    inquiry_id:int
    note:str=Field(min_length=1,max_length=4000)
    next_at:str=''

@app.post('/api/followups')
def followup(body:FollowUp,actor=Depends(auth)):
    if body.next_at:
        try: datetime.fromisoformat(body.next_at)
        except ValueError: raise HTTPException(422,'Invalid follow-up date')
    with db() as c:
        r=c.execute('SELECT * FROM inquiries WHERE id=?',(body.inquiry_id,)).fetchone()
        if not r: raise HTTPException(404,'Inquiry not found')
        fid=c.execute('INSERT INTO followups(inquiry_id,note,next_at,created_at,actor) VALUES(?,?,?,?,?)',(body.inquiry_id,body.note,body.next_at,now(),actor)).lastrowid
        if r['status']=='new': c.execute("UPDATE inquiries SET status='contacted' WHERE id=?",(body.inquiry_id,))
        return dict(c.execute('SELECT * FROM followups WHERE id=?',(fid,)).fetchone())

class Line(BaseModel):
    product_id:int
    width:Decimal=Field(gt=0)
    height:Decimal=Field(gt=0)
    unit:Literal['mm','inch']
    material:str=Field(min_length=1,max_length=100)
    color:str=Field(min_length=1,max_length=100)
    control:str=Field(default='manual',max_length=100)
    quantity:int=Field(gt=0,le=100000)
    unit_price:Decimal=Field(ge=0,le=10000000)

class QuoteBody(BaseModel):
    inquiry_id:int
    locale:Literal['zh','en']='en'
    currency:str=Field(default='NZD',pattern='^[A-Z]{3}$')
    valid_until:date
    discount:Decimal=Field(default=Decimal('0'),ge=0)
    shipping:Decimal=Field(default=Decimal('0'),ge=0)
    tax:Decimal=Field(default=Decimal('0'),ge=0)
    terms:str=Field(default='Demonstration prices. Confirm terms before ordering.',max_length=4000)
    lines:list[Line]=Field(min_length=1,max_length=100)

def money(v): return str(Decimal(v).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))

def quote_data(c,b:QuoteBody):
    if b.valid_until < date.today(): raise HTTPException(422,'Quote expiry must not be in the past')
    lines=[]
    for line in b.lines:
        p=c.execute('SELECT data FROM products WHERE id=?',(line.product_id,)).fetchone()
        if not p: raise HTTPException(422,'Unknown product')
        d=line.model_dump(mode='json'); d['product']=json.loads(p['data']); d['unit_price']=money(line.unit_price); d['amount']=money(Decimal(d['unit_price'])*line.quantity); lines.append(d)
    subtotal=sum((Decimal(l['amount']) for l in lines),Decimal(0))
    if b.discount>subtotal: raise HTTPException(422,'Discount exceeds subtotal')
    d=b.model_dump(mode='json'); d.update(lines=lines,subtotal=money(subtotal),discount=money(b.discount),shipping=money(b.shipping),tax=money(b.tax),total=money(subtotal-b.discount+b.shipping+b.tax),demo=True)
    return d

def store_version(c,qid,n,d):
    vid=c.execute('INSERT INTO quote_versions(quote_id,version,data,created_at) VALUES(?,?,?,?)',(qid,n,dump(d),now())).lastrowid
    for line in d['lines']: c.execute('INSERT INTO quote_lines(version_id,data) VALUES(?,?)',(vid,dump(line)))
    return version_dict(c,c.execute('SELECT * FROM quote_versions WHERE id=?',(vid,)).fetchone())

def version_dict(c,r):
    d=json.loads(r['data']); d.update(id=r['id'],quote_id=r['quote_id'],version=r['version'],created_at=r['created_at'])
    d['accepted_order_id']=next((x['id'] for x in c.execute('SELECT id FROM orders WHERE version_id=?',(r['id'],))),None)
    return d

def quote_dict(c,r):
    d=dict(r); d['versions']=[version_dict(c,v) for v in c.execute('SELECT * FROM quote_versions WHERE quote_id=? ORDER BY version',(r['id'],))]; return d

@app.post('/api/quotes',dependencies=[Depends(auth)])
def create_quote(body:QuoteBody):
    with db() as c:
        if not c.execute('SELECT id FROM inquiries WHERE id=?',(body.inquiry_id,)).fetchone(): raise HTTPException(404,'Inquiry not found')
        d=quote_data(c,body)
        qid=c.execute('INSERT INTO quotes(inquiry_id,created_at) VALUES(?,?)',(body.inquiry_id,now())).lastrowid
        store_version(c,qid,1,d)
        c.execute("UPDATE inquiries SET status='quoted' WHERE id=? AND status!='won'",(body.inquiry_id,))
        return quote_dict(c,c.execute('SELECT * FROM quotes WHERE id=?',(qid,)).fetchone())

@app.get('/api/quotes',dependencies=[Depends(auth)])
def quotes():
    with db() as c: return [quote_dict(c,r) for r in c.execute('SELECT * FROM quotes ORDER BY id DESC')]

@app.get('/api/quotes/{qid}',dependencies=[Depends(auth)])
def quote(qid:int):
    with db() as c:
        r=c.execute('SELECT * FROM quotes WHERE id=?',(qid,)).fetchone()
        if not r: raise HTTPException(404,'Quote not found')
        return quote_dict(c,r)

@app.post('/api/quotes/{qid}/versions',dependencies=[Depends(auth)])
def revise(qid:int,body:QuoteBody):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        q=c.execute('SELECT * FROM quotes WHERE id=?',(qid,)).fetchone()
        if not q: raise HTTPException(404,'Quote not found')
        if q['inquiry_id']!=body.inquiry_id: raise HTTPException(422,'Cannot change quote customer')
        n=c.execute('SELECT MAX(version) FROM quote_versions WHERE quote_id=?',(qid,)).fetchone()[0]+1
        return store_version(c,qid,n,quote_data(c,body))

def get_version(c,qid,n):
    r=c.execute('SELECT * FROM quote_versions WHERE quote_id=? AND version=?',(qid,n)).fetchone()
    if not r: raise HTTPException(404,'Version not found')
    return r

class Accept(BaseModel):
    note:str=Field(min_length=1,max_length=2000)

@app.post('/api/quotes/{qid}/versions/{n}/accept')
def accept(qid:int,n:int,body:Accept,actor=Depends(auth)):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        r=get_version(c,qid,n)
        existing=c.execute('SELECT * FROM orders WHERE version_id=?',(r['id'],)).fetchone()
        if existing: return order_dict(c,existing)
        latest=c.execute('SELECT MAX(version) FROM quote_versions WHERE quote_id=?',(qid,)).fetchone()[0]
        if n!=latest: raise HTTPException(409,'Superseded quote cannot be accepted')
        if c.execute('SELECT id FROM orders WHERE version_id IN (SELECT id FROM quote_versions WHERE quote_id=?)',(qid,)).fetchone(): raise HTTPException(409,'Quote already has an order')
        d=version_dict(c,r)
        if date.fromisoformat(d['valid_until'])<date.today(): raise HTTPException(409,'Quote expired')
        iq=c.execute('SELECT * FROM inquiries WHERE id=?',(d['inquiry_id'],)).fetchone()
        d['customer']=json.loads(iq['data']);d['confirmation_note']=body.note;d['confirmed_by']=actor
        oid=c.execute('INSERT INTO orders(version_id,snapshot,status,created_at) VALUES(?,?,?,?)',(r['id'],dump(d),'confirmed',now())).lastrowid
        c.execute("UPDATE inquiries SET status='won' WHERE id=?",(d['inquiry_id'],))
        history(c,oid,'','confirmed',body.note,actor)
        return order_dict(c,c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone())

def history(c,oid,old,new,note,actor):
    c.execute('INSERT INTO status_history(entity,entity_id,old_status,new_status,note,actor,created_at) VALUES(?,?,?,?,?,?,?)',('order',oid,old,new,note,actor,now()))

def order_dict(c,r):
    d=dict(r);d['snapshot']=json.loads(d['snapshot']);d['history']=[dict(x) for x in c.execute("SELECT * FROM status_history WHERE entity='order' AND entity_id=? ORDER BY id",(r['id'],))];return d

@app.get('/api/orders',dependencies=[Depends(auth)])
def orders():
    with db() as c: return [order_dict(c,r) for r in c.execute('SELECT * FROM orders ORDER BY id DESC')]

@app.get('/api/orders/{oid}',dependencies=[Depends(auth)])
def order(oid:int):
    with db() as c:
        r=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
        if not r: raise HTTPException(404,'Order not found')
        return order_dict(c,r)

class Status(BaseModel):
    status:Literal['confirmed','production','ready','delivered']
    note:str=Field(default='',max_length=2000)

@app.post('/api/orders/{oid}/status')
def status(oid:int,body:Status,actor=Depends(auth)):
    sequence=['confirmed','production','ready','delivered']
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        r=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
        if not r: raise HTTPException(404,'Order not found')
        if body.status==r['status']: return order_dict(c,r)
        if sequence.index(body.status)!=sequence.index(r['status'])+1: raise HTTPException(409,'Advance one stage at a time')
        c.execute('UPDATE orders SET status=? WHERE id=?',(body.status,oid));history(c,oid,r['status'],body.status,body.note,actor)
        return order_dict(c,c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone())

@app.get('/api/dashboard',dependencies=[Depends(auth)])
def dashboard():
    with db() as c:
        return {'new_inquiries':c.execute("SELECT COUNT(*) FROM inquiries WHERE status='new'").fetchone()[0], 'customers':c.execute('SELECT COUNT(*) FROM customers').fetchone()[0], 'quotes':c.execute('SELECT COUNT(*) FROM quotes').fetchone()[0], 'active_orders':c.execute("SELECT COUNT(*) FROM orders WHERE status!='delivered'").fetchone()[0], 'followups':[dict(r) for r in c.execute("SELECT * FROM followups WHERE next_at!='' AND id IN (SELECT MAX(id) FROM followups GROUP BY inquiry_id) ORDER BY next_at")]}

@app.get('/api/quotes/{qid}/versions/{n}/export',response_class=HTMLResponse,dependencies=[Depends(auth)])
def export(qid:int,n:int,lang:Literal['zh','en']='en'):
    with db() as c:
        d=version_dict(c,get_version(c,qid,n)); iq=c.execute('SELECT data FROM inquiries WHERE id=?',(d['inquiry_id'],)).fetchone();customer=json.loads(iq['data'])
    zh=lang=='zh'; title='报价单' if zh else 'Quotation'
    labels=['产品','规格','材质 / 颜色 / 控制','数量','单价','金额'] if zh else ['Product','Dimensions','Material / Colour / Control','Qty','Unit price','Amount']
    rows=''
    for l in d['lines']:
        values=[l['product']['name_zh' if zh else 'name_en'],f"{l['width']} × {l['height']} {l['unit']}",f"{l['material']} / {l['color']} / {l['control']}",l['quantity'],l['unit_price'],l['amount']]
        rows+='<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in values)+'</tr>'
    pairs=[('小计' if zh else 'Subtotal',d['subtotal']),('折扣' if zh else 'Discount',d['discount']),('运费' if zh else 'Shipping',d['shipping']),('税额' if zh else 'Tax',d['tax']),('总额' if zh else 'Total',d['total'])]
    return f'''<!doctype html><html lang="{lang}"><meta charset="utf-8"><title>VERA {title}</title><style>body{{font:16px Arial,sans-serif;max-width:1000px;margin:40px auto;padding:24px;color:#222}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ddd}}tr{{break-inside:avoid}}h1{{font-family:Georgia,serif}}.totals{{text-align:right}}@media print{{button{{display:none}}body{{margin:0}}}}</style><h1>VERA · {title}</h1><p>{'演示报价，非实际承诺' if zh else 'Demonstration quote — not an actual commercial offer'}</p><p>Q-{qid:05d} / v{n} · {escape(customer['company'])} · {escape(customer['contact_name'])}</p><p>{'有效期' if zh else 'Valid until'}: {d['valid_until']} · {d['currency']}</p><table><thead><tr>{''.join('<th>'+v+'</th>' for v in labels)}</tr></thead><tbody>{rows}</tbody></table><div class="totals">{''.join('<p>'+k+': '+d['currency']+' '+v+'</p>' for k,v in pairs)}</div><p>{escape(d['terms'])}</p><button onclick="window.print()">{'打印 / 保存 PDF' if zh else 'Print / Save PDF'}</button></html>'''


class AssistRequest(BaseModel):
    tone: Literal['brief','formal'] = 'brief'

@app.post('/api/inquiries/{iid}/assistant', dependencies=[Depends(auth)])
def assist_inquiry(iid:int, body:AssistRequest):
    from assistant import build_assistance
    with db() as c:
        row=c.execute('SELECT * FROM inquiries WHERE id=?',(iid,)).fetchone()
        if not row: raise HTTPException(404,'Inquiry not found')
        i=inquiry_dict(c,row)
        cu=customer_dict(c,c.execute('SELECT * FROM customers WHERE id=?',(row['customer_id'],)).fetchone())
        qs=[quote_dict(c,q) for q in c.execute('SELECT * FROM quotes WHERE inquiry_id=? ORDER BY id',(iid,))]
        os_=[order_dict(c,o) for o in c.execute('SELECT o.* FROM orders o JOIN quote_versions v ON v.id=o.version_id JOIN quotes q ON q.id=v.quote_id WHERE q.inquiry_id=? ORDER BY o.id',(iid,))]
        return build_assistance(i,cu,qs,os_,body.tone)


# Product maintenance shares the public catalogue. Historical quotes contain their own snapshots.
import base64
import binascii
import re
from fastapi.staticfiles import StaticFiles
MEDIA_DIR=Path(os.environ.get('VERA_MEDIA_DIR',str(Path(__file__).with_name('media'))))
MEDIA_DIR.mkdir(parents=True,exist_ok=True)
app.mount('/api/media',StaticFiles(directory=str(MEDIA_DIR)),name='product-media')

def catalog_product(d):
    image={1:'/images/aluminium.jpg',2:'/images/vera-timber-detail.png',3:'/images/composite.jpg'}.get(d['id'],'')
    return {'image_url':image,'published':True,'unit':'mm','width_min':None,'width_max':None,'height_min':None,'height_max':None,'colors':[],'controls':[],**d}

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
        if self.image_url and not re.fullmatch(r'/(?:images|api/media)/[a-zA-Z0-9_.-]+\.(?:png|jpg|jpeg|webp)',self.image_url):raise ValueError('Choose a local PNG, JPEG or WebP product image')
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
        if not c.execute('SELECT 1 FROM products WHERE id=?',(pid,)).fetchone():raise HTTPException(404,'Product not found')
        d={'id':pid,**body.model_dump()};c.execute('UPDATE products SET data=? WHERE id=?',(dump(d),pid));return d

class ImageUpload(BaseModel):
    data:str=Field(min_length=1,max_length=7_000_000)
    content_type:Literal['image/png','image/jpeg','image/webp']

@app.post('/api/admin/product-images',dependencies=[Depends(require_admin)])
def upload_product_image(body:ImageUpload):
    try:raw=base64.b64decode(body.data,validate=True)
    except (ValueError,binascii.Error):raise HTTPException(422,'Invalid image encoding')
    if len(raw)>5*1024*1024:raise HTTPException(413,'Image must be 5 MB or smaller')
    mime=body.content_type
    valid=(mime=='image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n') and b'IEND' in raw[-16:]) or (mime=='image/jpeg' and raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9')) or (mime=='image/webp' and raw[:4]==b'RIFF' and raw[8:12]==b'WEBP')
    if not valid:raise HTTPException(422,'Image content does not match PNG, JPEG or WebP')
    ext={'image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[mime]
    name=secrets.token_hex(16)+'.'+ext
    (MEDIA_DIR/name).write_bytes(raw)
    return {'image_url':'/api/media/'+name}
