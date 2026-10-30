"""Manual invoices, payment details in settings, and the customer's own invoice list/PDF.
Synthetic data only; no real SMTP or production database.
"""
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND'] = 'sqlite'
    os.environ['VERA_DB'] = str(Path(folder) / 'test.db')
    os.environ['VERA_STORAGE_BACKEND'] = 'local'
    from fastapi.testclient import TestClient
    from service import app

    staff, a, b = TestClient(app), TestClient(app), TestClient(app)

    def post(client, path, body=None, status=200):
        r = client.post('/api/' + path, json=body)
        assert r.status_code == status, (path, r.status_code, r.text)
        return r.json()

    staff.headers['Authorization'] = 'Bearer ' + post(staff, 'auth/login', {'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})['token']
    ids = {}
    for key, client in (('A', a), ('B', b)):
        ids[key] = post(staff, 'operations/customers', dict(company=f'Manual {key}', contact_name='Test contact', email=f'manual{key}@example.invalid', phone='123',
                                                            company_address='Company', username=f'manual{key}', password='test-password',
                                                            customer_type='wholesale', customer_code=f'M{key}'))['customer_id']
        client.headers['Authorization'] = 'Bearer ' + post(client, 'portal/login', {'username': f'manual{key}', 'password': 'test-password'})['token']

    # Payment details live in settings, admin only, and reach the invoice text.
    assert staff.get('/api/operations/settings').json()['payment_details'] == {'account_name': '', 'bank_name': '', 'account_number': '', 'reference_note': '', 'configured': False}
    post(a, 'operations/settings', {'payment_details': {'account_number': '12-3456-7890123-00'}}, 401)
    saved = post(staff, 'operations/settings', {'payment_details': {'account_name': 'VERA Shading Ltd', 'bank_name': 'TEST Bank', 'account_number': '12-3456-7890123-00'}})
    assert saved['payment_details']['configured'] is True
    assert staff.get('/api/operations/settings').json()['payment_details']['account_number'] == '12-3456-7890123-00'
    post(staff, 'operations/settings', {'payment_details': {'account_number': 'x' * 101}}, 422)

    # A manual invoice: charges and a credit (negative line), GST included, kept apart from order invoices.
    body = dict(customer_id=ids['A'], operation_key='manual-key-0001', items=[
        {'description': 'Installation, Sterling House', 'amount': '460.00'},
        {'description': 'Air freight, 2 orders', 'amount': '115.00'},
        {'description': 'Credit from September', 'amount': '-75.00'}])
    inv = post(staff, 'operations/invoices/manual', body)
    assert inv['kind'] == 'manual' and inv['amount'] == '500.00' and inv['status'] == 'draft' and inv['order_ids'] == []
    # One running number for every invoice kind; a manual invoice with no linked order has no reference.
    assert re.fullmatch(r'INV-\d{5}', inv['invoice_number']) and inv['tax_rate'] == '0.15'
    assert post(staff, 'operations/invoices/manual', body)['id'] == inv['id']
    post(staff, 'operations/invoices/manual', {**body, 'items': [{'description': 'Other', 'amount': '10'}]}, 409)  # key reused for different data
    second = post(staff, 'operations/invoices/manual', {**body, 'operation_key': 'manual-key-0002', 'items': [{'description': 'Extra', 'amount': '23.00'}]})
    assert second['sequence'] == inv['sequence'] + 1 and second['invoice_number'] == f"INV-{inv['sequence'] + 1:05d}"
    post(staff, 'operations/invoices/manual', {**body, 'operation_key': 'manual-key-0003', 'items': [{'description': 'Credit only', 'amount': '-10'}]}, 422)
    post(staff, 'operations/invoices/manual', {**body, 'operation_key': 'manual-key-0004', 'items': [{'description': 'Zero', 'amount': '0'}]}, 422)
    post(staff, 'operations/invoices/manual', {**body, 'operation_key': 'manual-key-0005', 'items': []}, 422)
    post(staff, 'operations/invoices/manual', {**body, 'operation_key': 'manual-key-0006', 'customer_id': 99999}, 404)
    post(a, 'operations/invoices/manual', body, 401)

    with patch.dict(os.environ, {'VERA_EMAIL_MODE': 'demo', 'VERA_DEMO_EMAIL_ADDRESS': 'owner@example.invalid'}):
        preview = staff.get(f"/api/operations/invoices/{inv['id']}/mail-preview").json()
    for expected in ('Installation, Sterling House', 'Amount incl. GST: NZD 460.00', 'Credit from September', 'NZD -75.00', 'Amount due: NZD 500.00',
                     'Includes GST (15%): NZD 65.22', 'Account number: 12-3456-7890123-00', f"quote {inv['invoice_number']} as the reference"):
        assert expected in preview['body'], (expected, preview['body'])
    assert 'Account number' in preview['html'] and 'Credit from September' in preview['html'] and preview['invoice_number'] == inv['invoice_number']
    pdf = staff.get(f"/api/operations/invoices/{inv['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')

    # The customer sees an invoice only after VERA sends it, and only their own.
    assert a.get('/api/portal/invoices').json() == {'invoices': [], 'unpaid_count': 0, 'unpaid_total': '0.00'}
    assert a.get(f"/api/portal/invoices/{inv['id']}/pdf").status_code == 404  # still a draft
    with patch('email_service.configuration', return_value=({'configured': False}, None)):
        post(staff, f"operations/invoices/{inv['id']}/send")
    mine = a.get('/api/portal/invoices').json()
    assert mine['unpaid_count'] == 1 and mine['unpaid_total'] == '500.00' and len(mine['invoices']) == 1
    row = mine['invoices'][0]
    assert row['invoice_number'] == inv['invoice_number'] and row['reference'] == '' and row['payment_status'] == 'unpaid' and row['kind'] == 'manual' and row['pdf_path'] == f"portal/invoices/{inv['id']}/pdf"
    assert [l['description'] for l in row['lines']] == ['Installation, Sterling House', 'Air freight, 2 orders', 'Credit from September']
    assert not {'actor', 'request_hash', 'rebate_allocations', 'rules_evidence'} & set(row)
    assert b.get('/api/portal/invoices').json()['invoices'] == []
    assert b.get(f"/api/portal/invoices/{inv['id']}/pdf").status_code == 404
    assert a.get(f"/api/portal/invoices/{inv['id']}/pdf").content.startswith(b'%PDF')
    assert staff.get('/api/portal/invoices').status_code == 401 and TestClient(app).get('/api/portal/invoices').status_code == 401

    # Payment is recorded without touching any order, and the list turns green.
    paid = post(staff, f"operations/invoices/{inv['id']}/received", {'note': 'TEST bank transfer'})
    assert paid['payment_status'] == 'received'
    after = a.get('/api/portal/invoices').json()
    assert after['unpaid_count'] == 0 and after['invoices'][0]['payment_status'] == 'paid' and after['invoices'][0]['received_at']
    print('PASS manual invoices: separate kind, GST and credits, payment details in settings, customer list/PDF scoped and draft-hidden')
