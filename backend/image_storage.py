"""Local files, a private Cloudflare R2 bucket, or a private Supabase bucket."""
import hashlib,hmac,os,re,json
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from urllib.parse import quote,urlsplit
from database import BACKEND
BASE_URL=(os.getenv('SUPABASE_URL') or os.getenv('NEXT_PUBLIC_PGSUPABASE_URL') or '').rstrip('/')
SERVICE_KEY=os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_SECRET_KEY') or ''
BUCKET=os.getenv('VERA_STORAGE_BUCKET','vera-product-images')
R2_ENDPOINT=(os.getenv('R2_ENDPOINT') or '').strip()
R2_BUCKET=(os.getenv('R2_BUCKET') or 'vera-crm').strip()
R2_ACCESS=(os.getenv('R2_ACCESS_ID') or '').strip()
R2_SECRET=(os.getenv('R2_ACCESS_KEY') or '').strip()
if R2_ENDPOINT:
    parsed_r2=urlsplit(R2_ENDPOINT if '://' in R2_ENDPOINT else 'https://'+R2_ENDPOINT)
    if parsed_r2.path.strip('/'):
        R2_BUCKET=parsed_r2.path.strip('/').split('/')[0]
    R2_ENDPOINT=f'{parsed_r2.scheme}://{parsed_r2.netloc}'
R2_HOST=urlsplit(R2_ENDPOINT).hostname or ''
def cloud_mode():
    chosen=os.getenv('VERA_STORAGE_BACKEND')
    if chosen:return chosen
    if R2_ACCESS and R2_SECRET and R2_HOST:return 'r2'
    if BACKEND=='postgres' and BASE_URL and SERVICE_KEY:return 'supabase'
    return 'local'
MODE=cloud_mode()
MAX_BYTES=(3 if os.getenv('VERCEL') else 5)*1024*1024
MEDIA_DIR=Path(os.getenv('VERA_MEDIA_DIR','/tmp/vera-media' if os.getenv('VERCEL') else str(Path(__file__).with_name('media'))))
NAME=re.compile(r'[a-f0-9]{32}\.(?:png|jpg|jpeg|webp)')
if MODE not in ('local','supabase','r2'):raise RuntimeError('Invalid image storage backend')
if MODE=='supabase' and not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,62}',BUCKET):raise RuntimeError('Invalid image bucket name')
if MODE=='r2' and not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,62}',R2_BUCKET):raise RuntimeError('Invalid R2 bucket name')
if MODE=='supabase':
    parsed=urlsplit(BASE_URL)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or not SERVICE_KEY:raise RuntimeError('Configure server-side Supabase URL and service key')
elif MODE=='r2':
    parsed=urlsplit(R2_ENDPOINT)
    if parsed.scheme!='https' or not R2_HOST or parsed.username or parsed.password or not R2_ACCESS or not R2_SECRET:raise RuntimeError('Configure server-side R2 endpoint and access keys')
elif os.getenv('VERCEL'):raise RuntimeError('Vercel image uploads require persistent R2 storage configuration')
else:MEDIA_DIR.mkdir(parents=True,exist_ok=True)
_ready=False

class StorageError(RuntimeError):
    def __init__(self,status):self.status=status;super().__init__('Image storage request failed (HTTP '+str(status)+')')

def storage_request(method,path,data=None,mime=None):
    headers={'apikey':SERVICE_KEY}
    if SERVICE_KEY.startswith('eyJ'):headers['Authorization']='Bearer '+SERVICE_KEY
    if mime:headers['Content-Type']=mime
    request=Request(BASE_URL+'/storage/v1/'+path,data=data,headers=headers,method=method)
    try:
        with urlopen(request,timeout=30) as response:return response.read()
    except HTTPError as exc:
        try:payload=json.loads(exc.read());missing=str(payload.get('error','')).lower() in ('bucket not found','object not found') or str(payload.get('message','')).lower() in ('bucket not found','object not found')
        except (ValueError,TypeError):missing=False
        raise StorageError(404 if missing else exc.code) from None
    except URLError:raise StorageError(503) from None

