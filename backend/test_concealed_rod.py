"""Control Rod = Internal Concealed carries the Hidden tilt rod charge (+$40/sqm of billable area), once only.
Synthetic fixture only; no real SMTP or production database.
"""
import os
import tempfile
from decimal import Decimal
from pathlib import Path

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
    post(staff, 'operations/customers', dict(company='Rod only', contact_name='Test contact', email='rod@example.invalid', phone='123',
                                             company_address='Company', username='rodclient', password='test-password',
                                             customer_type='wholesale', customer_code='ROD'))
    customer.headers['Authorization'] = 'Bearer ' + post(customer, 'portal/login', {'username': 'rodclient', 'password': 'test-password'})['token']
    publish_fixture_knowledge(staff, fixture(), 'test.xlsm')
    product = next(p for p in customer.get('/api/portal/catalog').json()['products'] if p['source_code'] == 'Shutters_PVC')

    def amount(options, width='1200', height='1500'):
        body = dict(project_name='Rod', site_address='', submission_key='rod-price-0001', installation_required=False,
                    lines=[dict(window_name='W', product_id=product['id'], width_mm=width, height_mm=height, quantity=1, panel_count=2,
                                options={'colour': 'White TEST', 'fitting': 'In Fit', **options})])
        line = post(customer, 'portal/price', body)['lines'][0]
        return Decimal(line['amount']), Decimal(line['area'])

    plain, area = amount({'control_rod': 'Front Centre'})
    assert amount({})[0] == plain  # an unset rod prices like any other plain rod (the order table preview relies on this)
    concealed, _ = amount({'control_rod': 'Internal Concealed'})
    assert concealed - plain == area * 40, (plain, concealed, area)
    # Case and spacing do not hide the charge; ticking the add-on as well never charges twice.
    assert amount({'control_rod': ' internal concealed '})[0] == concealed
    assert amount({'control_rod': 'Internal Concealed', 'hidden_tilt_rod': 'yes'})[0] == concealed
    assert amount({'control_rod': 'Internal Concealed', 'hidden_tilt_rod': 'no'})[0] == concealed
    # The 1 sqm order minimum scales the extra too: a 0.5 sqm window on its own is charged as 1 sqm.
    small_plain, small_area = amount({'control_rod': 'Front Centre'}, '300', '400')
    small_concealed, _ = amount({'control_rod': 'Internal Concealed'}, '300', '400')
    assert small_area == Decimal('0.5') and small_concealed - small_plain == Decimal('40.00'), (small_area, small_plain, small_concealed)
    print('PASS internal concealed rod: +$40/sqm of billable area, once only')
