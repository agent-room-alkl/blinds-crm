"""Meeting 27 Oct: optional site address, customised frame, ETA from the deposit, ready/complete without payment gate.
Synthetic fixture only; no real SMTP or production database.
"""
import os
import re
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from demo_workbook import fixture

with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND'] = 'sqlite'
    os.environ['VERA_DB'] = str(Path(folder) / 'test.db')
    os.environ['VERA_STORAGE_BACKEND'] = 'local'
    from fastapi.testclient import TestClient
    from service import app
    from _pricing_test_helpers import publish_fixture_knowledge

    staff, customer = TestClient(app), TestClient(app)

    def post(client, path, body=None, status=200):
        r = client.post('/api/' + path, json=body)
        assert r.status_code == status, (path, r.status_code, r.text)
        return r.json()

    staff.headers['Authorization'] = 'Bearer ' + post(staff, 'auth/login', {'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})['token']
    post(staff, 'operations/customers', dict(company='ETA only', contact_name='Test contact', email='eta@example.invalid', phone='123',
                                             company_address='Company', username='etaclient', password='test-password',
                                             customer_type='wholesale', customer_code='ETA'))
    customer.headers['Authorization'] = 'Bearer ' + post(customer, 'portal/login', {'username': 'etaclient', 'password': 'test-password'})['token']
    publish_fixture_knowledge(staff, fixture(), 'test.xlsm')

    catalog = customer.get('/api/portal/catalog').json()
    frame = next(a for a in catalog['addons'] if a['key'] == 'custom_frame')
    assert [c['value'] for c in frame['choices']] == ['no', 'yes'] and frame['choices'][1]['percent'] == '10'
    assert frame['choices'][1]['label_en'] == 'Yes, +10%'
    product = next(p for p in catalog['products'] if p['source_code'] == 'Shutters_PVC')
    options = {'colour': 'White TEST', 'fitting': 'In Fit'}

    def body(key, address, install=False, extra=None, name='Job'):
        return dict(project_name=name, site_address=address, submission_key=key, installation_required=install,
                    lines=[dict(window_name='Window', product_id=product['id'], width_mm='1000', height_mm='1000', quantity=1,
                                panel_count=2, options={**options, **(extra or {})})])

    # The address is only required when VERA installs.
    plain = post(customer, 'portal/price', body('addr-plain-1', ''))
    assert plain['subtotal'] == '100.00' and plain['installation'] == '0.00'
    post(customer, 'portal/price', body('addr-install', '', install=True), 422)
    post(customer, 'portal/price', body('addr-install', '   ', install=True), 422)
    assert post(customer, 'portal/price', body('addr-install-ok', '1 Site Road', install=True))['installation'] == '150.00'

    # Customised frame: +10% of the window price, calculated on the server.
    framed = post(customer, 'portal/price', body('frame-ok-1', '', extra={'custom_frame': 'yes', 'special_request': 'Frame 20mm narrower'}))
    assert framed['subtotal'] == '110.00' and framed['total'] == '126.50', framed
    post(customer, 'portal/price', body('frame-bad-1', '', extra={'custom_frame': 'maybe'}), 422)

    # The lead time runs from the deposit, not from acceptance.
    order = post(customer, 'portal/orders', body('order-key-1', '', name='ETA job'))
    oid = order['id']
    assert order['lead_time']['starts_on'] == 'deposit_received' and not order.get('eta')
    reviewed = post(staff, f'operations/orders/{oid}/review', {'confirm_order_number': True})
    assert not reviewed.get('eta') and not reviewed.get('deposit_paid_at')
    received = post(staff, f'operations/orders/{oid}/deposit-received')
    expected = (date.today() + timedelta(weeks=10)).isoformat()
    assert received['deposit_paid_at'] and received['eta'] in {expected, (date.today() + timedelta(weeks=10, days=1)).isoformat(),
                                                              (date.today() + timedelta(weeks=10, days=-1)).isoformat()}
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', received['eta']) and received['lead_time']['weeks'] == '10'
    seen = customer.get('/api/portal/orders').json()[0]
    assert seen['eta'] == received['eta'] and seen['deposit_paid_at'] == received['deposit_paid_at']
    assert post(staff, f'operations/orders/{oid}/deposit-received')['eta'] == received['eta']

    # Ready, then complete, without the balance being paid.
    post(staff, f'operations/orders/{oid}/supplier-order', {'reference': 'ETA supplier'})
    post(staff, 'operations/transit', {'order_ids': [oid], 'operation_key': 'eta-transit'})
    lines = [dict(line_id='1', quantity=1)]
    with patch('email_service.configuration', return_value=({'configured': False}, None)):
        ready = post(staff, 'operations/fulfilment', dict(order_id=oid, kind='arrival', operation_key='eta-arrival', lines=lines))['order']
    assert ready['status'] == 'ready' and ready['ready_at'] and customer.get('/api/portal/orders').json()[0]['status'] == 'ready'
    done = post(staff, 'operations/fulfilment', dict(order_id=oid, kind='delivery', operation_key='eta-pickup', lines=lines))['order']
    assert done['status'] == 'complete' and done['completed_at'] and done['payment_status'] == 'deposit_received'
    # Payment is still recorded afterwards.
    invoice = post(staff, 'operations/settlements', dict(order_ids=[oid], operation_key='eta-balance', rules_evidence='TEST balance after pickup',
                                                         billing_basis='all_arrived_remaining_total'))
    paid = post(staff, f"operations/invoices/{invoice['id']}/received", {'note': 'TEST paid after pickup'})
    assert paid['payment_status'] == 'received'
    final = next(o for o in staff.get('/api/operations/orders').json() if o['id'] == oid)
    assert final['status'] == 'complete' and final['payment_status'] == 'paid'
    print('PASS optional site address, custom frame +10%, ETA from deposit, ready/complete without payment gate')
