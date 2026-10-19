"""Isolated current staff API/auth checks; retired routes must be absent."""
import os,tempfile
from unittest.mock import patch
with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND']='postgres' if os.getenv('VERA_TEST_SCHEMA') else 'sqlite'
    os.environ['VERA_DB']=os.path.join(folder,'core.db');os.environ['VERA_STORAGE_BACKEND']='local'
    from service import app,init_db,db
    if os.getenv('VERA_TEST_SCHEMA'):init_db()
    from fastapi.testclient import TestClient
    client=TestClient(app)
    assert client.get('/api/health').json()['status']=='ok'
    assert client.get('/api/users').status_code==401
    result=client.post('/api/auth/login',json={'username':'dylan','password':os.getenv('VERA_DEMO_PASSWORD','vera-demo')})
    assert result.status_code==200,result.text
    client.headers['Authorization']='Bearer '+result.json()['token']
    assert client.get('/api/auth/me').json()['role']=='admin'
    assert client.post('/api/users',json={'username':'staff','name':'Staff','password':'test-password','role':'staff'}).status_code==200
    assert client.post('/api/users/dylan/role',json={'role':'staff'}).status_code==409
    assert client.get('/api/operations/settings').status_code==200
    staff=TestClient(app)
    staff.headers['Authorization']='Bearer '+staff.post('/api/auth/login',json={'username':'staff','password':'test-password'}).json()['token']
    assert staff.get('/api/operations/settings').status_code==403
    with patch.dict(os.environ,{'VERA_EMAIL_MODE':'demo','VERA_DEMO_EMAIL_ADDRESS':'owner@example.invalid'}):
        assert client.get('/api/operations/runtime').json()['demo_email_address']=='owner@example.invalid'
        assert staff.get('/api/operations/runtime').json()['demo_email_address']==''
    for path in ('inquiries','quotes','orders','customers','workbench','quote-drafts','communications/unassigned','dashboard','integrations/status'):
        assert client.get('/api/'+path).status_code==404,path
    assert client.post('/api/inquiries',json={}).status_code==404
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/users').status_code==401
    from cleanup_legacy import LEGACY_TABLES,table_names
    with db() as c:assert not (set(LEGACY_TABLES)&table_names(c))
    print('PASS staff auth/users/admin safeguards/settings; retired API404; fresh schema contains no legacy tables')
