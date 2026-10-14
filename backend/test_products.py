import os,tempfile,json,base64
from datetime import date,timedelta
with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB']=folder+'/test.db';os.environ['VERA_MEDIA_DIR']=folder+'/media'
    from service import app
    from fastapi.testclient import TestClient
    c=TestClient(app)
    assert c.get('/api/admin/products').status_code==401
    c.headers['Authorization']='Bearer '+c.post('/api/auth/login',json={'username':'dylan','password':os.environ.get('VERA_DEMO_PASSWORD','vera-demo')}).json()['token']
    assert len(c.get('/api/products').json())==3
    p=c.get('/api/admin/products').json()[0]
    iid=c.post('/api/inquiries',json={'company':'Catalogue QA Demo','contact_name':'Demo','channel':'qa@example.invalid','locale':'en'}).json()['id']
    q=c.post('/api/quotes',json={'inquiry_id':iid,'locale':'en','currency':'NZD','valid_until':str(date.today()+timedelta(days=30)),'discount':0,'shipping':0,'tax':0,'terms':'Demo','lines':[{'product_id':1,'width':1000,'height':1200,'unit':'mm','material':'Aluminium','color':'White','control':'Manual','quantity':1,'unit_price':100}]}).json()
    order=c.post(f"/api/quotes/{q['id']}/versions/1/accept",json={'note':'Demo test acceptance'}).json()
    frozen=order['snapshot'];before=c.get(f"/api/quotes/{q['id']}").json()
    edited={**p,'name_en':'Updated Catalogue Demo','width_min':500,'width_max':1800,'height_min':600,'height_max':2400,'colors':['White','Black'],'controls':['Cord'],'published':True}
    assert c.post('/api/admin/products/1',json=edited).status_code==200
    assert c.get('/api/products/1').json()['name_en']=='Updated Catalogue Demo'
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
    assert c.post('/api/admin/product-images',json={'data':base64.b64encode(b'not an image').decode(),'content_type':'image/png'}).status_code==422
    assert c.post('/api/admin/product-images',json={'data':base64.b64encode(raw).decode(),'content_type':'image/jpeg'}).status_code==422
    c.post('/api/users',json={'username':'viewer','name':'Demo Viewer','password':'test-viewer','role':'staff'})
    staff=TestClient(app);staff.headers['Authorization']='Bearer '+staff.post('/api/auth/login',json={'username':'viewer','password':'test-viewer'}).json()['token']
    assert staff.get('/api/admin/products').status_code==200
    assert staff.post('/api/admin/products/1',json=edited).status_code==403
    assert staff.post('/api/admin/product-images',json={'data':base64.b64encode(raw).decode(),'content_type':'image/png'}).status_code==403
    print('PASS: catalogue CRUD, public visibility, auth/staff403, local image upload, MIME validation, dimension validation, immutable quote and order snapshots')
