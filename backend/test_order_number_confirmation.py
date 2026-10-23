"""Regression checks for generated, hidden, editable, and confirmed order numbers."""
import os
import re
import tempfile

with tempfile.TemporaryDirectory() as folder:
    os.environ['VERA_DB_BACKEND'] = 'sqlite'
    os.environ['VERA_STORAGE_BACKEND'] = 'local'
    os.environ['VERA_DB'] = os.path.join(folder, 'order-numbers.db')
    from service import app
    from fastapi.testclient import TestClient

    staff, wholesale, retail = TestClient(app), TestClient(app), TestClient(app)

    def call(client, method, path, body=None, expected=200):
        response = client.get(f'/api/{path}') if method == 'get' else client.post(f'/api/{path}', json=body)
        assert response.status_code == expected, (path, response.status_code, response.text)
        return response.json() if response.content else None

    admin = call(staff, 'post', 'auth/login', {'username':'dylan','password':os.getenv('VERA_DEMO_PASSWORD','vera-demo')})
    staff.headers['Authorization'] = 'Bearer '+admin['token']
    customers = []
    for client, kind, username in [(wholesale,'wholesale','wholesale-test'),(retail,'retail','retail-test')]:
        customer = call(staff,'post','operations/customers',{
            'company':username,'contact_name':'Test User','email':username+'@example.invalid','phone':'12345',
            'company_address':'Test address','username':username,'password':'test-password',
            'customer_type':kind,'customer_code':'TEST' if kind=='wholesale' else None})
        customers.append(customer)
        session = call(client,'post','portal/login',{'username':username,'password':'test-password'})
        client.headers['Authorization'] = 'Bearer '+session['token']

    price = {'evidence':'TEST ONLY','currency':'NZD','tax_basis':'test','rate_per_m2':'100','minimum_area':'1',
             'dimension_step_mm':1,'max_width_mm':3000,'max_height_mm':3000,'options':{},
             'formula':'area_fixed_percent_installation','deposit_basis':'order_total'}
    call(staff,'post','operations/pricing/1',price)
    order_body = {'project_name':'Test Job','site_address':'Test Site','submission_key':'submission-0001',
                  'lines':[{'window_name':'Window 1','product_id':1,'width_mm':1000,'height_mm':1000,'quantity':1,'options':{}}]}

    wholesale_pending = call(wholesale,'post','portal/orders',order_body)
    assert wholesale_pending['order_number_confirmed'] is False and 'order_number' not in wholesale_pending
    admin_orders = call(staff,'get','operations/orders')
    wholesale_order = next(order for order in admin_orders if order['id']==wholesale_pending['id'])
    assert wholesale_order['order_number']=='TEST-Test Job'
    assert call(wholesale,'get','portal/orders')[0].get('order_number') is None
    assert call(wholesale,'post',f"operations/orders/{wholesale_pending['id']}/order-number",{'order_number':'x'},401)
    call(staff,'post',f"operations/orders/{wholesale_pending['id']}/review",{'confirm_order_number':False},409)

    retail_pending = call(retail,'post','portal/orders',{**order_body,'project_name':'Retail Job','submission_key':'submission-0002'})
    retail_order = next(order for order in call(staff,'get','operations/orders') if order['id']==retail_pending['id'])
    assert re.fullmatch(r'R\d{6}\d{2}A',retail_order['order_number']), retail_order['order_number']
    assert 'order_number' not in retail_pending and call(retail,'get','portal/orders')[0].get('order_number') is None

    edited_number = 'TEST-Edited Job'
    saved = call(staff,'post',f"operations/orders/{wholesale_pending['id']}/order-number",{'order_number':edited_number})
    assert saved['order_number']==edited_number and saved['order_number_confirmed'] is False
    call(staff,'post',f"operations/orders/{retail_pending['id']}/order-number",{'order_number':edited_number},409)
    confirmed = call(staff,'post',f"operations/orders/{wholesale_pending['id']}/review",{
        'order_number':edited_number,'confirm_order_number':True})
    assert confirmed['status']=='accepted' and confirmed['order_number_confirmed'] is True
    assert call(wholesale,'get','portal/orders')[0]['order_number']==edited_number
    call(staff,'post',f"operations/orders/{wholesale_pending['id']}/order-number",{'order_number':'after-accept'},409)
    print('PASS order number flow: customer-type generation, portal hiding, admin edit, duplicate guard, mandatory confirmation, and post-confirm visibility')
