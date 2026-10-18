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
    
    # Create Provider A with template config A
    resp=staff.post('/api/operations/providers',json={'name':'Supplier Alpha','contact_email':'alpha@example.com','notes':'Focused on shutters'})
    assert resp.status_code==200,f'Create provider A failed: {resp.text}'
    pid_a=resp.json()['id']
    print(f'✓ Created Provider A (Supplier Alpha) id={pid_a}')
    
    # Create Provider B with different template config B
    resp=staff.post('/api/operations/providers',json={'name':'Supplier Beta','contact_email':'beta@example.com','notes':'Focused on blinds'})
    assert resp.status_code==200,f'Create provider B failed: {resp.text}'
    pid_b=resp.json()['id']
    print(f'✓ Created Provider B (Supplier Beta) id={pid_b}')
    
    # Create inactive provider
    resp=staff.post('/api/operations/providers',json={'name':'Inactive Supplier','contact_email':'inactive@example.com','notes':'Inactive'})
    inactive_pid=resp.json()['id']
    staff.post(f'/api/operations/providers/{inactive_pid}',json={'name':'Inactive Supplier','contact_email':'inactive@example.com','notes':'Inactive','active':False})
    print(f'✓ Created inactive provider {inactive_pid}')
    
    # Template A: 6 columns in specific order
    mappings_a={'order_id':'A','window_name':'B','width_mm':'C','height_mm':'D','quantity':'E','arrived':'F'}
    resp=staff.post('/api/operations/provider-templates',json={
        'provider_id':pid_a,'name':'Alpha Template','sheet_name':'AlphaOrders','column_mappings':mappings_a})
    assert resp.status_code==200,f'Create template A failed: {resp.text}'
    tid_a=resp.json()['id']
    assert resp.json()['sheet_name']=='AlphaOrders'
    print(f'✓ Created Template A (AlphaOrders, 6 cols) id={tid_a}')
    
    # Template B: DIFFERENT columns, DIFFERENT order, DIFFERENT sheet name
    mappings_b={'project_name':'A','company':'B','contact_name':'C','window_name':'D','product_id':'E','quantity':'F','panel_count':'G','delivered':'H'}
    resp=staff.post('/api/operations/provider-templates',json={
        'provider_id':pid_b,'name':'Beta Template','sheet_name':'BetaProduction','column_mappings':mappings_b})
    assert resp.status_code==200,f'Create template B failed: {resp.text}'
    tid_b=resp.json()['id']
    assert resp.json()['sheet_name']=='BetaProduction'
    print(f'✓ Created Template B (BetaProduction, 8 cols) id={tid_b}')
    
    # Invalid mapping (unknown field) should be rejected
    resp=staff.post('/api/operations/provider-templates',json={
        'provider_id':pid_a,'name':'Bad Template','sheet_name':'Bad','column_mappings':{'invalid_field':'A'}})
    assert resp.status_code==422,'Invalid field should be rejected'
    print('✓ Invalid field mapping rejected')
    
    # Empty mappings should be rejected
    resp=staff.post('/api/operations/provider-templates',json={
        'provider_id':pid_a,'name':'Empty Template','sheet_name':'Empty','column_mappings':{}})
    assert resp.status_code==422,'Empty mappings should be rejected'
    print('✓ Empty column mappings rejected')
    
    # Assign Provider A + Template A to first order
    orders_list=staff.get('/api/operations/orders').json()
    oid1=orders_list[0]['id']
    resp=staff.post(f'/api/operations/orders/{oid1}/assign-provider',json={'provider_id':pid_a,'template_id':tid_a,'is_preferred':True})
    assert resp.status_code==200
    print(f'✓ Assigned Provider A + Template A to order {oid1}')
    
    # Re-login portal (was logged out earlier in test) and create second order for Provider B testing
    token=post(portal,'portal/login',{'username':'customerA','password':'test-password'})['token']
    portal.headers['Authorization']='Bearer '+token
    project2={'project_name':'Test Project 2','site_address':'789 Site Ave','submission_key':'test-sub-002',
             'lines':[{'window_name':'Office','product_id':1,'width_mm':1800,'height_mm':2100,'quantity':1,'panel_count':2,'options':{}}]}
    post(portal,'portal/orders',project2)
    oid2=portal.get('/api/portal/orders').json()[-1]['id']
    post(staff,f'operations/orders/{oid2}/review')
    post(staff,f'operations/orders/{oid2}/deposit-received')
    resp=staff.post(f'/api/operations/orders/{oid2}/assign-provider',json={'provider_id':pid_b,'template_id':tid_b,'is_preferred':True})
    assert resp.status_code==200
    print(f'✓ Assigned Provider B + Template B to order {oid2}')
    
    # Cannot assign inactive provider
    resp=staff.post(f'/api/operations/orders/{oid1}/assign-provider',json={'provider_id':inactive_pid,'template_id':None})
    assert resp.status_code==404,'Inactive provider should be rejected'
    print('✓ Inactive provider assignment blocked')
    
    # Export order 1 with Template A: validate AlphaOrders sheet with 6 specific columns
    import openpyxl,io
    resp=staff.get(f'/api/operations/orders/{oid1}/supplier-export')
    assert resp.status_code==200,f'Template A export failed: {resp.status_code} {resp.text}'
    wb_a=openpyxl.load_workbook(io.BytesIO(resp.content))
    assert 'AlphaOrders' in wb_a.sheetnames,'Template A sheet name AlphaOrders'
    ws_a=wb_a['AlphaOrders']
    assert ws_a['A1'].value=='order_id','Template A col A = order_id'
    assert ws_a['B1'].value=='window_name','Template A col B = window_name'
    assert ws_a['C1'].value=='width_mm','Template A col C = width_mm'
    assert ws_a['D1'].value=='height_mm','Template A col D = height_mm'
    assert ws_a['E1'].value=='quantity','Template A col E = quantity'
    assert ws_a['F1'].value=='arrived','Template A col F = arrived'
    assert ws_a['G1'].value is None,'Template A has only 6 columns'
    assert ws_a['A2'].value is not None,'Data row exists'
    print('✓ Provider A export: AlphaOrders sheet, 6 columns (order_id, window_name, width_mm, height_mm, quantity, arrived), data validated')
    
    # Export order 2 with Template B: validate BetaProduction sheet with 8 DIFFERENT columns
    resp=staff.get(f'/api/operations/orders/{oid2}/supplier-export')
    assert resp.status_code==200,f'Template B export failed: {resp.status_code} {resp.text}'
    wb_b=openpyxl.load_workbook(io.BytesIO(resp.content))
    assert 'BetaProduction' in wb_b.sheetnames,'Template B sheet name BetaProduction'
    ws_b=wb_b['BetaProduction']
    assert ws_b['A1'].value=='project_name','Template B col A = project_name (DIFFERENT from Template A)'
    assert ws_b['B1'].value=='company','Template B col B = company (DIFFERENT from Template A)'
    assert ws_b['C1'].value=='contact_name','Template B col C = contact_name (DIFFERENT from Template A)'
    assert ws_b['D1'].value=='window_name','Template B col D = window_name (DIFFERENT position)'
    assert ws_b['E1'].value=='product_id','Template B col E = product_id (DIFFERENT from Template A)'
    assert ws_b['F1'].value=='quantity','Template B col F = quantity (DIFFERENT position)'
    assert ws_b['G1'].value=='panel_count','Template B col G = panel_count (NOT in Template A)'
    assert ws_b['H1'].value=='delivered','Template B col H = delivered (NOT in Template A)'
    assert ws_b['A2'].value is not None,'Data row exists'
    print('✓ Provider B export: BetaProduction sheet, 8 columns (project_name, company, contact_name, window_name, product_id, quantity, panel_count, delivered), COMPLETELY DIFFERENT from Provider A, data validated')
    
    # Export for inactive provider should fail
    resp=staff.get(f'/api/operations/orders/{oid1}/supplier-export?provider_id={inactive_pid}')
    assert resp.status_code==404,'Cannot export for inactive provider'
    print('✓ Inactive provider export blocked')
    
    # Create third order without provider assignment for fallback testing
    project3={'project_name':'Unassigned Project','site_address':'999 Site Ave','submission_key':'test-sub-003',
             'lines':[{'window_name':'Garage','product_id':1,'width_mm':1600,'height_mm':1900,'quantity':1,'panel_count':1,'options':{}}]}
    post(portal,'portal/orders',project3)
    oid3=portal.get('/api/portal/orders').json()[-1]['id']
    post(staff,f'operations/orders/{oid3}/review')
    post(staff,f'operations/orders/{oid3}/deposit-received')
    resp=staff.get(f'/api/operations/orders/{oid3}/supplier-export')
    assert resp.status_code==422,'Should require template or explicit fallback'
    print('✓ Export without template requires explicit fallback flag (422)')
    
    # Basic fallback with flag: clearly labeled filename
    resp=staff.get(f'/api/operations/orders/{oid3}/supplier-export?allow_basic_fallback=true')
    assert resp.status_code==200,'Basic fallback with flag should work'
    assert 'BASIC-NOT-VERIFIED' in resp.headers['content-disposition'],'Filename must indicate BASIC-NOT-VERIFIED'
    wb_basic=openpyxl.load_workbook(io.BytesIO(resp.content))
    assert 'Project' in wb_basic.sheetnames,'Basic fallback uses Project sheet (different from both custom templates)'
    print('✓ Basic fallback: BASIC-NOT-VERIFIED filename, Project sheet (generic, not supplier-specific)')
    
    print('PASS provider management: two providers with DIFFERENT templates (AlphaOrders 6-col vs BetaProduction 8-col), validated DIFFERENT headers/columns/sheet names, invalid mapping rejected, inactive provider blocked, basic fallback clearly labeled')

    for mapping in [{'order_id':'INVALID!'}, {'order_id':'XFE'}, {'order_id':'A','window_name':'A'}]:
        assert staff.post('/api/operations/provider-templates',json={'provider_id':pid_a,'name':'Invalid','sheet_name':'Valid','column_mappings':mapping}).status_code==422
    for name in ['Bad/Sheet', 'a'*32, "'Bad", 'Bad\x01']:
        assert staff.post('/api/operations/provider-templates',json={'provider_id':pid_a,'name':'Invalid','sheet_name':name,'column_mappings':{'order_id':'A'}}).status_code==422
    config={'provider_id':pid_a,'name':'Sparse','sheet_name':'A & "B"','column_mappings':{'order_id':'C','window_name':'AA','quantity':'Z'}}
    template=post(staff,'operations/provider-templates',config)
    post(staff,f'operations/orders/{oid1}/assign-provider',{'provider_id':pid_a,'template_id':template['id']})
    response=staff.get(f'/api/operations/orders/{oid1}/supplier-export')
    sheet=openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert sheet.title=='A & "B"'
    assert sheet['A1'].value is None and sheet['C1'].value=='order_id' and sheet['Z1'].value=='quantity' and sheet['AA1'].value=='window_name'
    assert sheet['C2'].value==oid1 and isinstance(sheet['Z2'].value,int)
    print('PASS sparse C/Z/AA placement, numeric cells, XML names, invalid/duplicate/out-of-range columns')
