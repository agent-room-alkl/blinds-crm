import os,re,base64,json
assert re.fullmatch(r'vera_test_[a-f0-9]{12}',os.getenv('VERA_TEST_SCHEMA',''))
assert os.getenv('VERA_DB_SCHEMA')==os.environ['VERA_TEST_SCHEMA']
os.environ['VERA_STORAGE_BACKEND']='r2'
from service import app,init_db
from image_storage import delete_image,MODE
from fastapi.testclient import TestClient
assert MODE=='r2';init_db();c=TestClient(app)
token=c.post('/api/auth/login',json={'username':'dylan','password':os.environ['VERA_DEMO_PASSWORD']}).json()['token'];c.headers['Authorization']='Bearer '+token
raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=')
name=None
try:
    r=c.post('/api/admin/product-images',json={'data':base64.b64encode(raw).decode(),'content_type':'image/png'});assert r.status_code==200,r.status_code
    image_url=r.json()['image_url'];name=image_url.rsplit('/',1)[1];assert re.fullmatch(r'[a-f0-9]{32}\.png',name)
    assert c.get(image_url).content==raw
    public=TestClient(app);assert public.get(image_url).status_code==404
    p=c.get('/api/admin/products').json()[0]
    assert c.post('/api/admin/products/1',json={**p,'image_urls':[image_url]}).status_code==200
    assert public.get(image_url).content==raw
    assert c.post('/api/admin/products/1',json={**p,'published':False,'image_urls':[image_url]}).status_code==200
    assert public.get(image_url).status_code==404
    assert c.get(image_url).content==raw
    print('PASS: live PostgreSQL + private R2 upload API, authenticated hidden previews, public published gallery image, hidden again denied')
finally:
    if name:delete_image(name)
