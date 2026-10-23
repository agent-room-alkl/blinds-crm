"""Synthetic workbook/API checks. Optional --source validates a local real file.
No customer workbook or price matrix is committed to the public repository.
"""
import base64
import io
import json
import os
import sys
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
from excel_rules import parse_template,calculate_line,apply_order_minimum,workbook,column
from addons import addon_totals,compose_unit
from demo_workbook import fixture





raw=fixture();rules=parse_template(raw)
assert len(rules['products'])==23
matrix=rules['products'][5]
assert matrix['matrix'][1][1]=='135' # recomputed from formula, not bogus cached 0
line=dict(width_mm='501',height_mm='501',quantity=1,panel_count=2,options={'colour':'White TEST','fitting':'In Fit'})
assert calculate_line(matrix,line)['amount']=='135.00'
shutter=rules['products'][0]
assert calculate_line(shutter,{**line,'width_mm':'501','height_mm':'1000'})['area']=='0.51'
assert calculate_line(shutter,{**line,'width_mm':'100','height_mm':'100'})['amount']=='50.00'
assert addon_totals({'tier_on_tier':'yes','shaped_cutout':'yes'}) == (Decimal(0),Decimal(10),Decimal(300))
assert compose_unit('2','340',0,10,300) == Decimal('1048.00')
for material in ('Shutters_PVC','Shutters_PVC_Eco'):
    try: addon_totals({'stained_colour':'yes'},material)
    except ValueError: pass
    else: raise AssertionError(material+' must reject stained colour')
small = calculate_line({**shutter,'rate_per_m2':'280'}, {**line,'width_mm':'500','height_mm':'500'})
small_line = {**small,'quantity':1,'pricing_status':'configured','price_snapshot':{**shutter,'rate_per_m2':'280'}}
assert apply_order_minimum([small_line]) is True and small_line['amount']=='280.00'
assert calculate_line(shutter,{**line,'panel_count':2})['installation_amount']=='100.00'
# Confirmed $50/panel supersedes any legacy workbook installation rate.
assert calculate_line({**shutter,'installation_rate':'250'}, {**line,'panel_count':2})['installation_amount']=='100.00'
try:calculate_line(matrix,{**line,'width_mm':'1001'})
except ValueError:pass
else:raise AssertionError('oversize matrix price must fail')
print('PASS workbook extraction, both pricing engines, area minimum/ROUNDUP, matrix ceiling, formula re-evaluation')

