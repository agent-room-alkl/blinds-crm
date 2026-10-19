"""Build the single LOCAL review database from the supplied workbook. Never writes PostgreSQL.
Real contacts and private rates stay in the database; generated orders are explicitly simulations.
Run: python backend/seed_current.py --workbook <path> --database backend/vera.db
Existing databases are refused. This script never deletes other databases.
"""
import argparse,os,json,base64
from pathlib import Path

def main():
 root=Path(__file__).resolve().parent
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workbook',type=Path,required=True);p.add_argument('--database',type=Path,default=root/'vera.db');a=p.parse_args()
 target=a.database.resolve();source=a.workbook.resolve()
 if target.parent!=root or target.suffix!='.db':raise SystemExit('Target must be one .db file directly inside backend')
 if target.exists():raise SystemExit('Refusing to overwrite existing database')
 from excel_rules import workbook
 raw=source.read_bytes();sheets,_=workbook(raw);cells=sheets['In Put']
 value=lambda c:str(cells.get(c,{}).get('value') or '').strip()
 people={}
 for row in range(7,26):
  company=value('B'+str(row))
  if company:people.setdefault(company,dict(company=company,contact_name=value('C'+str(row)),phone=value('D'+str(row)),email=value('E'+str(row)),source_code=value('F'+str(row)),source_row=row))
 if len(people)!=19:raise SystemExit('Expected 19 unique customer companies in source')
 images=json.loads((root/'website_products.json').read_text(encoding='utf-8'));allowed=set(images)
 os.environ.update(VERA_DB_BACKEND='sqlite',VERA_DB=str(target),VERA_STORAGE_BACKEND='local',SMTP_HOST='',SMTP_FROM='',SMTP_USER='',SMTP_PASSWORD='',VERA_DEMO_PASSWORD='vera-demo')
 from service import app,db,dump,now
 from fastapi.testclient import TestClient
 staff=TestClient(app)
 def post(client,path,body=None):
  r=client.post('/api/'+path,json=body)
  if r.status_code!=200:raise RuntimeError(path+': '+str(r.status_code)+' '+r.text)
  return r.json()
 staff.headers['Authorization']='Bearer '+post(staff,'auth/login',{'username':'dylan','password':'vera-demo'})['token']
 imported=post(staff,'operations/template-import',{'filename':source.name,'content_base64':base64.b64encode(raw).decode()})
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  for row in c.execute('SELECT id,data FROM products').fetchall():
   item=json.loads(row['data']);code=item.get('source_code')
   if code not in allowed:c.execute('DELETE FROM products WHERE id=?',(row['id'],));continue
   item.update(name_en={'Shutters_PVC_Eco':'VERA Eco','Shutters_PVC':'VERA Classic','Shutters_Pinewood':'VERA Natural','Shutters_Basswood':'VERA Prime','VERA_Ashwood_provisional':'VERA Deluxe'}[code],image_urls=[images[code]['local']],image_url=images[code]['local'],content_source=images[code]['source'],published=True,portal_only=False)
   item['name_zh']=item['name_en'];c.execute('UPDATE products SET data=? WHERE id=?',(dump(item),row['id']))
 clients=[];profiles=[]
 for index,person in enumerate(people.values()):
  code=person['source_code'] or str(index+1);username='demo-trade' if index==0 else 'trade-'+code.lower()
  profile=post(staff,'operations/customers',dict(company=person['company'],contact_name=person['contact_name'] or '未提供联系人',phone=person['phone'],email=person['email']) | dict(company_address='待补充（Excel未提供有效地址）',username=username,password='local-demo-only'))
  with db() as c:c.execute('UPDATE customers SET notes=? WHERE id=?',(dump({'source_sheet':'In Put','source_row':person['source_row'],'source_code':code,'data_kind':'workbook_contact','address_missing':True}),profile['customer_id']))
  client=TestClient(app);client.headers['Authorization']='Bearer '+post(client,'portal/login',{'username':username,'password':'local-demo-only'})['token'];clients.append(client);profiles.append(profile)
 # Payment/quote issuers are facts, but their role as factory supplier is not established.
 for name,ref in [(value('E33'),'In Put!E33'),(value('C48'),'In Put!C48')]:
  provider=post(staff,'operations/providers',dict(name=name,contact_email='',notes='Excel模板付款/报价出具方；工厂供应商角色待确认。来源 '+ref))
  post(staff,'operations/providers/'+str(provider['id']),dict(name=name,contact_email='',notes='Excel模板付款/报价出具方；工厂供应商角色待确认。来源 '+ref,active=False))
 catalog=clients[0].get('/api/portal/catalog').json()['products'];bycode={x['source_code']:x for x in catalog}
 ordercells=sheets['Order'];v=lambda c:str(ordercells.get(c,{}).get('value') or '').strip()
 fieldcols={'opening_style':'F','layout_code':'H','vt_post':'I','ht_post':'J','midrail':'K','frame':'L','louver_size':'M','colour':'N','control_rod':'O','fitting':'P','special_request':'Q'}
 lines=[]
 for row in range(8,17):
  product=bycode[v('E'+str(row))];options={key:v(col+str(row)) for key,col in fieldcols.items() if v(col+str(row))}
  lines.append(dict(window_name=v('B'+str(row)),product_id=product['id'],width_mm=v('C'+str(row)),height_mm=v('D'+str(row)),quantity=1,panel_count=int(v('G'+str(row))),options=options))
 titles=['待审核','定金待收','待供应商确认','运输中','分批到货','已交付','待提货'];created=[]
 for n,title in enumerate(titles):
  # All lifecycle events below are local simulations, not statements about real customer orders.
  order=post(clients[n%3],'portal/orders',dict(project_name='模拟 / AA-Sterling / '+title,site_address='地址待补充（模拟订单）',submission_key='local-simulation-'+str(n),installation_required=False,lines=lines));oid=order['id'];created.append(oid)
  if n==0:continue
  reviewed=post(staff,f'operations/orders/{oid}/review')
  if n==1:continue
  post(staff,f'operations/orders/{oid}/deposit-received')
  if n==2:continue
  post(staff,f'operations/orders/{oid}/supplier-order',{'reference':'SIMULATED-NOT-SENT-'+str(n)})
  post(staff,'operations/transit',{'order_ids':[oid],'operation_key':'simulation-transit-'+str(n)})
  if n==3:continue
  quantities=[{'line_id':str(i+1),'quantity':1} for i in range(len(lines))]
  post(staff,'operations/fulfilment',dict(order_id=oid,kind='arrival',operation_key='simulation-arrival-'+str(n),lines=quantities[:3] if n==4 else quantities))
  if n==5:post(staff,'operations/fulfilment',dict(order_id=oid,kind='delivery',operation_key='simulation-delivery-'+str(n),lines=quantities))
 with db() as c:
  marker={'id':'local-current:v1','source_workbook':source.name,'customer_count':len(people),'simulated_order_ids':created,'missing':['客户有效地址','部分客户联系人/邮箱','确认工厂供应商身份','Deluxe正式费率'],'outbound_email':'disabled','created_at':now()}
  c.execute('INSERT INTO operations_records VALUES(?,?,?,?)',(marker['id'],'local_dataset',None,dump(marker)))
  count=c.execute('SELECT COUNT(*) FROM products').fetchone()[0];assert count==5
 print('Created canonical local DB:',target)
 print('19 workbook customers; 2 inactive issuer candidates; 5 website products; 7 explicitly simulated orders; outbound email disabled')
if __name__=='__main__':main()
