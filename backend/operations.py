"""Customer portal and project operations. Unknown commercial rules fail closed.

Separate customer sessions never authenticate against the legacy staff API.
JSON snapshots use the existing SQLite/PostgreSQL transaction adapter.
"""
import hashlib
import re
import base64
import json
import secrets
import time
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, field_validator

# Latest client reply overrides the earlier 20% planning baseline.
DEPOSIT_RATE = Decimal('0.60')

# Canonical VERA Deluxe (Ashwood) configuration schema
# Single source of truth: used by product records and pricing rules
# Stain colours 61-70, louver sizes 63/76/89/114mm, 11 fields total
DELUXE_SCHEMA = [
    {
        'key': 'colour',
        'label_zh': '颜色',
        'label_en': 'Colour',
        'choices': [
            'Golden Oak 61', 'Fruitwood 62', 'Old Mahogany 63', 'Coffee Bean 64',
            'BlackWalnut 65', 'Light Ash 66', 'Limed 67', 'Natural 68',
            'Rustic Gray 69', 'Provence Blue 70'
        ],
        'required': True,
        'type': 'select'
    },
    {
        'key': 'frame',
        'label_zh': '框型',
        'label_en': 'Frame',
        'choices': [],
        'required': False,
        'type': 'select'
    },
    {
        'key': 'louver_size',
        'label_zh': '叶片尺寸',
        'label_en': 'Louver size',
        'choices': ['63mm', '76mm', '89mm', '114mm'],
        'required': True,
        'type': 'select'
    },
    {
        'key': 'control_rod',
        'label_zh': '控制杆',
        'label_en': 'Control rod',
        'choices': [],
        'required': False,
        'type': 'select'
    },
    {
        'key': 'opening_style',
        'label_zh': '开合方式',
        'label_en': 'Opening style',
        'choices': [],
        'required': False,
        'type': 'text'
    },
    {
        'key': 'layout_code',
        'label_zh': '布局代码',
        'label_en': 'Layout code',
        'choices': [],
        'required': False,
        'type': 'text'
    },
    {
        'key': 'vt_post',
        'label_zh': '竖柱',
        'label_en': 'Vertical post',
        'choices': [],
        'required': False,
        'type': 'text'
    },
    {
        'key': 'ht_post',
        'label_zh': '横柱',
        'label_en': 'Horizontal post',
        'choices': [],
        'required': False,
        'type': 'text'
    },
    {
        'key': 'midrail',
        'label_zh': '中横档',
        'label_en': 'Midrail',
        'choices': [],
        'required': False,
        'type': 'text'
    },
    {
        'key': 'fitting',
        'label_zh': '安装尺寸类型',
        'label_en': 'Fitting',
        'choices': [],
        'required': False,
        'type': 'select'
    },
    {
        'key': 'special_request',
        'label_zh': '特殊要求',
        'label_en': 'Special request',
        'choices': [],
        'required': False,
        'type': 'text'
    }
]


