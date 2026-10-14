"""Run python backend/test_api.py; uses an isolated temporary SQLite database."""
import os
import tempfile
import json
from datetime import date, timedelta

with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND']='postgres' if os.getenv('VERA_TEST_SCHEMA') else 'sqlite'; os.environ['VERA_STORAGE_BACKEND']='local'; os.environ['VERA_DB']=os.path.join(folder,'test.db')
    from service import app,init_db
    if os.getenv('VERA_TEST_SCHEMA'):
        import re
        assert re.fullmatch(r'vera_test_[a-f0-9]{12}',os.environ['VERA_TEST_SCHEMA'])
        assert os.environ.get('VERA_DB_SCHEMA')==os.environ['VERA_TEST_SCHEMA']
        init_db()
    from fastapi.testclient import TestClient
    c=TestClient(app)
    assert c.get('/api/health').json()['status']=='ok'
    for path in ['inquiries','customers','quotes','orders','dashboard']:
        assert c.get('/api/'+path).status_code==401
    token=c.post('/api/auth/login',json={'username':'dylan','password':os.environ.get('VERA_DEMO_PASSWORD','vera-demo')}).json()['token']
    c.headers['Authorization']='Bearer '+token
    body={'company':'DEMO Trade','contact_name':'Test buyer','channel':'test@example.invalid','locale':'zh','submission_key':'test-unique'}
    r=c.post('/api/inquiries',json=body); assert r.status_code==200,r.text
    iid=r.json()['id'];assert c.post('/api/inquiries',json=body).json()['id']==iid
    assert len(c.get('/api/inquiries').json())==1
    assert c.post('/api/inquiries',json={**body,'submission_key':'bad','width':100}).status_code==422
    assert c.post('/api/followups',json={'inquiry_id':iid,'note':'Discussed dimensions','next_at':'2027-01-10T10:00'}).status_code==200
    q={'inquiry_id':iid,'locale':'zh','currency':'NZD','valid_until':str(date.today()+timedelta(days=30)),'discount':10,'shipping':20,'tax':30,'terms':'Demo terms','lines':[{'product_id':1,'width':1000,'height':1500,'unit':'mm','material':'aluminium','color':'white','control':'manual','quantity':2,'unit_price':100}]}
    r=c.post('/api/quotes',json=q);assert r.status_code==200,r.text
    quote=r.json();qid=quote['id'];v1=quote['versions'][0]
    assert v1['total']=='240.00'
    q['lines'][0]['unit_price']=125
    r=c.post(f'/api/quotes/{qid}/versions',json=q);assert r.status_code==200,r.text
    assert r.json()['version']==2
    assert c.get(f'/api/quotes/{qid}').json()['versions'][0]==v1
    assert c.post(f'/api/quotes/{qid}/versions/1/accept',json={'note':'old'}).status_code==409
    assert c.post(f'/api/quotes/{qid}/versions/2/accept',json={'note':'   '}).status_code==422
    r=c.post(f'/api/quotes/{qid}/versions/2/accept',json={'note':'Buyer confirmed in demo'});assert r.status_code==200,r.text
    order=r.json();oid=order['id'];snap=order['snapshot'];assert snap['total']=='290.00'
    assert c.post(f'/api/quotes/{qid}/versions/2/accept',json={'note':'retry'}).json()['id']==oid
    assert c.post(f'/api/orders/{oid}/status',json={'status':'delivered'}).status_code==409
    for status in ['production','ready','delivered']:
        assert c.post(f'/api/orders/{oid}/status',json={'status':status}).json()['status']==status
    q['lines'][0]['unit_price']=999
    assert c.post(f'/api/quotes/{qid}/versions',json=q).status_code==200
    assert c.get(f'/api/orders/{oid}').json()['snapshot']==snap
    assert len(c.get(f'/api/orders/{oid}').json()['history'])==4
    for lang in ['zh','en']:
        export=c.get(f'/api/quotes/{qid}/versions/2/export?lang={lang}')
        assert export.status_code==200 and '290.00' in export.text
    trade=next(x for x in c.get('/api/customers').json() if x['company']=='DEMO Trade')
    frozen=c.get(f'/api/orders/{oid}').json()['snapshot']
    edited=c.post(f"/api/customers/{trade['id']}",json={'company':'Renamed Trade','contact_name':'Renamed buyer','channel':'renamed@example.invalid','locale':'en','notes':'Prefers weekday morning','contact_id':trade['contacts'][0]['id']})
    assert edited.status_code==200,edited.text
    saved=next(x for x in c.get('/api/customers').json() if x['id']==trade['id'])
    assert saved['company']=='Renamed Trade' and saved['locale']=='en' and saved['notes']=='Prefers weekday morning'
    assert saved['contacts'][0]['name']=='Renamed buyer' and saved['contacts'][0]['channel']=='renamed@example.invalid'
    assert c.get(f'/api/orders/{oid}').json()['snapshot']==frozen==snap
    assert c.post(f"/api/customers/{trade['id']}",json={'company':'   ','contact_name':'   ','channel':'   ','locale':'en'}).status_code==422
    assert next(x for x in c.get('/api/customers').json() if x['id']==trade['id'])['company']=='Renamed Trade'
    assert TestClient(app).post(f"/api/customers/{trade['id']}",json={'company':'x','contact_name':'y','channel':'z','locale':'zh'}).status_code==401
    assert c.post('/api/conversations',json={'contact_name':'Demo','channel':'demo@example.invalid','locale':'en','weekday_slot':'Monday afternoon'}).status_code==200
    assert c.get('/api/auth/me').json()['role']=='admin'
    assert c.get('/api/users').json()[0]['username']=='dylan'
    created=c.post('/api/users',json={'username':'sam','name':'Sam','password':'staff-pass','role':'staff'})
    assert created.status_code==200,created.text
    staff=TestClient(app)
    staff_token=staff.post('/api/auth/login',json={'username':'sam','password':'staff-pass'}).json()['token']
    staff.headers['Authorization']='Bearer '+staff_token
    assert staff.get('/api/users').status_code==403
    assert c.post('/api/users/sam/role',json={'role':'admin'}).status_code==200
    assert c.post('/api/auth/password',json={'current':'not-the-password','new':'another-pass'}).status_code==400
    assert c.post('/api/users',json={'username':'blank','name':'   ','password':'staff-pass','role':'staff'}).status_code==422
    assert staff.post('/api/auth/password',json={'current':'staff-pass','new':'staff-pass-2'}).status_code==200
    assert staff.get('/api/orders').status_code==401
    assert staff.post('/api/auth/login',json={'username':'sam','password':'staff-pass-2'}).status_code==200
    frozen_assist=c.get(f'/api/orders/{oid}').json()['snapshot']
    follow_count=len(c.get(f'/api/inquiries/{iid}').json()['followups'])
    assert TestClient(app).post(f'/api/inquiries/{iid}/assistant',json={}).status_code==401
    assert c.post('/api/inquiries/999999/assistant',json={}).status_code==404
    assist=c.post(f'/api/inquiries/{iid}/assistant',json={})
    assert assist.status_code==200,assist.text
    draft=assist.json()
    assert draft['mode']=='rules' and draft['connected'] is False and draft['agreed'] is False and draft['locale']=='en'
    assert draft['suggested_next_at']!='2027-01-10T10:00' and 'not an agreed time' in draft['summary']
    assert any(f['source']=='customer.notes' and 'Prefers weekday morning' in f['text'] for f in draft['facts'])
    assert any(f['source'].startswith('followup:') and f['text']=='Discussed dimensions' for f in draft['facts'])
    assert any(f['source'].startswith('quote:') for f in draft['facts']) and any(f['source'].startswith('order:') for f in draft['facts'])
    assert '290.00' not in draft['reply'] and '999' not in draft['reply'] and 'does not include a price' in draft['reply']
    assert len(c.get(f'/api/inquiries/{iid}').json()['followups'])==follow_count
    assert c.get(f'/api/orders/{oid}').json()['snapshot']==frozen_assist
    zh=c.post('/api/inquiries',json={'company':'中文客户','contact_name':'李','channel':'li@example.invalid','locale':'zh','notes':'窗宽未知','submission_key':'zh-assist'})
    assert zh.status_code==200,zh.text
    zid=zh.json()['id']
    zd=c.post(f'/api/inquiries/{zid}/assistant',json={}).json()
    assert zd['locale']=='zh' and '窗宽未知' in zd['summary'] and '尺寸' in zd['gaps'] and '不含报价' in zd['reply'] and '999' not in zd['reply']
    assert c.get(f'/api/inquiries/{zid}').json()['status']=='new' and c.get(f'/api/inquiries/{zid}').json()['followups']==[]
    assert c.post('/api/auth/logout').status_code==200
    assert c.get('/api/orders').status_code==401
    print('PASS: auth, persisted inquiries, retry deduplication, followups, quote totals, immutable v1/v2, idempotent acceptance, status sequence, frozen snapshot, bilingual exports, customer file edit leaves order snapshot, conversation intention, user roles, assistant drafts, logout')