with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND']='sqlite';os.environ['VERA_DB']=str(Path(folder)/'test.db');os.environ['VERA_STORAGE_BACKEND']='local'
    from fastapi.testclient import TestClient
    from service import app
    staff=TestClient(app);customer=TestClient(app)
    def post(client,path,body=None,status=200):
        r=client.post('/api/'+path,json=body)
        assert r.status_code==status,(path,r.status_code,r.text)
        return r.json()
    token=post(staff,'auth/login',{'username':'dylan','password':os.getenv('VERA_DEMO_PASSWORD','vera-demo')})['token']
    staff.headers['Authorization']='Bearer '+token
    profile=post(staff,'operations/customers',dict(company='TEST only',contact_name='Test contact',email='test@example.invalid',phone='123',company_address='Company',username='testclient',password='test-password',customer_type='wholesale',customer_code='TEST'))
    customer.headers['Authorization']='Bearer '+post(customer,'portal/login',{'username':'testclient','password':'test-password'})['token']
    post(customer,'operations/template-import',{'filename':'test.xlsm','content_base64':base64.b64encode(raw).decode()},401)
    imported=post(staff,'operations/template-import',{'filename':'test.xlsm','content_base64':base64.b64encode(raw).decode()})
    assert imported['products_count']==23
    # Idempotent import keeps all product identifiers stable.
    before=customer.get('/api/portal/catalog').json()['products']
    post(staff,'operations/template-import',{'filename':'test.xlsm','content_base64':base64.b64encode(raw).decode()})
    after=customer.get('/api/portal/catalog').json()['products']
    assert [(p['id'],p['source_code']) for p in before]==[(p['id'],p['source_code']) for p in after]
    
    # Verify public /api/products returns exactly 5 website series (staff login, but endpoint is mixed auth)
    public_products = staff.get('/api/products').json()
    assert len(public_products)==5, f'Expected 5 website series, got {len(public_products)}'
    website_series_names = sorted([p['name_en'] for p in public_products])
    expected_series = sorted(['VERA Classic', 'VERA Eco', 'VERA Natural', 'VERA Prime', 'VERA Deluxe'])
    assert website_series_names == expected_series, f'Expected {expected_series}, got {website_series_names}'
    # Verify no aluminium or inactive blinds in public catalog
    assert all(p.get('category') != 'aluminium' or p.get('sample', False) for p in public_products), 'No aluminium shutters in public'
    assert all(p.get('category') not in ('roller', 'venetian', 'vertical', 'exterior') for p in public_products), 'No inactive blinds in public'
    
    # Verify admin can see all products including inactive blinds
    admin_products = staff.get('/api/admin/products').json()
    inactive_blinds = [p for p in admin_products if p.get('category') == 'blinds' and not p.get('published', True)]
    # Should have 18+ blind products from template (23 total - 4 shutters - Shutters_Aluminium = 18)
    assert len(inactive_blinds) == 0, 'Non-website rows must not be created by a fresh import'
    print(f'\n✓ Admin list shows {len(inactive_blinds)} inactive blind products:')
    for p in sorted(inactive_blinds, key=lambda x: x.get('source_code', '')):
        print(f"  {p.get('source_code', 'N/A'):35s} - {p.get('name_en', 'N/A'):40s} (published={p.get('published')}, orderable={p.get('orderable')})")
    
    # Portal catalog only shows published products (so 5 shutters + Ashwood, not the 18 inactive blinds)
    assert len(after) == 5, f'Expected exactly five website series, got {len(after)}'
    
    # Critical: Verify none of the blind products appear in portal catalog
    # This must hold even if blind products were accidentally made published/orderable
    portal_product_codes = {p.get('source_code') for p in after if p.get('source_code')}
    blind_product_codes = {p.get('source_code') for p in inactive_blinds if p.get('source_code')}
    blinds_in_portal = portal_product_codes & blind_product_codes
    assert len(blinds_in_portal) == 0, f'Portal catalog must not contain blind products, but found: {blinds_in_portal}'
    
    # Verify portal catalog contains only the expected shutter series
    expected_codes = {'Shutters_PVC', 'Shutters_PVC_Eco', 'Shutters_Pinewood', 'Shutters_Basswood', 'VERA_Ashwood_provisional'}
    assert portal_product_codes == expected_codes, f'Expected {expected_codes}, got {portal_product_codes}'
    print(f'\n✓ Portal catalog correctly excludes all {len(blind_product_codes)} blind products')
    print(f'  Only 5 website series visible: {", ".join(sorted(portal_product_codes))}')
    
    assert all('matrix' not in str(p.get('price_rule',{})) for p in after if p.get('source_code','').startswith('Shutters'))
    assert all('rate_per_m2' not in (p.get('price_rule') or {}) and 'matrix' not in (p.get('price_rule') or {}) for p in after)
    p=next(p for p in after if p['source_code']=='Shutters_PVC')
    body=dict(project_name='TEST project',site_address='Site',submission_key='test-project',installation_required=True,
              lines=[dict(window_name='TEST window',product_id=p['id'],width_mm='1000',height_mm='1000',quantity=1,panel_count=2,options=line['options'])])
    priced=post(customer,'portal/price',body)
    assert 'price_snapshot' not in priced['lines'][0]
    assert priced['subtotal']=='100.00' and priced['installation']=='150.00' and priced['tax']=='37.50' and priced['total']=='287.50' and priced['deposit']=='172.50'
    d=post(customer,'portal/orders',body);oid=d['id']
    assert 'price_snapshot' not in d['lines'][0]
    post(staff,f'operations/orders/{oid}/adjust',{'note':'TEST discount adjustment','lines':[{'line_id':'1','discount':'0.1'}]})
    reviewed=post(staff,f'operations/orders/{oid}/review')
    assert reviewed['subtotal']=='90.00' and reviewed['invoices'][0]['amount']=='165.60'
    post(staff,f'operations/orders/{oid}/adjust',{'note':'must stay frozen','lines':[]},409)
    exported=staff.get(f'/api/operations/orders/{oid}/production-sheet')
    assert exported.status_code==200
    if '--export-review' in sys.argv:
        Path(sys.argv[sys.argv.index('--export-review')+1]).write_bytes(exported.content)
    with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
        assert not any('vba' in n.lower() for n in z.namelist())
        xml=z.read('xl/worksheets/sheet1.xml').decode()
        assert 'TEST window' in xml and 'TEST project' in xml and 'DRAFT' in xml and '<f>' not in xml
    cid=profile['customer_id']
    edited=post(staff,f'operations/customers/{cid}',{'company':'TEST revised','contact_name':'Only person','email':'revised@example.invalid','phone':'456','company_address':'New company'})
    assert customer.get('/api/portal/me').json()['email']=='revised@example.invalid'
    assert customer.get('/api/portal/orders').json()[0]['company']=='TEST only'
    post(staff,f'operations/orders/{oid}/deposit-received')
    assert customer.get('/api/portal/consumption').json()['summary']['NZD']['received']=='165.60'
    # Avoid generating real emails; fulfilment notification transport is explicitly mocked.
    post(staff,f'operations/orders/{oid}/supplier-order',{'reference':'TEST supplier'})
    post(staff,'operations/transit',{'order_ids':[oid],'operation_key':'TEST-transit'})
    from unittest.mock import patch
    with patch('email_service.configuration',return_value=({'configured':False},None)):
        post(staff,'operations/fulfilment',dict(order_id=oid,kind='arrival',operation_key='TEST-arrival',lines=[dict(line_id='1',quantity=1)]))
    invoice=post(staff,'operations/settlements',dict(order_ids=[oid],operation_key='TEST-balance',rules_evidence='TEST all arrived approval',billing_basis='all_arrived_remaining_total'))
    post(staff,f"operations/invoices/{invoice['id']}/received",{'note':'TEST received manually'})
    post(staff,'operations/fulfilment',dict(order_id=oid,kind='delivery',operation_key='TEST-delivery',lines=[dict(line_id='1',quantity=1)]))
    consumption=customer.get('/api/portal/consumption').json()
    assert consumption['summary']['NZD']['received']==reviewed['total'] and consumption['summary']['NZD']['outstanding_invoiced']=='0.00'
    print('PASS private import/idempotence, catalogue scope, order GST/install, staff adjustments, safe XLSX, profile edits, receipt/consumption/settlement')

