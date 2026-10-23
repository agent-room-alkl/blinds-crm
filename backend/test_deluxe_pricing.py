"""Test VERA Deluxe pricing with all 11 fields (fitting, control_rod, etc.).

Ensures the product schema and pricing rule schema are in sync.
Tests fresh DB, legacy row, half-migrated row, and minimal-schema rule repair.
"""
import os
import json
import tempfile
import base64

with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND'] = 'sqlite'
    os.environ['VERA_STORAGE_BACKEND'] = 'local'
    os.environ['VERA_DB'] = os.path.join(folder, 'deluxe_pricing_test.db')
    
    from service import app
    from fastapi.testclient import TestClient
    import service as s
    from operations import migrate, DELUXE_SCHEMA
    from demo_workbook import fixture
    
    staff = TestClient(app)
    portal = TestClient(app)
    
    # Login
    r = staff.post('/api/auth/login', json={'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})
    assert r.status_code == 200, r.text
    staff.headers['Authorization'] = 'Bearer ' + r.json()['token']
    
    print('='*60)
    print('TEST 1: Fresh DB - Product and rule schemas match')
    print('='*60)
    
    # Create customer
    customer = staff.post('/api/operations/customers', json={
        'company': 'Test Company',
        'contact_name': 'Test User',
        'email': 'test@example.invalid',
        'phone': '12345',
        'company_address': 'Test Address',
        'username': 'testuser',
        'password': 'testpass123'
    }).json()
    
    portal_token = portal.post('/api/portal/login', json={
        'username': 'testuser',
        'password': 'testpass123'
    }).json()['token']
    portal.headers['Authorization'] = 'Bearer ' + portal_token
    
    # Import template
    template_bytes = fixture()
    from _pricing_test_helpers import publish_fixture_knowledge
    publish_fixture_knowledge(staff, template_bytes, 'test_template.xlsx', confirm_deluxe_fixture=True)
    print('✓ Fixture pricing knowledge reviewed and published')
    
    # Get catalog
    catalog_resp = portal.get('/api/portal/catalog')
    assert catalog_resp.status_code == 200
    catalog = catalog_resp.json()['products']
    
    deluxe = next((p for p in catalog if p.get('source_code') == 'VERA_Ashwood_provisional'), None)
    assert deluxe is not None, 'Deluxe not in catalog'
    assert len(deluxe['configuration_schema']) == 11, \
        f'Product schema should have 11 fields, got {len(deluxe["configuration_schema"])}'
    print(f'✓ Deluxe product has 11-field schema')
    
    # Test 1a: Deluxe with colour only (required fields only)
    price_req = {
        'project_name': 'Test 1a',
        'site_address': 'Test Site',
        'submission_key': 'test-1a-001',
        'installation_required': False,
        'lines': [{
            'window_name': 'Window 1',
            'product_id': deluxe['id'],
            'width_mm': 1000,
            'height_mm': 1000,
            'quantity': 1,
            'panel_count': 1,
            'options': {
                'colour': 'Golden Oak 61',
                'louver_size': '89mm'
            }
        }]
    }
    
    price_resp = portal.post('/api/portal/price', json=price_req)
    assert price_resp.status_code == 200, f'Test 1a failed: {price_resp.status_code} - {price_resp.text}'
    price_data = price_resp.json()
    print(f'✓ Test 1a: DELUXE colour + louver_size -> 200 (price={price_data["total"]})')
    
    # Test 1b: Deluxe with colour + fitting (and other optional fields)
    price_req['submission_key'] = 'test-1b-001'
    price_req['lines'][0]['options'] = {
        'colour': 'Golden Oak 61',
        'louver_size': '89mm',
        'fitting': 'In Fit',
        'frame': 'L-frame',
        'control_rod': 'Centre',
        'opening_style': 'Bi-fold',
        'layout_code': 'TT',
        'vt_post': '1',
        'ht_post': '0',
        'midrail': 'Yes',
        'special_request': 'Test special request'
    }
    
    price_resp = portal.post('/api/portal/price', json=price_req)
    assert price_resp.status_code == 200, f'Test 1b failed: {price_resp.status_code} - {price_resp.text}'
    price_data = price_resp.json()
    print(f'✓ Test 1b: DELUXE colour + fitting + all 11 fields -> 200 (price={price_data["total"]})')

    for fitting in ('In Fit', 'Out Fit', 'Make Size'):
        price_req['lines'][0]['options']['fitting'] = fitting
        response = portal.post('/api/portal/price', json=price_req)
        assert response.status_code == 200, response.text
    price_req['lines'][0]['options']['fitting'] = 'ZZZ-garbage'
    response = portal.post('/api/portal/price', json=price_req)
    assert response.status_code == 422, response.text
    response = portal.post('/api/portal/orders', json=price_req)
    assert response.status_code == 422, response.text
    print('PASS Deluxe fitting: all three workbook values accepted; garbage rejected by price and order endpoints')
    
    # Test 1c: Basswood (control - should still work)
    basswood = next((p for p in catalog if p.get('source_code') == 'Shutters_Basswood'), None)
    assert basswood is not None, 'Basswood not in catalog'
    
    price_req['submission_key'] = 'test-1c-001'
    price_req['lines'][0]['product_id'] = basswood['id']
    # Basswood requires colour and fitting (check its schema for actual required fields)
    bass_schema = basswood.get('configuration_schema', [])
    bass_required = {f['key'] for f in bass_schema if f.get('required')}
    print(f'  Basswood required fields: {bass_required}')
    
    # Provide minimal required fields
    bass_options = {}
    if 'colour' in bass_required:
        colour_choices = next((f['choices'] for f in bass_schema if f['key'] == 'colour'), [])
        if colour_choices:
            bass_options['colour'] = colour_choices[0]
    if 'fitting' in bass_required:
        fitting_choices = next((f['choices'] for f in bass_schema if f['key'] == 'fitting'), [])
        if fitting_choices:
            bass_options['fitting'] = fitting_choices[0]
    
    price_req['lines'][0]['options'] = bass_options
    
    price_resp = portal.post('/api/portal/price', json=price_req)
    assert price_resp.status_code == 200, f'Test 1c failed: {price_resp.status_code} - {price_resp.text}'
    price_data = price_resp.json()
    print(f'✓ Test 1c: BASSWOOD (control) with required fields -> 200 (price={price_data["total"]})')
    
    # Test 1d: Missing required fields should fail
    price_req['submission_key'] = 'test-1d-001'
    price_req['lines'][0]['product_id'] = deluxe['id']
    price_req['lines'][0]['options'] = {}  # Missing required colour and louver_size
    
    price_resp = portal.post('/api/portal/price', json=price_req)
    assert price_resp.status_code == 422, f'Test 1d should fail with 422, got {price_resp.status_code}'
    print(f'✓ Test 1d: DELUXE with empty options -> 422 (required fields enforced)')
    
    print('\n' + '='*60)
    print('TEST 2: Legacy DB - Migrated row')
    print('='*60)
    
    # Create a completely new environment for legacy testing
    with tempfile.TemporaryDirectory() as legacy_folder:
        legacy_db = os.path.join(legacy_folder, 'legacy_test.db')
        
        # Temporarily switch to the legacy DB
        old_db = os.environ['VERA_DB']
        os.environ['VERA_DB'] = legacy_db
        
        # Force reload of service module to pick up new DB path
        import importlib
        import sys
        # Remove cached modules
        for mod in list(sys.modules.keys()):
            if mod.startswith('service') or mod.startswith('operations'):
                del sys.modules[mod]
        
        # Import fresh
        import service as s_legacy
        from operations import migrate as migrate_legacy
        
        # Insert legacy row
        legacy_row = {
            'id': 27,
            'source_code': 'VERA_Ashwood_display',
            'name_zh': '旧 Deluxe',
            'name_en': 'Old Deluxe',
            'orderable': False,
            'scope': 'website_only',
            'configuration_schema': [],
            'published': True,
            'category': 'shutters',
            'sample': False,
            'portal_only': False
        }
        
        with s_legacy.db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO products(id, data) VALUES(?, ?)', (27, s_legacy.dump(legacy_row)))
        
        # Run migration
        with s_legacy.db() as c:
            c.execute('BEGIN IMMEDIATE')
            migrate_legacy(c)
        
        # Verify migration
        with s_legacy.db() as c:
            migrated_row = c.execute('SELECT data FROM products WHERE id=27').fetchone()
            migrated = json.loads(migrated_row['data'])
            
            assert migrated['source_code'] == 'VERA_Ashwood_provisional', 'source_code not updated'
            assert migrated['orderable'] == True, 'orderable not updated'
            assert migrated['scope'] == 'website_and_template', 'scope not updated'
            assert len(migrated['configuration_schema']) == 11, \
                f'Schema not updated: {len(migrated["configuration_schema"])} fields'
            
            # Check required fields are marked correctly
            colour_field = next(f for f in migrated['configuration_schema'] if f['key'] == 'colour')
            louver_field = next(f for f in migrated['configuration_schema'] if f['key'] == 'louver_size')
            assert colour_field['required'] == True, 'colour should be required'
            assert louver_field['required'] == True, 'louver_size should be required'
            
            print(f'✓ Legacy row migrated: 11 fields, required fields marked correctly')
        
        # Restore original DB
        os.environ['VERA_DB'] = old_db
        # Remove cached modules again
        for mod in list(sys.modules.keys()):
            if mod.startswith('service') or mod.startswith('operations'):
                del sys.modules[mod]
        # Reimport
        import service as s
        from operations import migrate
    
    print('\n' + '='*60)
    print('TEST 3: Half-migrated row repair')
    print('='*60)
    
    with tempfile.TemporaryDirectory() as half_folder:
        half_db = os.path.join(half_folder, 'half_test.db')
        
        # Temporarily switch to half DB
        old_db = os.environ['VERA_DB']
        os.environ['VERA_DB'] = half_db
        
        # Force reload
        import importlib
        import sys
        for mod in list(sys.modules.keys()):
            if mod.startswith('service') or mod.startswith('operations'):
                del sys.modules[mod]
        import service as s_half
        from operations import migrate as migrate_half
        
        # Insert half-migrated row (source_code updated but schema empty)
        half_row = {
            'id': 27,
            'source_code': 'VERA_Ashwood_provisional',
            'name_zh': 'VERA Deluxe',
            'name_en': 'VERA Deluxe',
            'orderable': False,  # Still wrong
            'scope': 'website_only',  # Still wrong
            'configuration_schema': [],  # Still empty
            'published': True,
            'category': 'shutters',
            'sample': False,
            'portal_only': False
        }
        
        with s_half.db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO products(id, data) VALUES(?, ?)', (27, s_half.dump(half_row)))
        
        # Run migration
        with s_half.db() as c:
            c.execute('BEGIN IMMEDIATE')
            migrate_half(c)
        
        # Verify repair
        with s_half.db() as c:
            repaired_row = c.execute('SELECT data FROM products WHERE id=27').fetchone()
            repaired = json.loads(repaired_row['data'])
            
            assert repaired['orderable'] == True, 'Half-migrated orderable not repaired'
            assert repaired['scope'] == 'website_and_template', 'Half-migrated scope not repaired'
            assert len(repaired['configuration_schema']) == 11, \
                f'Half-migrated schema not repaired: {len(repaired["configuration_schema"])} fields'
            
            print(f'✓ Half-migrated row repaired: orderable=True, scope=website_and_template, 11 fields')
        
        # Restore
        os.environ['VERA_DB'] = old_db
        for mod in list(sys.modules.keys()):
            if mod.startswith('service') or mod.startswith('operations'):
                del sys.modules[mod]
        import service as s
        from operations import migrate
    
    print('\n' + '='*60)
    print('TEST 4: Minimal-schema rule repair (idempotent)')
    print('='*60)
    
    # This test simulates a DB where the pricing rule was created with the old 2-field minimal schema
    # The fix should detect this and upgrade it to the full 11-field schema during pricing calculation
    
    with tempfile.TemporaryDirectory() as minimal_folder:
        minimal_db = os.path.join(minimal_folder, 'minimal_test.db')
        
        # Temporarily switch to minimal DB
        old_db = os.environ['VERA_DB']
        os.environ['VERA_DB'] = minimal_db
        
        # Force reload
        import importlib
        import sys
        for mod in list(sys.modules.keys()):
            if mod.startswith('service') or mod.startswith('operations'):
                del sys.modules[mod]
        
        from service import app as app_minimal
        import service as s_minimal
        from fastapi.testclient import TestClient
        
        staff2 = TestClient(app_minimal)
        portal2 = TestClient(app_minimal)
        
        # Login
        r = staff2.post('/api/auth/login', json={'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})
        assert r.status_code == 200
        staff2.headers['Authorization'] = 'Bearer ' + r.json()['token']
        
        # Create customer
        customer2 = staff2.post('/api/operations/customers', json={
            'company': 'Test Company 2',
            'contact_name': 'Test User 2',
            'email': 'test2@example.invalid',
            'phone': '12345',
            'company_address': 'Test Address 2',
            'username': 'testuser2',
            'password': 'testpass123'
        }).json()
        
        token2 = portal2.post('/api/portal/login', json={
            'username': 'testuser2',
            'password': 'testpass123'
        }).json()['token']
        portal2.headers['Authorization'] = 'Bearer ' + token2
        
        # Import template
        publish_fixture_knowledge(staff2, fixture(), 'test_template2.xlsx', confirm_deluxe_fixture=True)
        
        # Manually inject a minimal-schema rule into the template (simulate old code)
        with s_minimal.db() as c:
            template_pointer = c.execute(
                "SELECT data FROM operations_records WHERE id='template-current'"
            ).fetchone()
            template_id = json.loads(template_pointer['data'])['template_id']
            
            template_row = c.execute(
                "SELECT data FROM operations_records WHERE id=?", (template_id,)
            ).fetchone()
            template = json.loads(template_row['data'])
            
            # Find and modify the Deluxe rule to have only 2 fields (simulate old code)
            for i, p in enumerate(template['products']):
                if p['source_code'] == 'VERA_Ashwood_provisional':
                    # Replace with minimal schema
                    template['products'][i]['schema'] = [
                        {
                            'key': 'colour',
                            'label_zh': '颜色',
                            'label_en': 'Colour',
                            'choices': [
                                'Golden Oak 61', 'Fruitwood 62', 'Old Mahogany 63', 'Coffee Bean 64',
                                'BlackWalnut 65', 'Light Ash 66', 'Limed 67', 'Natural 68',
                                'Rustic Gray 69', 'Provence Blue 70'
                            ],
                            'required': False,
                            'type': 'select'
                        },
                        {
                            'key': 'louver_size',
                            'label_zh': '叶片尺寸',
                            'label_en': 'Louver size',
                            'choices': ['63mm', '76mm', '89mm', '114mm'],
                            'required': False,
                            'type': 'select'
                        }
                    ]
                    break
            
            # Save modified template
            c.execute(
                "UPDATE operations_records SET data=? WHERE id=?",
                (s_minimal.dump(template), template_id)
            )
        
        print('✓ Injected minimal-schema rule (2 fields) into template')
        
        # Get catalog
        catalog2 = portal2.get('/api/portal/catalog').json()['products']
        deluxe2 = next(p for p in catalog2 if p.get('source_code') == 'VERA_Ashwood_provisional')
        
        # Try pricing with fitting (should fail before fix, succeed after fix)
        price_req2 = {
            'project_name': 'Test 4',
            'site_address': 'Test Site',
            'submission_key': 'test-4-001',
            'installation_required': False,
            'lines': [{
                'window_name': 'Window 1',
                'product_id': deluxe2['id'],
                'width_mm': 1000,
                'height_mm': 1000,
                'quantity': 1,
                'panel_count': 1,
                'options': {
                    'colour': 'Golden Oak 61',
                    'louver_size': '89mm',
                    'fitting': 'In Fit'
                }
            }]
        }
        
        price_resp2 = portal2.post('/api/portal/price', json=price_req2)
        assert price_resp2.status_code == 200, \
            f'Pricing with fitting should succeed after fix, got {price_resp2.status_code}: {price_resp2.text}'
        
        print(f'✓ Pricing with fitting succeeds despite minimal-schema rule (auto-repaired)')
        
        # Verify idempotency: second call should also work
        price_req2['submission_key'] = 'test-4-002'
        price_resp2b = portal2.post('/api/portal/price', json=price_req2)
        assert price_resp2b.status_code == 200
        
        print(f'✓ Idempotent: second pricing call also succeeds')
        
        # Restore
        os.environ['VERA_DB'] = old_db
        for mod in list(sys.modules.keys()):
            if mod.startswith('service') or mod.startswith('operations'):
                del sys.modules[mod]
        import service as s
        from operations import migrate
    
    print('\n' + '='*60)
    print('PASS: All VERA Deluxe pricing tests')
    print('='*60)
    print('✓ Test 1: Fresh DB - Product and rule schemas match')
    print('  - 1a: colour + louver_size -> 200')
    print('  - 1b: colour + fitting + all 11 fields -> 200')
    print('  - 1c: Basswood (control) -> 200')
    print('  - 1d: Empty options -> 422 (required fields enforced)')
    print('✓ Test 2: Legacy row migrated correctly')
    print('✓ Test 3: Half-migrated row repaired')
    print('✓ Test 4: Minimal-schema rule auto-repaired (idempotent)')
    print('')
