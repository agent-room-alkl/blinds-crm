"""Persistent drafts, mail idempotency and automatic analysis; no external delivery."""
import os,tempfile,json
from unittest.mock import patch
with tempfile.TemporaryDirectory() as folder:
    os.environ.update(VERA_DB_BACKEND='postgres' if os.getenv('VERA_TEST_SCHEMA') else 'sqlite',VERA_STORAGE_BACKEND='local',VERA_DB=folder+'/test.db',OPENAI_API_KEY='',IMAP_HOST='',SMTP_HOST='',SMTP_FROM='')
    from service import app,init_db,db,dump
    if os.getenv('VERA_TEST_SCHEMA'):
        import re
        assert re.fullmatch(r'vera_test_[a-f0-9]{12}',os.environ['VERA_TEST_SCHEMA'])
        assert os.environ['VERA_DB_SCHEMA']==os.environ['VERA_TEST_SCHEMA'];init_db()
    from fastapi.testclient import TestClient
    c=TestClient(app)
    assert c.get('/api/workbench').status_code==401
    token=c.post('/api/auth/login',json={'username':'dylan','password':os.getenv('VERA_DEMO_PASSWORD','vera-demo')}).json()['token']
    c.headers['Authorization']='Bearer '+token
    iid=c.post('/api/inquiries',json={'company':'Workflow customer','contact_name':'Buyer','channel':'buyer@example.invalid','locale':'en','submission_key':'workflow-001'}).json()['id']
    d=c.post(f'/api/inquiries/{iid}/quote-draft',json={}).json();did=d['id']
    assert c.post(f'/api/inquiries/{iid}/quote-draft',json={}).json()['id']==did
    assert c.post(f'/api/quote-drafts/{did}/publish',json={'revision':1}).status_code==422
    data=d['data'];data['terms']='Incomplete saved proposal'
    d=c.post(f'/api/quote-drafts/{did}',json={'revision':1,'data':data}).json()
    assert d['revision']==2 and c.get(f'/api/quote-drafts/{did}').json()['data']['terms']==data['terms']
    assert c.post(f'/api/quote-drafts/{did}',json={'revision':1,'data':data}).status_code==409
    data['lines']=[{'product_id':1,'width':1200,'height':1600,'unit':'mm','material':'aluminium','color':'white','control':'manual','quantity':2,'unit_price':'100.00'}]
    d=c.post(f'/api/quote-drafts/{did}',json={'revision':2,'data':data}).json()
    r=c.post(f'/api/quote-drafts/{did}/publish',json={'revision':3});assert r.status_code==200,r.text
    v=r.json();qid=v['quote_id'];assert v['total']=='200.00'
    assert c.post(f'/api/quote-drafts/{did}/publish',json={'revision':3}).json()==v
    assert not c.get('/api/quote-drafts').json()
    revision=c.post(f'/api/inquiries/{iid}/quote-draft',json={'quote_id':qid}).json()
    old=c.get(f'/api/quotes/{qid}').json()['versions'][0]
    revision['data']['tax']='0.001'
    saved=c.post(f"/api/quote-drafts/{revision['id']}",json={'revision':1,'data':revision['data']}).json()
    assert c.post(f"/api/quote-drafts/{revision['id']}/publish",json={'revision':saved['revision']}).status_code==422
    assert c.get(f'/api/quotes/{qid}').json()['versions'][0]==old
    mail={'recipient':'buyer@example.invalid','subject':'Quotation','body':'Please confirm the dimensions.','send_key':'workflow-email-00001','quote_id':qid,'version':1}
    assert c.post(f'/api/inquiries/{iid}/communications/email',json=mail).status_code==503
    smtp={'SMTP_HOST':'smtp.example.invalid','SMTP_FROM':'sales@example.invalid'}
    with patch.dict(os.environ,smtp),patch('email_service.send_email',return_value='<workflow-outbound@example.invalid>') as send:
        r=c.post(f'/api/inquiries/{iid}/communications/email',json=mail);assert r.status_code==200,r.text
        sent=r.json();assert sent['status']=='smtp_accepted' and sent['analysis']['state']=='unconfigured'
        assert send.call_args.kwargs['attachments'][0][0].endswith('.html')
        assert c.post(f'/api/inquiries/{iid}/communications/email',json=mail).json()['id']==sent['id'];assert send.call_count==1
        assert c.post(f'/api/inquiries/{iid}/communications/email',json={**mail,'body':'Changed'}).status_code==409
    with patch.dict(os.environ,smtp),patch('email_service.send_email',side_effect=TimeoutError('private')) as send:
        uncertain={**mail,'send_key':'workflow-email-00002'}
        r=c.post(f'/api/inquiries/{iid}/communications/email',json=uncertain);assert r.json()['status']=='unknown' and 'private' not in r.text
        assert c.post(f'/api/inquiries/{iid}/communications/email',json=uncertain).json()['status']=='unknown';assert send.call_count==1
    incoming={'external_id':'<incoming@example.invalid>','sender':'buyer@example.invalid','subject':'Requirements','body':'Please confirm width 1200 mm by 2026-12-01.','references':['<workflow-outbound@example.invalid>']}
    assert c.post('/api/integrations/mail/inbound',json=incoming).status_code==503
    job={'CRON_SECRET':'workflow-test-secret-0000000001','OPENAI_API_KEY':'test-only'}
    analysis={'summary':'Customer requested width confirmation.','facts':[{'field':'width','value':'1200 mm','evidence':'width 1200 mm'}],'tasks':[{'title':'Confirm width','due_at':'2026-12-01','evidence':incoming['body']}]}
    with patch.dict(os.environ,job),patch('ai_client.analyze',return_value=analysis):
        headers={'Authorization':'Bearer '+job['CRON_SECRET']}
        assert c.post('/api/integrations/mail/inbound',json=incoming).status_code==401
        r=c.post('/api/integrations/mail/inbound',json=incoming,headers=headers);assert r.status_code==200,r.text
        assert r.json()['inquiry_id']==iid
        assert c.post('/api/integrations/mail/inbound',json=incoming,headers=headers).json()['id']==r.json()['id']
        ws=c.get(f'/api/inquiries/{iid}/workspace').json();assert len(ws['tasks'])==1
        assert ws['communications'][0]['analysis']['state']=='ready'
        assert c.post(f"/api/project-tasks/{ws['tasks'][0]['id']}/complete",json={}).status_code==200
        unassigned={**incoming,'external_id':'<new-contact@example.invalid>','sender':'new@example.invalid','references':[]}
        r=c.post('/api/integrations/mail/inbound',json=unassigned,headers=headers);assert r.json()['inquiry_id'] is None
        assert len(c.get('/api/communications/unassigned').json())==1
        assert c.post(f"/api/communications/{r.json()['id']}/assign",json={'inquiry_id':iid}).status_code==200
    with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'}),patch('ai_client.analyze',side_effect=RuntimeError('private')):
        r=c.post(f'/api/inquiries/{iid}/communications/note',json={'kind':'phone','body':'Original phone record'});assert r.status_code==200,r.text
        assert r.json()['body']=='Original phone record' and r.json()['analysis']['state']=='error'
    from ai_client import generate,EmailDraft,AIError,analyze,Analysis
    from unittest.mock import MagicMock
    response=MagicMock();response.__enter__.return_value=response
    response.read.return_value=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'subject':'Draft','body':'Review details'})}}]}).encode()
    with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','OPENAI_MODEL':'gpt-5'}),patch('ai_client.urlopen',return_value=response) as provider:
        assert generate(EmailDraft,'Draft',{}).body=='Review details'
        payload=json.loads(provider.call_args.args[0].data);assert payload['model']=='gpt-5' and payload['store'] is False and payload['response_format']['json_schema']['strict'] is True
    with patch('ai_client.generate',return_value=Analysis(summary='Summary',facts=[{'field':'width','value':'999','evidence':'invented'}],tasks=[])):
        assert analyze('Subject','Actual customer body')['facts']==[]
    print('PASS: incomplete draft persistence, revision conflicts, finalization idempotency/precision, immutable history, email attachment/dedup/uncertain send, reply matching, automatic tasks, unassigned association, AI failure retention and GPT-5 strict request; no real email or AI calls')
