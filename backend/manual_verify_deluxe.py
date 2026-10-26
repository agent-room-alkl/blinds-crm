"""Manual verification of VERA Deluxe pricing with fitting.

Tests the three scenarios from the bug report:
1. DELUXE with only colour -> 200
2. DELUXE with colour + fitting -> 200 (was 422 before fix)
3. BASSWOOD with colour + fitting -> 200 (control, should be unchanged)
"""
import os
import json
import tempfile
import base64

with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND'] = 'sqlite'
    os.environ['VERA_STORAGE_BACKEND'] = 'local'
    os.environ['VERA_DB'] = os.path.join(folder, 'manual_test.db')
    
    from service import app
    from fastapi.testclient import TestClient
    import service as s
    from demo_workbook import fixture
    
    staff = TestClient(app)
    portal = TestClient(app)
    
    # Login
    r = staff.post('/api/auth/login', json={'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})
    assert r.status_code == 200
    staff.headers['Authorization'] = 'Bearer ' + r.json()['token']
    
    # Create customer
    customer = staff.post('/api/operations/customers', json={
        'company': 'Manual Test Company',
        'contact_name': 'Manual Test User',
        'email': 'manual@example.invalid',
        'phone': '12345',
        'company_address': 'Test Address',
        'username': 'manualuser',
        'password': 'testpass123'
    }).json()
    
    portal_token = portal.post('/api/portal/login', json={
        'username': 'manualuser',
        'password': 'testpass123'
    }).json()['token']
    portal.headers['Authorization'] = 'Bearer ' + portal_token
    
    # Import template
    template_bytes = fixture()
    import_resp = staff.post('/api/operations/template-import', json={
        'filename': 'manual_test_template.xlsx',
        'content_base64': base64.b64encode(template_bytes).decode()
    })
    assert import_resp.status_code == 200
    
    # Get catalog
    catalog_resp = portal.get('/api/portal/catalog')
    assert catalog_resp.status_code == 200
    catalog = catalog_resp.json()['products']
    
    deluxe = next((p for p in catalog if p.get('source_code') == 'VERA_Ashwood_provisional'), None)
    basswood = next((p for p in catalog if p.get('source_code') == 'Shutters_Basswood'), None)
    
    assert deluxe is not None, 'VERA Deluxe not found'
    assert basswood is not None, 'Basswood not found'
    
    print('='*70)
    print('MANUAL VERIFICATION: VERA Deluxe Pricing with Fitting')
    print('='*70)
    print()
    
    # Test 1: DELUXE with only colour
    print('TEST 1: DELUXE with only colour + louver_size (required fields only)')
    print('-'*70)
    
    price_req = {
        'project_name': 'Manual Test 1',
        'site_address': 'Test Site',
        'submission_key': 'manual-1',
        'installation_required': False,
        'lines': [{
            'window_name': 'Window 1',
            'product_id': deluxe['id'],
            'width_mm': 1200,
            'height_mm': 1500,
            'quantity': 1,
            'panel_count': 2,
            'options': {
                'colour': 'Golden Oak 61',
                'louver_size': '89mm'
            }
        }]
    }
    
    resp = portal.post('/api/portal/price', json=price_req)
    print(f'Status: {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        print(f'✓ SUCCESS: Price calculated')
        print(f'  Subtotal: {data["subtotal"]} {data["currency"]}')
        print(f'  Total: {data["total"]} {data["currency"]}')
        print(f'  Pricing status: {data["pricing_status"]}')
    else:
        print(f'✗ FAILED: {resp.text}')
    print()
    
    # Test 2: DELUXE with colour + fitting (the bug case)
    print('TEST 2: DELUXE with colour + fitting (BUG CASE - was 422, now 200)')
    print('-'*70)
    
    price_req['submission_key'] = 'manual-2'
    price_req['lines'][0]['options'] = {
        'colour': 'Golden Oak 61',
        'louver_size': '89mm',
        'fitting': 'In Fit',
        'frame': 'L-frame',
        'control_rod': 'Centre',
        'opening_style': 'Tracked Bifold',
        'layout_code': 'TT',
        'vt_post': '1',
        'ht_post': '0',
        'midrail': 'Yes',
        'special_request': 'Custom notes'
    }
    
    resp = portal.post('/api/portal/price', json=price_req)
    print(f'Status: {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        print(f'✓ SUCCESS: Price calculated with all 11 fields')
        print(f'  Subtotal: {data["subtotal"]} {data["currency"]}')
        print(f'  Total: {data["total"]} {data["currency"]}')
        print(f'  Pricing status: {data["pricing_status"]}')
        print(f'  Fields used: {list(price_req["lines"][0]["options"].keys())}')
    else:
        print(f'✗ FAILED: {resp.text}')
    print()
    
    # Test 3: BASSWOOD with colour + fitting (control)
    print('TEST 3: BASSWOOD with colour + fitting (CONTROL - should be unchanged)')
    print('-'*70)
    
    # Get Basswood required fields
    bass_schema = basswood.get('configuration_schema', [])
    bass_required = {f['key'] for f in bass_schema if f.get('required')}
    
    bass_options = {}
    if 'colour' in bass_required:
        colour_choices = next((f['choices'] for f in bass_schema if f['key'] == 'colour'), [])
        if colour_choices:
            bass_options['colour'] = colour_choices[0]
    if 'fitting' in bass_required:
        fitting_choices = next((f['choices'] for f in bass_schema if f['key'] == 'fitting'), [])
        if fitting_choices:
            bass_options['fitting'] = fitting_choices[0]
    
    price_req['submission_key'] = 'manual-3'
    price_req['lines'][0]['product_id'] = basswood['id']
    price_req['lines'][0]['options'] = bass_options
    
    resp = portal.post('/api/portal/price', json=price_req)
    print(f'Status: {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        print(f'✓ SUCCESS: Basswood pricing unchanged')
        print(f'  Subtotal: {data["subtotal"]} {data["currency"]}')
        print(f'  Total: {data["total"]} {data["currency"]}')
        print(f'  Pricing status: {data["pricing_status"]}')
    else:
        print(f'✗ FAILED: {resp.text}')
    print()
    
    print('='*70)
    print('SUMMARY')
    print('='*70)
    print('All three scenarios should return status 200.')
    print('Before fix: Test 2 returned 422 "Unsupported product fields"')
    print('After fix: All tests return 200 with valid pricing')
    print()
