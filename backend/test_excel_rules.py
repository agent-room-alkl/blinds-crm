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
from excel_rules import parse_template,calculate_line,workbook,column

CODES=['Shutters_PVC','Shutters_PVC_Eco','Shutters_Pinewood','Shutters_Basswood','Shutters_Aluminium',
       'Roller_Blinds_BO_VIBE','Roller_Blinds_BO_LeReve','Roller_Blinds_BO_Skye','Roller_Blinds_BO_Karma','Roller_Blinds_BO_Mantra',
       'Roller_Blinds_Sunscreen','Roller_Blinds_LF_LeReve','Roller_Blinds_LF_Skye','Roller_Blinds_LF_Mantra',
       'Venetian_Blinds_PVC','Venetian_Blinds_Wood','Venetian_Blinds_Aluminium_25mm','Venetian_Blinds_Aluminium_50mm',
       'Vertical_Blinds_VIBE_89mm','Vertical_Blinds_VIBE_100mm','Vertical_Blinds_Karma_89mm','Exterior_Blinds_Mesh','Exterior_Blinds_ClearPVC']


def fixture():
    """Entirely invented price values; recognizable template layout only."""
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    cells={name:{} for name in ['Product Listing','Pricing','Order','In Put']}
    names={}
    for n,code in enumerate(CODES,2):
        cells['Product Listing']['A'+str(n)]=code
        cells['Product Listing']['B'+str(n)]='White TEST'
        names[code]="'Product Listing'!$B$"+str(n)
        if n<=6:
            cells['Pricing']['A'+str(483+n)]=code
            cells['Pricing']['B'+str(483+n)]='100'
        else:
            names[code+'_w']='Pricing!$B$1:$C$1';names[code+'_h']='Pricing!$A$2:$A$3';names[code+'_Price']='Pricing!$B$2:$C$3'
        cells['Pricing']['A'+str(489+n)]=code
        cells['Pricing']['B'+str(489+n)]='10'
    cells['Product Listing']['B101']='In Fit';names['Fitting']="'Product Listing'!$B$101"
    for col in range(2,10):cells['Product Listing'][column(col)+'102']=str(Decimal(col-1)/20)
    cells['Pricing'].update({'B1':'500','C1':'1000','A2':'500','A3':'1000','B2':'100','C2':'150','B3':'200','C3':('ROUNDUP(B2*1.35,0)','0')})
    cells['In Put'].update({'Q33':('(Q31+N(Q32))*0.15',None),'Q32':('IF(Order!I4,MAX(SUM(Order!X8:X500),150),"Supply Only")',None)})
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        wb=ET.Element('workbook',xmlns=ns);sh=ET.SubElement(wb,'sheets')
        rel=ET.Element('Relationships',xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        for i,(name,values) in enumerate(cells.items(),1):
            ET.SubElement(sh,'sheet',{'name':name,'sheetId':str(i),'{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id':'r'+str(i)})
            ET.SubElement(rel,'Relationship',Id='r'+str(i),Target='worksheets/sheet'+str(i)+'.xml')
            sheet=ET.Element('worksheet',xmlns=ns);data=ET.SubElement(sheet,'sheetData')
            for ref,val in values.items():
                row=ET.SubElement(data,'row',r='1');cell=ET.SubElement(row,'c',r=ref)
                if isinstance(val,tuple):
                    ET.SubElement(cell,'f').text=val[0]
                    if val[1] is not None:ET.SubElement(cell,'v').text=val[1]
                else:
                    cell.set('t','inlineStr'); inline=ET.SubElement(cell,'is');ET.SubElement(inline,'t').text=val
            z.writestr('xl/worksheets/sheet'+str(i)+'.xml',ET.tostring(sheet))
        defs=ET.SubElement(wb,'definedNames')
        for name,target in names.items():ET.SubElement(defs,'definedName',name=name).text=target
        z.writestr('xl/workbook.xml',ET.tostring(wb));z.writestr('xl/_rels/workbook.xml.rels',ET.tostring(rel))
    return out.getvalue()


raw=fixture();rules=parse_template(raw)
assert len(rules['products'])==23
matrix=rules['products'][5]
assert matrix['matrix'][1][1]=='135' # recomputed from formula, not bogus cached 0
line=dict(width_mm='501',height_mm='501',quantity=1,panel_count=2,options={'colour':'White TEST','fitting':'In Fit'})
assert calculate_line(matrix,line)['amount']=='135.00'
shutter=rules['products'][0]
assert calculate_line(shutter,{**line,'width_mm':'501','height_mm':'1000'})['area']=='0.51'
assert calculate_line(shutter,{**line,'width_mm':'100','height_mm':'100'})['amount']=='50.00'
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
    profile=post(staff,'operations/customers',dict(company='TEST only',contact_name='Test contact',email='test@example.invalid',phone='123',company_address='Company',username='testclient',password='test-password'))
    customer.headers['Authorization']='Bearer '+post(customer,'portal/login',{'username':'testclient','password':'test-password'})['token']
    post(customer,'operations/template-import',{'filename':'test.xlsm','content_base64':base64.b64encode(raw).decode()},401)
    imported=post(staff,'operations/template-import',{'filename':'test.xlsm','content_base64':base64.b64encode(raw).decode()})
    assert imported['products_count']==23
    # Idempotent import keeps all product identifiers stable.
    before=customer.get('/api/portal/catalog').json()['products']
    post(staff,'operations/template-import',{'filename':'test.xlsm','content_base64':base64.b64encode(raw).decode()})
    after=customer.get('/api/portal/catalog').json()['products']
    assert [(p['id'],p['source_code']) for p in before]==[(p['id'],p['source_code']) for p in after]
    assert len(staff.get('/api/products').json())==5
    assert len(after)==24 and all('matrix' not in str(p.get('price_rule',{})) for p in after if p.get('source_code','').startswith('Shutters'))
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
    post(staff,'operations/fulfilment',dict(order_id=oid,kind='delivery',operation_key='TEST-delivery',lines=[dict(line_id='1',quantity=1)]))
    invoice=post(staff,'operations/settlements',dict(order_ids=[oid],operation_key='TEST-balance',rules_evidence='TEST fully delivered approval',billing_basis='fully_delivered_remaining_total'))
    post(staff,f"operations/invoices/{invoice['id']}/received",{'note':'TEST received manually'})
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
