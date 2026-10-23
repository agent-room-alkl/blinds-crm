"""Test T-13 legacy VERA Deluxe (Ashwood) migration from real backup row."""
import os
import json
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND'] = 'sqlite'
    os.environ['VERA_STORAGE_BACKEND'] = 'local'
    os.environ['VERA_DB'] = os.path.join(folder, 'ashwood_test.db')
    
    from service import app
    from fastapi.testclient import TestClient
    import service as s
    from operations import migrate
    
    staff = TestClient(app)
    portal = TestClient(app)
    
    # Login
    r = staff.post('/api/auth/login', json={'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})
    assert r.status_code == 200, r.text
    staff.headers['Authorization'] = 'Bearer ' + r.json()['token']
    
    # Load the real legacy row from the owner's backup DB
    with (Path(__file__).parent / 'fixtures' / 'legacy_ashwood_row_id27.json').open(encoding='utf-8') as f:
        legacy_row = json.load(f)
    
    print(f'✓ Loaded real legacy row id={legacy_row["id"]}:')
    print(f'  - source_code: {legacy_row["source_code"]}')
    print(f'  - orderable: {legacy_row["orderable"]}')
    print(f'  - scope: {legacy_row["scope"]}')
    print(f'  - configuration_schema fields: {len(legacy_row["configuration_schema"])}')
    print(f'  - description_zh: {legacy_row["description_zh"][:50]}...')
    
    # Insert the real legacy row exactly as-is
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT INTO products(id, data) VALUES(?, ?)', 
                  (legacy_row['id'], s.dump(legacy_row)))
    
    print(f'\n--- Before migration ---')
    with s.db() as c:
        before_row = c.execute('SELECT data FROM products WHERE id=?', (legacy_row['id'],)).fetchone()
        before_data = json.loads(before_row['data'])
        print(f'source_code: {before_data["source_code"]}')
        print(f'orderable: {before_data["orderable"]}')
        print(f'scope: {before_data["scope"]}')
        print(f'published: {before_data["published"]}')
        print(f'configuration_schema: {len(before_data["configuration_schema"])} fields')
        print(f'description_zh: {before_data["description_zh"]}')
        print(f'description_en: {before_data["description_en"]}')
    
    # Run migration (first time)
    print(f'\n--- Running migration (first time) ---')
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        migrate(c)
    
    # Verify migration results
    with s.db() as c:
        after_row = c.execute('SELECT data FROM products WHERE id=?', (legacy_row['id'],)).fetchone()
        after_data = json.loads(after_row['data'])
        
        print(f'\n--- After migration ---')
        print(f'source_code: {after_data["source_code"]}')
        print(f'orderable: {after_data["orderable"]}')
        print(f'scope: {after_data["scope"]}')
        print(f'published: {after_data["published"]}')
        print(f'configuration_schema: {len(after_data["configuration_schema"])} fields')
        print(f'description_zh: {after_data["description_zh"]}')
        print(f'description_en: {after_data["description_en"]}')
        
        # Test requirement 1: Real fixture used
        assert after_data['id'] == 27, f'Must use real row id=27, got {after_data["id"]}'
        
        # Test requirement 2: Schema has 11 fields with Deluxe colours 61-70 and louver sizes
        assert len(after_data['configuration_schema']) == 11, \
            f'Expected 11 fields, got {len(after_data["configuration_schema"])}'
        
        colour_field = next((f for f in after_data['configuration_schema'] if f['key'] == 'colour'), None)
        assert colour_field is not None, 'colour field missing'
        assert colour_field['choices'] == [
            'Golden Oak 61', 'Fruitwood 62', 'Old Mahogany 63', 'Coffee Bean 64',
            'BlackWalnut 65', 'Light Ash 66', 'Limed 67', 'Natural 68',
            'Rustic Gray 69', 'Provence Blue 70'
        ], f'Colour choices must be stain colours 61-70, got {colour_field["choices"]}'
        
        louver_field = next((f for f in after_data['configuration_schema'] if f['key'] == 'louver_size'), None)
        assert louver_field is not None, 'louver_size field missing'
        assert louver_field['choices'] == ['63mm', '76mm', '89mm', '114mm'], \
            f'Louver sizes must be 63/76/89/114mm, got {louver_field["choices"]}'
        
        # Test requirement 3: Checklist
        assert after_data['orderable'] == True, 'orderable must be true'
        assert after_data['scope'] == 'website_and_template', 'scope must be website_and_template'
        assert after_data['published'] == True, 'published must stay true'
        assert after_data['description_zh'] == '官网展示系列。当前为占位价 1.00/m²，严禁报价给客户。', \
            f'description_zh mismatch'
        assert after_data['description_en'] == 'Website collection. Current placeholder rate 1.00/m² must not be quoted to customers.', \
            f'description_en mismatch'
        
        # Preserved fields
        assert after_data.get('portal_only') == legacy_row.get('portal_only'), 'portal_only changed'
        assert after_data.get('sample') == legacy_row.get('sample'), 'sample changed'
        assert after_data.get('warranty_years') == legacy_row.get('warranty_years'), 'warranty_years changed'
        assert after_data.get('content_source') == legacy_row.get('content_source'), 'content_source changed'
        assert after_data['id'] == legacy_row['id'], 'id changed'
        
        print(f'\n✓ Requirement 3: Checklist passed')
        print(f'  - configuration_schema: 11 fields ✓')
        print(f'  - orderable: true ✓')
        print(f'  - scope: website_and_template ✓')
        print(f'  - published: true (preserved) ✓')
        print(f'  - descriptions: updated ✓')
        print(f'  - Preserved: portal_only={after_data.get("portal_only")}, sample={after_data.get("sample")}, warranty_years={after_data.get("warranty_years")}')
    
    # Test requirement 4: Idempotency - run migration twice
    print(f'\n--- Running migration (second time) ---')
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        migrate(c)
        second_row = c.execute('SELECT data FROM products WHERE id=?', (legacy_row['id'],)).fetchone()
        second_data = json.loads(second_row['data'])
        
        # Compare after first and second migration - should be identical
        assert second_data == after_data, 'Migration is not idempotent'
        print(f'✓ Idempotency test 1: Running migrate() twice gives identical row')
    
    # Test requirement 4b: Half-migrated row gets repaired
    print(f'\n--- Testing half-migrated row repair ---')
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        # Simulate a half-migrated row: source_code updated but other fields still wrong
        half_migrated = {
            **legacy_row,
            'source_code': 'VERA_Ashwood_provisional',
            'orderable': False,  # Still wrong
            'scope': 'website_only',  # Still wrong
            'configuration_schema': []  # Still empty
        }
        c.execute('UPDATE products SET data=? WHERE id=?', 
                  (s.dump(half_migrated), legacy_row['id']))
        
        # Run migration again - should repair
        migrate(c)
        
        repaired_row = c.execute('SELECT data FROM products WHERE id=?', (legacy_row['id'],)).fetchone()
        repaired_data = json.loads(repaired_row['data'])
        
        assert repaired_data['orderable'] == True, 'Half-migrated orderable not repaired'
        assert repaired_data['scope'] == 'website_and_template', 'Half-migrated scope not repaired'
        assert len(repaired_data['configuration_schema']) == 11, 'Half-migrated schema not repaired'
        print(f'✓ Idempotency test 2: Half-migrated row repaired')
    
    # Test requirement 4c: No duplicate row created
    print(f'\n--- Testing no duplicate rows ---')
    with s.db() as c:
        before_count = c.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        migrate(c)
        after_count = c.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        
        assert before_count == after_count, f'Migration created duplicate rows: {before_count} -> {after_count}'
        
        deluxe_rows = c.execute(
            "SELECT COUNT(*) FROM products WHERE json_extract(data, '$.source_code') = 'VERA_Ashwood_provisional'"
        ).fetchone()[0]
        assert deluxe_rows == 1, f'Expected exactly 1 Deluxe row, got {deluxe_rows}'
        print(f'✓ Idempotency test 3: No duplicate rows created (count={after_count}, Deluxe rows={deluxe_rows})')
    
    # Test requirement 5: End-to-end with real DB flow
    print(f'\n--- End-to-end test with template import ---')
    
    # Create a customer
    customer = staff.post('/api/operations/customers', json={
        'company': 'Test Company',
        'customer_type': 'wholesale',
        'customer_code': 'TEST',
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
    
    # Import a template with Basswood (so Deluxe provisional can be synthesized)
    from demo_workbook import fixture
    import base64
    template_bytes = fixture()
    
    from _pricing_test_helpers import publish_fixture_knowledge
    publish_fixture_knowledge(staff, template_bytes, 'test_template.xlsx')
    print('✓ Fixture pricing knowledge reviewed and published')
    
    # Check portal catalog includes Deluxe
    catalog_resp = portal.get('/api/portal/catalog')
    assert catalog_resp.status_code == 200, f'Catalog failed: {catalog_resp.text}'
    catalog = catalog_resp.json()['products']
    
    deluxe_product = next((p for p in catalog if p.get('source_code') == 'VERA_Ashwood_provisional'), None)
    assert deluxe_product is not None, 'Deluxe not in portal catalog'
    assert len(deluxe_product.get('configuration_schema', [])) == 11, \
        f'Deluxe in catalog has wrong schema: {len(deluxe_product.get("configuration_schema", []))} fields'
    
    # Verify colour choices in catalog
    cat_colour = next((f for f in deluxe_product['configuration_schema'] if f['key'] == 'colour'), None)
    assert cat_colour and cat_colour['choices'][0] == 'Golden Oak 61', \
        f'Catalog Deluxe colours wrong: {cat_colour["choices"][:2] if cat_colour else "missing"}'
    
    print(f'✓ Portal catalog includes Deluxe with 11 fields and 61-70 colours')
    
    # Test pricing with Deluxe
    # Deluxe uses the same required fields for display and pricing validation.
    price_order = {
        'project_name': 'Deluxe Test Order',
        'site_address': 'Test Site',
        'submission_key': 'deluxe-test-001',
        'installation_required': False,
        'lines': [{
            'window_name': 'Test Window',
            'product_id': legacy_row['id'],
            'width_mm': 1200,
            'height_mm': 1500,
            'quantity': 2,
            'panel_count': 2,
            'options': {'colour': 'Golden Oak 61', 'louver_size': '89mm', 'fitting': 'In Fit'}
        }]
    }

    # Retain the old placeholder arithmetic coverage while confirming the public
    # quote and order APIs reject provisional pricing.
    with s.db() as c:
        pointer = json.loads(c.execute(
            "SELECT data FROM operations_records WHERE id='template-current'"
        ).fetchone()['data'])
        template = json.loads(c.execute(
            'SELECT data FROM operations_records WHERE id=?', (pointer['template_id'],)
        ).fetchone()['data'])
        deluxe_rule = next(rule for rule in template['products']
                           if rule.get('source_code') == 'VERA_Ashwood_provisional')
        from excel_rules import calculate_line
        calculated = calculate_line(deluxe_rule, price_order['lines'][0],
                                    product_code='VERA_Ashwood_provisional',
                                    addon_definitions=template.get('addons'),
                                    installation_per_panel=template.get('installation_per_panel'))
        from decimal import Decimal
        fixture_subtotal = Decimal(calculated['amount'])
        fixture_tax = fixture_subtotal * Decimal(template['tax_rate'])
        assert fixture_subtotal == Decimal('3.60')
        assert fixture_tax == Decimal('0.54')
        assert fixture_subtotal + fixture_tax == Decimal('4.14')
    
    price_resp = portal.post('/api/portal/price', json=price_order)
    assert price_resp.status_code == 409, \
        f'Unconfirmed Deluxe placeholder must not be quoted: {price_resp.status_code} - {price_resp.text}'
    assert 'not ready' in price_resp.json()['detail']
    order_resp = portal.post('/api/portal/orders', json=price_order)
    assert order_resp.status_code == 409, \
        f'Unconfirmed Deluxe placeholder must not be ordered: {order_resp.status_code} - {order_resp.text}'
    print('✓ Provisional Deluxe remains visible in the catalog and blocked from quotes and orders')
    
    # Verify other series still work (test that we didn't break anything)
    print(f'\n--- Regression test: other series still pass ---')
    
    # Check Basswood (Prime) is still orderable
    basswood = next((p for p in catalog if p.get('source_code') == 'Shutters_Basswood'), None)
    assert basswood is not None and basswood.get('orderable'), 'Basswood should still be orderable'
    print(f'✓ Basswood (VERA Prime) still orderable')
    
    # Check blind products are excluded (18-blind exclusion)
    blind_codes = [
        'Roller_Blinds_BO_VIBE', 'Roller_Blinds_BO_LeReve', 'Roller_Blinds_BO_Skye',
        'Venetian_Blinds_PVC', 'Vertical_Blinds_VIBE_89mm'
    ]
    catalog_codes = [p.get('source_code') for p in catalog]
    blind_in_catalog = [code for code in blind_codes if code in catalog_codes]
    assert len(blind_in_catalog) == 0, f'Blind products should not be in catalog: {blind_in_catalog}'
    print(f'✓ 18-blind exclusion still passes (no blinds in portal catalog)')
    
    print(f'\n' + '='*60)
    print(f'PASS T-13: Legacy VERA Deluxe migration')
    print(f'='*60)
    print(f'✓ Requirement 1: Uses real fixture (id=27)')
    print(f'✓ Requirement 2: 11-field schema with 61-70 colours and 63/76/89/114mm louvers')
    print(f'✓ Requirement 3: Checklist (orderable, scope, published, descriptions)')
    print(f'✓ Requirement 4: Idempotency (twice, half-migrated, no duplicates)')
    print(f'✓ Requirement 5: End-to-end (catalog, provisional quote/order rejection, regression)')
    print(f'')
    print(f'Before migration (row 27):')
    print(json.dumps(before_data, indent=2, ensure_ascii=False))
    print(f'')
    print(f'After migration (row 27):')
    print(json.dumps(after_data, indent=2, ensure_ascii=False))