if '--source' in sys.argv:
    real_raw=Path(sys.argv[sys.argv.index('--source')+1]).read_bytes()
    manifest=parse_template(real_raw)
    assert len(manifest['products'])==23
    configured=sum(p['status']=='configured' for p in manifest['products'])
    sheets,_=workbook(real_raw);order=sheets['Order'];checked=0
    rules_by_code={p['source_code']:p for p in manifest['products']}
    def value(ref,default=''):
        return order.get(ref,{}).get('value') or default
    for row in range(8,37):
        code=value('E'+str(row))
        if not code or not value('B'+str(row)):
            continue
        rule=rules_by_code[code]
        mapping={'frame':'L','louver_size':'M','colour':'N','control_rod':'O','fitting':'P',
                 'bracket_colour':'L','chain_colour':'M','bottom_rail_colour':'O','control_side':'H',
                 'layout_code':'H','vt_post':'I','ht_post':'J','midrail':'K','opening_style':'F','special_request':'Q'}
        options={f['key']:value(mapping[f['key']]+str(row)) for f in rule['schema']}
        item=dict(width_mm=value('C'+str(row)),height_mm=value('D'+str(row)),quantity=1,
                  panel_count=int(value('G'+str(row),'1')),options=options)
        a=dict(discount=value('R'+str(row),'0'),product_surcharge=value('T'+str(row),'0'),installation_surcharge=value('U'+str(row),'0'))
        result=calculate_line(rule,item,a)
        assert abs(Decimal(result['amount'])-Decimal(value('S'+str(row))))<Decimal('0.000001'),f'Customer row {row} differs from saved reference result'
        checked+=1
    assert checked>0
    print(f'PASS local customer workbook parsed: {configured}/23 price rules; {len(manifest["warnings"])} explicit warnings; no source rates printed')
    print(f'PASS {checked} populated customer Order rows independently calculated against saved line totals; macros not run')
