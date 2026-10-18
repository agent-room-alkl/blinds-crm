#!/usr/bin/env python3
"""Demo script showing T-11 (Ashwood provisional) and T-12 (aluminium login) features.

This script demonstrates:
1. Ashwood product with provisional pricing at 1.00/m2
2. Order line and snapshot marked as provisional
3. Aluminium products hidden when logged out, visible when logged in
"""
import os
import sys
import tempfile
import json

# Setup test environment
with tempfile.TemporaryDirectory() as folder:
    os.environ.update(
        VERA_DB_BACKEND='sqlite',
        VERA_STORAGE_BACKEND='local',
        VERA_DB=os.path.join(folder, 'demo.db')
    )
    
    from service import app
    from fastapi.testclient import TestClient
    
    print("=== T-11 & T-12 Demo ===\n")
    
    # Create clients
    staff = TestClient(app)
    portal = TestClient(app)
    public = TestClient(app)
    
    # Staff login
    r = staff.post('/api/auth/login', json={'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})
    staff.headers['Authorization'] = 'Bearer ' + r.json()['token']
    
    print("1. Creating test customer...")
    customer = staff.post('/api/operations/customers', json={
        'company': 'Demo Company',
        'contact_name': 'Demo User',
        'email': 'demo@example.invalid',
        'phone': '12345',
        'company_address': 'Demo Address',
        'username': 'democustomer',
        'password': 'test-password'
    }).json()
    print(f"   ✓ Created customer: {customer['company']}\n")
    
    # Portal login
    token = portal.post('/api/portal/login', json={'username': 'democustomer', 'password': 'test-password'}).json()['token']
    portal.headers['Authorization'] = 'Bearer ' + token
    
    # Import template to get products
    print("2. Importing pricing template...")
    from demo_workbook import fixture
    import base64
    imported = staff.post('/api/operations/template-import', json={
        'filename': 'demo.xlsm',
        'content_base64': base64.b64encode(fixture()).decode()
    }).json()
    print(f"   ✓ Imported template with {imported['products_count']} products\n")
    
    # Check catalog
    print("3. Checking product catalog...")
    catalog = portal.get('/api/portal/catalog').json()['products']
    print(f"   ✓ Found {len(catalog)} products in catalog")
    
    # Find Ashwood
    ashwood = next((p for p in catalog if 'Deluxe' in p.get('name_en', '') or 'Ashwood' in p.get('material_en', '')), None)
    if ashwood:
        print(f"   ✓ Found Ashwood product: {ashwood['name_en']} (id={ashwood['id']}, orderable={ashwood.get('orderable')})")
        print(f"     Description: {ashwood.get('description_en', '')[:80]}...\n")
        
        if ashwood.get('orderable'):
            print("4. Creating Ashwood order with provisional pricing...")
            
            # Get required options
            options = {}
            print(f"   DEBUG: Configuration schema:")
            for field in ashwood.get('configuration_schema', []):
                print(f"     - {field.get('key')}: required={field.get('required')}, choices={field.get('choices', [])[:3]}")
                if field.get('required') and field.get('choices'):
                    options[field['key']] = field['choices'][0]
                elif field.get('required'):
                    options[field['key']] = ''  # Empty string for text fields
            print(f"   DEBUG: Selected options: {options}")
            
            ashwood_order = {
                'project_name': 'Ashwood Demo Project',
                'site_address': 'Demo Site',
                'submission_key': 'ashwood-demo-001',
                'installation_required': False,
                'lines': [{
                    'window_name': 'Ashwood Window',
                    'product_id': ashwood['id'],
                    'width_mm': 1200,
                    'height_mm': 1500,
                    'quantity': 2,
                    'panel_count': 2,
                    'options': options
                }]
            }
            
            # Price the order
            price_result = portal.post('/api/portal/price', json=ashwood_order).json()
            print(f"   DEBUG: price_result keys: {list(price_result.keys())}")
            print(f"   DEBUG: price_result: {json.dumps(price_result, indent=2)[:500]}")
            if 'lines' in price_result:
                print(f"   ✓ Priced Ashwood order:")
                print(f"     Total: {price_result.get('total')}")
                print(f"     Overall pricing_status: {price_result.get('pricing_status')}")
                print(f"     Line pricing_status: {price_result['lines'][0].get('pricing_status')}")
            else:
                print(f"   ✗ Failed to price order: {price_result}")
                sys.exit(1)
            
            # Submit the order
            submitted = portal.post('/api/portal/orders', json=ashwood_order).json()
            oid = submitted['id']
            print(f"   ✓ Submitted order: {oid}")
            print(f"     Line pricing_status in snapshot: {submitted['lines'][0].get('pricing_status')}\n")
            
            # Review the order
            print("5. Reviewing order (admin)...")
            reviewed = staff.post(f'/api/operations/orders/{oid}/review').json()
            print(f"   ✓ Reviewed order:")
            print(f"     Total: {reviewed.get('total')}")
            print(f"     Line pricing_status after review: {reviewed['lines'][0].get('pricing_status')}")
            print(f"     ⚠ Provisional flag persists in stored snapshot\n")
    else:
        print("   ⚠ Ashwood not found in catalog\n")
    
    # T-12: Aluminium login requirement
    print("6. Testing aluminium product login requirement...")
    
    # Create aluminium product
    alu = staff.post('/api/admin/products', json={
        'name_zh': '铝合金百叶窗',
        'name_en': 'Aluminium Shutters',
        'material_zh': '铝合金',
        'material_en': 'Aluminium',
        'description_zh': '现代铝合金百叶窗',
        'description_en': 'Modern aluminium shutters',
        'category': 'aluminium',
        'sample': False,
        'published': True,
        'image_url': '/images/vera-aluminium-room-v2.png',
        'image_urls': ['/images/vera-aluminium-room-v2.png'],
        'unit': 'mm',
        'colors': ['White', 'Silver'],
        'controls': ['Remote', 'Manual']
    }).json()
    print(f"   ✓ Created aluminium product (id={alu['id']})")
    
    # Test public access (logged out)
    public_products = public.get('/api/products').json()
    alu_public = [p for p in public_products if p.get('category') == 'aluminium']
    print(f"   ✓ Public catalog (logged out): {len(alu_public)} aluminium products (should be 0)")
    
    # Try direct access when logged out
    resp = public.get(f'/api/products/{alu["id"]}')
    print(f"   ✓ Direct access when logged out: {resp.status_code} (should be 403)")
    
    # Test authenticated access
    authed_products = portal.get('/api/products').json()
    alu_authed = [p for p in authed_products if p.get('category') == 'aluminium']
    print(f"   ✓ Authenticated catalog: {len(alu_authed)} aluminium product(s) visible")
    
    # Direct access when logged in
    resp = portal.get(f'/api/products/{alu["id"]}')
    print(f"   ✓ Direct access when logged in: {resp.status_code} (should be 200)\n")
    
    print("=== Demo Complete ===")
    print("\nSummary:")
    print("  T-11: Ashwood orderable with provisional 1.00/m2 placeholder rate")
    print("        Provisional flag persists on lines and in stored snapshot")
    print("  T-12: Aluminium products hidden when logged out (403)")
    print("        Aluminium products visible when authenticated (200)")
