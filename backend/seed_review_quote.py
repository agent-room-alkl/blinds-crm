"""Idempotent local demo: an unaccepted quote exposes the acceptance step."""
import json, os, urllib.request
ROOT='http://127.0.0.1:8000/api/'
def call(path,body=None,token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    request=urllib.request.Request(ROOT+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    with urllib.request.urlopen(request) as response:return json.load(response)
token=call('auth/login',{'username':'dylan','password':os.environ.get('VERA_DEMO_PASSWORD','vera-demo')})['token']
i=call('inquiries',{'company':'Harbour Interiors · Demo','contact_name':'Emma Chen · Demo','channel':'emma@harbour.example','locale':'en','product_id':2,'quantity':6,'width':1200,'height':1800,'unit':'mm','expected_date':'Timing to be agreed after specification review','notes':'Demonstration project: six timber blinds for an office fit-out. Customer has received the quote and has not accepted yet. All names and prices are illustrative.','submission_key':'demo-acceptance-walkthrough-2026'})
quotes=call('quotes',token=token)
q=next((q for q in quotes if q['inquiry_id']==i['id']),None)
if not q:q=call('quotes',{'inquiry_id':i['id'],'locale':'en','currency':'NZD','valid_until':'2027-12-31','discount':0,'shipping':60,'tax':0,'terms':'Illustrative demo prices only. Production and delivery timing require customer confirmation.','lines':[{'product_id':2,'width':1200,'height':1800,'unit':'mm','material':'Timber','color':'Natural oak','control':'Cord','quantity':6,'unit_price':185}]},token)
print(f"Demo inquiry #{i['id']} and quote Q-{q['id']} ready; no order was generated.")
call('auth/logout',{},token)
