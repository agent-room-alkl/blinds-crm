"""Opening Style decides the track add-on: Tracked Bifold +$350, Tracked Sliding +$400, Hinged neither.
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
    post(staff, 'operations/customers', dict(company='Track only', contact_name='Test contact', email='track@example.invalid', phone='123',
                                             company_address='Company', username='trackclient', password='test-password',
                                             customer_type='wholesale', customer_code='TRK'))
    customer.headers['Authorization'] = 'Bearer ' + post(customer, 'portal/login', {'username': 'trackclient', 'password': 'test-password'})['token']
    publish_fixture_knowledge(staff, fixture(), 'test.xlsm')
    product = next(p for p in customer.get('/api/portal/catalog').json()['products'] if p['source_code'] == 'Shutters_PVC')

    def body(options, key='track-price-0001', name='Track'):
        return dict(project_name=name, site_address='', submission_key=key, installation_required=False,
                    lines=[dict(window_name='W', product_id=product['id'], width_mm='1200', height_mm='1500', quantity=1, panel_count=2,
                                options={'colour': 'White TEST', 'fitting': 'In Fit', **options})])

    def line(options):
        return post(customer, 'portal/price', body(options))['lines'][0]

    hinged = Decimal(line({'opening_style': 'Hinged'})['amount'])
    bifold = line({'opening_style': 'Tracked Bifold'})
    sliding = line({'opening_style': 'Tracked Sliding'})
    assert Decimal(bifold['amount']) - hinged == 350 and bifold['options']['tracked_bifold'] == 'yes', bifold
    assert Decimal(sliding['amount']) - hinged == 400 and sliding['options']['tracked_sliding'] == 'yes', sliding
    # The Opening Style wins over a stale or contradicting add-on choice, so only one track is ever charged.
    assert Decimal(line({'opening_style': 'Tracked Bifold', 'tracked_sliding': 'yes', 'tracked_bifold': 'no'})['amount']) == Decimal(bifold['amount'])
    assert Decimal(line({'opening_style': 'Hinged', 'tracked_bifold': 'yes'})['amount']) == hinged
    # No Opening Style keeps the add-on as chosen.
    assert Decimal(line({'tracked_bifold': 'yes'})['amount']) == Decimal(bifold['amount'])
    # The submitted order keeps the add-on, so review, exports and invoices see it too.
    saved = post(customer, 'portal/orders', body({'opening_style': 'Tracked Bifold'}, key='track-order-0001', name='Track order'))
    assert saved['lines'][0]['options'].get('tracked_bifold') == 'yes' and 'tracked_sliding' not in saved['lines'][0]['options'], saved['lines'][0]
    print('PASS opening style sets the track add-on: bifold +$350, sliding +$400, hinged none')
