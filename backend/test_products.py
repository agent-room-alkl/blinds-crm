import os,tempfile,json,base64
from datetime import date,timedelta
with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND']='postgres' if os.getenv('VERA_TEST_SCHEMA') else 'sqlite'; os.environ['VERA_STORAGE_BACKEND']='local'; os.environ['VERA_DB']=folder+'/test.db';os.environ['VERA_MEDIA_DIR']=folder+'/media'
    from service import app,init_db
    if os.getenv('VERA_TEST_SCHEMA'):
        import re
        assert re.fullmatch(r'vera_test_[a-f0-9]{12}',os.environ['VERA_TEST_SCHEMA'])
        assert os.environ.get('VERA_DB_SCHEMA')==os.environ['VERA_TEST_SCHEMA']
        init_db()
    from fastapi.testclient import TestClient
    c=TestClient(app)
    assert c.get('/api/admin/products').status_code==401
    c.headers['Authorization']='Bearer '+c.post('/api/auth/login',json={'username':'dylan','password':os.environ.get('VERA_DEMO_PASSWORD','vera-demo')}).json()['token']
    assert len(c.get('/api/products').json())==3
    assert len(c.get('/api/products/1').json()['image_urls'])==2
    p=c.get('/api/admin/products').json()[0]
    iid=c.post('/api/inquiries',json={'company':'Catalogue QA Demo','contact_name':'Demo','channel':'qa@example.invalid','locale':'en'}).json()['id']
    q=c.post('/api/quotes',json={'inquiry_id':iid,'locale':'en','currency':'NZD','valid_until':str(date.today()+timedelta(days=30)),'discount':0,'shipping':0,'tax':0,'terms':'Demo','lines':[{'product_id':1,'width':1000,'height':1200,'unit':'mm','material':'Aluminium','color':'White','control':'Manual','quantity':1,'unit_price':100}]}).json()
    order=c.post(f"/api/quotes/{q['id']}/versions/1/accept",json={'note':'Demo test acceptance'}).json()
    frozen=order['snapshot'];before=c.get(f"/api/quotes/{q['id']}").json()
    edited={**p,'name_en':'Updated Catalogue Demo','width_min':500,'width_max':1800,'height_min':600,'height_max':2400,'colors':['White','Black'],'controls':['Cord'],'published':True}
    assert c.post('/api/admin/products/1',json=edited).status_code==200
    assert c.get('/api/products/1').json()['name_en']=='Updated Catalogue Demo'
    gallery=[edited['image_urls'][1],edited['image_urls'][0]]
    assert c.post('/api/admin/products/1',json={**edited,'image_urls':gallery}).status_code==200
    assert c.get('/api/products/1').json()['image_urls']==gallery
    assert c.get('/api/products/1').json()['image_url']==gallery[0]
    assert c.post('/api/admin/products/1',json={**edited,'image_urls':['/images/../x.png']}).status_code==422
    assert c.post('/api/admin/products/1',json={**edited,'image_urls':['/images/x.png']*13}).status_code==422
    assert c.post('/api/admin/products/1',json={**edited,'image_urls':[],'image_url':''}).status_code==422
    assert c.get(f"/api/orders/{order['id']}").json()['snapshot']==frozen
    assert c.get(f"/api/quotes/{q['id']}").json()==before
    assert c.post('/api/admin/products/1',json={**edited,'width_min':2000,'width_max':100}).status_code==422
    assert c.post('/api/admin/products/1',json={**edited,'image_url':'/images/../secret.png'}).status_code==422
    assert c.post('/api/admin/products/1',json={**edited,'name_en':'   '}).status_code==422
    draft=c.post('/api/admin/products',json={**edited,'name_en':'Hidden Demo','published':False}).json()
    assert c.get(f"/api/products/{draft['id']}").status_code==404
    assert draft['id'] not in [p['id'] for p in c.get('/api/products').json()]
    assert draft['id'] in [p['id'] for p in c.get('/api/admin/products').json()]
    raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=')
    upload=c.post('/api/admin/product-images',json={'data':base64.b64encode(raw).decode(),'content_type':'image/png'})
    assert upload.status_code==200,upload.text
    assert c.get(upload.json()['image_url']).content==raw
    assert TestClient(app).get(upload.json()['image_url']).status_code==404
    published={**edited,'image_urls':[upload.json()['image_url']]}
    assert c.post('/api/admin/products/1',json=published).status_code==200
    assert TestClient(app).get(upload.json()['image_url']).content==raw
    assert c.post('/api/admin/products/1',json={**published,'published':False}).status_code==200
    assert TestClient(app).get(upload.json()['image_url']).status_code==404
    assert c.post('/api/admin/products/1',json=edited).status_code==200
    assert c.post('/api/admin/product-images',json={'data':base64.b64encode(b'not an image').decode(),'content_type':'image/png'}).status_code==422
    assert c.post('/api/admin/product-images',json={'data':base64.b64encode(raw).decode(),'content_type':'image/jpeg'}).status_code==422
    c.post('/api/users',json={'username':'viewer','name':'Demo Viewer','password':'test-viewer','role':'staff'})
    staff=TestClient(app);staff.headers['Authorization']='Bearer '+staff.post('/api/auth/login',json={'username':'viewer','password':'test-viewer'}).json()['token']
    assert staff.get('/api/admin/products').status_code==200
    assert staff.post('/api/admin/products/1',json=edited).status_code==403
    assert staff.post('/api/admin/product-images',json={'data':base64.b64encode(raw).decode(),'content_type':'image/png'}).status_code==403
    print('PASS: catalogue CRUD, public visibility, auth/staff403, local image upload, MIME validation, unpublished image privacy, dimension validation, ordered galleries, cover/limit validation, immutable quote and order snapshots')
