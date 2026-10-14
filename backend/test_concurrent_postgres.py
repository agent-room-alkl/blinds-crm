import os,re
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
assert re.fullmatch(r'vera_test_[a-f0-9]{12}',os.getenv('VERA_TEST_SCHEMA',''))
assert os.getenv('VERA_DB_SCHEMA')==os.environ['VERA_TEST_SCHEMA']
from service import app,init_db
from fastapi.testclient import TestClient
init_db();client=TestClient(app)
token=client.post('/api/auth/login',json={'username':'dylan','password':os.environ['VERA_DEMO_PASSWORD']}).json()['token']
def post(path,body):
    c=TestClient(app);c.headers['Authorization']='Bearer '+token
    r=c.post('/api/'+path,json=body);assert r.status_code==200,r.status_code
    return r.json()
def parallel(path,body):
    with ThreadPoolExecutor(max_workers=4) as pool:return list(pool.map(lambda _:post(path,body),range(4)))
body={'company':'Parallel QA Demo','contact_name':'Demo','channel':'parallel@example.invalid','locale':'en','submission_key':'concurrent-inquiry'}
items=parallel('inquiries',body);assert len({i['id'] for i in items})==1
iid=items[0]['id']
qbody={'inquiry_id':iid,'locale':'en','currency':'NZD','valid_until':str(date.today()+timedelta(days=30)),'discount':0,'shipping':0,'tax':0,'terms':'Demo','lines':[{'product_id':1,'width':1000,'height':1200,'unit':'mm','material':'Aluminium','color':'White','control':'Manual','quantity':1,'unit_price':100}]}
qid=post('quotes',qbody)['id']
versions=parallel(f'quotes/{qid}/versions',qbody);assert sorted(v['version'] for v in versions)==[2,3,4,5]
orders=parallel(f'quotes/{qid}/versions/5/accept',{'note':'Parallel test acceptance'});assert len({o['id'] for o in orders})==1
client.headers['Authorization']='Bearer '+token
assert len(client.get('/api/inquiries').json())==1
assert len(client.get('/api/orders').json())==1
assert orders[0]['snapshot']['version']==5
print('PASS: real PostgreSQL concurrent inquiry retry deduplication, serial immutable versions2-5, idempotent single order acceptance')

from service import db
other_password=os.environ['VERA_DEMO_PASSWORD']+'-other'
assert client.post('/api/users',json={'username':'otheradmin','name':'Other Test Admin','password':other_password,'role':'admin'}).status_code==200
peer=TestClient(app);peer_token=peer.post('/api/auth/login',json={'username':'otheradmin','password':other_password}).json()['token']
def demote(pair):
    actor_token,target=pair;c=TestClient(app);c.headers['Authorization']='Bearer '+actor_token
    return c.post('/api/users/'+target+'/role',json={'role':'staff'}).status_code
with ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(demote,[(token,'otheradmin'),(peer_token,'dylan')]))
assert 200 in results and all(code in (200,403,409) for code in results)
with db() as c:assert c.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND active=1").fetchone()['n']==1
print('PASS: simultaneous administrator demotions retain exactly one active administrator')
