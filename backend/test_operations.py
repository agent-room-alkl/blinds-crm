"""Isolated requirements checks. No real SMTP, AI, or production database calls."""
import os
import tempfile
from unittest.mock import patch

with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND'] = 'sqlite'
    os.environ['VERA_STORAGE_BACKEND'] = 'local'
    os.environ['VERA_DB'] = os.path.join(folder, 'operations.db')
    from service import app
    from fastapi.testclient import TestClient
    staff = TestClient(app)
    portal = TestClient(app)
    other = TestClient(app)
    r = staff.post('/api/auth/login', json={'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})
    assert r.status_code == 200, r.text
    staff.headers['Authorization'] = 'Bearer '+r.json()['token']

    def post(client, path, body=None, status=200):
        r = client.post('/api/'+path, json=body)
        assert r.status_code == status, (path, r.status_code, r.text)
        return r.json()

    def provision(name):
        return post(staff, 'operations/customers', dict(company=name, contact_name='Only person', email=name+'@example.invalid',
                    phone='12345', company_address='Company address', username=name, password='test-password'))

    a = provision('customerA')
    b = provision('customerB')
    post(staff, 'operations/customers', {**{k: a[k] for k in ('company','contact_name','email','phone','company_address')},
         'customer_id': a['customer_id'], 'username': 'another', 'password': 'test-password'}, 409)
    for c, name in [(portal, 'customerA'), (other, 'customerB')]:
        token = post(c, 'portal/login', {'username': name, 'password': 'test-password'})['token']
        c.headers['Authorization'] = 'Bearer '+token
    for path in ('users','operations/orders','operations/customers'):
        assert portal.get('/api/'+path).status_code == 401, path
    for path in ('customers','orders','inquiries','quotes','workbench'):
        assert portal.get('/api/'+path).status_code == 404, path
    assert staff.get('/api/portal/me').status_code == 401
    assert portal.get('/api/portal/me').json()['company_address'] == 'Company address'
    assert 'password' not in str(staff.get('/api/operations/customers').json())
    print('PASS identity: one account/contact, company isolation and separate staff sessions')

    body = dict(project_name='Windows project', site_address='Installation address', submission_key='project-0001', lines=[
        dict(window_name='Bedroom',product_id=1,width_mm=1000,height_mm=1000,quantity=3,options={}),
        dict(window_name='Lounge',product_id=1,width_mm=1000,height_mm=1000,quantity=2,options={})])
    post(portal,'portal/price',body,409)
    pending = post(portal,'portal/orders',body)
    oid = pending['id']
    assert pending['total'] is None and not pending['invoices']
    assert post(portal,'portal/orders',body)['id'] == oid
    post(portal,'portal/orders',{**body, 'project_name':'changed'},409)
    post(staff,f'operations/orders/{oid}/review',status=409)
    post(staff,f'operations/orders/{oid}/deposit-received',status=409)
    post(staff,f'operations/orders/{oid}/supplier-order',{'reference':'supplier-1'},409)
    assert other.get('/api/portal/orders').json() == []
    print('PASS unknown rules: no fabricated prices/invoices; idempotent pending submission')

    rule = dict(evidence='TEST FIXTURE ONLY, not a commercial price sheet',currency='NZD',tax_basis='TEST inclusive',
                rate_per_m2='100', minimum_area='1', dimension_step_mm=1,max_width_mm=3000,max_height_mm=3000,
                options={},formula='area_fixed_percent_installation',deposit_basis='order_total')
    post(staff,'operations/pricing/1',rule)
    priced = post(portal,'portal/price',body)
    assert priced['total'] == '500.00'
    # Reject unconfigured prices and client-injected manual prices.
    bad = {**body, 'submission_key':'bad-price', 'lines':[{**body['lines'][0], 'unit_price':'0.01'}]}
    post(portal,'portal/orders',bad,422)
    reviewed = post(staff,f'operations/orders/{oid}/review')
    assert reviewed['total'] == '500.00' and reviewed['invoices'][0]['amount'] == '300.00'
    assert reviewed['invoices'][0]['deposit_rate'] == '0.60'
    from operations import deposit_amount
    assert deposit_amount('500.02') == '300.02'  # round up, not half-up (300.012).
    assert len(post(staff,f'operations/orders/{oid}/review')['invoices']) == 1
    deposit_id=reviewed['invoices'][0]['id']
    with patch('email_service.configuration',return_value=({'configured':False},None)):
        assert post(staff,f'operations/invoices/{deposit_id}/send')['status']=='not_configured'
    with patch('email_service.configuration',return_value=({'configured':True},None)), patch('email_service.send_email',return_value='<test-deposit>'):
        post(staff,f'operations/notifications/invoice-mail:{deposit_id}/retry')
    assert next(i for i in staff.get('/api/operations/invoices').json() if i['id']==deposit_id)['status']=='sent'
    post(staff,f'operations/orders/{oid}/supplier-order',{'reference':'supplier-1'},409)
    post(staff,f'operations/orders/{oid}/deposit-received')
    post(staff,f'operations/orders/{oid}/deposit-received')
    ordered = post(staff,f'operations/orders/{oid}/supplier-order',{'reference':'supplier-1'})
    assert sum(h['action']=='deposit_received' for h in ordered['history']) == 1
    assert staff.get(f'/api/operations/orders/{oid}/supplier-export').status_code == 422,'Without template, should require explicit fallback flag'
    transit = post(staff,'operations/transit',{'order_ids':[oid,'not-found'],'operation_key':'transit-001'})
    assert [r['status'] for r in transit['results']] == ['success','failed']
    print('PASS review/deposit: submission does not invoice; acceptance invoices 60% ROUNDUP; separate receipt gate')

    first = dict(order_id=oid,kind='arrival',operation_key='arrival-001',lines=[dict(line_id='1',quantity=2)])
    with patch('email_service.configuration',return_value=({'configured':True},None)), patch('email_service.send_email',return_value='<test-1>') as send:
        arrived = post(staff,'operations/fulfilment',first)
        post(staff,'operations/fulfilment',first)
        assert send.call_count == 1
        assert 'Bedroom: 2' in send.call_args.args[2] and 'Lounge' not in send.call_args.args[2]
    assert arrived['order']['status']=='partially_arrived'
    assert arrived['order']['payment_status']=='deposit_received'
    post(staff,'operations/fulfilment',{**first,'lines':[dict(line_id='1',quantity=1)]},409)
    post(staff,'operations/fulfilment',{**first,'operation_key':'over-arrival','lines':[dict(line_id='1',quantity=2)]},422)
    post(staff,'operations/fulfilment',dict(order_id=oid,kind='delivery',operation_key='over-delivery',lines=[dict(line_id='1',quantity=3)]),422)
    delivered = post(staff,'operations/fulfilment',dict(order_id=oid,kind='delivery',operation_key='delivery-001',lines=[dict(line_id='1',quantity=1)]))['order']
    assert sum(l['arrived'] for l in delivered['lines']) == 2
    assert sum(l['delivered'] for l in delivered['lines']) == 1
    assert sum(l['quantity']-l['arrived'] for l in delivered['lines']) == 3
    assert delivered['arrival_status']=='partially_arrived' and delivered['delivery_status']=='partially_delivered'
    settle = dict(order_ids=[oid],operation_key='settlement-001',rules_evidence='TEST confirmed settlement example',billing_basis='fully_delivered_remaining_total')
    post(staff,'operations/settlements',settle,409)
    with patch('email_service.configuration',return_value=({'configured':False},None)):
        batch = post(staff,'operations/fulfilment',dict(order_id=oid,kind='arrival',operation_key='arrival-002',lines=[dict(line_id='1',quantity=1),dict(line_id='2',quantity=2)]))
        assert batch['notification']['status']=='not_configured'
    final = post(staff,'operations/fulfilment',dict(order_id=oid,kind='delivery',operation_key='delivery-002',lines=[dict(line_id='1',quantity=2),dict(line_id='2',quantity=2)]))['order']
    assert final['status']=='delivered' and final['payment_status']=='deposit_received'
    print('PASS fulfilment: 3+2 / arrival2 / delivery1; bounds, separate progress, actual-batch mail and dedupe')

    rebate = dict(customer_id=a['customer_id'],source_order_ids=[oid],month='2026-01',amount='50',evidence='TEST confirmed monthly credit',currency='NZD')
    credit = post(staff,'operations/rebates',rebate)
    post(staff,'operations/rebates',rebate,409)
    invoice = post(staff,'operations/settlements',settle)
    assert invoice['gross']=='200.00' and invoice['amount']=='150.00'
    assert post(staff,'operations/settlements',settle)['id'] == invoice['id']
    post(staff,'operations/settlements',{**settle,'operation_key':'new-settle-001'},409)
    credits = staff.get('/api/operations/rebates').json()['credits']
    assert credits[0]['used']=='50.00' and credits[0]['remaining']=='0.00' and len(credits[0]['allocations'])==1
    with patch('email_service.configuration',return_value=({'configured':True},None)), patch('email_service.send_email',return_value='<test-invoice>') as send:
        post(staff,f"operations/invoices/{invoice['id']}/send")
        post(staff,f"operations/invoices/{invoice['id']}/send")
        assert send.call_count == 1
    ob = post(other,'portal/orders',{**body,'submission_key':'other-project'})
    post(staff,'operations/settlements',{**settle,'order_ids':[oid,ob['id']],'operation_key':'mixed-companies'},422)
    assert len(other.get('/api/portal/consumption').json()['invoices']) == 0
    print('PASS settlement/rebate: company boundaries, deposit deduction, credit source/use dedupe and invoice-send dedupe')

    # A new price sheet never rewrites a reviewed order snapshot.
    post(staff,'operations/pricing/1',{**rule,'rate_per_m2':'999'})
    assert portal.get('/api/portal/orders').json()[0]['total']=='500.00'
    post(portal,'portal/logout')
    assert portal.get('/api/portal/orders').status_code == 401
    print('PASS frozen prices and logout. All operations requirements checks passed.')

    # Provider management comprehensive tests
    print('\n--- Provider management ---')
    # Portal token must be rejected by operations endpoints
    resp=other.get('/api/operations/providers')
    assert resp.status_code==401,'Portal token must not access operations endpoints'
    print('✓ Portal token rejected by operations/providers')
    
    # Create active provider
    resp=staff.post('/api/operations/providers',json={'name':'Test Supplier','contact_email':'supplier@example.com','notes':'Test notes'})
    assert resp.status_code==200,f'Create provider failed: {resp.text}'
    pid=resp.json()['id']
    print(f'✓ Created provider {pid}')
    
    # Create inactive provider
    resp=staff.post('/api/operations/providers',json={'name':'Inactive Supplier','contact_email':'inactive@example.com','notes':'Inactive'})
    inactive_pid=resp.json()['id']
    staff.post(f'/api/operations/providers/{inactive_pid}',json={'name':'Inactive Supplier','contact_email':'inactive@example.com','notes':'Inactive','active':False})
    print(f'✓ Created inactive provider {inactive_pid}')
    
    # List providers
    resp=staff.get('/api/operations/providers')
    assert resp.status_code==200
    assert any(p['id']==pid for p in resp.json())
    print('✓ Listed providers')
    
    # Create custom template with column mappings
    mappings={'order_id':'A','window_name':'B','width_mm':'C','height_mm':'D','quantity':'E','arrived':'F'}
    resp=staff.post('/api/operations/provider-templates',json={
        'provider_id':pid,'name':'Custom Template','sheet_name':'OrderSheet','column_mappings':mappings})
    assert resp.status_code==200,f'Create template failed: {resp.text}'
    tid=resp.json()['id']
    print(f'✓ Created custom template {tid}')
    
    # Assign provider with template to order
    orders_list=staff.get('/api/operations/orders').json()
    oid=orders_list[0]['id']
    resp=staff.post(f'/api/operations/orders/{oid}/assign-provider',json={'provider_id':pid,'template_id':tid,'is_preferred':True})
    assert resp.status_code==200
    assert resp.json()['provider_id']==pid
    print('✓ Assigned provider with custom template to order')
    
    # Cannot assign inactive provider
    resp=staff.post(f'/api/operations/orders/{oid}/assign-provider',json={'provider_id':inactive_pid,'template_id':None})
    assert resp.status_code==404,'Inactive provider should be rejected'
    print('✓ Inactive provider assignment blocked')
    
    # Get order providers
    resp=staff.get(f'/api/operations/orders/{oid}/providers')
    assert resp.status_code==200
    assert len(resp.json())>0
    print('✓ Retrieved order providers')
    
    # Export with custom template and validate XLSX structure
    import openpyxl,io
    resp=staff.get(f'/api/operations/orders/{oid}/supplier-export')
    assert resp.status_code==200,f'Custom template export failed: {resp.status_code} {resp.text}'
    assert resp.headers['content-type']=='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    wb=openpyxl.load_workbook(io.BytesIO(resp.content))
    assert 'OrderSheet' in wb.sheetnames,'Custom sheet name must exist'
    ws=wb['OrderSheet']
    # Validate headers match mappings
    assert ws['A1'].value=='order_id','Header A1 should be order_id'
    assert ws['B1'].value=='window_name','Header B1 should be window_name'
    assert ws['C1'].value=='width_mm','Header C1 should be width_mm'
    # Validate data rows
    assert ws['A2'].value is not None,'Order ID data in row 2'
    assert ws['B2'].value is not None,'Window name data in row 2'
    print('✓ Exported with custom template; validated XLSX structure (OrderSheet, mapped headers, data rows)')
    
    # Export for inactive provider should fail
    resp=staff.get(f'/api/operations/orders/{oid}/supplier-export?provider_id={inactive_pid}')
    assert resp.status_code==404,'Cannot export for inactive provider'
    print('✓ Inactive provider export blocked')
    
    # Export without template but no fallback allowed should fail
    oid2=orders_list[1]['id'] if len(orders_list)>1 else oid
    resp=staff.get(f'/api/operations/orders/{oid2}/supplier-export')
    assert resp.status_code==422,'Should require template or explicit fallback'
    print('✓ Export without template requires explicit fallback flag')
    
    # Basic fallback with flag
    resp=staff.get(f'/api/operations/orders/{oid2}/supplier-export?allow_basic_fallback=true')
    assert resp.status_code==200,'Basic fallback with flag should work'
    assert 'BASIC-NOT-VERIFIED' in resp.headers['content-disposition'],'Filename must indicate basic fallback'
    wb2=openpyxl.load_workbook(io.BytesIO(resp.content))
    assert 'Project' in wb2.sheetnames,'Basic fallback uses Project sheet'
    print('✓ Basic fallback export with explicit flag; XLSX validated; filename clearly marked BASIC-NOT-VERIFIED')
    
    print('PASS provider management: portal token rejection, CRUD, templates, active/inactive handling, custom XLSX with mapped columns, basic fallback with clear labeling')
