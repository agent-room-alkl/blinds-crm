"""Shipment batches: named, ETA propagation to orders, auto in-transit, arrival -> Ready + draft balance invoices.
Synthetic fixture only; no real SMTP or production database.
"""
import os
import tempfile
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

    staff = TestClient(app)
    clients = {'A': TestClient(app), 'B': TestClient(app)}

    def post(client, path, body=None, status=200):
        r = client.post('/api/' + path, json=body)
        assert r.status_code == status, (path, r.status_code, r.text)
        return r.json()

    staff.headers['Authorization'] = 'Bearer ' + post(staff, 'auth/login', {'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})['token']
    for key, client in clients.items():
        post(staff, 'operations/customers', dict(company=f'Batch {key}', contact_name='Test contact', email=f'batch{key}@example.invalid', phone='123',
                                                 company_address='Company', username=f'batch{key}', password='test-password',
                                                 customer_type='wholesale', customer_code=f'B{key}'))
        client.headers['Authorization'] = 'Bearer ' + post(client, 'portal/login', {'username': f'batch{key}', 'password': 'test-password'})['token']
    publish_fixture_knowledge(staff, fixture(), 'test.xlsm')
    product = next(p for p in clients['A'].get('/api/portal/catalog').json()['products'] if p['source_code'] == 'Shutters_PVC')

    def ordered(who, name):
        body = dict(project_name=name, site_address='', submission_key=f'sub-{who}-{name}', installation_required=False,
                    lines=[dict(window_name='W', product_id=product['id'], width_mm='1000', height_mm='1000', quantity=1, panel_count=1,
                                options={'colour': 'White TEST', 'fitting': 'In Fit'})])
        oid = post(clients[who], 'portal/orders', body)['id']
        post(staff, f'operations/orders/{oid}/review', {'confirm_order_number': True})
        post(staff, f'operations/orders/{oid}/deposit-received')
        post(staff, f'operations/orders/{oid}/supplier-order', {'reference': 'ref-' + name})
        return oid

    a1, a2, b1 = ordered('A', 'Alpha one'), ordered('A', 'Alpha two'), ordered('B', 'Bravo one')
    extra = ordered('B', 'Bravo two')
    assert {c['id'] for c in staff.get('/api/operations/shipments/candidates').json()} == {a1, a2, b1, extra}
    assert clients['A'].get('/api/operations/shipments').status_code == 401

    batch = post(staff, 'operations/shipments', {'name': 'P4261008', 'order_ids': [a1, a2, b1], 'eta': '2026-12-20', 'operation_key': 'batch-key-0001'})
    assert batch['name'] == 'P4261008' and batch['eta'] == '2026-12-20' and batch['status'] == 'in_transit'
    assert post(staff, 'operations/shipments', {'name': 'P4261008', 'order_ids': [a1, a2, b1], 'eta': '2026-12-20', 'operation_key': 'batch-key-0001'})['id'] == batch['id']
    post(staff, 'operations/shipments', {'name': 'p4261008', 'order_ids': [extra], 'operation_key': 'batch-key-0002'}, 409)  # names are unique
    post(staff, 'operations/shipments', {'name': 'P-again', 'order_ids': [a1], 'operation_key': 'batch-key-0003'}, 409)       # already batched
    post(staff, 'operations/shipments', {'name': 'bad', 'order_ids': [extra], 'eta': 'next week', 'operation_key': 'batch-key-0004'}, 422)
    assert {c['id'] for c in staff.get('/api/operations/shipments/candidates').json()} == {extra}

    orders = {o['id']: o for o in staff.get('/api/operations/orders').json()}
    assert all(orders[i]['status'] == 'in_transit' and orders[i]['eta'] == '2026-12-20' and orders[i]['batch_name'] == 'P4261008' for i in (a1, a2, b1))
    seen = clients['A'].get('/api/portal/orders').json()
    assert {o['id'] for o in seen} == {a1, a2} and all(o['batch_name'] == 'P4261008' and o['eta'] == '2026-12-20' and 'shipment_id' not in o for o in seen)

    # A new ETA reaches every order in the batch and is recorded where the customer can see it.
    moved = post(staff, f"operations/shipments/{batch['id']}/eta", {'eta': '2027-01-10'})
    assert moved['eta'] == '2027-01-10' and set(moved['updated_order_ids']) == {a1, a2, b1}
    a_view = next(o for o in clients['A'].get('/api/portal/orders').json() if o['id'] == a1)
    assert a_view['eta'] == '2027-01-10'
    update = [h for h in a_view['history'] if h['action'] == 'eta_updated'][-1]
    assert update['previous'] == '2026-12-20' and update['eta'] == '2027-01-10'
    post(staff, f"operations/shipments/{batch['id']}/eta", {'eta': '31/12/2026'}, 422)
    # A later deposit never overwrites the batch date.
    assert next(o for o in staff.get('/api/operations/orders').json() if o['id'] == b1)['eta'] == '2027-01-10'

    listed = staff.get('/api/operations/shipments').json()
    assert len(listed) == 1 and listed[0]['name'] == 'P4261008' and [o['id'] for o in listed[0]['orders']] == [a1, a2, b1]

    # Costing a batch needs each order's factory price first; the message names orders, not internal ids.
    blocked = post(staff, f"operations/shipments/{batch['id']}/costs", {'freight_land': '30.00', 'freight_sea': '60.00'}, 409)
    assert 'project:' not in blocked['detail'] and 'BA-Alpha one' in blocked['detail'] and 'BB-Bravo one' in blocked['detail'], blocked
    assert all(o['factory_price_usd'] is None and o['freight_cost'] is None for o in staff.get('/api/operations/shipments').json()[0]['orders'])

    # Costs keep working on a named batch.
    for oid in (a1, a2, b1):
        post(staff, f'operations/orders/{oid}/purchase-cost', {'factory_price_usd': '100.00'})
    costed = post(staff, f"operations/shipments/{batch['id']}/costs", {'freight_land': '30.00', 'freight_sea': '60.00'})
    assert costed['name'] == 'P4261008' and sum(float(x) for x in costed['freight_shares']) == 90.0
    shown = {o['id']: o for o in staff.get('/api/operations/shipments').json()[0]['orders']}
    assert all(shown[i]['factory_price_usd'] == '100.00' and shown[i]['freight_cost'] and shown[i]['duty_basis'] == 'estimate' for i in (a1, a2, b1))
    assert round(sum(float(shown[i]['freight_cost']) for i in (a1, a2, b1)), 2) == 90.0

    # Arrival: every order Ready, one balance draft per company, customers notified once.
    with patch('email_service.configuration', return_value=({'configured': False}, None)):
        arrived = post(staff, f"operations/shipments/{batch['id']}/arrive")
        again = post(staff, f"operations/shipments/{batch['id']}/arrive")
    assert arrived['status'] == 'arrived' and len(arrived['invoice_ids']) == 2 and again['invoice_ids'] == arrived['invoice_ids']
    orders = {o['id']: o for o in staff.get('/api/operations/orders').json()}
    assert all(orders[i]['status'] == 'ready' and orders[i]['ready_at'] and orders[i]['balance_invoice_id'] in arrived['invoice_ids'] for i in (a1, a2, b1))
    assert orders[extra]['status'] == 'supplier_ordered'
    invoices = {i['id']: i for i in staff.get('/api/operations/invoices').json()}
    drafts = [invoices[i] for i in arrived['invoice_ids']]
    assert {tuple(sorted(d['order_ids'])) for d in drafts} == {tuple(sorted([a1, a2])), (b1,)} and all(d['status'] == 'draft' and d['kind'] == 'balance' for d in drafts)
    assert len([n for n in staff.get('/api/operations/notifications').json() if n['id'].startswith('arrival:' + batch['id'])]) == 3
    # Pickup is still its own step and does not wait for payment.
    done = post(staff, 'operations/fulfilment', dict(order_id=b1, kind='delivery', operation_key='batch-pickup-1', lines=[dict(line_id='1', quantity=1)]))['order']
    assert done['status'] == 'complete' and done['payment_status'] == 'deposit_received'
    print('PASS shipment batches: named, unique, ETA propagation, auto in-transit, arrival to Ready with per-company balance drafts')
