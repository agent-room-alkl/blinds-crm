"""Isolated manual orders and email delivery tests. Never sends real email."""
import os,tempfile,json
from unittest.mock import patch,MagicMock
with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND']='postgres' if os.getenv('VERA_TEST_SCHEMA') else 'sqlite'
    os.environ['VERA_STORAGE_BACKEND']='local';os.environ['VERA_DB']=folder+'/test.db'
    from service import app,init_db
    if os.getenv('VERA_TEST_SCHEMA'):
        import re
        assert re.fullmatch(r'vera_test_[a-f0-9]{12}',os.environ['VERA_TEST_SCHEMA'])
        assert os.environ['VERA_DB_SCHEMA']==os.environ['VERA_TEST_SCHEMA'];init_db()
    from fastapi.testclient import TestClient
    import email_service
    c=TestClient(app)
    line={'product_id':1,'width':1200,'height':1600,'unit':'mm','material':'aluminium','color':'white','control':'manual','quantity':2,'unit_price':'150'}
    body={'company':'Phone customer','contact_name':'Buyer','channel':'phone-001','source':'phone','reference':'EXT-001','currency':'NZD','discount':10,'shipping':20,'tax':30,'confirmation_note':'Buyer confirmed by phone','submission_key':'manual-retry-00001','lines':[line]}
    assert c.post('/api/orders/manual',json=body).status_code==401
    token=c.post('/api/auth/login',json={'username':'dylan','password':os.getenv('VERA_DEMO_PASSWORD','vera-demo')}).json()['token'];c.headers['Authorization']='Bearer '+token
    r=c.post('/api/orders/manual',json=body);assert r.status_code==200,r.text
    order=r.json();oid=order['id'];snapshot=order['snapshot']
    assert order['version_id'] is None and snapshot['quote_id'] is None
    assert snapshot['order_source']=='manual' and snapshot['source']=='phone' and snapshot['total']=='340.00'
    assert not c.get('/api/quotes').json() and not c.get('/api/inquiries').json()
    assert c.post('/api/orders/manual',json=body).json()['id']==oid
    assert c.post('/api/orders/manual',json={**body,'reference':'changed'}).status_code==409
    assert len(c.get('/api/orders').json())==1
    cid=snapshot['customer_id'];customer=c.get('/api/customers').json()[0]
    assert customer['id']==cid and customer['orders'][0]['id']==oid
    existing={**body,'customer_id':cid,'submission_key':'manual-existing-00002','source':'email'}
    assert c.post('/api/orders/manual',json=existing).status_code==200
    assert len(c.get('/api/customers').json())==1
    assert c.post('/api/orders/manual',json={**body,'submission_key':'invalid-order-00003','discount':999}).status_code==422
    assert len(c.get('/api/orders').json())==2
    assert c.post(f'/api/orders/{oid}/status',json={'status':'delivered'}).status_code==409
    for stage in ('production','ready','delivered'):assert c.post(f'/api/orders/{oid}/status',json={'status':stage}).status_code==200
    assert c.get(f'/api/orders/{oid}').json()['snapshot']==snapshot
    from concurrent.futures import ThreadPoolExecutor
    parallel={**existing,'submission_key':'manual-concurrent-00004'}
    def submit_order(_):
        with TestClient(app) as client:
            client.headers['Authorization']='Bearer '+token
            response=client.post('/api/orders/manual',json=parallel)
            assert response.status_code==200,response.text
            return response.json()['id']
    with ThreadPoolExecutor(max_workers=4) as pool:assert len(set(pool.map(submit_order,range(4))))==1
    assert len(c.get('/api/orders').json())==3
    inquiry=c.post('/api/inquiries',json={'company':'Email customer','contact_name':'Recipient','channel':'buyer@example.invalid','locale':'zh','submission_key':'mail-inquiry-001'}).json();iid=inquiry['id']
    mail={'recipient':'buyer@example.invalid','subject':'Project follow-up','body':'Please confirm the dimensions.'}
    with patch.dict(os.environ,{'SMTP_HOST':'','SMTP_FROM':''}):
        assert not c.get('/api/email/config').json()['configured']
        assert c.post(f'/api/inquiries/{iid}/email',json=mail).status_code==503
    smtp={'SMTP_HOST':'smtp.example.invalid','SMTP_FROM':'sales@example.invalid','SMTP_USERNAME':'sales@example.invalid','SMTP_PASSWORD':'test-only','SMTP_SECURITY':'starttls','SMTP_PORT':'587'}
    with patch.dict(os.environ,smtp),patch('email_service.smtplib.SMTP') as factory:
        client=factory.return_value.__enter__.return_value;client.send_message.return_value={}
        assert c.post(f'/api/inquiries/{iid}/email',json={**mail,'recipient':'not-an-email'}).status_code==422
        assert c.post(f'/api/inquiries/{iid}/email',json={**mail,'subject':'Unsafe\nBcc: other@example.invalid'}).status_code==422
        assert not factory.called
        sent=c.post(f'/api/inquiries/{iid}/email',json=mail);assert sent.status_code==200,sent.text
        client.starttls.assert_called_once();client.login.assert_called_once();client.send_message.assert_called_once()
        message=client.send_message.call_args.args[0];assert message['To']==mail['recipient'] and mail['body'] in message.get_content()
        followups=c.get('/api/inquiries').json()[0]['followups'];assert len(followups)==1 and mail['subject'] in followups[0]['note']
    with patch.dict(os.environ,smtp),patch('email_service.send_email',side_effect=RuntimeError('private credential must not leak')):
        r=c.post(f'/api/inquiries/{iid}/email',json=mail);assert r.status_code==502 and 'private credential' not in r.text
        assert len(c.get('/api/inquiries').json()[0]['followups'])==1
    print('PASS: manual order auth, standalone customer/order, totals, idempotency/conflict, existing customer, status/snapshot, SMTP config, mocked TLS delivery/activity, header validation and failure privacy; no real email sent')
