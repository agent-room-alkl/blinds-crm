"""Seed current-feature samples in backend/.demo only. Never writes PostgreSQL.

Run: python backend/seed_demo.py
The existing marked demo is reused; unrelated/existing databases are refused.
"""
import argparse
import json
import os
from pathlib import Path
from datetime import timedelta


def main():
    root=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=root/'.demo'/'vera-demo.db')
    args=parser.parse_args();target=args.database.resolve();allowed=(root/'.demo').resolve()
    if not target.is_relative_to(allowed) or target.suffix!='.db':
        raise SystemExit('Demo database must be a .db file inside backend/.demo')
    if target.exists():
        import sqlite3
        with sqlite3.connect(target) as c:
            exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='operations_records'").fetchone()
            marker=c.execute("SELECT 1 FROM operations_records WHERE id='demo-seed:v1'").fetchone() if exists else None
        if not marker:
            raise SystemExit('Refusing an existing database without this demo marker')
        print('Existing marked demo reused:',target)
        return
    os.environ.update(VERA_DB_BACKEND='sqlite',VERA_DB=str(target),VERA_STORAGE_BACKEND='local',
                      VERA_DEMO_PASSWORD='vera-demo',SMTP_HOST='',SMTP_FROM='')
    target.parent.mkdir(parents=True,exist_ok=True)
    from service import app,db,dump,business_now
    from fastapi.testclient import TestClient
    staff=TestClient(app)
    def post(client,path,body=None):
        response=client.post('/api/'+path,json=body)
        if response.status_code!=200:
            raise RuntimeError(path+': '+str(response.status_code)+' '+response.text)
        return response.json()
    token=post(staff,'auth/login',{'username':'dylan','password':'vera-demo'})['token']
    staff.headers['Authorization']='Bearer '+token
    post(staff,'operations/pricing-knowledge/initialize-default',{})
    clients=[];profiles=[]
    for i,company in enumerate(['DEMO North Studio','DEMO Harbour Trade','DEMO South Projects'],1):
        username='demo-trade' if i==1 else 'demo-trade-'+str(i)
        profiles.append(post(staff,'operations/customers',dict(company=company,contact_name='Demo buyer '+str(i),
                         email=f'demo-{i}@example.invalid',phone='000 000 00'+str(i),company_address=f'DEMO {i} Example Road, Auckland',
                         username=username,password='local-demo-only',customer_type='wholesale',customer_code=f'DEMO{i}')))
        client=TestClient(app);client.headers['Authorization']='Bearer '+post(client,'portal/login',{'username':username,'password':'local-demo-only'})['token']
        clients.append(client)
    catalog=clients[0].get('/api/portal/catalog').json()['products']
    pid=next(p['id'] for p in catalog if p.get('source_code')=='Shutters_PVC')
    names=['DEMO City Apartment','DEMO Coastal Renovation','DEMO Office Fit-out','DEMO Terrace Homes','DEMO Staged Delivery','DEMO Completed Project','DEMO Ready for Collection']
    created=[]
    for n,name in enumerate(names):
        order=post(clients[n%3],'portal/orders',dict(project_name=name,site_address=f'DEMO Site {n+1}, Example Street',
                   submission_key='demo-project-'+str(n+1),installation_required=n==1,
                   lines=[dict(window_name='Bedroom 01',product_id=pid,width_mm='1200',height_mm='1500',quantity=3,panel_count=2,options={'colour':'White TEST','fitting':'In Fit','opening_style':'Hinged'}),
                          dict(window_name='Living 02',product_id=pid,width_mm='1000',height_mm='800',quantity=2,panel_count=2,options={'colour':'White TEST','fitting':'In Fit','opening_style':'Hinged'})]))
        oid=order['id'];created.append(oid)
        if n==0:continue
        order=post(staff,f'operations/orders/{oid}/review')
        if n==1:
            post(staff,f"operations/invoices/{order['invoices'][0]['id']}/send")
            continue
        post(staff,f'operations/orders/{oid}/deposit-received')
        post(staff,f'operations/orders/{oid}/supplier-order',{'reference':'DEMO-SUP-'+str(n+1)})
        if n==2:continue
        post(staff,'operations/transit',{'order_ids':[oid],'operation_key':'demo-transit-'+str(n+1)})
        if n==3:continue
        arrival=[{'line_id':'1','quantity':3},{'line_id':'2','quantity':2}]
        post(staff,'operations/fulfilment',dict(order_id=oid,kind='arrival',operation_key='demo-arrival-'+str(n+1),lines=arrival))
        if n==5:
            month=(business_now().date().replace(day=1)-timedelta(days=1)).strftime('%Y-%m')
            post(staff,'operations/rebates',dict(customer_id=profiles[n%3]['customer_id'],source_order_ids=[oid],month=month,amount='35',evidence='DEMO confirmed opening credit; invented data',currency='NZD'))
            inv=post(staff,'operations/settlements',dict(order_ids=[oid],operation_key='demo-balance',rules_evidence='DEMO all-arrived settlement example',billing_basis='all_arrived_remaining_total'))
            post(staff,f"operations/invoices/{inv['id']}/received",{'note':'DEMO sample receipt only'})
            post(staff,'operations/fulfilment',dict(order_id=oid,kind='delivery',operation_key='demo-delivery-'+str(n+1),lines=arrival))
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        marker={'id':'demo-seed:v1','scope':'demo','description':'Invented local sample data; no real customer or email','project_ids':created}
        c.execute('INSERT INTO operations_records VALUES(?,?,?,?)',(marker['id'],'demo_marker',None,dump(marker)))
    print('Created labelled demo from the curated default pricing knowledge: 3 companies, 7 projects, deposit/balance invoices, whole-order fulfilment and a used rebate')
    print('Database:',target)
    print('No operational database or real email was used')


if __name__=='__main__':main()
