"""Five-series catalogue, missing source email, and restart regression."""
import os,tempfile,base64
from pathlib import Path
with tempfile.TemporaryDirectory() as folder:
 os.environ.update(VERA_DB_BACKEND='sqlite',VERA_DB=str(Path(folder)/'test.db'),VERA_STORAGE_BACKEND='local')
 from service import app,db,init_db,dump
 from fastapi.testclient import TestClient
 from demo_workbook import fixture
 client=TestClient(app)
 r=client.post('/api/auth/login',json={'username':'dylan','password':'vera-demo'});assert r.status_code==200
 client.headers['Authorization']='Bearer '+r.json()['token']
 r=client.post('/api/operations/customers',json={'company':'Source contact without email','contact_name':'Not supplied','email':'','phone':'000','company_address':'Not supplied','username':'missing-email','password':'test-only-password'});assert r.status_code==200,r.text
 r=client.post('/api/operations/template-import',json={'filename':'fixture.xlsx','content_base64':base64.b64encode(fixture()).decode()});assert r.status_code==200,r.text
 with db() as c:
  # Canonical rebuild deliberately discards unreferenced initial sample rows.
  c.execute("DELETE FROM products WHERE id IN (1,2,3)")
 init_db();init_db()
 assert len(client.get('/api/admin/products').json())==5,'Restart must not recreate sample products'
 portal=TestClient(app);r=portal.post('/api/portal/login',json={'username':'missing-email','password':'test-only-password'});assert r.status_code==200
 portal.headers['Authorization']='Bearer '+r.json()['token']
 products=portal.get('/api/portal/catalog').json()['products']
 assert [p['name_en'] for p in products]==['VERA Eco','VERA Classic','VERA Natural','VERA Prime','VERA Deluxe']
 for p in products:assert p['image_url'].startswith('/images/website-')
 with db() as c:c.execute('INSERT INTO products VALUES(?,?)',(999,dump({'id':999,'source_code':'Shutters_Aluminium','category':'shutters','published':True,'orderable':True,'name_en':'Excluded Aluminium'})))
 assert len(portal.get('/api/portal/catalog').json()['products'])==5
 body={'project_name':'Rejected','site_address':'Test','submission_key':'excluded-aluminium','lines':[{'window_name':'Test','product_id':999,'width_mm':1000,'height_mm':1000,'quantity':1,'panel_count':1,'options':{}}]}
 assert portal.post('/api/portal/price',json=body).status_code==422
print('PASS five website series, source email may be absent, restart does not add samples, Aluminium rejected')