def ensure_bucket():
    global _ready
    if MODE!='supabase' or _ready:return
    try:info=json.loads(storage_request('GET','bucket/'+BUCKET))
    except StorageError as exc:
        if exc.status!=404:raise
        payload=json.dumps({'id':BUCKET,'name':BUCKET,'public':False,'file_size_limit':5*1024*1024,'allowed_mime_types':['image/png','image/jpeg','image/webp']}).encode()
        try:storage_request('POST','bucket',payload,'application/json')
        except StorageError as create_error:
            if create_error.status not in (400,409):raise
        info=json.loads(storage_request('GET','bucket/'+BUCKET))
    if info.get('public'):raise RuntimeError('Use a dedicated private product-image bucket')
    _ready=True

def r2_object_request(method,name,data=None,mime=None,sign=True):
    if not NAME.fullmatch(name):raise ValueError('Invalid image filename')
    payload=data or b''
    payload_hash=hashlib.sha256(payload).hexdigest()
    now=datetime.now(timezone.utc)
    amzdate=now.strftime('%Y%m%dT%H%M%SZ');datestamp=now.strftime('%Y%m%d')
    canonical_uri='/'+quote(R2_BUCKET)+'/'+quote(name)
    headers={'host':R2_HOST,'x-amz-content-sha256':payload_hash,'x-amz-date':amzdate}
    if mime:headers['content-type']=mime
    signed=sorted(headers)
    canonical_headers=''.join(k+':'+headers[k]+'\n' for k in signed)
    signed_headers=';'.join(signed)
    canonical='\n'.join([method,canonical_uri,'',canonical_headers,signed_headers,payload_hash])
    scope=datestamp+'/auto/s3/aws4_request'
    to_sign='\n'.join(['AWS4-HMAC-SHA256',amzdate,scope,hashlib.sha256(canonical.encode()).hexdigest()])
    def mac(key,msg):return hmac.new(key,msg.encode(),hashlib.sha256).digest()
    signing=mac(mac(mac(mac(('AWS4'+R2_SECRET).encode(),datestamp),'auto'),'s3'),'aws4_request')
    signature=hmac.new(signing,to_sign.encode(),hashlib.sha256).hexdigest()
    request_headers={k:headers[k] for k in headers if k!='host'}
    if sign:request_headers['Authorization']=f'AWS4-HMAC-SHA256 Credential={R2_ACCESS}/{scope}, SignedHeaders={signed_headers}, Signature={signature}'
    request=Request(R2_ENDPOINT+canonical_uri,data=data if method=='PUT' else None,headers=request_headers,method=method)
    try:
        with urlopen(request,timeout=30) as response:return response.status,response.read()
    except HTTPError as exc:
        exc.read()
        raise StorageError(exc.code) from None
    except URLError:raise StorageError(503) from None

def unsigned_read_denied(name):
    if not NAME.fullmatch(name):raise ValueError('Invalid image filename')
    request=Request(R2_ENDPOINT+'/'+quote(R2_BUCKET)+'/'+quote(name),method='GET')
    try:
        with urlopen(request,timeout=30) as response:response.read();return False
    except HTTPError as exc:
        body=exc.read().decode('utf-8','replace')
        if exc.code in (401,403):return True
        return exc.code==400 and '<Code>InvalidArgument</Code>' in body and '<Message>Authorization</Message>' in body
    except URLError:return False

def put_image(name,data,mime):
    if not NAME.fullmatch(name):raise ValueError('Invalid image filename')
    if MODE=='local':(MEDIA_DIR/name).write_bytes(data)
    elif MODE=='r2':r2_object_request('PUT',name,data,mime)
    else:
        ensure_bucket();storage_request('POST','object/'+BUCKET+'/'+name,data,mime)

def get_image(name):
    if not NAME.fullmatch(name):raise FileNotFoundError()
    if MODE=='local':return (MEDIA_DIR/name).read_bytes()
    if MODE=='r2':
        try:_,body=r2_object_request('GET',name);return body
        except StorageError as exc:
            if exc.status==404:raise FileNotFoundError() from None
            raise
    return storage_request('GET','object/authenticated/'+BUCKET+'/'+name)

def delete_image(name):
    if not NAME.fullmatch(name):raise ValueError('Invalid image filename')
    if MODE=='local':
        path=MEDIA_DIR/name
        if path.exists():path.unlink()
        return
    if MODE=='r2':
        r2_object_request('DELETE',name);return
    storage_request('DELETE','object/'+BUCKET,json.dumps({'prefixes':[name]}).encode(),'application/json')
