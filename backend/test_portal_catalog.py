"""Test portal catalog ordering and affects_price metadata"""
import os,tempfile
with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND']='sqlite'
    os.environ['VERA_DB']=os.path.join(folder,'test.db')
    os.environ['VERA_STORAGE_BACKEND']='local'
    os.environ['VERA_DEMO_PASSWORD']='test-password'
    from service import app
    from fastapi.testclient import TestClient
    client=TestClient(app)
    
    # Login as demo admin
    token=client.post('/api/auth/login',json={'username':'dylan','password':'test-password'}).json()['token']
    client.headers['Authorization']='Bearer '+token
    
    # Create test customer
    customer=client.post('/api/operations/customers',json={
        'company':'Test Company','contact_name':'Test User','email':'test@example.com',
        'phone':'123456','company_address':'Test Address','username':'testuser','password':'testpass123'
    }).json()
    
    # Login as customer
    portal=TestClient(app)
    portal_token=portal.post('/api/portal/login',json={'username':'testuser','password':'testpass123'}).json()['token']
    portal.headers['Authorization']='Bearer '+portal_token
    
    # Get catalog
    catalog_response=portal.get('/api/portal/catalog').json()
    products=catalog_response['products']
    
    # Test 1: Catalog ordering matches website (Eco, Classic, Natural, Prime, Deluxe, Aluminium)
    expected_order=['Shutters_PVC_Eco','Shutters_PVC','Shutters_Pinewood','Shutters_Basswood','VERA_Ashwood_provisional','Shutters_Aluminium']
    actual_codes=[p['source_code'] for p in products]
    
    # Filter to only codes that exist (not all may be in seed)
    expected_present=[code for code in expected_order if code in actual_codes]
    actual_present=[code for code in actual_codes if code in expected_order]
    
    print(f'✓ Catalog returned {len(products)} products')
    print(f'  Expected order (present): {expected_present}')
    print(f'  Actual order: {actual_present}')
    
    if expected_present != actual_present:
        raise AssertionError(f'Catalog order mismatch: expected {expected_present}, got {actual_present}')
    print('✓ Catalog products in correct website order')
    
    # Test 2: affects_price metadata present and correct
    for p in products:
        if p.get('price_rule') and isinstance(p['price_rule'],dict):
            affects=p['price_rule'].get('affects_price',{})
            if affects:
                # Check that price-affecting fields are marked True
                assert affects.get('product_id')==True,f"{p['source_code']}: product_id should affect price"
                assert affects.get('width_mm')==True,f"{p['source_code']}: width_mm should affect price"
                assert affects.get('height_mm')==True,f"{p['source_code']}: height_mm should affect price"
                # Check that non-price-affecting fields are marked False
                assert affects.get('colour')==False,f"{p['source_code']}: colour should NOT affect price"
                assert affects.get('louver_size')==False,f"{p['source_code']}: louver_size should NOT affect price"
                assert affects.get('frame_type')==False,f"{p['source_code']}: frame_type should NOT affect price"
                print(f'✓ {p["source_code"]}: affects_price metadata correct')
    
    # Test 3: Old VERA_Ashwood_display code is handled
    # Create a product with old code and verify it's normalized
    old_ashwood={'id':99,'name_zh':'测试旧Ashwood','name_en':'Test Old Ashwood',
                 'source_code':'VERA_Ashwood_display','material_zh':'白蜡木','material_en':'Ashwood',
                 'description_zh':'测试','description_en':'Test','category':'shutters','sample':False,
                 'published':True,'orderable':True}
    from service import db,dump
    with db() as c:
        c.execute('INSERT OR REPLACE INTO products VALUES(?,?)',(99,dump(old_ashwood)))
    
    # Get catalog again
    catalog_response=portal.get('/api/portal/catalog').json()
    products=catalog_response['products']
    actual_codes=[p['source_code'] for p in products]
    
    # Old code should be normalized to provisional
    assert 'VERA_Ashwood_display' not in actual_codes,'Old Ashwood code should be normalized'
    deluxe_count=actual_codes.count('VERA_Ashwood_provisional')
    print(f'✓ Old VERA_Ashwood_display normalized (Deluxe count: {deluxe_count})')
    
    print('\nPASS catalog ordering and affects_price metadata')
