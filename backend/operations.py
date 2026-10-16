"""Customer portal and project operations. Unknown commercial rules fail closed.

Separate customer sessions never authenticate against the legacy staff API.
JSON snapshots use the existing SQLite/PostgreSQL transaction adapter.
"""
import hashlib
import json
import secrets
import time
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, field_validator

# Latest client reply overrides the earlier 20% planning baseline.
DEPOSIT_RATE = Decimal('0.60')


def deposit_amount(total):
    """Matches the 60% output in the supplied workbook, In Put!P51."""
    return str((Decimal(total) * DEPOSIT_RATE).quantize(Decimal('.01'), rounding=ROUND_UP))


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS portal_profiles(customer_id INTEGER PRIMARY KEY REFERENCES customers(id), username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS portal_sessions(token_hash TEXT PRIMARY KEY,customer_id INTEGER REFERENCES customers(id),expires_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS operations_records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,customer_id INTEGER REFERENCES customers(id),data TEXT NOT NULL);
    ''')


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Profile(Input):
    customer_id: int | None = None
    company: str = Field(min_length=1, max_length=200)
    contact_name: str = Field(min_length=1, max_length=200)
    email: str = Field(max_length=200)
    phone: str = Field(min_length=1, max_length=100)
    company_address: str = Field(min_length=1, max_length=1000)
    username: str = Field(min_length=3, max_length=100, pattern=r'^[A-Za-z0-9_.@-]+$')
    password: str = Field(min_length=8, max_length=200)

    @field_validator('email')
    @classmethod
    def valid_email(cls, v):
        from email_service import address
        return address(v)


class Login(Input):
    username: str
    password: str


class Window(Input):
    window_name: str = Field(min_length=1, max_length=200)
    product_id: int = Field(gt=0)
    width_mm: Decimal = Field(gt=0, le=20000, allow_inf_nan=False)
    height_mm: Decimal = Field(gt=0, le=20000, allow_inf_nan=False)
    quantity: int = Field(gt=0, le=10000, strict=True)
    options: dict[str, str] = Field(default_factory=dict, max_length=30)


class Project(Input):
    project_name: str = Field(min_length=1, max_length=200)
    site_address: str = Field(min_length=1, max_length=1000)
    lines: list[Window] = Field(min_length=1, max_length=200)
    submission_key: str = Field(min_length=8, max_length=100)


class PriceRule(Input):
    # Explicit configuration after the real price sheet is supplied; never seeded.
    evidence: str = Field(min_length=5, max_length=1000)
    currency: str = Field(default='NZD', pattern=r'^[A-Z]{3}$')
    tax_basis: str = Field(min_length=1, max_length=100)
    rate_per_m2: Decimal = Field(gt=0, allow_inf_nan=False)
    minimum_area: Decimal = Field(ge=0, allow_inf_nan=False)
    dimension_step_mm: int = Field(gt=0, le=1000)
    max_width_mm: int = Field(gt=0, le=20000)
    max_height_mm: int = Field(gt=0, le=20000)
    options: dict[str, dict[str, dict[str, Decimal]]] = Field(default_factory=dict)
    # Formula: (area * rate + fixed upgrades) * (1 + summed percentages/100) + installation.
    formula: Literal['area_fixed_percent_installation']
    deposit_basis: Literal['order_total']


class Supplier(Input):
    reference: str = Field(min_length=1, max_length=200)


class Batch(Input):
    order_ids: list[str] = Field(min_length=1, max_length=100)
    operation_key: str = Field(min_length=8, max_length=100)


class Quantity(Input):
    line_id: str
    quantity: int = Field(gt=0, strict=True)


class Fulfilment(Input):
    order_id: str
    kind: Literal['arrival', 'delivery']
    operation_key: str = Field(min_length=8, max_length=100)
    lines: list[Quantity] = Field(min_length=1, max_length=200)


class Credit(Input):
    customer_id: int
    source_order_ids: list[str] = Field(min_length=1, max_length=200)
    month: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    evidence: str = Field(min_length=5, max_length=2000)
    currency: str = Field(default='NZD', pattern=r'^[A-Z]{3}$')


class Settlement(Batch):
    rules_evidence: str = Field(min_length=5, max_length=1000)
    billing_basis: Literal['fully_delivered_remaining_total']


def register(app, s):
    def money(v):
        return str(Decimal(v).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

    def bodyhash(body):
        return hashlib.sha256(body.model_dump_json().encode()).hexdigest()

    def get(c, rid, kind=None):
        row = c.execute('SELECT * FROM operations_records WHERE id=?', (rid,)).fetchone()
        if not row or (kind and row['kind'] != kind):
            raise HTTPException(404, 'Record not found')
        return json.loads(row['data'])

    def records(c, kind, cid=None):
        rows = c.execute('SELECT * FROM operations_records WHERE kind=?', (kind,)).fetchall()
        return [json.loads(r['data']) for r in rows if cid is None or r['customer_id'] == cid]

    def put(c, kind, d, cid=None):
        c.execute('INSERT INTO operations_records(id,kind,customer_id,data) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                  (d['id'], kind, cid, s.dump(d)))

    def profile(c, cid):
        r = c.execute('SELECT data FROM portal_profiles WHERE customer_id=?', (cid,)).fetchone()
        if not r:
            raise HTTPException(404, 'Portal customer not found')
        return json.loads(r['data'])

    def customer_auth(credentials=Depends(s.security)):
        if not credentials or credentials.scheme.lower() != 'bearer':
            raise HTTPException(401, 'Customer sign in required')
        with s.db() as c:
            r = c.execute('SELECT * FROM portal_sessions WHERE token_hash=?',
                          (hashlib.sha256(credentials.credentials.encode()).hexdigest(),)).fetchone()
            if not r or r['expires_at'] < time.time():
                raise HTTPException(401, 'Customer session expired')
            return r['customer_id']

    def event(d, action, actor, **extra):
        d['history'].append({'action': action, 'actor': actor, 'created_at': s.now(), **extra})

    def enrich(c, d):
        return {**d, 'invoices': [i for i in records(c, 'invoice', d['customer_id']) if d['id'] in i['order_ids']]}

    def key(prefix, value):
        return prefix + hashlib.sha256(value.encode()).hexdigest()

    def replay(c, rid, digest):
        r = c.execute('SELECT data FROM operations_records WHERE id=?', (rid,)).fetchone()
        if not r:
            return None
        d = json.loads(r['data'])
        if d['request_hash'] != digest:
            raise HTTPException(409, 'Operation key already used for different data')
        return d

    def calculate(c, body):
        lines, total, currency, tax_basis, missing = [], Decimal(0), None, None, []
        for n, line in enumerate(body.lines):
            p = c.execute('SELECT data FROM products WHERE id=?', (line.product_id,)).fetchone()
            if not p or not s.catalog_product(json.loads(p['data']))['published']:
                raise HTTPException(422, 'Select an available product series')
            raw = c.execute('SELECT data FROM operations_records WHERE id=?', ('price:' + str(line.product_id),)).fetchone()
            d = {**line.model_dump(mode='json'), 'id': str(n + 1), 'arrived': 0, 'delivered': 0}
            if not raw:
                missing.append(line.product_id)
                d.update(unit_price=None, amount=None, pricing_status='rules_required')
                lines.append(d)
                continue
            rule = json.loads(raw['data'])
            if currency and (currency != rule['currency'] or tax_basis != rule['tax_basis']):
                raise HTTPException(422, 'Mixed currencies or tax bases are not supported')
            currency, tax_basis = rule['currency'], rule['tax_basis']
            if line.width_mm > rule['max_width_mm'] or line.height_mm > rule['max_height_mm']:
                raise HTTPException(422, 'Dimensions exceed confirmed production limits')
            step = Decimal(rule['dimension_step_mm'])
            from decimal import ROUND_CEILING
            w = (line.width_mm / step).to_integral_value(rounding=ROUND_CEILING) * step
            h = (line.height_mm / step).to_integral_value(rounding=ROUND_CEILING) * step
            area = max(w * h / Decimal(1000000), Decimal(rule['minimum_area']))
            fixed = percent = installation = Decimal(0)
            if set(line.options) != set(rule['options']):
                raise HTTPException(422, 'Complete exactly the configured product options')
            for option, value in line.options.items():
                charges = rule['options'].get(option, {}).get(value)
                if charges is None:
                    raise HTTPException(422, 'Unsupported product configuration')
                fixed += Decimal(charges.get('fixed', '0'))
                percent += Decimal(charges.get('percent', '0'))
                installation += Decimal(charges.get('installation', '0'))
            unit = Decimal(money((area * Decimal(rule['rate_per_m2']) + fixed) * (1 + percent / 100) + installation))
            amount = unit * line.quantity
            d.update(unit_price=money(unit), amount=money(amount), pricing_status='configured', price_snapshot=rule)
            total += amount
            lines.append(d)
        return {'lines': lines, 'total': None if missing else money(total), 'currency': currency or 'NZD',
                'tax_basis': tax_basis, 'pricing_status': 'rules_required' if missing else 'configured', 'missing_price_rules': sorted(set(missing))}

    def queue(c, cid, subject, text, nid, invoice_id=None):
        # Persist recipient and actual batch scope before any transport attempt.
        p = profile(c, cid)
        d = {'id': nid, 'customer_id': cid, 'recipient': p['email'], 'subject': subject, 'body': text,
             'status': 'pending', 'created_at': s.now(), 'invoice_id': invoice_id}
        put(c, 'notification', d, cid)
        return nid

    def deliver(nid):
        from email_service import configuration, send_email
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, nid, 'notification')
            if d['status'] != 'pending':
                return d
            if not configuration()[0]['configured']:
                d.update(status='not_configured', error='SMTP is not configured')
                put(c, 'notification', d, d['customer_id'])
                return d
            d['status'] = 'sending'
            put(c, 'notification', d, d['customer_id'])
        try:
            mid = send_email(d['recipient'], d['subject'], d['body'])
            d.update(status='sent', message_id=mid, sent_at=s.now())
        except Exception:
            # SMTP may have accepted the message before the connection failed.
            d.update(status='delivery_unknown', error='Check the sending mailbox before confirming a retry')
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            put(c, 'notification', d, d['customer_id'])
        return d

    @app.post('/api/portal/login')
    def login(body: Login):
        with s.db() as c:
            r = c.execute('SELECT * FROM portal_profiles WHERE username=?', (body.username,)).fetchone()
            if not r or not s.password_ok(body.password, r['password_hash']):
                raise HTTPException(401, 'Invalid customer credentials')
            token = secrets.token_urlsafe(32)
            c.execute('INSERT INTO portal_sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), r['customer_id'], time.time()+86400))
            return {'token': token}

    @app.post('/api/portal/logout')
    def logout(cid=Depends(customer_auth), credentials=Depends(s.security)):
        with s.db() as c:
            c.execute('DELETE FROM portal_sessions WHERE token_hash=?', (hashlib.sha256(credentials.credentials.encode()).hexdigest(),))
        return {'ok': True}

    @app.get('/api/portal/me')
    def me(cid=Depends(customer_auth)):
        with s.db() as c:
            return profile(c, cid)

    @app.get('/api/operations/customers')
    def customers(actor=Depends(s.auth)):
        with s.db() as c:
            return [json.loads(r['data']) for r in c.execute('SELECT data FROM portal_profiles')]

    @app.post('/api/operations/customers')
    def create_customer(body: Profile, actor=Depends(s.require_admin)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM portal_profiles WHERE username=?', (body.username,)).fetchone():
                raise HTTPException(409, 'Username already provisioned')
            cid = body.customer_id
            if cid:
                if not c.execute('SELECT 1 FROM customers WHERE id=?', (cid,)).fetchone():
                    raise HTTPException(404, 'Customer not found')
                if c.execute('SELECT 1 FROM portal_profiles WHERE customer_id=?', (cid,)).fetchone():
                    raise HTTPException(409, 'This customer already has its single portal account')
                c.execute('UPDATE customers SET company=? WHERE id=?', (body.company, cid))
            else:
                cid = c.execute('INSERT INTO customers(company,locale) VALUES(?,?)', (body.company, 'en')).lastrowid
            d = body.model_dump(exclude={'password'}, mode='json')
            d.update(customer_id=cid, created_at=s.now(), created_by=actor)
            c.execute('INSERT INTO portal_profiles VALUES(?,?,?,?)', (cid, body.username, s.password_hash(body.password), s.dump(d)))
            return d

    @app.post('/api/operations/pricing/{pid}')
    def configure_price(pid: int, body: PriceRule, actor=Depends(s.require_admin)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM products WHERE id=?', (pid,)).fetchone():
                raise HTTPException(404, 'Product not found')
            for choices in body.options.values():
                if not choices:
                    raise HTTPException(422, 'Option choices are required')
                for charges in choices.values():
                    if set(charges) - {'fixed', 'percent', 'installation'} or any(not v.is_finite() or v < 0 for v in charges.values()):
                        raise HTTPException(422, 'Invalid confirmed option charges')
            d = body.model_dump(mode='json')
            d.update(id='price:'+str(pid), product_id=pid, actor=actor, updated_at=s.now())
            put(c, 'price', d)
            return d

    @app.get('/api/portal/catalog')
    def catalog(cid=Depends(customer_auth)):
        with s.db() as c:
            prices = {r['product_id']: r for r in records(c, 'price')}
            products = [s.catalog_product(json.loads(r['data'])) for r in c.execute('SELECT data FROM products')]
            return {'products': [{**p, 'price_rule': prices.get(p['id'])} for p in products if p['published']],
                    'pricing_status': 'configured' if prices else 'rules_required'}

    @app.post('/api/portal/price')
    def price(body: Project, cid=Depends(customer_auth)):
        with s.db() as c:
            d = calculate(c, body)
            if d['total'] is None:
                raise HTTPException(409, 'Confirmed price sheet is required for these product series')
            return d

    @app.post('/api/portal/orders')
    def submit(body: Project, cid=Depends(customer_auth)):
        oid = key('project:', str(cid)+':'+body.submission_key)
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = replay(c, oid, bodyhash(body))
            if old:
                return enrich(c, old)
            p = profile(c, cid)
            d = {**calculate(c, body), 'id': oid, 'customer_id': cid, 'company': p['company'],
                 'contact_name': p['contact_name'], 'email': p['email'], 'phone': p['phone'],
                 'company_address': p['company_address'], 'project_name': body.project_name, 'site_address': body.site_address,
                 'status': 'pending_review', 'payment_status': 'deposit_unpaid', 'history': [], 'created_at': s.now(),
                 'request_hash': bodyhash(body)}
            event(d, 'submitted', p['username'])
            put(c, 'project', d, cid)
            return enrich(c, d)

    @app.get('/api/portal/orders')
    def portal_orders(cid=Depends(customer_auth)):
        with s.db() as c:
            return [enrich(c, d) for d in records(c, 'project', cid)]

    @app.get('/api/operations/orders')
    def orders(actor=Depends(s.auth)):
        with s.db() as c:
            return [enrich(c, d) for d in records(c, 'project')]

    @app.post('/api/operations/orders/{oid}/review')
    def review(oid: str, actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, oid, 'project')
            if d['status'] != 'pending_review':
                return enrich(c, d)
            if d['total'] is None:
                # Re-price only an unreviewed submission; reviewed snapshots stay immutable.
                b = Project(project_name=d['project_name'], site_address=d['site_address'], submission_key='repricing',
                            lines=[{k: line[k] for k in Window.model_fields} for line in d['lines']])
                d.update(calculate(c, b))
            if d['total'] is None:
                raise HTTPException(409, 'Price rules must be confirmed before review acceptance and invoicing')
            d['status'] = 'accepted'
            event(d, 'review_accepted', actor)
            inv = {'id': 'deposit:'+oid, 'customer_id': d['customer_id'], 'kind': 'deposit', 'order_ids': [oid],
                   'amount': deposit_amount(d['total']), 'currency': d['currency'], 'tax_basis': d['tax_basis'],
                   'deposit_rate': str(DEPOSIT_RATE), 'rounding': 'ROUND_UP_2DP',
                   'rule_source': 'Client reply 2026-10-15; In Put!P51',
                   'status': 'draft', 'created_at': s.now(), 'actor': actor, 'lines': [{'order_id': oid, 'amount': deposit_amount(d['total'])}]}
            put(c, 'invoice', inv, d['customer_id'])
            put(c, 'project', d, d['customer_id'])
            return enrich(c, d)

    @app.post('/api/operations/orders/{oid}/deposit-received')
    def received(oid: str, actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, oid, 'project')
            if d['status'] == 'pending_review':
                raise HTTPException(409, 'Accept technical review first')
            if d['payment_status'] == 'deposit_unpaid':
                d['payment_status'] = 'deposit_received'
                event(d, 'deposit_received', actor)
                put(c, 'project', d, d['customer_id'])
            return enrich(c, d)

    @app.post('/api/operations/orders/{oid}/supplier-order')
    def supplier_order(oid: str, body: Supplier, actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, oid, 'project')
            if d['payment_status'] != 'deposit_received':
                raise HTTPException(409, 'Confirm the deposit before supplier ordering')
            if d['status'] == 'accepted':
                d.update(status='supplier_ordered', supplier_reference=body.reference)
                event(d, 'supplier_ordered', actor, reference=body.reference)
                put(c, 'project', d, d['customer_id'])
            elif d.get('supplier_reference') != body.reference:
                raise HTTPException(409, 'Supplier order already recorded with another reference')
            return enrich(c, d)

    @app.get('/api/operations/orders/{oid}/supplier-export')
    def supplier_export(oid: str, actor=Depends(s.auth)):
        raise HTTPException(409, 'Confirmed supplier Excel template and field mapping are required')

    @app.post('/api/operations/transit')
    def transit(body: Batch, actor=Depends(s.auth)):
        rid = key('transit:', body.operation_key)
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = replay(c, rid, bodyhash(body))
            if old:
                return old
            result = []
            for oid in dict.fromkeys(body.order_ids):
                try:
                    d = get(c, oid, 'project')
                    if d['status'] == 'in_transit':
                        result.append({'order_id': oid, 'status': 'skipped', 'reason': 'Already in transit'})
                        continue
                    if d['status'] != 'supplier_ordered':
                        raise HTTPException(409, 'Only supplier-ordered projects can enter transit')
                    d['status'] = 'in_transit'
                    event(d, 'in_transit', actor)
                    put(c, 'project', d, d['customer_id'])
                    result.append({'order_id': oid, 'status': 'success'})
                except HTTPException as e:
                    result.append({'order_id': oid, 'status': 'failed', 'reason': e.detail})
            d = {'id': rid, 'request_hash': bodyhash(body), 'results': result}
            put(c, 'batch', d)
            return d

    @app.post('/api/operations/fulfilment')
    def fulfilment(body: Fulfilment, actor=Depends(s.auth)):
        rid = key('fulfilment:', body.operation_key)
        nid = None
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = replay(c, rid, bodyhash(body))
            if old:
                return old
            d = get(c, body.order_id, 'project')
            if d['status'] not in ('in_transit', 'partially_arrived', 'arrived', 'partially_delivered', 'delivered'):
                raise HTTPException(409, 'Record supplier order and transit before fulfilment')
            if len({line.line_id for line in body.lines}) != len(body.lines):
                raise HTTPException(422, 'Each line may occur only once per batch')
            field = 'arrived' if body.kind == 'arrival' else 'delivered'
            scope = []
            for q in body.lines:
                line = next((l for l in d['lines'] if l['id'] == q.line_id), None)
                if not line or line[field]+q.quantity > (line['quantity'] if field == 'arrived' else line['arrived']):
                    raise HTTPException(422, 'Quantity exceeds ordered or arrived quantity')
                line[field] += q.quantity
                scope.append({'line_id': q.line_id, 'window_name': line['window_name'], 'quantity': q.quantity})
            if all(l['delivered'] == l['quantity'] for l in d['lines']):
                d['status'] = 'delivered'
            elif any(l['delivered'] for l in d['lines']):
                d['status'] = 'partially_delivered'
            elif all(l['arrived'] == l['quantity'] for l in d['lines']):
                d['status'] = 'arrived'
            else:
                d['status'] = 'partially_arrived'
            # Separate progress fields retain arrival state even during partial delivery.
            d['arrival_status'] = 'arrived' if all(l['arrived'] == l['quantity'] for l in d['lines']) else 'partially_arrived'
            d['delivery_status'] = 'delivered' if all(l['delivered'] == l['quantity'] for l in d['lines']) else ('partially_delivered' if any(l['delivered'] for l in d['lines']) else 'not_delivered')
            event(d, body.kind, actor, batch_id=rid, lines=scope)
            put(c, 'project', d, d['customer_id'])
            if body.kind == 'arrival':
                nid = queue(c, d['customer_id'], 'VERA arrival: '+d['project_name'],
                            'This batch has arrived:\n'+'\n'.join(f"{l['window_name']}: {l['quantity']}" for l in scope)+'\nPlease contact VERA to arrange collection or installation.', 'arrival:'+rid)
            result = {'id': rid, 'request_hash': bodyhash(body), 'order': enrich(c, d), 'notification_id': nid}
            put(c, 'fulfilment', result, d['customer_id'])
        if nid:
            result['notification'] = deliver(nid)
        return result

    @app.get('/api/operations/notifications')
    def notifications(actor=Depends(s.auth)):
        with s.db() as c:
            return records(c, 'notification')

    @app.post('/api/operations/notifications/{nid}/retry')
    def retry(nid: str, actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, nid, 'notification')
            if d['status'] == 'delivery_unknown' or d['status'] == 'sending':
                raise HTTPException(409, 'Check the sending mailbox; delivery may have succeeded')
            if d['status'] == 'not_configured':
                d['status'] = 'pending'
                put(c, 'notification', d, d['customer_id'])
        return deliver(nid)

    @app.get('/api/operations/invoices')
    def invoices(actor=Depends(s.auth)):
        with s.db() as c:
            return records(c, 'invoice')

    @app.post('/api/operations/invoices/{iid}/send')
    def send_invoice(iid: str, actor=Depends(s.auth)):
        nid = 'invoice-mail:'+iid
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, iid, 'invoice')
            row = c.execute('SELECT 1 FROM operations_records WHERE id=?', (nid,)).fetchone()
            if not row:
                text = 'VERA invoice '+iid+'\n'+d['currency']+' '+d['amount']+'\n'+'\n'.join(l['order_id']+': '+l['amount'] for l in d['lines'])
                queue(c, d['customer_id'], 'VERA invoice '+iid, text, nid, iid)
            d['notification_id'] = nid
            put(c, 'invoice', d, d['customer_id'])
        n = deliver(nid)
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, iid, 'invoice')
            d['status'] = n['status']
            put(c, 'invoice', d, d['customer_id'])
        return d

    @app.post('/api/operations/rebates')
    def credit(body: Credit, actor=Depends(s.require_admin)):
        # An explicit confirmed result imports the monthly calculation; no fabricated ladder.
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            profile(c, body.customer_id)
            source = sorted(set(body.source_order_ids))
            for oid in source:
                d = get(c, oid, 'project')
                if d['customer_id'] != body.customer_id or d['currency'] != body.currency:
                    raise HTTPException(422, 'Rebate sources must belong to this company and currency')
            existing = records(c, 'rebate', body.customer_id)
            if any(set(source) & set(d['source_order_ids']) for d in existing):
                raise HTTPException(409, 'An order rebate has already been calculated')
            d = body.model_dump(mode='json')
            d.update(id='rebate:'+secrets.token_hex(12), remaining=money(body.amount), used='0.00', status='confirmed_import', created_at=s.now(), actor=actor, allocations=[])
            d['amount'] = money(body.amount)
            if Decimal(d['amount']) <= 0:
                raise HTTPException(422, 'Rebate must round to a positive amount')
            put(c, 'rebate', d, body.customer_id)
            return d

    @app.get('/api/operations/rebates')
    def rebates(actor=Depends(s.auth)):
        with s.db() as c:
            return {'calculation_status': 'confirmed_monthly_rules_required', 'credits': records(c, 'rebate')}

    @app.post('/api/operations/settlements')
    def settle(body: Settlement, actor=Depends(s.auth)):
        iid = key('balance:', body.operation_key)
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = replay(c, iid, bodyhash(body))
            if old:
                return old
            orders = [get(c, oid, 'project') for oid in dict.fromkeys(body.order_ids)]
            if len({(d['customer_id'], d['currency'], d['tax_basis']) for d in orders}) != 1:
                raise HTTPException(422, 'Combine only one company, currency and tax basis')
            if any(d['status'] != 'delivered' or d['payment_status'] != 'deposit_received' for d in orders):
                raise HTTPException(409, 'Partial-arrival billing rules are unconfirmed; only fully delivered paid-deposit orders are eligible')
            if any(d.get('balance_invoice_id') for d in orders):
                raise HTTPException(409, 'An order already has a balance invoice')
            cid, currency = orders[0]['customer_id'], orders[0]['currency']
            lines = []
            for d in orders:
                deposit = get(c, 'deposit:'+d['id'], 'invoice')
                lines.append({'order_id': d['id'], 'amount': money(Decimal(d['total'])-Decimal(deposit['amount']))})
            gross = sum((Decimal(l['amount']) for l in lines), Decimal(0))
            remaining, allocations = gross, []
            for r in sorted(records(c, 'rebate', cid), key=lambda x: (x['month'], x['id'])):
                # Use only next-period confirmed credits; never use this month's credit early.
                if r['currency'] != currency or r['month'] >= s.business_now().strftime('%Y-%m'):
                    continue
                used = min(remaining, Decimal(r['remaining']))
                if used <= 0:
                    continue
                r['remaining'] = money(Decimal(r['remaining'])-used)
                r['used'] = money(Decimal(r['used'])+used)
                r['allocations'].append({'invoice_id': iid, 'amount': money(used)})
                put(c, 'rebate', r, cid)
                remaining -= used
                allocations.append({'rebate_id': r['id'], 'amount': money(used)})
            d = {'id': iid, 'customer_id': cid, 'kind': 'balance', 'order_ids': [o['id'] for o in orders], 'lines': lines,
                 'currency': currency, 'tax_basis': orders[0]['tax_basis'], 'gross': money(gross), 'amount': money(remaining),
                 'rebate_allocations': allocations, 'status': 'draft', 'created_at': s.now(), 'actor': actor,
                 'request_hash': bodyhash(body), 'rules_evidence': body.rules_evidence}
            put(c, 'invoice', d, cid)
            for o in orders:
                o['balance_invoice_id'] = iid
                event(o, 'balance_invoice_created', actor, invoice_id=iid)
                put(c, 'project', o, cid)
            return d

    @app.get('/api/portal/consumption')
    def consumption(cid=Depends(customer_auth)):
        with s.db() as c:
            # Separate ordered value from confirmed receipts; balance receipts are not inferred.
            orders = records(c, 'project', cid)
            return {'orders': [enrich(c, d) for d in orders], 'invoices': records(c, 'invoice', cid),
                    'rebates': records(c, 'rebate', cid), 'statistics_status': 'consumption_basis_requires_confirmation'}