def deposit_amount(total):
    """Matches the 60% output in the supplied workbook, In Put!P51."""
    return str((Decimal(total) * DEPOSIT_RATE).quantize(Decimal('.01'), rounding=ROUND_UP))


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS portal_profiles(customer_id INTEGER PRIMARY KEY REFERENCES customers(id), username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS portal_sessions(token_hash TEXT PRIMARY KEY,customer_id INTEGER REFERENCES customers(id),expires_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS operations_records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,customer_id INTEGER REFERENCES customers(id),data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS providers(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,contact_email TEXT,notes TEXT,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS provider_templates(id INTEGER PRIMARY KEY AUTOINCREMENT,provider_id INTEGER REFERENCES providers(id),name TEXT NOT NULL,sheet_name TEXT NOT NULL,column_mappings TEXT NOT NULL,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS order_providers(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id TEXT NOT NULL,provider_id INTEGER REFERENCES providers(id),template_id INTEGER,is_preferred INTEGER DEFAULT 0,assigned_at TEXT NOT NULL);
    ''')
    
    # Migrate legacy VERA_Ashwood_display to VERA_Ashwood_provisional
    # On legacy DBs, Ashwood was created with orderable=False, scope=website_only, and empty configuration_schema
    # This migration brings it up to the current state: orderable, website_and_template scope, and the real 11-field schema
    import json
    
    # Use the canonical DELUXE_SCHEMA defined at module level
    
    # Migrate any legacy Ashwood products (idempotent)
    for row in c.execute('SELECT id, data FROM products').fetchall():
        product = json.loads(row['data'])
        
        # Handle both old (VERA_Ashwood_display) and current (VERA_Ashwood_provisional) codes
        if product.get('source_code') in ('VERA_Ashwood_display', 'VERA_Ashwood_provisional'):
            # Always update to current code
            product['source_code'] = 'VERA_Ashwood_provisional'
            product['orderable'] = True
            product['scope'] = 'website_and_template'
            product['published'] = True  # Ensure published stays true
            product['description_zh'] = '官网展示系列。当前为占位价 1.00/m²，严禁报价给客户。'
            product['description_en'] = 'Website collection. Current placeholder rate 1.00/m² must not be quoted to customers.'
            
            # Always set the complete 11-field schema (idempotent repair)
            product['configuration_schema'] = DELUXE_SCHEMA
            
            # Preserve these fields from the original row
            # portal_only, sample, warranty_years, content_source, id stay unchanged
            
            c.execute('UPDATE products SET data=? WHERE id=?', (json.dumps(product, ensure_ascii=False), row['id']))


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
    panel_count: int = Field(default=1, gt=0, le=100, strict=True)
    options: dict[str, str] = Field(default_factory=dict, max_length=30)


class Project(Input):
    project_name: str = Field(min_length=1, max_length=200)
    site_address: str = Field(min_length=1, max_length=1000)
    lines: list[Window] = Field(min_length=1, max_length=200)
    submission_key: str = Field(min_length=8, max_length=100)
    installation_required: bool = False


class TemplateUpload(Input):
    filename: str = Field(min_length=1,max_length=200)
    content_base64: str = Field(min_length=1,max_length=14000000)


class ProfileEdit(Input):
    company: str = Field(min_length=1,max_length=200)
    contact_name: str = Field(min_length=1,max_length=200)
    email: str
    phone: str = Field(min_length=1,max_length=100)
    company_address: str = Field(min_length=1,max_length=1000)

    @field_validator('email')
    @classmethod
    def valid_email(cls,v):
        from email_service import address
        return address(v)


class LineAdjustment(Input):
    line_id: str
    discount: Decimal = Field(default=Decimal(0),ge=0,le=1,allow_inf_nan=False)
    product_surcharge: Decimal = Field(default=Decimal(0),ge=0,allow_inf_nan=False)
    installation_surcharge: Decimal = Field(default=Decimal(0),ge=0,allow_inf_nan=False)


class Adjustments(Input):
    lines: list[LineAdjustment] = Field(max_length=200)
    note: str = Field(min_length=5,max_length=1000)

def column_number(value):
    if not re.fullmatch(r'[A-Z]{1,3}', value):
        raise HTTPException(422, 'Invalid Excel column')
    number = 0
    for letter in value:
        number = number * 26 + ord(letter) - 64
    if number > 16384:
        raise HTTPException(422, 'Excel column exceeds XFD')
    return number


def validate_template(sheet_name, mappings):
    if not sheet_name.strip() or len(sheet_name) > 31 or re.search(r"[\\/?:*\[\]\x00-\x1f]", sheet_name) or sheet_name.startswith("'") or sheet_name.endswith("'"):
        raise HTTPException(422, 'Invalid Excel sheet name')
    columns = [column_number(value) for value in mappings.values()]
    if len(set(columns)) != len(columns):
        raise HTTPException(422, 'Duplicate Excel columns')


class ProviderCreate(Input):
    name: str = Field(min_length=1, max_length=200)
    contact_email: str = Field(default='', max_length=200)
    notes: str = Field(default='', max_length=2000)

class ProviderEdit(Input):
    name: str = Field(min_length=1, max_length=200)
    contact_email: str = Field(default='', max_length=200)
    notes: str = Field(default='', max_length=2000)
    active: bool

class ProviderTemplateCreate(Input):
    provider_id: int
    name: str = Field(min_length=1, max_length=200)
    sheet_name: str = Field(min_length=1, max_length=100)
    column_mappings: dict[str, str]  # field_name -> column_letter

class OrderProviderAssignment(Input):
    provider_id: int
    template_id: int | None = None
    is_preferred: bool = Field(default=False)

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


class Receipt(Input):
    note: str = Field(min_length=3,max_length=1000)


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

    def portal_view(d):
        # Customers see their calculated prices, never the complete private source matrix.
        return {**{k:v for k,v in d.items() if k!='request_hash'},
                'lines':[{k:v for k,v in line.items() if k!='price_snapshot'} for line in d['lines']]}

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

    def calculate(c, body, adjustments=None):
        active = c.execute('SELECT data FROM operations_records WHERE id=?',('template-current',)).fetchone()
        if active:
            template_id = json.loads(active['data'])['template_id']
            template = get(c,template_id,'template')
            rules = {p['source_code']:p for p in template['products']}
            product_rows = {r['id']:json.loads(r['data']) for r in c.execute('SELECT * FROM products')}
            
            # Synthesize or update provisional Ashwood rule from Basswood template
            basswood_rule = rules.get('Shutters_Basswood')
            if basswood_rule:
                existing_deluxe = rules.get('VERA_Ashwood_provisional')
                # Create or update the rule to use the canonical DELUXE_SCHEMA
                # This ensures product schema and rule schema stay in sync
                # Also fixes any existing rules that were created with the 2-field minimal schema
                if not existing_deluxe or len(existing_deluxe.get('schema', [])) != 11:
                    rules['VERA_Ashwood_provisional'] = {
                        **basswood_rule,
                        'source_code': 'VERA_Ashwood_provisional',
                        'rate_per_m2': '1.00',
                        'provisional': True,
                        'status': 'provisional_placeholder',
                        'warnings': ['Placeholder price 1.00/m² must not be quoted to customers'],
                        'schema': DELUXE_SCHEMA,  # Full 11-field schema (same as product)
                        'options': {}  # No pricing options for provisional
                    }
            
            if any(product_rows.get(l.product_id,{}).get('source_code') for l in body.lines):
                from excel_rules import calculate_line, up
                lines, subtotal, installation = [], Decimal(0), Decimal(0)
                for n,line in enumerate(body.lines):
                    p = product_rows.get(line.product_id,{})
                    rule = rules.get(p.get('source_code'))
                    
                    # Portal catalog allowlist: reject blind products
                    if p.get('category') == 'blinds':
                        raise HTTPException(422, 'Blind products are not available for customer orders')
                    
                    if not p.get('published') or not rule:
                        raise HTTPException(409,'No imported price rule for this product; display-only or mixed legacy product')
                    raw=line.model_dump(mode='json')
                    selected_adjustment=(adjustments or {}).get(str(n+1))
                    if selected_adjustment and Decimal(selected_adjustment.get('discount','0')) not in {Decimal(0),*[Decimal(v) for v in template['discounts'] if v is not None]}:
                        raise HTTPException(422,'Select a discount defined by the imported workbook')
                    
                    # Check orderable status: configured or provisional
                    if rule['status'] not in ('configured', 'provisional_placeholder'):
                        raise HTTPException(409, f"Product pricing rule is not ready: {rule.get('status')}")
                    
                    try:
                        calculated=calculate_line(rule,raw,selected_adjustment)
                    except ValueError as e:
                        raise HTTPException(422,str(e)) from None
                    if body.installation_required and calculated['installation_amount'] is None:
                        raise HTTPException(409,'This product has no installation price in the supplied template')
                    subtotal+=Decimal(calculated['amount'])
                    if body.installation_required:
                        installation+=Decimal(calculated['installation_amount'])
                    
                    # Mark provisional pricing on the line
                    pricing_status = 'provisional' if rule.get('provisional') else 'configured'
                    lines.append({**raw,**calculated,'id':str(n+1),'arrived':0,'delivered':0,
                                  'source_code':p['source_code'],'product_name':p.get('name_en'),
                                  'pricing_status':pricing_status,'rule_version':template['version'],
                                  'price_snapshot':rule})
                installation=max(installation,Decimal(template['minimum_installation'])) if body.installation_required else Decimal(0)
                # Excel Q33/P49 retain precision; currency display rounds only at the boundary.
                tax=(subtotal+installation)*Decimal(template['tax_rate'])
                total=subtotal+installation+tax
                
                # Mark overall status as provisional if any line is provisional
                overall_status = 'provisional' if any(l['pricing_status'] == 'provisional' for l in lines) else 'configured'
                return {'lines':lines,'subtotal':money(subtotal),'installation':money(installation),
                        'installation_required':body.installation_required,'tax':money(tax),'tax_rate':template['tax_rate'],
                        'total':money(total),'tax_exact':str(tax),'total_exact':str(total),
                        'deposit':deposit_amount(total),'currency':'NZD','tax_basis':'GST included in total',
                        'pricing_status':overall_status,'missing_price_rules':[],'rule_version':template['version']}
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
        d = {'id': nid, 'customer_id': cid, 'recipient': p['email'], 'subject': subject.replace('\r',' ').replace('\n',' '), 'body': text,
             'status': 'pending', 'created_at': s.now(), 'invoice_id': invoice_id}
        put(c, 'notification', d, cid)
        return nid

    def deliver(nid):
        from email_service import configuration, send_email
        def save(c,d):
            put(c,'notification',d,d['customer_id'])
            if d.get('invoice_id'):
                invoice=get(c,d['invoice_id'],'invoice')
                invoice['status']=d['status']
                put(c,'invoice',invoice,d['customer_id'])
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, nid, 'notification')
            if d['status'] != 'pending':
                return d
            if not configuration()[0]['configured']:
                d.update(status='not_configured', error='SMTP is not configured')
                save(c,d)
                return d
            d['status'] = 'sending'
            save(c,d)
        try:
            mid = send_email(d['recipient'], d['subject'], d['body'])
            d.update(status='sent', message_id=mid, sent_at=s.now())
        except Exception:
            # SMTP may have accepted the message before the connection failed.
            d.update(status='delivery_unknown', error='Check the sending mailbox before confirming a retry')
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            save(c,d)
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

    @app.get('/api/operations/settings')
    def settings(actor=Depends(s.require_admin)):
        from email_service import configuration
        return {'email':configuration()[0],'storage':s.STORAGE_MODE,'database':s.BACKEND}

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

    @app.post('/api/operations/customers/{cid}')
    def edit_profile(cid:int,body:ProfileEdit,actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d=profile(c,cid)
            d.update(body.model_dump(),updated_at=s.now(),updated_by=actor)
            c.execute('UPDATE portal_profiles SET data=? WHERE customer_id=?',(s.dump(d),cid))
            c.execute('UPDATE customers SET company=? WHERE id=?',(body.company,cid))
            return d

    @app.get('/api/operations/template-status')
    def template_status(actor=Depends(s.auth)):
        with s.db() as c:
            row=c.execute('SELECT data FROM operations_records WHERE id=?',('template-current',)).fetchone()
            if not row:
                return {'status':'not_imported','warnings':['Administrator must import the current order workbook']}
            pointer=json.loads(row['data']); d=get(c,pointer['template_id'],'template')
            return {'status':'imported','version':d['version'],'products_count':len(d['products']),
                    'warnings':d['warnings'],'imported_at':d['imported_at'],'source':d['source']}

    @app.post('/api/operations/template-import')
    def import_template(body:TemplateUpload,actor=Depends(s.require_admin)):
        from excel_rules import parse_template
        if not body.filename.lower().endswith(('.xlsm','.xlsx')):
            raise HTTPException(422,'Upload the order workbook as xlsm or xlsx')
        try:
            raw=base64.b64decode(body.content_base64,validate=True)
            manifest=parse_template(raw)
        except Exception as e:
            message=str(e) if isinstance(e,ValueError) else 'Invalid or unsupported workbook structure'
            raise HTTPException(422,message) from None
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            manifest.update(id='template:'+manifest['version'],imported_at=s.now(),actor=actor)
            if not c.execute('SELECT 1 FROM operations_records WHERE id=?',(manifest['id'],)).fetchone():
                put(c,'template',manifest)
            put(c,'template_pointer',{'id':'template-current','template_id':manifest['id']})
            existing={r['id']:json.loads(r['data']) for r in c.execute('SELECT * FROM products')}
            next_id=max(existing,default=0)+1
            brands={'Shutters_PVC_Eco':('VERA Eco','PVC'), 'Shutters_PVC':('VERA Classic','PVC Premium'),
                    'Shutters_Pinewood':('VERA Natural','Pinewood'), 'Shutters_Basswood':('VERA Prime','Basswood')}
            for rule in manifest['products']:
                code=rule['source_code']
                old=next((p for p in existing.values() if p.get('source_code')==code),None)
                pid=old['id'] if old else next_id
                if not old: next_id+=1
                brand,material=brands.get(code,(code.replace('_',' '),code.split('_')[-1]))
                warranty={'Shutters_PVC_Eco':5,'Shutters_PVC':20,'Shutters_Pinewood':5,'Shutters_Basswood':10}.get(code)
                
                # T-12: Deactivate blind products (roller/venetian/vertical/exterior)
                # Keep 4 shutter series + Ashwood active, hide 18+ blind products
                is_blind = rule['kind'] == 'blind'
                published = not is_blind  # Blinds hidden, shutters visible
                orderable = rule['status'] == 'configured' and not is_blind
                
                p={**(old or {}),'id':pid,'source_code':code,'name_zh':brand,'name_en':brand,
                   'material_zh':material,'material_en':material,'category':'shutters' if rule['kind']=='shutter' else 'blinds',
                   'sample':False,'published':published,'portal_only':code not in brands,
                   'scope':'website_and_template' if code in brands else 'template_only',
                   'description_zh':'按客户现用模板配置，规格与价格由服务端规则计算。',
                   'description_en':'Configured from the current order workbook. Pricing is calculated by server rules.',
                   'image_urls':(old or {}).get('image_urls',[]),'configuration_schema':rule['schema'],
                   'orderable':orderable,'rule_version':manifest['version']}
                if warranty:
                    p.update(warranty_years=warranty,content_source='https://verashading.com/products')
                c.execute('INSERT INTO products(id,data) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(pid,s.dump(p)))
            
            # Now handle Ashwood after all template products are processed
            # Use the canonical DELUXE_SCHEMA defined at module level
            
            ash=next((p for p in existing.values() if p.get('source_code')=='VERA_Ashwood_provisional'),None)
            
            if not ash:
                # Create new Ashwood product with the canonical Deluxe schema
                ash={'id':next_id,'source_code':'VERA_Ashwood_provisional','name_zh':'VERA Deluxe','name_en':'VERA Deluxe',
                     'material_zh':'Ashwood','material_en':'Ashwood','category':'shutters','sample':False,'published':True,
                     'portal_only':False,'scope':'website_and_template','orderable':True,'configuration_schema':DELUXE_SCHEMA,
                     'warranty_years':10,'content_source':'https://verashading.com/products',
                     'description_zh':'官网展示系列。当前为占位价 1.00/m²，严禁报价给客户。',
                     'description_en':'Website collection. Current placeholder rate 1.00/m² must not be quoted to customers.', 
                     'image_urls':[]}
                c.execute('INSERT INTO products(id,data) VALUES(?,?)',(next_id,s.dump(ash)))
            else:
                # Update existing Ashwood with the canonical Deluxe schema
                ash.update(
                    orderable=True, 
                    scope='website_and_template',
                    configuration_schema=DELUXE_SCHEMA,
                    description_zh='官网展示系列。当前为占位价 1.00/m²，严禁报价给客户。',
                    description_en='Website collection. Current placeholder rate 1.00/m² must not be quoted to customers.'
                )
                c.execute('UPDATE products SET data=? WHERE id=?',(s.dump(ash),ash['id']))
            for pid,p in existing.items():
                if p.get('source_code') and p['source_code'] not in ('VERA_Ashwood_provisional', 'VERA_Ashwood_display') and p['source_code'] not in {r['source_code'] for r in manifest['products']}:
                    p.update(published=False,orderable=False)
                    c.execute('UPDATE products SET data=? WHERE id=?',(s.dump(p),pid))
                if p.get('sample') and ('示例' in p.get('name_zh','') or 'Sample' in p.get('name_en','')):
                    p['published']=False
                    c.execute('UPDATE products SET data=? WHERE id=?',(s.dump(p),pid))
        return {'version':manifest['version'],'products_count':len(manifest['products']),'warnings':manifest['warnings']}

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
            active=c.execute('SELECT data FROM operations_records WHERE id=?',('template-current',)).fetchone()
            imported={}
            if active:
                template=get(c,json.loads(active['data'])['template_id'],'template')
                imported={r['source_code']:{k:r[k] for k in ('options','formula','status','version') if k in r} for r in template['products']}
                
                # Synthesize provisional Ashwood rule for catalog display
                basswood_rule = next((r for r in template['products'] if r['source_code'] == 'Shutters_Basswood'), None)
                if basswood_rule and 'VERA_Ashwood_provisional' not in imported:
                    imported['VERA_Ashwood_provisional'] = {
                        'options': basswood_rule.get('options', {}),
                        'formula': basswood_rule.get('formula'),
                        'status': 'provisional_placeholder',
                        'version': template['version']
                    }
            
            # Portal catalog allowlist: 5 website series + Aluminium (orderable after login)
            # Exclude all blinds regardless of published/orderable flags
            # Order matches verashading.com homepage: Eco, Classic, Natural, Prime, Deluxe, then Aluminium
            # Accept both VERA_Ashwood_provisional (current) and VERA_Ashwood_display (legacy, migrated at startup)
            PORTAL_ALLOWED_CODES = [
                'Shutters_PVC_Eco',           # VERA Eco
                'Shutters_PVC',                # VERA Classic
                'Shutters_Pinewood',           # VERA Natural
                'Shutters_Basswood',           # VERA Prime
                'VERA_Ashwood_provisional',    # VERA Deluxe (current)
                'VERA_Ashwood_display',        # VERA Deluxe (legacy, migrated at startup)
                'Shutters_Aluminium'           # VERA Aluminium (login required)
            ]
            
            # Build product dict for ordering - normalize old Ashwood code
            product_map = {}
            for p in products:
                code = p.get('source_code')
                if code in PORTAL_ALLOWED_CODES and p.get('category') != 'blinds':
                    # Normalize old Ashwood display code to provisional for consistent handling
                    if code == 'VERA_Ashwood_display':
                        p = {**p, 'source_code': 'VERA_Ashwood_provisional'}
                        code = 'VERA_Ashwood_provisional'
                    product_map[code] = p
            
            # Return products in website order with price rules and affects_price metadata
            orderable_products = []
            ORDER = ['Shutters_PVC_Eco', 'Shutters_PVC', 'Shutters_Pinewood', 'Shutters_Basswood', 'VERA_Ashwood_provisional', 'Shutters_Aluminium']
            for code in ORDER:
                if code in product_map:
                    p = product_map[code]
                    # Check both new and old Ashwood codes for price rules
                    price_rule = imported.get(code) or imported.get('VERA_Ashwood_display') or prices.get(p['id'])
                    # Add affects_price metadata: only series, width, height affect product price
                    # Panel count only affects installation fee. All config options (colour, frame, louver, etc.) do NOT affect price
                    if price_rule and isinstance(price_rule, dict):
                        price_rule = {**price_rule, 'affects_price': {
                            'product_id': True,
                            'width_mm': True,
                            'height_mm': True,
                            'panel_count': False,  # Only affects installation, not product price
                            'colour': False,
                            'louver_size': False,
                            'frame_type': False,
                            'control_rod': False,
                            'opening_style': False,
                            'install_method': False,
                            'layout': False,
                            'posts': False,
                            'midrail': False,
                        }}
                    orderable_products.append({**p, 'price_rule': price_rule})
            
            return {'products': orderable_products,
                    'pricing_status': 'configured' if prices or imported else 'rules_required'}

    @app.post('/api/portal/price')
    def price(body: Project, cid=Depends(customer_auth)):
        with s.db() as c:
            d = calculate(c, body)
            if d['total'] is None:
                raise HTTPException(409, 'Confirmed price sheet is required for these product series')
            return portal_view(d)

    @app.post('/api/portal/orders')
    def submit(body: Project, cid=Depends(customer_auth)):
        oid = key('project:', str(cid)+':'+body.submission_key)
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = replay(c, oid, bodyhash(body))
            if old:
                return portal_view(enrich(c, old))
            p = profile(c, cid)
            d = {**calculate(c, body), 'id': oid, 'customer_id': cid, 'company': p['company'],
                 'contact_name': p['contact_name'], 'email': p['email'], 'phone': p['phone'],
                 'company_address': p['company_address'], 'project_name': body.project_name, 'site_address': body.site_address,
                 'status': 'pending_review', 'payment_status': 'deposit_unpaid', 'history': [], 'created_at': s.now(),
                 'request_hash': bodyhash(body),'installation_required':body.installation_required,'adjustments':{}}
            event(d, 'submitted', p['username'])
            put(c, 'project', d, cid)
            return portal_view(enrich(c, d))

    @app.get('/api/portal/orders')
    def portal_orders(cid=Depends(customer_auth)):
        with s.db() as c:
            return [portal_view(enrich(c, d)) for d in records(c, 'project', cid)]

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
                            installation_required=d.get('installation_required',False),
                            lines=[{k: line[k] for k in Window.model_fields if k in line} for line in d['lines']])
                d.update(calculate(c, b))
            if d['total'] is None:
                raise HTTPException(409, 'Price rules must be confirmed before review acceptance and invoicing')
            d['status'] = 'accepted'
            event(d, 'review_accepted', actor)
            inv = {'id': 'deposit:'+oid, 'customer_id': d['customer_id'], 'kind': 'deposit', 'order_ids': [oid],
                   'amount': d.get('deposit') or deposit_amount(d['total']), 'currency': d['currency'], 'tax_basis': d['tax_basis'],
                   'deposit_rate': str(DEPOSIT_RATE), 'rounding': 'ROUND_UP_2DP',
                   'rule_source': 'Client reply 2026-10-15; In Put!P51',
                   'status': 'draft', 'created_at': s.now(), 'actor': actor, 'lines': [{'order_id': oid, 'amount': d.get('deposit') or deposit_amount(d['total'])}]}
            put(c, 'invoice', inv, d['customer_id'])
            put(c, 'project', d, d['customer_id'])
            return enrich(c, d)

    @app.post('/api/operations/orders/{oid}/adjust')
    def adjust(oid:str,body:Adjustments,actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d=get(c,oid,'project')
            if d['status']!='pending_review':
                raise HTTPException(409,'Commercial adjustments are allowed only before review acceptance')
            if len({l.line_id for l in body.lines})!=len(body.lines) or any(l.line_id not in {r['id'] for r in d['lines']} for l in body.lines):
                raise HTTPException(422,'Specify valid distinct window line IDs')
            changes={l.line_id:l.model_dump(mode='json',exclude={'line_id'}) for l in body.lines}
            b=Project(project_name=d['project_name'],site_address=d['site_address'],submission_key='staff-adjustment',
                      installation_required=d.get('installation_required',False),
                      lines=[{k:l[k] for k in Window.model_fields if k in l} for l in d['lines']])
            d.update(calculate(c,b,changes),adjustments=changes)
            event(d,'staff_price_adjustment',actor,note=body.note,adjustments=changes)
            put(c,'project',d,d['customer_id'])
            return enrich(c,d)

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
                inv=get(c,'deposit:'+oid,'invoice')
                inv.update(payment_status='received',received_at=s.now(),received_by=actor)
                put(c,'invoice',inv,d['customer_id'])
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
    def supplier_export(oid: str, provider_id: int | None = None, allow_basic_fallback: bool = False, actor=Depends(s.auth)):
        import json
        from fastapi.responses import Response
        import io, zipfile
        from xml.etree import ElementTree as ET
        from xml.sax.saxutils import quoteattr
        
        with s.db() as c:
            d=get(c,oid,'project')
            if d['status']=='pending_review':
                raise HTTPException(409,'Accept technical review before producing supplier documents')
            
            # Determine provider: explicit param or first assigned provider
            template_id=None
            if not provider_id:
                assigned=c.execute('SELECT provider_id,template_id FROM order_providers WHERE order_id=? ORDER BY is_preferred DESC,assigned_at LIMIT 1',(oid,)).fetchone()
                if assigned:
                    provider_id=assigned['provider_id']
                    template_id=assigned['template_id']
            else:
                # Provider_id provided, look up template
                assigned=c.execute('SELECT template_id FROM order_providers WHERE order_id=? AND provider_id=?',(oid,provider_id)).fetchone()
                template_id=assigned['template_id'] if assigned else None
            
            # Validate active provider if specified
            if provider_id:
                provider=c.execute('SELECT active,name FROM providers WHERE id=?',(provider_id,)).fetchone()
                if not provider or not provider['active']:
                    raise HTTPException(404,'Cannot export for inactive provider')
                provider_name=provider['name']
            else:
                provider_name=None
            
            # If no provider or no template, check if basic fallback allowed
            if not provider_id or not template_id:
                if not allow_basic_fallback:
                    raise HTTPException(422,'No provider template configured for this order. Use allow_basic_fallback=true for generic template.')
                # Use basic fallback
                from order_exports import export_project
                raw=export_project(d,'production')
                return Response(raw,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                               headers={'Content-Disposition':f'attachment; filename="vera-supplier-BASIC-NOT-VERIFIED.xlsx"',
                                       'Cache-Control':'no-store'})
            
            # Load custom template
            template=c.execute('SELECT * FROM provider_templates WHERE id=? AND provider_id=? AND active=1',
                             (template_id,provider_id)).fetchone()
            if not template:
                if allow_basic_fallback:
                    from order_exports import export_project
                    raw=export_project(d,'production')
                    return Response(raw,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                   headers={'Content-Disposition':f'attachment; filename="vera-supplier-BASIC-NOT-VERIFIED.xlsx"',
                                           'Cache-Control':'no-store'})
                raise HTTPException(422,'Provider template is inactive or deleted')
            
            # Generate custom template export
            mappings=json.loads(template['column_mappings'])
            sheet_name=template['sheet_name']
            validate_template(sheet_name, mappings)
            ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            ET.register_namespace('',ns)
            
            # Build header row
            columns=sorted(mappings.items(),key=lambda x:column_number(x[1]))
            headers={col:field for field,col in columns}
            
            # Build data rows
            rows=[headers]
            for line in d['lines']:
                row_data={}
                for field,col_letter in mappings.items():
                    if field=='order_id': row_data[field]=d['id']
                    elif field=='project_name': row_data[field]=d['project_name']
                    elif field=='company': row_data[field]=d['company']
                    elif field=='contact_name': row_data[field]=d['contact_name']
                    elif field=='company_address': row_data[field]=d['company_address']
                    elif field=='site_address': row_data[field]=d['site_address']
                    elif field=='phone': row_data[field]=d['phone']
                    elif field=='email': row_data[field]=d['email']
                    elif field=='window_name': row_data[field]=line['window_name']
                    elif field=='product_id': row_data[field]=str(line['product_id'])
                    elif field=='width_mm': row_data[field]=line['width_mm']
                    elif field=='height_mm': row_data[field]=line['height_mm']
                    elif field=='quantity': row_data[field]=line['quantity']
                    elif field=='panel_count': row_data[field]=line.get('panel_count',1)
                    elif field=='options': row_data[field]='; '.join(f"{k}: {v}" for k,v in line['options'].items())
                    elif field=='arrived': row_data[field]=line['arrived']
                    elif field=='delivered': row_data[field]=line['delivered']
                rows.append({col:row_data.get(field,'') for field,col in columns})
            
            # Create XLSX
            sheet=ET.Element('{'+ns+'}worksheet')
            data=ET.SubElement(sheet,'{'+ns+'}sheetData')
            for r,values in enumerate(rows,1):
                row=ET.SubElement(data,'{'+ns+'}row',{'r':str(r)})
                for col_letter,v in values.items():
                    numeric=(r>1 and isinstance(v,(int,float)))
                    cell=ET.SubElement(row,'{'+ns+'}c',{'r':col_letter+str(r),**({} if numeric else {'t':'inlineStr'})})
                    if numeric:
                        ET.SubElement(cell,'{'+ns+'}v').text=str(v)
                    else:
                        inline=ET.SubElement(cell,'{'+ns+'}is')
                        ET.SubElement(inline,'{'+ns+'}t').text=str(v)
            
            package={
                '[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
                '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
                'xl/workbook.xml':f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name={quoteattr(sheet_name)} sheetId="1" r:id="rId1"/></sheets></workbook>',
                'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
                'xl/worksheets/sheet1.xml':ET.tostring(sheet,encoding='utf-8')}
            
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for name,content in package.items():
                    z.writestr(name,content)
            
            filename=f"vera-provider-{provider_id}-{d['id'].replace(':','-')}.xlsx"
            return Response(out.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                           headers={'Content-Disposition':f'attachment; filename="{filename}"','Cache-Control':'no-store'})

    def project_export(oid,kind):
        from fastapi.responses import Response
        from order_exports import export_project
        with s.db() as c:
            d=get(c,oid,'project')
            if d['status']=='pending_review':
                raise HTTPException(409,'Accept technical review before producing order documents')
            raw=export_project(d,kind)
        return Response(raw,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition':f'attachment; filename="vera-{kind}.xlsx"','Cache-Control':'no-store'})

    @app.get('/api/operations/orders/{oid}/production-sheet')
    def production_sheet(oid:str,actor=Depends(s.auth)):
        return project_export(oid,'production')

    @app.get('/api/operations/orders/{oid}/job-sheet')
    def job_sheet(oid:str,actor=Depends(s.auth)):
        return project_export(oid,'job')

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
            result=consumption_data(c,cid)
            result['orders']=[portal_view(d) for d in result['orders']]
            return result

    def consumption_data(c,cid):
        profile(c,cid)
        orders=records(c,'project',cid); invoices=records(c,'invoice',cid); credits=records(c,'rebate',cid)
        totals={}
        for d in orders:
            currency=d['currency']; v=totals.setdefault(currency,{'ordered':Decimal(0),'invoiced':Decimal(0),'received':Decimal(0),'outstanding_invoiced':Decimal(0)})
            if d['total'] is not None: v['ordered']+=Decimal(d['total'])
        for i in invoices:
            v=totals.setdefault(i['currency'],{'ordered':Decimal(0),'invoiced':Decimal(0),'received':Decimal(0),'outstanding_invoiced':Decimal(0)})
            v['invoiced']+=Decimal(i['amount'])
            v['received' if i.get('payment_status')=='received' else 'outstanding_invoiced']+=Decimal(i['amount'])
        return {'orders':[enrich(c,d) for d in orders],'invoices':invoices,'rebates':credits,
                'summary':{currency:{k:money(v) for k,v in values.items()} for currency,values in totals.items()},
                'statistics_status':'separate_ordered_invoiced_and_manually_confirmed_receipts',
                'unpriced_orders':sum(d['total'] is None for d in orders)}

    @app.get('/api/operations/customers/{cid}/consumption')
    def staff_consumption(cid:int,actor=Depends(s.auth)):
        with s.db() as c:
            return consumption_data(c,cid)

    @app.post('/api/operations/invoices/{iid}/received')
    def invoice_received(iid:str,body:Receipt,actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            inv=get(c,iid,'invoice')
            if inv['kind']!='balance':
                raise HTTPException(409,'Confirm deposits through the project deposit-received action')
            if inv.get('payment_status')!='received':
                inv.update(payment_status='received',received_at=s.now(),received_by=actor,receipt_note=body.note)
                for oid in inv['order_ids']:
                    d=get(c,oid,'project'); d['payment_status']='paid'
                    event(d,'balance_received',actor,invoice_id=iid,note=body.note)
                    put(c,'project',d,d['customer_id'])
                put(c,'invoice',inv,inv['customer_id'])
            return inv

    # Provider management
    @app.get('/api/operations/providers')
    def list_providers(actor=Depends(s.auth)):
        with s.db() as c:
            return [dict(row) for row in c.execute('SELECT * FROM providers ORDER BY name').fetchall()]

    @app.post('/api/operations/providers')
    def create_provider(body:ProviderCreate,actor=Depends(s.require_admin)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            cursor=c.execute('INSERT INTO providers(name,contact_email,notes,created_at) VALUES(?,?,?,?)',
                     (body.name,body.contact_email,body.notes,s.now()))
            pid=cursor.lastrowid
            return dict(c.execute('SELECT * FROM providers WHERE id=?',(pid,)).fetchone())

    @app.post('/api/operations/providers/{pid}')
    def update_provider(pid:int,body:ProviderEdit,actor=Depends(s.require_admin)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            cursor=c.execute('UPDATE providers SET name=?,contact_email=?,notes=?,active=? WHERE id=?',
                     (body.name,body.contact_email,body.notes,1 if body.active else 0,pid))
            if cursor.rowcount==0:
                raise HTTPException(404,'Provider not found')
            return dict(c.execute('SELECT * FROM providers WHERE id=?',(pid,)).fetchone())

    @app.get('/api/operations/provider-templates')
    def list_provider_templates(provider_id:int|None=None,actor=Depends(s.auth)):
        with s.db() as c:
            if provider_id:
                return [dict(row) for row in c.execute('SELECT * FROM provider_templates WHERE provider_id=? ORDER BY name',(provider_id,)).fetchall()]
            return [dict(row) for row in c.execute('SELECT * FROM provider_templates ORDER BY provider_id,name').fetchall()]

    @app.post('/api/operations/provider-templates')
    def create_provider_template(body:ProviderTemplateCreate,actor=Depends(s.require_admin)):
        import json
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            # Validate provider exists and is active
            provider=c.execute('SELECT active FROM providers WHERE id=?',(body.provider_id,)).fetchone()
            if not provider or not provider['active']:
                raise HTTPException(404,'Active provider not found')
            # Validate column mappings
            if not body.column_mappings:
                raise HTTPException(422,'Column mappings cannot be empty')
            valid_fields={'order_id','project_name','company','contact_name','company_address','site_address','phone','email',
                         'window_name','product_id','width_mm','height_mm','quantity','panel_count','options','arrived','delivered'}
            for field in body.column_mappings:
                if field not in valid_fields:
                    raise HTTPException(422,f'Unknown field: {field}')
            validate_template(body.sheet_name, body.column_mappings)
            cursor=c.execute('INSERT INTO provider_templates(provider_id,name,sheet_name,column_mappings,created_at) VALUES(?,?,?,?,?)',
                     (body.provider_id,body.name,body.sheet_name,json.dumps(body.column_mappings),s.now()))
            tid=cursor.lastrowid
            return dict(c.execute('SELECT * FROM provider_templates WHERE id=?',(tid,)).fetchone())

    @app.post('/api/operations/orders/{oid}/assign-provider')
    def assign_provider(oid:str,body:OrderProviderAssignment,actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            # Validate order exists
            d=get(c,oid,'project')
            # Validate provider is active
            provider=c.execute('SELECT active FROM providers WHERE id=?',(body.provider_id,)).fetchone()
            if not provider or not provider['active']:
                raise HTTPException(404,'Active provider not found')
            # Validate template if provided
            if body.template_id:
                template=c.execute('SELECT * FROM provider_templates WHERE id=? AND provider_id=? AND active=1',
                                 (body.template_id,body.provider_id)).fetchone()
                if not template:
                    raise HTTPException(404,'Active template not found for this provider')
            # Check if already assigned
            if body.is_preferred:
                c.execute('UPDATE order_providers SET is_preferred=0 WHERE order_id=?', (oid,))
            existing=c.execute('SELECT id FROM order_providers WHERE order_id=? AND provider_id=?',(oid,body.provider_id)).fetchone()
            if existing:
                c.execute('UPDATE order_providers SET template_id=?,is_preferred=? WHERE id=?',
                         (body.template_id,1 if body.is_preferred else 0,existing['id']))
                return {'order_id':oid,'provider_id':body.provider_id,'template_id':body.template_id,'updated':True}
            c.execute('INSERT INTO order_providers(order_id,provider_id,template_id,is_preferred,assigned_at) VALUES(?,?,?,?,?)',
                     (oid,body.provider_id,body.template_id,1 if body.is_preferred else 0,s.now()))
            return {'order_id':oid,'provider_id':body.provider_id,'template_id':body.template_id,'assigned_at':s.now()}

    @app.get('/api/operations/orders/{oid}/providers')
    def list_order_providers(oid:str,actor=Depends(s.auth)):
        with s.db() as c:
            get(c,oid,'project')  # Validate order exists
            return [dict(row) for row in c.execute('''
                SELECT op.*,p.name as provider_name,p.active as provider_active,
                       pt.name as template_name,pt.sheet_name
                FROM order_providers op
                JOIN providers p ON op.provider_id=p.id
                LEFT JOIN provider_templates pt ON op.template_id=pt.id
                WHERE op.order_id=? ORDER BY op.is_preferred DESC,op.assigned_at
            ''',(oid,)).fetchall()]
