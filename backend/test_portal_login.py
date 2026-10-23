"""Admin opens or resets an existing customer's portal login; old password and sessions stop working."""
import os
import tempfile

with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND'] = 'sqlite'
    os.environ['VERA_STORAGE_BACKEND'] = 'local'
    os.environ['VERA_DB'] = os.path.join(folder, 'portal-login.db')
    from service import app
    from fastapi.testclient import TestClient

    admin, staff, portal = TestClient(app), TestClient(app), TestClient(app)

    def call(client, path, body=None, expected=200):
        response = client.get(f'/api/{path}') if body is None else client.post(f'/api/{path}', json=body)
        assert response.status_code == expected, (path, response.status_code, response.text)
        return response.json() if response.content else None

    token = call(admin, 'auth/login', {'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})['token']
    admin.headers['Authorization'] = 'Bearer ' + token
    call(admin, 'users', {'username': 'staff', 'name': 'Staff', 'password': 'staff-password', 'role': 'staff'})
    staff.headers['Authorization'] = 'Bearer ' + call(staff, 'auth/login', {'username': 'staff', 'password': 'staff-password'})['token']

    def provision(name):
        return call(admin, 'operations/customers', {
            'company': name, 'contact_name': 'Test User', 'email': name + '@example.invalid', 'phone': '12345',
            'company_address': 'Test address', 'username': name, 'password': 'first-password',
            'customer_type': 'wholesale', 'customer_code': name.upper()})

    first, second = provision('alpha'), provision('beta')
    portal.headers['Authorization'] = 'Bearer ' + call(portal, 'portal/login', {'username': 'alpha', 'password': 'first-password'})['token']
    assert portal.get('/api/portal/me').status_code == 200

    path = f"operations/customers/{first['customer_id']}/portal-login"
    call(staff, path, {'username': 'alpha-new', 'password': 'second-password'}, 403)
    call(admin, path, {'username': 'beta', 'password': 'second-password'}, 409)
    call(admin, path, {'username': 'alpha-new', 'password': 'short'}, 422)
    call(admin, 'operations/customers/999999/portal-login', {'username': 'nobody', 'password': 'second-password'}, 404)

    result = call(admin, path, {'username': 'alpha-new', 'password': 'second-password'})
    assert result == {'customer_id': first['customer_id'], 'username': 'alpha-new', 'portal_login': 'active'}
    assert 'password' not in str(admin.get('/api/operations/customers').json())
    listed = next(c for c in admin.get('/api/operations/customers').json() if c['customer_id'] == first['customer_id'])
    assert listed['username'] == 'alpha-new' and listed['portal_login'] == 'active' and listed['company'] == 'alpha'

    assert portal.get('/api/portal/me').status_code == 401  # the earlier session no longer works
    call(TestClient(app), 'portal/login', {'username': 'alpha', 'password': 'first-password'}, 401)
    call(TestClient(app), 'portal/login', {'username': 'alpha-new', 'password': 'first-password'}, 401)
    assert call(TestClient(app), 'portal/login', {'username': 'alpha-new', 'password': 'second-password'})['token']
    assert call(TestClient(app), 'portal/login', {'username': 'beta', 'password': 'first-password'})['token']
    print('PASS portal login reset: admin only, unique username, old password and sessions revoked, profile kept')
