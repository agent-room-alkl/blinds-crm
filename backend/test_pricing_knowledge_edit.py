"""Editing pricing knowledge from the CRM: drafts save over POST and PUT, and add-on text follows the amount."""
import copy,os,tempfile
with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND']='sqlite'
    os.environ['VERA_DB']=os.path.join(folder,'test.db')
    os.environ['VERA_STORAGE_BACKEND']='local'
    os.environ['VERA_DEMO_PASSWORD']='test-password'
    from service import app
    from fastapi.testclient import TestClient
    from addons import with_price_labels
    staff=TestClient(app)
    staff.headers['Authorization']='Bearer '+staff.post('/api/auth/login',json={'username':'dylan','password':'test-password'}).json()['token']
    assert staff.post('/api/operations/pricing-knowledge/initialize-default',json={}).status_code==200
    assert staff.post('/api/operations/customers',json=dict(company='Label Co',contact_name='L',email='',phone='1',company_address='A',
        username='label-user',password='label-pass-1',customer_type='wholesale',customer_code='LC')).status_code==200
    portal=TestClient(app)
    portal.headers['Authorization']='Bearer '+portal.post('/api/portal/login',json={'username':'label-user','password':'label-pass-1'}).json()['token']

    def cutout(addons):
        return next(c for a in addons if a['key']=='shaped_cutout' for c in a['choices'] if c['value']=='yes')

    def publish(change, verb):
        draft=staff.post('/api/operations/pricing-knowledge/drafts/from-current',json={}).json()
        manifest=copy.deepcopy(draft['manifest']);change(manifest)
        send=staff.post if verb=='POST' else staff.put
        saved=send('/api/operations/pricing-knowledge/drafts/'+draft['id'],json={'manifest':manifest,'facts':[]})
        assert saved.status_code==200,(verb,saved.status_code,saved.text)
        published=staff.post('/api/operations/pricing-knowledge/drafts/'+draft['id']+'/publish',json={})
        assert published.status_code==200,published.text

    catalog=portal.get('/api/portal/catalog').json()
    assert (cutout(catalog['addons'])['label_zh'],cutout(catalog['addons'])['label_en'])==('要，+$300/件','Yes, +$300 each')

    # The CRM saves drafts with POST; the amount changes and the customer-facing text follows it.
    publish(lambda m:cutout(m['addons']).update(fixed='360'),'POST')
    catalog=portal.get('/api/portal/catalog').json()
    assert (cutout(catalog['addons'])['label_zh'],cutout(catalog['addons'])['label_en'])==('要，+$360/件','Yes, +$360 each'),cutout(catalog['addons'])
    product=next(p for p in catalog['products'] if p['source_code']=='Shutters_Basswood')
    options={f['key']:(f['choices'][0] if f.get('choices') else 'QA') for f in product.get('configuration_schema') or [] if f.get('choices') or f.get('required')}
    quote=portal.post('/api/portal/price',json=dict(project_name='Label',site_address='A',submission_key='label-quote-1',installation_required=False,
        lines=[dict(window_name='W',product_id=product['id'],width_mm=1000,height_mm=1000,quantity=1,panel_count=1,options={**options,'shaped_cutout':'yes'})]))
    assert quote.status_code==200 and quote.json()['subtotal']=='700.00',quote.text

    # PUT still works, and the editor sees the regenerated text too.
    publish(lambda m:next(c for a in m['addons'] if a['key']=='stained_colour' for c in a['choices'] if c['value']=='yes').update(per_sqm='22.5'),'PUT')
    current=staff.get('/api/operations/pricing-knowledge').json()['current']
    stain=next(c for a in current['addons'] if a['key']=='stained_colour' for c in a['choices'] if c['value']=='yes')
    assert (stain['label_zh'],stain['label_en'])==('要，+$22.50/㎡','Yes, +$22.50/sqm'),stain

    # Unpriced choices keep their text; a priced non-yes choice keeps its name with the amount added.
    addons=with_price_labels([{'key':'extra_installation','choices':[{'value':'none','label_zh':'无','label_en':'None'},
        {'value':'tile','label_zh':'瓷砖','label_en':'Tile'},{'value':'concrete','label_zh':'水泥墙，+$40/件','label_en':'Concrete wall, +$40 each','fixed':'50'},
        {'value':'yes','label_zh':'要','label_en':'Yes','percent':'12.5'}]}])
    labels=[(c['label_zh'],c['label_en']) for c in addons[0]['choices']]
    assert labels==[('无','None'),('瓷砖','Tile'),('水泥墙，+$50/件','Concrete wall, +$50 each'),('要，+12.5%','Yes, +12.5%')],labels
    print('PASS drafts save over POST and PUT; add-on text follows published amounts in catalog and editor; quotes use the new amount')
