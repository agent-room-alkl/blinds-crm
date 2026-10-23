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
import os
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
from typing import Literal
from pathlib import Path

WEBSITE_IMAGES = json.loads((Path(__file__).parent / "website_products.json").read_text(encoding="utf-8"))

import invoice_mail
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
        'type': 'text'
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
        'type': 'text'
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
        'choices': ['In Fit', 'Out Fit', 'Make Size'],
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


def deposit_amount(total, rate=DEPOSIT_RATE):
    """Matches the 60% output in the supplied workbook, In Put!P51."""
    return str((Decimal(total) * Decimal(rate)).quantize(Decimal('.01'), rounding=ROUND_UP))


def prepare_knowledge_manifest(manifest):
    """Return a detached editable copy with the current VERA commercial rules."""
    from addons import ADDONS, ORDER_INSTALLATION_MINIMUM, PANEL_INSTALLATION
    value = json.loads(json.dumps(manifest))
    value.setdefault('addons', json.loads(json.dumps(ADDONS)))
    value.setdefault('installation_per_panel', str(PANEL_INSTALLATION))
    value.setdefault('minimum_installation', str(ORDER_INSTALLATION_MINIMUM))
    value.setdefault('order_minimum_area', '1')
    value.setdefault('deposit_rate', str(DEPOSIT_RATE))
    value.setdefault('tax_rate', '0.15')
    value.setdefault('tax_basis', 'GST included in total')
    value.setdefault('knowledge_sources', [])
    value.setdefault('knowledge_facts', [])
    rules = {rule.get('source_code'): rule for rule in value.get('products', [])}
    basswood = rules.get('Shutters_Basswood')
    if basswood and 'VERA_Ashwood_provisional' not in rules:
        value['products'].append({
            **basswood,
            'source_code': 'VERA_Ashwood_provisional',
            'schema': DELUXE_SCHEMA,
            'rate_per_m2': '1.00',
            'provisional': True,
            'status': 'provisional_placeholder',
            'warnings': ['Unconfirmed placeholder. Map and confirm the source price before publishing.'],
        })
    return value


def default_pricing_knowledge_manifest(wholesale_bytes, price_list_bytes, price_list_text):
    """Build a cited, conservative default from the supplied wholesale XLSM and V5 PDF text."""
    from excel_rules import parse_template, workbook
    import hashlib
    from datetime import datetime, timezone

    wholesale = parse_template(wholesale_bytes)
    sheets, _ = workbook(wholesale_bytes)
    pricing = sheets['Pricing']
    manifest = prepare_knowledge_manifest(wholesale)
    core = {
        'Shutters_PVC_Eco': ('250', 'Pricing!A486:B486'),
        'Shutters_PVC': ('280', 'Pricing!A485:B485'),
        'Shutters_Pinewood': ('320', 'Pricing!A487:B487'),
        'Shutters_Basswood': ('340', 'Pricing!A488:B488'),
    }
    normalized_pdf=' '.join(price_list_text.split())
    for label,rate in [('PVC Eco','250'),('PVC','280'),('Pinewood','320'),('Basswood','340'),('Ashwood','380')]:
        if not re.search(r'\b'+re.escape(label)+r'\s+\$\s*'+re.escape(rate)+r'\.00',normalized_pdf,re.I):
            raise ValueError('The supplied V5 PDF does not contain the expected '+label+' rate text')
    for required_text in ('Minimum order: 1 sqm per order','Minimum chargeable area: 0.5 sqm per window/item',
                          '60% deposit required on order'):
        if required_text not in normalized_pdf:
            raise ValueError('The supplied V5 PDF is missing an expected pricing term: '+required_text)
    if not re.search(r'10.\s*12 weeks from order confirmation',normalized_pdf,re.I) or not re.search(r'12.\s*14 weeks from order confirmation',normalized_pdf,re.I):
        raise ValueError('The supplied V5 PDF is missing the standard or shaped lead-time note')
    for rule in manifest['products']:
        code = rule.get('source_code')
        if code in core:
            rate, _ = core[code]
            if str(pricing.get('B'+str({'Shutters_PVC':485,'Shutters_PVC_Eco':486,'Shutters_Pinewood':487,'Shutters_Basswood':488}[code]),{}).get('value')) != rate:
                raise ValueError('The supplied wholesale workbook does not match the verified four-series source values')
            rule.update(rate_per_m2=rate, minimum_area='0.5', status='configured', provisional=False,
                        formula='excel_shutter', kind='shutter')
        elif code == 'VERA_Ashwood_provisional':
            rule.update(rate_per_m2='1.00', status='provisional_placeholder', provisional=True,
                        warnings=['The V5 Ashwood rate has no confirmed mapping to this workbook product code.'])
    defaults = prepare_knowledge_manifest({})
    manifest.update(addons=defaults['addons'], installation_per_panel=str(defaults['installation_per_panel']),
                    minimum_installation=str(defaults['minimum_installation']), order_minimum_area='1',
                    tax_rate='0.15', deposit_rate='0.60', tax_basis='GST charged on product and installation; included in quoted total',
                    source='Default pricing knowledge compiled from supplied wholesale XLSM and V5 dealer PDF')
    # Record only checked, actionable source-backed rules as active knowledge facts.
    facts = []
    source_hashes = {'wholesale': hashlib.sha256(wholesale_bytes).hexdigest(),
                     'v5': hashlib.sha256(price_list_bytes).hexdigest()}
    for code, (rate, location) in core.items():
        facts.append({'id':'fact:'+code, 'category':'base_price', 'label':code, 'value':rate,
                      'unit':'NZD/sqm', 'scope':'Wholesale shutter series', 'status':'confirmed',
                      'source_id':'source:wholesale-xlsm', 'source_location':location,
                      'source_excerpt':f'{code} | NZD {rate}/sqm', 'source_sha256':source_hashes['wholesale']})
    listing=sheets['Product Listing']
    for col in 'BCDEFGHI':
        cell=listing.get(col+'102',{})
        raw=cell.get('value')
        if raw not in (None,''):
            facts.append({'id':'fact:discount:'+col,'category':'discount_option','label':'Workbook discount option',
                          'value':str(raw),'unit':'source value','scope':'Staff adjustment values; source mapping retained from imported workbook',
                          'status':'configured','source_id':'source:wholesale-xlsm','source_location':f'Product Listing!{col}102',
                          'source_excerpt':str(raw),'source_sha256':source_hashes['wholesale']})
    def cite_fact(fid,label,value,unit,location,excerpt,category='pricing_rule',source_id='source:v5-pdf'):
        source_key='wholesale' if source_id=='source:wholesale-xlsm' else 'v5'
        facts.append({'id':'fact:'+fid,'category':category,'label':label,'value':value,'unit':unit,
                      'scope':'VERA wholesale shutter pricing','status':'confirmed',
                      'source_id':source_id,'source_location':location,
                      'source_excerpt':excerpt,'source_sha256':source_hashes[source_key]})
    cite_fact('minimum-window-area','Minimum billable area per window','0.5','sqm','page 1',
              'Minimum chargeable area: 0.5 sqm per window/item.')
    cite_fact('minimum-order-area','Minimum order area','1','sqm','page 1','Minimum order: 1 sqm per order.')
    cite_fact('deposit-rate','Deposit at order','60','%','page 1','Payment terms: 60% deposit required on order, with the remaining 40% payable before pick-up or installation.')
    cite_fact('gst-rate','GST','15','%','In Put!Q33','(Q31+N(Q32))*0.15',source_id='source:wholesale-xlsm')
    cite_fact('installation-minimum','Minimum installation charge','150','NZD/order','In Put!Q32','MAX(SUM(Order!X8:X500),150)',source_id='source:wholesale-xlsm')
    facts.append({'id':'fact:installation-rate','category':'application_parameter','label':'Installation per panel','value':'50','unit':'NZD/panel',
                  'scope':'Current confirmed VERA application rule','status':'confirmed','source_id':'application-rule',
                  'source_location':'backend/addons.py:PANEL_INSTALLATION','source_excerpt':'Current application constant PANEL_INSTALLATION = Decimal(50).'})
    facts.append({'id':'fact:workbook-installation-line','category':'source_conflict','label':'Wholesale workbook installation line','value':'60','unit':'NZD per product line (basis unclear)',
                  'scope':'Source value retained for review; not used as the panel installation rate','status':'conflicts_with_current_rule',
                  'source_id':'source:wholesale-xlsm','source_location':'Pricing!A510:B513',
                  'source_excerpt':'Shutters_PVC, Shutters_PVC_Eco, Shutters_Pinewood and Shutters_Basswood each show 60 in column B.'})
    v5_rates={'PVC Eco':'250','PVC':'280','Pinewood':'320','Basswood':'340','Ashwood':'380'}
    for material,value in v5_rates.items():
        cite_fact('v5-'+material.lower().replace(' ','-'),f'V5 dealer list: {material}',value,'NZD/sqm','page 1',f'{material} $ {value}.00',category='source_fact')
    for fid,label,value,unit,excerpt in [
        ('tracked-bifold','Tracked bifold','350','NZD/item','Tracked Bifold (per item): +$350'),
        ('tracked-sliding','Tracked sliding','400','NZD/item','Tracked Sliding (per item): +$400'),
        ('stained-colour','Stained colour','20','NZD/sqm','Stained Colour (per sqm): +$20'),
        ('stainless-hinges','Stainless hinges','10','NZD/sqm','Stainless Hinges (per sqm): +$10'),
        ('hidden-hinges','Hidden hinges','40','NZD/sqm','Hidden Hinges (per sqm): +$40'),
        ('hidden-tilt-rod','Hidden tilt rod','40','NZD/sqm','Hidden Tilt Rod (per sqm): +$40'),
        ('tier-on-tier','Tier on tier','10','%','Tier on Tier (per sqm): +10%'),
        ('double-closure','Double closure','35','NZD/sqm','Double Closure (per sqm): +$35'),
        ('shaped-cutout','Shaped / French door cut out','300','NZD/item','Shaped / French Door Cut Out (per item): +$300')]:
        cite_fact(fid,label,value,unit,'page 1',excerpt,'add_on_price')
    # The four common prices are corroborated across both sources.
    for fid,material in [('Shutters_PVC_Eco','PVC Eco'),('Shutters_PVC','PVC'),('Shutters_Pinewood','Pinewood'),('Shutters_Basswood','Basswood')]:
        facts.append({'id':'corroboration:'+fid,'category':'source_alignment','label':material+' price cross-check',
                      'value':core[fid][0],'unit':'NZD/sqm','scope':'Wholesale sources agree','status':'corroborated',
                      'source_id':'source:v5-pdf','source_location':'page 1',
                      'source_excerpt':f'{material} rate in V5 agrees with wholesale workbook {core[fid][1]}.'})
    manifest['knowledge_facts']=facts
    manifest['knowledge_sources']=['source:wholesale-xlsm','source:v5-pdf']
    manifest['knowledge_warnings']=[
        {'code':'deluxe_mapping_unconfirmed','message':'V5 lists Ashwood at NZD 380/sqm; workbook has no Ashwood row and no Deluxe label. Do not map or quote Deluxe until the product mapping and rate are confirmed.','status':'needs_confirmation'},
        {'code':'workbook_installation_rate_conflict','message':'The workbook Pricing rows show NZD 60 per product line; V5 says installation is quoted separately. The current app uses the separately confirmed NZD 50 per shutter panel and NZD 150 minimum. Do not reinterpret the workbook $60 line as the panel rule.','status':'resolved_by_existing_business_confirmation'},
        {'code':'retail_scope_unconfirmed','message':'The supplied XLSM is a wholesale template. A separate retail price/logo schedule was not found, so this default is wholesale only.','status':'needs_confirmation'},
    ]
    manifest['knowledge_rules']=[
        {'id':'shutter_area_price','formula':'billable area × series rate + selected named surcharges','status':'confirmed','source_id':'source:v5-pdf','source_location':'page 1; minimum-area notes'},
        {'id':'area_rounding','formula':'each window area rounds up to 0.01 sqm; minimum 0.5 sqm per window; order floor 1 sqm','status':'confirmed','source_id':'source:v5-pdf','source_location':'page 1'},
        {'id':'gst','formula':'(product subtotal + installation) × 15%','status':'confirmed','source_id':'source:wholesale-xlsm','source_location':'In Put!Q33'},
        {'id':'deposit','formula':'60% on order; remaining 40% before pickup or installation','status':'confirmed','source_id':'source:v5-pdf','source_location':'page 1'},
        {'id':'installation','formula':'NZD 50 per panel; order minimum NZD 150 when selected','status':'confirmed','source_id':'application-rule','source_location':'backend/addons.py:PANEL_INSTALLATION; wholesale XLSM In Put!Q32'},
    ]
    now=datetime.now(timezone.utc).isoformat()
    for sid,filename,ext,raw,locs in [
        ('source:wholesale-xlsm','Shutter Studio Wholesale Order Template - native repaired.xlsm','.xlsm',wholesale_bytes,5),
        ('source:v5-pdf','VERA Interior Shutters Wholesale Price - V5.pdf','.pdf',price_list_bytes,1)]:
        manifest.setdefault('source_records',[]).append({'id':sid,'filename':filename,'extension':ext,
            'sha256':hashlib.sha256(raw).hexdigest(),'source_type':'seeded_reference','section_count':locs,
            'uploaded_at':now,'analysis_status':'curated','uploaded_by':'system-seed'})
    manifest['knowledge_curated_at']=now
    manifest['knowledge_published']=True
    manifest['version']=hashlib.sha256(json.dumps({k:v for k,v in manifest.items() if k not in ('id','version','actor','imported_at')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    manifest.update(id='template:'+manifest['version'],imported_at=now,actor='system-seed')
    return manifest


def pricing_variable_map(manifest):
    """Describe the real runtime parameter read by each editable pricing input."""
    products={rule.get('source_code'):rule for rule in manifest.get('products',[])}
    bindings=[]
    effects={
        'rate_per_m2':'重算窗单价与行金额，并传导到商品小计、GST、总价和定金。',
        'minimum_area':'改变此系列每窗计费面积、行金额与后续合计。',
        'order_minimum_area':'触发整单面积补足，重算 shutter 行金额与合计。',
        'installation_per_panel':'改变安装费用、GST、总价和定金。',
        'minimum_installation':'改变选择安装时的订单最低安装费及后续合计。',
        'tax_rate':'改变 GST、含税总价与定金。',
        'deposit_rate':'只改变新订单应付定金金额。',
        'discounts':'决定员工在报价调整中可选的折扣值；选中后影响行单价。',
    }
    for code,rule in products.items():
        if rule.get('kind')!='shutter': continue
        bindings.append({'id':'base:'+code,'category':'基础单价','label':code,
                         'variable':f"products[{code}].rate_per_m2",'field':'rate_per_m2','source_code':code,
                         'effect':effects['rate_per_m2'],'source':'Pricing 工作簿单元格 + V5 PDF 第1页' if code!='VERA_Ashwood_provisional' else 'V5 Ashwood 来源事实；Deluxe 映射未确认'})
        bindings.append({'id':'min-window:'+code,'category':'计价面积','label':code+' 单窗最低面积',
                         'variable':f"products[{code}].minimum_area",'field':'minimum_area','source_code':code,
                         'effect':effects['minimum_area'],'source':'V5 PDF 第1页；代码按窗面积向上取至0.01㎡'})
    for addon in manifest.get('addons',[]):
        for choice in addon.get('choices',[]):
            if choice.get('value') in ('no','none'): continue
            for field in ('fixed','per_sqm','percent'):
                if field not in choice: continue
                bindings.append({'id':f"addon:{addon['key']}:{choice['value']}:{field}",'category':'附加项',
                    'label':f"{addon.get('label_zh') or addon['key']} · {choice.get('label_zh') or choice['value']}",
                    'variable':f"addons[{addon['key']}].choices[{choice['value']}].{field}",
                    'field':field,'addon_key':addon['key'],'choice_value':choice['value'],
                    'effect':'改变该附加项对行金额的固定金额、每㎡金额或百分比加价。','source':'V5 PDF 第1页'})
    for field,label,var in [('order_minimum_area','整单最低计价面积','order_minimum_area'),
                            ('installation_per_panel','每扇安装费','installation_per_panel'),
                            ('minimum_installation','最低安装费','minimum_installation'),
                            ('tax_rate','GST税率','tax_rate'),('deposit_rate','定金比例','deposit_rate')]:
        bindings.append({'id':'parameter:'+field,'category':'整单参数','label':label,'variable':var,
                         'field':field,'effect':effects[field],'source':'V5 PDF / wholesale XLSM'})
    bindings.append({'id':'discounts','category':'员工折扣','label':'模板中的折扣选项','variable':'discounts[]',
                     'field':'discounts','effect':effects['discounts'],'source':'Product Listing!B102:I102'})
    bindings.append({'id':'area-rounding','category':'计价规则','label':'面积和金额 ROUNDUP','variable':'excel_rules.up() / code constant',
                     'field':None,'effect':'面积进位到0.01㎡，金额向上进位到0.01；目前由代码固定，知识库界面不能编辑。',
                     'source':'backend/excel_rules.py'})
    return bindings


def apply_knowledge_facts(manifest, facts):
    """Apply only facts an administrator explicitly approved and mapped."""
    value = prepare_knowledge_manifest(manifest)
    rules = {rule['source_code']: rule for rule in value['products']}
    addon_defs = {addon['key']: addon for addon in value['addons']}
    for fact in facts:
        if not fact.get('approved'):
            continue
        rule_type = fact.get('suggested_rule')
        if rule_type == 'reference_only':
            continue
        if rule_type not in {'base_price_per_sqm','addon_fixed','addon_per_sqm','addon_percent','minimum_area_per_window','minimum_area_per_order','tax_rate','deposit_rate','installation_per_panel','minimum_installation'}:
            raise HTTPException(422, 'This fact type is not supported for pricing rules')
        raw = str(fact.get('value', '')).strip().replace('$', '').replace(',', '')
        try:
            amount = Decimal(raw.rstrip('%'))
        except Exception:
            raise HTTPException(422, 'Approved fact has an invalid numeric value') from None
        if not amount.is_finite() or amount < 0:
            raise HTTPException(422, 'Approved fact must be a finite non-negative number')
        if rule_type == 'base_price_per_sqm':
            code = fact.get('suggested_product_code')
            rule = rules.get(code)
            if not rule:
                raise HTTPException(422, 'Map this fact to a supported product before approving it')
            if not raw or amount <= 0:
                raise HTTPException(422, 'A base price must be greater than zero')
            rule.update(rate_per_m2=str(amount), status='configured', provisional=False)
            rule['warnings'] = [w for w in rule.get('warnings', []) if 'placeholder' not in w.lower()]
        elif rule_type in ('addon_fixed', 'addon_per_sqm', 'addon_percent'):
            key = fact.get('suggested_option_key')
            addon = addon_defs.get(key)
            if not addon:
                raise HTTPException(422, 'Map this fact to a supported add-on before approving it')
            value_name = fact.get('choice_value') or 'yes'
            choice = next((row for row in addon.get('choices', []) if row.get('value') == value_name), None)
            if not choice:
                raise HTTPException(422, 'The selected add-on choice does not exist')
            field = {'addon_fixed': 'fixed', 'addon_per_sqm': 'per_sqm', 'addon_percent': 'percent'}[rule_type]
            for other in ('fixed', 'per_sqm', 'percent'):
                choice.pop(other, None)
            choice[field] = str(amount)
        elif rule_type in ('minimum_area_per_window', 'minimum_area_per_order', 'tax_rate', 'deposit_rate',
                           'installation_per_panel', 'minimum_installation'):
            if rule_type == 'minimum_area_per_window':
                rule = rules.get(fact.get('suggested_product_code'))
                if not rule:
                    raise HTTPException(422, 'Map the minimum area to a supported product')
                rule['minimum_area'] = str(amount)
            else:
                target = {
                    'minimum_area_per_order': 'order_minimum_area',
                    'tax_rate': 'tax_rate',
                    'deposit_rate': 'deposit_rate',
                    'installation_per_panel': 'installation_per_panel',
                    'minimum_installation': 'minimum_installation',
                }[rule_type]
                rate_is_percent = '%' in str(fact.get('value','')) or str(fact.get('unit','')).strip().lower() in ('%','percent','percentage') or amount > 1
                value[target] = str(amount / 100 if rule_type in ('tax_rate', 'deposit_rate') and rate_is_percent else amount)
        else:
            raise HTTPException(422, 'This fact type is not supported for pricing rules')
    return value


def allocate_order_number(c):
    """Caller holds BEGIN IMMEDIATE (the PostgreSQL advisory transaction lock)."""
    rid = 'order-number-sequence'
    row = c.execute('SELECT data FROM operations_records WHERE id=?', (rid,)).fetchone()
    number = int(json.loads(row['data'])['value']) + 1 if row else 1
    if number >= 10**15:
        raise HTTPException(409, 'Order number capacity reached')
    c.execute('INSERT INTO operations_records(id,kind,customer_id,data) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
              (rid, 'internal_counter', None, json.dumps({'id': rid, 'value': number})))
    return f'V{number:07d}'


def backfill_order_numbers(c):
    rows = c.execute("SELECT id,data FROM operations_records WHERE kind='project' ORDER BY id").fetchall()
    orders = sorted((json.loads(row['data']) for row in rows), key=lambda d: (d.get('created_at', ''), d['id']))
    changed = 0
    for order in orders:
        if not order.get('order_number'):
            order['order_number'] = allocate_order_number(c)
            c.execute('UPDATE operations_records SET data=? WHERE id=?', (json.dumps(order, ensure_ascii=False), order['id']))
            changed += 1
    return changed


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
    customer_type: Literal['retail', 'wholesale'] = 'wholesale'
    customer_code: str | None = Field(default=None, max_length=50)

    @field_validator('email')
    @classmethod
    def valid_email(cls, v):
        from email_service import address
        return address(v) if v else ''


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


class PricingKnowledgeSourceUpload(Input):
    filename: str = Field(min_length=1,max_length=200)
    content_base64: str = Field(min_length=1,max_length=7000000)


class PricingKnowledgeDraftEdit(Input):
    manifest: dict
    facts: list[dict] = Field(default_factory=list, max_length=500)


class ProfileEdit(Input):
    company: str = Field(min_length=1,max_length=200)
    contact_name: str = Field(min_length=1,max_length=200)
    email: str
    phone: str = Field(min_length=1,max_length=100)
    company_address: str = Field(min_length=1,max_length=1000)
    customer_type: Literal['retail', 'wholesale'] | None = None
    customer_code: str | None = Field(default=None, max_length=50)

    @field_validator('email')
    @classmethod
    def valid_email(cls,v):
        from email_service import address
        return address(v) if v else ''


class LineAdjustment(Input):
    line_id: str
    discount: Decimal = Field(default=Decimal(0),ge=0,le=1,allow_inf_nan=False)
    product_surcharge: Decimal = Field(default=Decimal(0),ge=0,allow_inf_nan=False)
    installation_surcharge: Decimal = Field(default=Decimal(0),ge=0,allow_inf_nan=False)


class Adjustments(Input):
    lines: list[LineAdjustment] = Field(max_length=200)
    note: str = Field(min_length=5,max_length=1000)


class OrderNumberEdit(Input):
    order_number: str = Field(min_length=1, max_length=200)


class OrderReview(Input):
    order_number: str | None = Field(default=None, min_length=1, max_length=200)
    confirm_order_number: bool = False

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
    supersedes_id: int | None = None

class PricingApplicability(Input):
    provider_ids: list[int] = Field(default_factory=list, max_length=200)

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
    # Area charges receive the percentage; fixed per-item charges are added afterward.
    formula: Literal['area_fixed_percent_installation']
    deposit_basis: Literal['order_total']


class Supplier(Input):
    reference: str | None = Field(default=None, max_length=200)


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
    billing_basis: Literal['all_arrived_remaining_total']


class Receipt(Input):
    note: str = Field(min_length=3,max_length=1000)


class ShipmentCosts(Input):
    freight_land: Decimal = Field(ge=0, allow_inf_nan=False)
    freight_sea: Decimal = Field(ge=0, allow_inf_nan=False)
    duty_total: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)


class PurchaseCost(Input):
    factory_price_usd: Decimal = Field(ge=0, allow_inf_nan=False)
    measured_sqm: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)


DUTY_ESTIMATE_RATE = Decimal('0.15')
USD_NZD_RATE = Decimal('1.70')


def allocate_share(total, weights, amounts):
    total = Decimal(total)
    weights, amounts = [Decimal(w) for w in weights], [Decimal(a) for a in amounts]
    if total == 0:
        return ['0.00' for _ in weights]
    weight_sum = sum(weights, Decimal(0))
    if weight_sum <= 0:
        raise HTTPException(422, 'Cannot allocate when the weight total is zero')
    parts = [(total * weight / weight_sum).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) for weight in weights]
    drift = (total - sum(parts, Decimal(0))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    if drift:
        idx = max(range(len(amounts)), key=lambda i: amounts[i])
        parts[idx] += drift
    return [str(v) for v in parts]


def register(app, s):
    def money(v):
        return str(Decimal(v).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

    def bodyhash(body):
        return hashlib.sha256(body.model_dump_json().encode()).hexdigest()

    def assign_business_number(c, customer, project_name):
        kind = customer.get('customer_type') or 'wholesale'
        if kind == 'wholesale':
            code = (customer.get('customer_code') or '').strip()
            if not code:
                raise HTTPException(409, 'Add a wholesale customer code to the customer profile before ordering')
            number = code + '-' + project_name.strip()
            numbers = [json.loads(row['data']).get('order_number', '') for row in c.execute("SELECT data FROM operations_records WHERE kind='project'")]
            if any(value.casefold() == number.casefold() for value in numbers):
                raise HTTPException(409, 'This wholesale order number already exists; use a unique job name')
            return number
        day = s.business_now().strftime('%y%m%d')
        pattern = re.compile(rf'^R{day}(\d{{2}})[A-Z]+$', re.I)
        numbers = [json.loads(row['data']).get('order_number', '') for row in c.execute("SELECT data FROM operations_records WHERE kind='project'")]
        sequence = max((int(m.group(1)) for value in numbers if (m := pattern.fullmatch(value))), default=0) + 1
        if sequence > 99:
            raise HTTPException(409, 'Daily retail order number sequence is full')
        return f'R{day}{sequence:02d}A'

    def validate_order_number_unique(c, order_number, order_id):
        number = order_number.strip()
        if not number:
            raise HTTPException(422, 'Order number cannot be empty')
        rows = c.execute("SELECT id,data FROM operations_records WHERE kind='project'").fetchall()
        for row in rows:
            if row['id'] == order_id:
                continue
            existing = json.loads(row['data']).get('order_number', '')
            if existing and existing.casefold() == number.casefold():
                raise HTTPException(409, 'This order number is already in use')
        return number

    def lead_time_for(lines):
        shaped = any(line.get('options', {}).get('shaped_cutout') == 'yes' for line in lines)
        weeks = '12–14' if shaped else '10–12'
        return {'weeks': weeks, 'text': weeks + ' calendar weeks from staff acceptance', 'starts_on': 'staff_acceptance', 'calendar_weeks': True,
                'shaped_cutout': shaped}

    def get(c, rid, kind=None):
        row = c.execute('SELECT * FROM operations_records WHERE id=?', (rid,)).fetchone()
        if not row or (kind and row['kind'] != kind):
            raise HTTPException(404, 'Record not found')
        return json.loads(row['data'])

    def records(c, kind, cid=None):
        rows = c.execute('SELECT * FROM operations_records WHERE kind=?', (kind,)).fetchall()
        out = [json.loads(r['data']) for r in rows if cid is None or r['customer_id'] == cid]
        if kind == 'invoice' and out:
            numbers = {d['id']: d.get('order_number') for d in (json.loads(r['data']) for r in c.execute("SELECT data FROM operations_records WHERE kind='project'").fetchall())}
            for i in out:
                i['invoice_number'] = invoice_mail.invoice_number(i, numbers)
        return out

    def invoice_email(c, iid):
        # One builder for the stored invoice: used by preview, queueing, delivery and the PDF download.
        inv = get(c, iid, 'invoice')
        orders = {oid: get(c, oid, 'project') for oid in inv['order_ids']}
        return invoice_mail.build(inv, profile(c, inv['customer_id']), orders)

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
        hidden = {'request_hash','freight_cost','duty_cost','duty_estimate','duty_basis','purchase_cost',
                  'factory_price_usd','usd_nzd_rate','measured_sqm','measured_sqm_source','total_cost',
                  'gross_profit','cost_per_sqm','shipment_id'}
        if d.get('order_number_confirmed') is False:
            hidden.add('order_number')
        return {**{k:v for k,v in d.items() if k not in hidden},
                'order_number_confirmed':d.get('order_number_confirmed', True),
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
            template = prepare_knowledge_manifest(get(c,template_id,'template'))
            if not template.get('knowledge_published'):
                # Compatibility for a version that was already active before
                # the knowledge workflow existed. It was explicitly activated
                # by an administrator; only configured non-provisional rules
                # below remain usable. New legacy imports/activations are blocked.
                template['legacy_previously_activated'] = True
            rules = {p['source_code']:p for p in template['products']}
            product_rows = {r['id']:json.loads(r['data']) for r in c.execute('SELECT * FROM products')}
            
            # Keep the confirmed Deluxe rate intact; repair only its config schema.
            basswood_rule = rules.get('Shutters_Basswood')
            if basswood_rule:
                existing_deluxe = rules.get('VERA_Ashwood_provisional')
                if existing_deluxe and existing_deluxe.get('schema') != DELUXE_SCHEMA:
                    existing_deluxe['schema'] = DELUXE_SCHEMA
                elif not existing_deluxe:
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
                from excel_rules import calculate_line, apply_order_minimum
                lines, subtotal, installation = [], Decimal(0), Decimal(0)
                for n,line in enumerate(body.lines):
                    p = product_rows.get(line.product_id,{})
                    rule = rules.get(p.get('source_code'))
                    
                    # Portal catalog allowlist: reject blind products
                    if p.get('source_code') == 'Shutters_Aluminium':
                        raise HTTPException(422, 'This product is outside the five VERA website series')
                    if p.get('category') == 'blinds':
                        raise HTTPException(422, 'Blind products are not available for customer orders')
                    
                    if not p.get('published') or not rule:
                        raise HTTPException(409,'No imported price rule for this product; display-only or mixed legacy product')
                    raw=line.model_dump(mode='json')
                    selected_adjustment=(adjustments or {}).get(str(n+1))
                    if selected_adjustment and Decimal(selected_adjustment.get('discount','0')) not in {Decimal(0),*[Decimal(v) for v in template['discounts'] if v is not None]}:
                        raise HTTPException(422,'Select a discount defined by the imported workbook')
                    
                    # Unconfirmed and placeholder prices never produce a quote.
                    if rule.get('status') != 'configured' or rule.get('provisional'):
                        raise HTTPException(409, f"Product pricing rule is not ready: {rule.get('status')}")
                    try:
                        rate = Decimal(str(rule.get('rate_per_m2', '0')))
                    except Exception:
                        rate = Decimal(0)
                    if rule.get('formula') == 'excel_shutter' and (not rate.is_finite() or rate <= 0):
                        raise HTTPException(409, 'A positive confirmed price is required for this product')
                    
                    try:
                        calculated=calculate_line(rule,raw,selected_adjustment,product_code=p.get('source_code'),
                                                  addon_definitions=template.get('addons'),
                                                  installation_per_panel=template.get('installation_per_panel'))
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
                order_minimum_applied = apply_order_minimum(lines,template.get('addons'),template.get('order_minimum_area','1'))
                subtotal = sum((Decimal(line['amount']) for line in lines), Decimal(0))
                installation=max(installation,Decimal(template['minimum_installation'])) if body.installation_required else Decimal(0)
                # Excel Q33/P49 retain precision; currency display rounds only at the boundary.
                tax=(subtotal+installation)*Decimal(template['tax_rate'])
                total=subtotal+installation+tax
                
                # Mark overall status as provisional if any line is provisional
                overall_status = 'provisional' if any(l['pricing_status'] == 'provisional' for l in lines) else 'configured'
                return {'lines':lines,'subtotal':money(subtotal),'installation':money(installation),
                        'installation_required':body.installation_required,'tax':money(tax),'tax_rate':template['tax_rate'],
                        'total':money(total),'tax_exact':str(tax),'total_exact':str(total),
                        'deposit':deposit_amount(total,template.get('deposit_rate',DEPOSIT_RATE)),
                        'deposit_rate':str(template.get('deposit_rate',DEPOSIT_RATE)),
                        'currency':'NZD','tax_basis':'GST included in total',
                        'pricing_status':overall_status,'missing_price_rules':[],'rule_version':template['version'],
                        'order_minimum_applied':order_minimum_applied}
        product_rows={r['id']:json.loads(r['data']) for r in c.execute('SELECT * FROM products')}
        if any(product_rows.get(line.product_id,{}).get('source_code','').startswith('Shutters_') or
               product_rows.get(line.product_id,{}).get('source_code') in ('VERA_Ashwood_provisional','VERA_Ashwood_display')
               for line in body.lines):
            raise HTTPException(409,'Shutter pricing must be reviewed and published in the pricing knowledge base before quotes can be calculated')
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
            fixed = per_sqm = percent = installation = Decimal(0)
            if set(line.options) != set(rule['options']):
                raise HTTPException(422, 'Complete exactly the configured product options')
            for option, value in line.options.items():
                charges = rule['options'].get(option, {}).get(value)
                if charges is None:
                    raise HTTPException(422, 'Unsupported product configuration')
                fixed += Decimal(charges.get('fixed', '0'))
                per_sqm += Decimal(charges.get('per_sqm', '0'))
                percent += Decimal(charges.get('percent', '0'))
                installation += Decimal(charges.get('installation', '0'))
            unit = Decimal(money((area * (Decimal(rule['rate_per_m2']) + per_sqm)) * (1 + percent / 100) + fixed + installation))
            amount = unit * line.quantity
            d.update(area=str(area), unit_price=money(unit), amount=money(amount), pricing_status='configured', price_snapshot=rule)
            total += amount
            lines.append(d)
        return {'lines': lines, 'total': None if missing else money(total), 'currency': currency or 'NZD',
                'tax_basis': tax_basis, 'pricing_status': 'rules_required' if missing else 'configured', 'missing_price_rules': sorted(set(missing))}

    def queue(c, cid, subject, text, nid, invoice_id=None, html=None):
        # Persist recipient and actual batch scope before any transport attempt.
        p = profile(c, cid)
        d = {'id': nid, 'customer_id': cid, 'recipient': p['email'], 'subject': subject.replace('\r',' ').replace('\n',' '), 'body': text,
             'status': 'pending', 'created_at': s.now(), 'invoice_id': invoice_id}
        if html:
            d['html'] = html
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
            mail_state=configuration()[0]
            if mail_state.get('mode')=='demo' and not mail_state['configured']:
                d.update(status='demo_suppressed',error='Demo mode: email was not sent')
                save(c,d)
                return d
            if not mail_state['configured']:
                d.update(status='not_configured', error='SMTP is not configured')
                save(c,d)
                return d
            attachments = []
            if d.get('invoice_id'):
                try:
                    model = invoice_email(c, d['invoice_id'])
                    attachments = [(model['number'] + '.pdf', invoice_mail.render_pdf(model), 'application', 'pdf')]
                except Exception:
                    raise HTTPException(500, 'The invoice PDF could not be created; nothing was sent')
            d['status'] = 'sending'
            save(c,d)
        try:
            mid = send_email(d['recipient'], d['subject'], d['body'], attachments=attachments, html=d.get('html'))
            demo=mail_state.get('mode')=='demo'
            d.update(status='demo_sent' if demo else 'sent', message_id=mid, sent_at=s.now())
            if demo:d['delivered_to']=mail_state['demo_recipient']
        except Exception:
            # SMTP may have accepted the message before the connection failed.
            d.update(status='delivery_unknown', error='Check the sending mailbox before confirming a retry')
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            save(c,d)
        return d

    def shutter_lines(c, order):
        products = {row['id']: json.loads(row['data']) for row in c.execute('SELECT id,data FROM products')}
        return [line for line in order.get('lines') or []
                if products.get(line.get('product_id'), {}).get('category') == 'shutters']

    def set_cost_area(c, order):
        if order.get('measured_sqm_source') == 'staff':
            return
        area = sum((Decimal(line['width_mm']) * Decimal(line['height_mm']) / Decimal(1000000) * int(line.get('quantity') or 1)
                    for line in shutter_lines(c, order)), Decimal(0))
        order.update(measured_sqm=str(area.quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)), measured_sqm_source='order_dimensions')

    def refresh_costs(order):
        purchase = Decimal(order.get('purchase_cost') or '0')
        if order.get('purchase_cost') is not None:
            order['duty_estimate'] = money(purchase * DUTY_ESTIMATE_RATE)
            if order.get('duty_basis') != 'actual':
                order['duty_cost'], order['duty_basis'] = order['duty_estimate'], 'estimate'
        freight, duty = Decimal(order.get('freight_cost') or '0'), Decimal(order.get('duty_cost') or '0')
        total_cost = purchase + freight + duty
        order['total_cost'] = money(total_cost)
        order['gross_profit'] = None if order.get('total') is None else money(Decimal(order['total']) - total_cost)
        sqm = Decimal(order['measured_sqm']) if order.get('measured_sqm') else Decimal(0)
        order['cost_per_sqm'] = None if sqm <= 0 else money(total_cost / sqm)

    def allocate_shipment(c, shipment):
        orders = [get(c, oid, 'project') for oid in shipment['order_ids']]
        for order in orders:
            set_cost_area(c, order)
        missing = [order['id'] for order in orders if order.get('purchase_cost') is None]
        if missing:
            raise HTTPException(409, 'Record the USD factory price for each shipment order first: ' + ', '.join(missing))
        costs = [Decimal(order['purchase_cost']) for order in orders]
        freight = allocate_share(Decimal(shipment['freight_land']) + Decimal(shipment['freight_sea']),
                                 [Decimal(order['measured_sqm']) for order in orders], costs)
        actual = shipment.get('duty_total') is not None
        duties = allocate_share(shipment['duty_total'], costs, costs) if actual else None
        for i, order in enumerate(orders):
            order['freight_cost'] = freight[i]
            if actual:
                order.update(duty_cost=duties[i], duty_basis='actual')
            else:
                order.update(duty_cost=order.get('duty_estimate', '0.00'), duty_basis='estimate')
            refresh_costs(order)
            put(c, 'project', order, order['customer_id'])
        shipment.update(freight_shares=freight, duty_shares=[order['duty_cost'] for order in orders],
                        duty_basis='actual' if actual else 'estimate')

    @app.post('/api/operations/shipments')
    def create_shipment(body: Batch, actor=Depends(s.auth)):
        sid = 'ship-' + hashlib.sha256(body.operation_key.encode()).hexdigest()[:24]
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = replay(c, sid, bodyhash(body))
            if old:
                return old
            members, results = [], []
            for oid in dict.fromkeys(body.order_ids):
                try:
                    order = get(c, oid, 'project')
                    if order['status'] != 'supplier_ordered':
                        raise HTTPException(409, 'Only supplier-ordered projects can join a sea shipment')
                    if not shutter_lines(c, order):
                        raise HTTPException(409, 'Only shutter orders join a sea shipment')
                    if order.get('shipment_id'):
                        raise HTTPException(409, 'Order already belongs to a shipment')
                    order['shipment_id'] = sid
                    set_cost_area(c, order)
                    put(c, 'project', order, order['customer_id'])
                    members.append(oid)
                    results.append({'order_id': oid, 'status': 'success'})
                except HTTPException as error:
                    results.append({'order_id': oid, 'status': 'skipped', 'reason': error.detail})
            if not members:
                raise HTTPException(409, 'No eligible shutter orders could join this shipment')
            shipment = {'id': sid, 'order_ids': members, 'results': results, 'request_hash': bodyhash(body), 'created_at': s.now(), 'actor': actor}
            put(c, 'shipment', shipment)
            return shipment

    @app.get('/api/operations/shipments/{sid}')
    def shipment_detail(sid: str, actor=Depends(s.auth)):
        with s.db() as c:
            shipment = get(c, sid, 'shipment')
            shipment['orders'] = [get(c, oid, 'project') for oid in shipment['order_ids']]
            return shipment

    @app.post('/api/operations/shipments/{sid}/costs')
    def shipment_costs(sid: str, body: ShipmentCosts, actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            shipment = get(c, sid, 'shipment')
            shipment.update(freight_land=money(body.freight_land), freight_sea=money(body.freight_sea),
                            duty_total=None if body.duty_total is None else money(body.duty_total))
            allocate_shipment(c, shipment)
            put(c, 'shipment', shipment)
            return shipment

    @app.post('/api/operations/orders/{oid}/purchase-cost')
    def purchase_cost(oid: str, body: PurchaseCost, actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            order = get(c, oid, 'project')
            order.update(factory_price_usd=money(body.factory_price_usd), usd_nzd_rate=str(USD_NZD_RATE),
                         purchase_cost=money(body.factory_price_usd * USD_NZD_RATE))
            if body.measured_sqm is not None:
                order.update(measured_sqm=str(body.measured_sqm), measured_sqm_source='staff')
            else:
                set_cost_area(c, order)
            refresh_costs(order)
            put(c, 'project', order, order['customer_id'])
            shipment = get(c, order['shipment_id'], 'shipment') if order.get('shipment_id') else None
            if shipment and 'freight_land' in shipment:
                allocate_shipment(c, shipment)
                put(c, 'shipment', shipment)
                order = get(c, oid, 'project')
            return {key: order.get(key) for key in ('id','factory_price_usd','usd_nzd_rate','purchase_cost','measured_sqm',
                    'freight_cost','duty_cost','duty_estimate','duty_basis','total_cost','gross_profit','cost_per_sqm')}

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

    @app.get('/api/operations/runtime')
    def runtime(actor=Depends(s.auth)):
        from email_service import configuration
        state=configuration()[0]
        with s.db() as c:
            user=c.execute('SELECT role FROM users WHERE username=? AND active=1',(actor,)).fetchone()
        is_admin=bool(user and user['role']=='admin')
        return {'email_mode':state['mode'],'email_delivery_enabled':state['delivery_enabled'] and state['configured'],
                'demo_email_address':state['demo_recipient'] if state['mode']=='demo' and is_admin else ''}

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
                if any(r['company'].strip().casefold()==body.company.strip().casefold() for r in c.execute('SELECT company FROM customers')):
                    raise HTTPException(409,'Company already exists; manage its existing customer account')
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
            d.update(body.model_dump(exclude_unset=True),updated_at=s.now(),updated_by=actor)
            c.execute('UPDATE portal_profiles SET data=? WHERE customer_id=?',(s.dump(d),cid))
            c.execute('UPDATE customers SET company=? WHERE id=?',(body.company,cid))
            return d

    @app.get('/api/operations/orders/{oid}/lead-time')
    def accepted_lead_time(oid: str, actor=Depends(s.auth)):
        with s.db() as c:
            d = get(c, oid, 'project')
            if d['status'] == 'pending_review':
                raise HTTPException(409, 'Lead time starts after staff review accepts the order')
            return d.get('lead_time') or lead_time_for(d['lines'])

    @app.get('/api/operations/pricing-templates')
    def pricing_templates(actor=Depends(s.auth)):
        with s.db() as c:
            pointer = c.execute('SELECT data FROM operations_records WHERE id=?', ('template-current',)).fetchone()
            active = json.loads(pointer['data'])['template_id'] if pointer else None
            projects = records(c, 'project')
            result = []
            for template in records(c, 'template'):
                scope = c.execute('SELECT data FROM operations_records WHERE id=?', ('pricing-scope:'+template['id'],)).fetchone()
                used = [{'id':d['id'], 'order_number':d.get('order_number'), 'project_name':d['project_name'],
                         'lines':[line['id'] for line in d['lines'] if line.get('rule_version') == template['version']]}
                        for d in projects if any(line.get('rule_version') == template['version'] for line in d['lines'])]
                result.append({'id':template['id'], 'version':template['version'], 'active':template['id']==active,
                               'source':template.get('source'), 'imported_at':template.get('imported_at'),
                               'products':[p['source_code'] for p in template['products'] if p['source_code'] in
                                           ('Shutters_PVC_Eco','Shutters_PVC','Shutters_Pinewood','Shutters_Basswood','VERA_Ashwood_provisional')],
                               'provider_ids':json.loads(scope['data'])['provider_ids'] if scope else [],
                               'applicability_confirmed':bool(scope), 'orders':used})
            return result

    @app.post('/api/operations/pricing-templates/{tid}/applicability')
    def pricing_applicability(tid:str,body:PricingApplicability,actor=Depends(s.require_admin)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            get(c,tid,'template')
            ids = sorted(set(body.provider_ids))
            for pid in ids:
                if not c.execute('SELECT 1 FROM providers WHERE id=?',(pid,)).fetchone():
                    raise HTTPException(404,'Supplier not found')
            value={'id':'pricing-scope:'+tid,'template_id':tid,'provider_ids':ids,'updated_at':s.now(),'actor':actor}
            put(c,'pricing_applicability',value)
            return value

    @app.post('/api/operations/pricing-templates/{tid}/activate')
    def activate_pricing_template(tid:str,actor=Depends(s.require_admin)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            manifest=get(c,tid,'template')
            if not manifest.get('knowledge_published'):
                raise HTTPException(409,'Review and publish pricing through the pricing knowledge base')
            put(c,'template_pointer',{'id':'template-current','template_id':tid,'activated_at':s.now(),'actor':actor})
            return {'template_id':tid,'status':'active','historical_orders_unchanged':True}

    @app.get('/api/operations/template-status')
    def template_status(actor=Depends(s.auth)):
        with s.db() as c:
            row=c.execute('SELECT data FROM operations_records WHERE id=?',('template-current',)).fetchone()
            if not row:
                return {'status':'not_imported','warnings':['Administrator must import the current order workbook']}
            pointer=json.loads(row['data']); d=get(c,pointer['template_id'],'template')
            return {'status':'imported','version':d['version'],'products_count':len(d['products']),
                    'warnings':d['warnings'],'imported_at':d['imported_at'],'source':d['source']}

    def knowledge_source_card(source):
        return {key:source.get(key) for key in (
            'id','filename','extension','sha256','byte_count','section_count','uploaded_at',
            'uploaded_by','extraction_truncated','analysis_status','analysis_summary'
        )}

    @app.get('/api/operations/pricing-knowledge')
    def pricing_knowledge(actor=Depends(s.require_admin)):
        with s.db() as c:
            pointer=c.execute('SELECT data FROM operations_records WHERE id=?',('template-current',)).fetchone()
            current=None
            if pointer:
                current=prepare_knowledge_manifest(get(c,json.loads(pointer['data'])['template_id'],'template'))
                current.update(active=True)
                current['knowledge_bindings']=pricing_variable_map(current)
            sources=[knowledge_source_card(source) for source in records(c,'pricing_knowledge_source')]
            drafts=records(c,'pricing_knowledge_draft')
            drafts=[{**(draft if draft.get('status')=='draft' else {**draft,'facts':[]}),
                     'knowledge_bindings':pricing_variable_map(draft.get('manifest') or {})} for draft in drafts]
            seeded_sources=(current or {}).get('source_records',[])
            known_ids={source.get('id') for source in sources}
            sources.extend({**source,'seeded_reference':True} for source in seeded_sources if source.get('id') not in known_ids)
            return {'current':current,'sources':sources,'drafts':drafts,
                    'ai_configured':bool(os.getenv('OPENAI_API_KEY')),
                    'ai_model':os.getenv('VERA_PRICING_AI_MODEL','gpt-6-astra')}

    @app.post('/api/operations/pricing-knowledge/initialize-default')
    def initialize_default_pricing_knowledge(actor=Depends(s.require_admin)):
        """Seed the compiled default from the supplied source files on first use."""
        from pricing_knowledge import read_default_source_files
        from pathlib import Path
        existing_version=None
        with s.db() as c:
            pointer=c.execute('SELECT data FROM operations_records WHERE id=?',('template-current',)).fetchone()
            if pointer:
                current=get(c,json.loads(pointer['data'])['template_id'],'template')
                if current.get('knowledge_curated_at'):
                    return {'active':True,'version':current.get('version'),'already_initialized':True}
                existing_version=current.get('version')
        source_root=Path(os.getenv('VERA_PRICING_DEFAULT_SOURCES_DIR') or (Path(__file__).resolve().parents[2]/'vera'))
        try:
            wholesale_bytes,price_list_bytes,price_list_text=read_default_source_files(source_root)
            manifest=default_pricing_knowledge_manifest(wholesale_bytes,price_list_bytes,price_list_text)
        except (OSError,ValueError) as error:
            raise HTTPException(422,'Could not initialize default knowledge: '+str(error)) from None
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            pointer=c.execute('SELECT data FROM operations_records WHERE id=?',('template-current',)).fetchone()
            if pointer:
                current=get(c,json.loads(pointer['data'])['template_id'],'template')
                if current.get('knowledge_curated_at'):
                    return {'active':True,'version':current.get('version'),'already_initialized':True}
                existing_version=current.get('version')
                manifest['supersedes_version']=existing_version
                manifest['version']=hashlib.sha256(s.dump({k:v for k,v in manifest.items() if k not in ('id','version','actor','imported_at')}).encode()).hexdigest()
                manifest.update(id='template:'+manifest['version'],imported_at=s.now(),actor=actor)
            if c.execute('SELECT 1 FROM operations_records WHERE id=?',(manifest['id'],)).fetchone():
                put(c,'template_pointer',{'id':'template-current','template_id':manifest['id'],'activated_at':s.now(),'actor':actor})
            else:
                put(c,'template',manifest)
                put(c,'template_pointer',{'id':'template-current','template_id':manifest['id'],'activated_at':s.now(),'actor':actor})
            known={r['id']:json.loads(r['data']) for r in c.execute('SELECT * FROM products')}
            next_id=max(known,default=0)+1
            mapping={'Shutters_PVC_Eco':('VERA Eco','PVC'),'Shutters_PVC':('VERA Classic','PVC Premium'),
                     'Shutters_Pinewood':('VERA Natural','Pinewood'),'Shutters_Basswood':('VERA Prime','Basswood'),
                     'VERA_Ashwood_provisional':('VERA Deluxe','Ashwood')}
            for rule in manifest['products']:
                code=rule.get('source_code')
                if code not in mapping: continue
                product=next((p for p in known.values() if p.get('source_code')==code),None)
                if product:
                    product.update(name_en=mapping[code][0],name_zh=mapping[code][0],category='shutters',material=mapping[code][1],
                                   published=rule.get('status')=='configured',orderable=rule.get('status')=='configured',
                                   configuration_schema=rule.get('schema',product.get('configuration_schema',[])))
                    c.execute('UPDATE products SET data=? WHERE id=?',(s.dump(product),product['id']))
                else:
                    product={'id':next_id,'name_en':mapping[code][0],'name_zh':mapping[code][0],'category':'shutters',
                             'material':mapping[code][1],'source_code':code,'published':rule.get('status')=='configured',
                             'orderable':rule.get('status')=='configured','orderable_after_login':False,
                             'configuration_schema':rule.get('schema',[]),'display_position':next_id}
                    put(c,'product',product);known[next_id]=product;next_id+=1
            return {'active':True,'version':manifest['version'],'already_initialized':False,'supersedes_version':existing_version,
                    'confirmed_series':4,'unresolved_series':['VERA_Ashwood_provisional'],
                    'historical_orders_unchanged':True}

    @app.post('/api/operations/pricing-knowledge/drafts/from-current')
    def create_pricing_knowledge_draft_from_current(actor=Depends(s.require_admin)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            pointer=c.execute('SELECT data FROM operations_records WHERE id=?',('template-current',)).fetchone()
            if not pointer: raise HTTPException(409,'Initialize the default pricing knowledge first')
            base=prepare_knowledge_manifest(get(c,json.loads(pointer['data'])['template_id'],'template'))
            did='pricing-draft:'+secrets.token_hex(12)
            draft={'id':did,'status':'draft','title':'Pricing knowledge edit · '+str(base.get('version',''))[:12],
                   'summary':'Editable copy of the active version. Existing source citations and knowledge facts are retained.',
                   'manifest':base,'facts':[],'base_version':base.get('version'),
                   'source_ids':base.get('knowledge_sources') or [],'created_at':s.now(),'created_by':actor,'updated_at':s.now()}
            put(c,'pricing_knowledge_draft',draft)
            return draft

    @app.post('/api/operations/pricing-knowledge/sources')
    def upload_pricing_knowledge_source(body:PricingKnowledgeSourceUpload,actor=Depends(s.require_admin)):
        from pricing_knowledge import extract_source
        try:
            raw=base64.b64decode(body.content_base64,validate=True)
            if len(raw) > 5 * 1024 * 1024:
                raise ValueError('Source file exceeds the 5 MB limit')
            extracted=extract_source(body.filename,raw)
        except Exception as error:
            message=str(error) if isinstance(error,(ValueError,RuntimeError)) else 'Could not read this source file'
            raise HTTPException(422,message) from None
        sid='pricing-source:'+secrets.token_hex(12)
        source={**extracted,'id':sid,'content_base64':base64.b64encode(raw).decode('ascii'),'uploaded_at':s.now(),
                'uploaded_by':actor,'analysis_status':'not_analyzed'}
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            put(c,'pricing_knowledge_source',source)
        return {**knowledge_source_card(source),'parsed_template_available':bool(source.get('parsed_template'))}

    @app.get('/api/operations/pricing-knowledge/sources/{sid}/file')
    def download_pricing_knowledge_source(sid:str,actor=Depends(s.require_admin)):
        import binascii
        from fastapi.responses import Response
        source=None
        with s.db() as c:
            source=get(c,sid,'pricing_knowledge_source')
        try: raw=base64.b64decode(source['content_base64'],validate=True)
        except (KeyError,ValueError,binascii.Error): raise HTTPException(404,'Source file not found') from None
        mime={'.pdf':'application/pdf','.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
              '.xlsm':'application/vnd.ms-excel.sheet.macroEnabled.12'}.get(source['extension'],'application/octet-stream')
        filename=re.sub(r'[^A-Za-z0-9._-]','_',source['filename'])
        return Response(raw,media_type=mime,headers={'Content-Disposition':f'attachment; filename="{filename}"','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

    @app.post('/api/operations/pricing-knowledge/sources/{sid}/analyze')
    def analyze_pricing_knowledge_source(sid:str,actor=Depends(s.require_admin)):
        from pricing_knowledge import analyze_source
        with s.db() as c:
            source=get(c,sid,'pricing_knowledge_source')
            pointer=c.execute('SELECT data FROM operations_records WHERE id=?',('template-current',)).fetchone()
            active=prepare_knowledge_manifest(get(c,json.loads(pointer['data'])['template_id'],'template')) if pointer else None
        base=active or source.get('parsed_template')
        if not base:
            raise HTTPException(409,'Upload the existing wholesale pricing workbook first so the knowledge base has product rules to review')
        if active is None and not source.get('parsed_template'):
            raise HTTPException(409,'The first pricing source must be the existing wholesale pricing workbook')
        try:
            analysis=analyze_source(source['extracted_text'])
        except RuntimeError as error:
            raise HTTPException(503,str(error)) from None
        except ValueError as error:
            raise HTTPException(422,str(error)) from None
        draft_id='pricing-draft:'+secrets.token_hex(12)
        manifest=prepare_knowledge_manifest(base)
        # A parsed legacy workbook provides the initial price matrix, but old
        # template pricing options are not part of the public add-on catalogue.
        # Every publication still goes through explicit review and confirmation.
        defaults=prepare_knowledge_manifest({})
        manifest['addons'] = defaults['addons']
        manifest['installation_per_panel'] = str(defaults['installation_per_panel'])
        manifest['minimum_installation'] = str(defaults['minimum_installation'])
        for rule in manifest.get('products', []):
            if rule.get('source_code') in {'Shutters_PVC_Eco','Shutters_PVC','Shutters_Pinewood','Shutters_Basswood'} and not rule.get('provisional'):
                rule['status'] = 'configured' if Decimal(str(rule.get('rate_per_m2') or '0')) > 0 else rule.get('status','missing')
        if active is None:
            # The legacy workbook initializes the existing four lines; Deluxe
            # remains blocked until a human confirms its source mapping.
            for rule in manifest.get('products', []):
                if rule.get('source_code')=='VERA_Ashwood_provisional':
                    rule.update(rate_per_m2='1.00',status='provisional_placeholder',provisional=True)
            for rule in manifest.get('products', []):
                if rule.get('source_code') in {'Shutters_PVC_Eco','Shutters_PVC','Shutters_Pinewood','Shutters_Basswood'}:
                    rule['installation_rate']=str(defaults['installation_per_panel'])
        manifest['knowledge_sources']=list(dict.fromkeys([*manifest.get('knowledge_sources',[]),sid]))
        facts=[]
        for fact in analysis['facts']:
            facts.append({**fact,'approved':False,'source_id':sid})
        draft={'id':draft_id,'status':'draft','title':source['filename'],'summary':analysis['summary'],
               'manifest':manifest,'facts':facts,'base_version':(active or {}).get('version'),
               'source_ids':[sid],'created_at':s.now(),'created_by':actor,'updated_at':s.now()}
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            source=get(c,sid,'pricing_knowledge_source')
            source.update(analysis_status='analyzed',analysis_summary=analysis['summary'],analyzed_at=s.now(),analyzed_by=actor)
            put(c,'pricing_knowledge_source',source)
            put(c,'pricing_knowledge_draft',draft)
        return draft

    @app.put('/api/operations/pricing-knowledge/drafts/{did}')
    def edit_pricing_knowledge_draft(did:str,body:PricingKnowledgeDraftEdit,actor=Depends(s.require_admin)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            draft=get(c,did,'pricing_knowledge_draft')
            if draft.get('status')!='draft': raise HTTPException(409,'Only draft knowledge can be edited')
            manifest=body.manifest
            if not isinstance(manifest.get('products'),list) or not isinstance(manifest.get('addons'),list) or len(manifest['products'])>100 or len(manifest['addons'])>100:
                raise HTTPException(422,'Draft rule structure exceeds supported limits')
            try:
                if len(s.dump(manifest)) > 500_000 or len(s.dump(body.facts)) > 250_000:
                    raise HTTPException(422,'Draft rule content is too large')
            except (TypeError,ValueError):
                raise HTTPException(422,'Draft rule content is invalid') from None
            source_ids = set(draft.get('source_ids') or [])
            allowed_codes = {'Shutters_PVC_Eco','Shutters_PVC','Shutters_Pinewood','Shutters_Basswood','VERA_Ashwood_provisional'}
            for fact in draft['facts']:
                if fact.get('source_id') not in source_ids or fact.get('suggested_rule') not in {'base_price_per_sqm','addon_fixed','addon_per_sqm','addon_percent','minimum_area_per_window','minimum_area_per_order','tax_rate','deposit_rate','installation_per_panel','minimum_installation','reference_only'}:
                    raise HTTPException(422,'Draft contains an unsupported or unlinked fact')
                if fact.get('suggested_product_code') is not None and fact.get('suggested_product_code') not in allowed_codes:
                    raise HTTPException(422,'Map facts only to supported VERA shutter series')
                if fact.get('suggested_rule','').startswith('addon_') and fact.get('suggested_option_key') not in {a.get('key') for a in (body.manifest.get('addons') or [])}:
                    raise HTTPException(422,'Map add-on facts to a supported add-on key')
            for rule in (body.manifest.get('products') or []):
                if rule.get('source_code') not in allowed_codes: continue
                for field in ('rate_per_m2','minimum_area'):
                    if field in rule:
                        try: amount=Decimal(str(rule[field]))
                        except Exception: amount=Decimal(-1)
                        if not amount.is_finite() or amount<0: raise HTTPException(422,'Invalid product price rule')
            draft.update(manifest=body.manifest,facts=body.facts,updated_at=s.now(),updated_by=actor)
            put(c,'pricing_knowledge_draft',draft)
            return draft

    @app.post('/api/operations/pricing-knowledge/drafts/{did}/publish')
    def publish_pricing_knowledge_draft(did:str,actor=Depends(s.require_admin)):
        from addons import ADDONS
        # Core website rates can be published while the unresolved Deluxe
        # mapping remains explicitly provisional and unavailable for quoting.
        required={'Shutters_PVC_Eco','Shutters_PVC','Shutters_Pinewood','Shutters_Basswood'}
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            draft=get(c,did,'pricing_knowledge_draft')
            if draft.get('status')!='draft': raise HTTPException(409,'Only a draft can be published')
            manifest=apply_knowledge_facts(draft['manifest'],draft.get('facts') or [])
            products={rule.get('source_code'):rule for rule in manifest.get('products') or []}
            for code in sorted(required):
                rule=products.get(code)
                try: rate=Decimal(str((rule or {}).get('rate_per_m2','0')))
                except Exception: rate=Decimal(0)
                if not rule or not rate.is_finite() or rate<=0 or rule.get('status')!='configured' or rule.get('provisional'):
                    raise HTTPException(422,'Complete and confirm a positive base price for '+code+' before publishing')
                try:
                    if Decimal(str(rule.get('minimum_area','0')))<=0: raise ValueError()
                except Exception: raise HTTPException(422,'Set a positive minimum billable area for '+code) from None
                if rule.get('kind')=='shutter' and rule.get('formula')!='excel_shutter':
                    raise HTTPException(422,'Unsupported shutter pricing formula for '+code)
            for key,minimum,maximum in [('tax_rate',Decimal(0),Decimal(1)),('deposit_rate',Decimal(0),Decimal(1)),
                                         ('minimum_installation',Decimal(0),Decimal('1000000')),
                                         ('installation_per_panel',Decimal(0),Decimal('1000000')),
                                         ('order_minimum_area',Decimal('0.001'),Decimal(1000))]:
                try: value=Decimal(str(manifest.get(key,'')))
                except Exception: value=Decimal(-1)
                if not value.is_finite() or value<minimum or value>maximum:
                    raise HTTPException(422,'Invalid knowledge base parameter: '+key)
            addons=manifest.get('addons') or []
            addon_keys=[item.get('key') for item in addons]
            if len(set(addon_keys))!=len(addon_keys) or set(addon_keys)!={item['key'] for item in ADDONS}:
                raise HTTPException(422,'Keep each supported V5 add-on key exactly once')
            for addon in addons:
                if not isinstance(addon.get('key'),str) or not isinstance(addon.get('choices'),list) or len(addon['choices'])>30:
                    raise HTTPException(422,'Invalid add-on structure')
                if not isinstance(addon.get('label_en'),str) or not isinstance(addon.get('label_zh'),str):
                    raise HTTPException(422,'Add-on labels must be text')
                for choice in addon.get('choices') or []:
                    if not isinstance(choice.get('value'),str) or len(choice['value'])>100:
                        raise HTTPException(422,'Invalid add-on choice')
                    if choice.get('value') in ('no','none'): continue
                    if set(choice)-{'value','label_zh','label_en','fixed','per_sqm','percent'}:
                        raise HTTPException(422,'Unsupported add-on rule fields')
                    for field in ('fixed','per_sqm','percent'):
                        if field in choice:
                            try: amount=Decimal(str(choice[field]))
                            except Exception: amount=Decimal(-1)
                            if not amount.is_finite() or amount<0:
                                raise HTTPException(422,'Invalid add-on amount for '+addon['key'])
                    charged=[key for key in ('fixed','per_sqm','percent') if key in choice]
                    if len(charged)>1:
                        raise HTTPException(422,'Each add-on choice must use one price method')
            manifest['warnings']=[]
            manifest['source']='Pricing knowledge: '+', '.join(draft.get('source_ids') or [])
            manifest['knowledge_facts']=[*(manifest.get('knowledge_facts') or []),
                                         *[{**fact,'status':'approved_candidate'} for fact in (draft.get('facts') or []) if fact.get('approved')]]
            manifest['version']=hashlib.sha256(s.dump({k:v for k,v in manifest.items() if k not in ('id','version','actor','imported_at')}).encode()).hexdigest()
            manifest.update(id='template:'+manifest['version'],imported_at=s.now(),actor=actor,knowledge_published=True)
            if c.execute('SELECT 1 FROM operations_records WHERE id=?',(manifest['id'],)).fetchone():
                raise HTTPException(409,'This exact pricing version already exists; create a new draft to publish changes')
            put(c,'template',manifest)
            # Keep product option schemas in sync with the published snapshot.
            # Existing order snapshots remain independent and are not rewritten.
            product_rows={r['id']:json.loads(r['data']) for r in c.execute('SELECT * FROM products')}
            by_code={p.get('source_code'):p for p in product_rows.values()}
            code_map={'Shutters_PVC_Eco':('VERA Eco','PVC'),'Shutters_PVC':('VERA Classic','PVC Premium'),
                      'Shutters_Pinewood':('VERA Natural','Pinewood'),'Shutters_Basswood':('VERA Prime','Basswood'),
                      'VERA_Ashwood_provisional':('VERA Deluxe','Ashwood')}
            for rule in manifest.get('products',[]):
                code=rule.get('source_code')
                if code not in code_map: continue
                product=by_code.get(code)
                display_provisional = code == 'VERA_Ashwood_provisional' and rule.get('status') == 'provisional_placeholder'
                if product:
                    product.update(configuration_schema=rule.get('schema',product.get('configuration_schema',[])),
                                   published=True if rule.get('status')=='configured' or display_provisional else product.get('published',True),
                    orderable=rule.get('status')=='configured')
                    c.execute('UPDATE products SET data=? WHERE id=?',(s.dump(product),product['id']))
                else:
                    names=code_map[code]; pid=max(product_rows,default=0)+1
                    orderable = rule.get('status') == 'configured'
                    product={'id':pid,'name_zh':names[0],'name_en':names[0],'category':'shutters','material':names[1],
                             'source_code':code,'published':orderable or display_provisional,'orderable':orderable,
                             'orderable_after_login':False,'configuration_schema':rule.get('schema',[]),'display_position':pid}
                    put(c,'product',product); product_rows[pid]=product
            for code,product in list(by_code.items()):
                if code in code_map and code not in products:
                    product.update(published=False,orderable=False)
                    c.execute('UPDATE products SET data=? WHERE id=?',(s.dump(product),product['id']))
            put(c,'template_pointer',{'id':'template-current','template_id':manifest['id'],'activated_at':s.now(),'actor':actor})
            draft.update(status='published',published_at=s.now(),published_by=actor,published_version=manifest['version'])
            put(c,'pricing_knowledge_draft',draft)
            return {'version':manifest['version'],'active':True,'historical_orders_unchanged':True}

    @app.post('/api/operations/template-import')
    def import_template(body:TemplateUpload,actor=Depends(s.require_admin)):
        raise HTTPException(410,'Immediate template activation is retired. Upload the workbook as pricing knowledge, analyze it, review its rules, and publish a version.')
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
                # Current catalogue is exactly the five website series; retain other rules only in the private manifest.
                if code not in brands:
                    continue
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
                   'image_urls':(old or {}).get('image_urls') or [WEBSITE_IMAGES[code]['local']],'configuration_schema':rule['schema'],
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
                     'image_urls':[WEBSITE_IMAGES['VERA_Ashwood_provisional']['local']]}
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
                    if set(charges) - {'fixed', 'percent', 'per_sqm', 'installation'} or any(not v.is_finite() or v < 0 for v in charges.values()):
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
            template=None
            if active:
                template=prepare_knowledge_manifest(get(c,json.loads(active['data'])['template_id'],'template'))
                if active:
                    # The current legacy pointer represents an already-active
                    # version. Per-rule configured/provisional checks still gate it.
                    for rule in template['products']:
                        if rule.get('status')!='configured' or rule.get('provisional'):
                            continue
                        if rule.get('formula')=='excel_shutter':
                            try: rate=Decimal(str(rule.get('rate_per_m2','0')))
                            except Exception: rate=Decimal(0)
                            if not rate.is_finite() or rate<=0: continue
                        imported[rule['source_code']]={k:rule[k] for k in ('options','formula','status','version') if k in rule}
            
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
                'VERA_Ashwood_display'         # VERA Deluxe (legacy, migrated at startup)
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
            ORDER = ['Shutters_PVC_Eco', 'Shutters_PVC', 'Shutters_Pinewood', 'Shutters_Basswood', 'VERA_Ashwood_provisional']
            for code in ORDER:
                if code in product_map:
                    p = product_map[code]
                    # Check both new and old Ashwood codes for price rules
                    price_rule = imported.get(code) or imported.get('VERA_Ashwood_display')
                    if template is None:
                        price_rule = None
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
                    if template:
                        configured=bool(code in imported)
                        schema=next((r.get('schema') for r in template['products'] if r.get('source_code')==code),None)
                        p={**p,'published':True if configured else p.get('published',False),
                           'orderable':bool(configured),'orderable_after_login':bool(configured),
                           'configuration_schema':schema or p.get('configuration_schema',[])}
                    else:
                        p={**p,'published':False,'orderable':False,'orderable_after_login':False}
                    orderable_products.append({**p, 'price_rule': price_rule})
            
            current = template if active else None
            return {'products': orderable_products,
                    'addons': current.get('addons',[]) if current else [],
                    'pricing_parameters': {key:current.get(key) for key in ('installation_per_panel','minimum_installation','order_minimum_area','deposit_rate','tax_rate')} if current else {},
                    'pricing_status': 'configured' if {'Shutters_PVC_Eco','Shutters_PVC','Shutters_Pinewood','Shutters_Basswood'} <= set(imported) else 'rules_required'}

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
            d = {**calculate(c, body), 'id': oid, 'order_number': assign_business_number(c, p, body.project_name), 'order_number_confirmed':False, 'customer_id': cid, 'company': p['company'],
                 'customer_type': p.get('customer_type') or 'wholesale',
                 'contact_name': p['contact_name'], 'email': p['email'], 'phone': p['phone'],
                 'company_address': p['company_address'], 'project_name': body.project_name, 'site_address': body.site_address,
                 'status': 'pending_review', 'payment_status': 'deposit_unpaid', 'history': [], 'created_at': s.now(),
                 'request_hash': bodyhash(body),'installation_required':body.installation_required,'adjustments':{}}
            d['lead_time'] = lead_time_for(d['lines'])
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
            result=[]
            for d in records(c, 'project'):
                customer=profile(c,d['customer_id'])
                result.append({**enrich(c,d),'customer_type':d.get('customer_type') or customer.get('customer_type') or 'wholesale'})
            return result

    @app.post('/api/operations/orders/{oid}/order-number')
    def edit_order_number(oid: str, body: OrderNumberEdit, actor=Depends(s.require_admin)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, oid, 'project')
            if d.get('status') != 'pending_review' or d.get('order_number_confirmed', True):
                raise HTTPException(409, 'Only an unconfirmed order number on a pending order can be changed')
            previous = d.get('order_number')
            d['order_number'] = validate_order_number_unique(c, body.order_number, oid)
            event(d, 'order_number_edited', actor, previous=previous, order_number=d['order_number'])
            put(c, 'project', d, d['customer_id'])
            return enrich(c, d)

    @app.post('/api/operations/orders/{oid}/review')
    def review(oid: str, body: OrderReview | None = None, actor=Depends(s.require_admin)):
        body = body or OrderReview()
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, oid, 'project')
            if d['status'] != 'pending_review':
                return enrich(c, d)
            number_confirmation_required = d.get('order_number_confirmed') is False
            if number_confirmation_required and not body.confirm_order_number:
                raise HTTPException(409, 'Review and confirm the order number before accepting this quote')
            if body.order_number is not None and number_confirmation_required:
                d['order_number'] = validate_order_number_unique(c, body.order_number, oid)
            if d['total'] is None:
                # Re-price only an unreviewed submission; reviewed snapshots stay immutable.
                b = Project(project_name=d['project_name'], site_address=d['site_address'], submission_key='repricing',
                            installation_required=d.get('installation_required',False),
                            lines=[{k: line[k] for k in Window.model_fields if k in line} for line in d['lines']])
                d.update(calculate(c, b))
            if d['total'] is None:
                raise HTTPException(409, 'Price rules must be confirmed before review acceptance and invoicing')
            if number_confirmation_required:
                d['order_number_confirmed'] = True
                event(d, 'order_number_confirmed', actor, order_number=d.get('order_number'))
            d['status'] = 'accepted'
            d['accepted_at'] = s.now()
            d.setdefault('lead_time', lead_time_for(d['lines']))
            d['lead_time']['starts_at'] = d['accepted_at']
            event(d, 'review_accepted', actor)
            inv = {'id': 'deposit:'+oid, 'invoice_number': (d.get('order_number') or oid[-8:].upper()) + '-D', 'customer_id': d['customer_id'], 'kind': 'deposit', 'order_ids': [oid],
                   'amount': d.get('deposit') or deposit_amount(d['total']), 'currency': d['currency'], 'tax_basis': d['tax_basis'],
                   'deposit_rate': str(d.get('deposit_rate') or DEPOSIT_RATE), 'rounding': 'ROUND_UP_2DP',
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
    def supplier_order(oid: str, body: Supplier | None = None, actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, oid, 'project')
            if d['payment_status'] != 'deposit_received':
                raise HTTPException(409, 'Confirm the deposit before supplier ordering')
            if d['status'] == 'accepted':
                d['status'] = 'supplier_ordered'
                if body and body.reference:
                    d['supplier_reference'] = body.reference
                event(d, 'supplier_ordered', actor)
                put(c, 'project', d, d['customer_id'])
            elif d['status'] != 'supplier_ordered':
                raise HTTPException(409, 'Supplier ordering can only be recorded after deposit confirmation')
            elif body and body.reference:
                if d.get('supplier_reference') and d['supplier_reference'] != body.reference:
                    raise HTTPException(409, 'Supplier reference is already recorded')
                d['supplier_reference'] = body.reference
                put(c, 'project', d, d['customer_id'])
            return enrich(c, d)

    @app.get('/api/operations/orders/{oid}/supplier-export')
    def supplier_export(oid: str, provider_id: int | None = None, allow_basic_fallback: bool = False, actor=Depends(s.auth)):
        import json
        from fastapi.responses import Response
        from supplier_exports import export_supplier
        with s.db() as c:
            d = get(c, oid, 'project')
            # A paid order has necessarily had its deposit received.
            if d.get('payment_status') not in ('deposit_received', 'paid'):
                raise HTTPException(409, 'Confirm the deposit before exporting the supplier order')
            customer = profile(c, d['customer_id'])
            products = {row['id']: json.loads(row['data']) for row in c.execute('SELECT id,data FROM products')}
            export_lines = []
            for line in d.get('lines') or []:
                product = products.get(line.get('product_id'), {})
                export_lines.append({**line, 'product_category': product.get('category'),
                                     'source_code': line.get('source_code') or product.get('source_code'),
                                     'product_name': product.get('name_en')})
            try:
                raw = export_supplier({**d, 'lines': export_lines}, customer)
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
            event(d, 'supplier_exported', actor, format='VERA Order')
            put(c, 'project', d, d['customer_id'])
        return Response(raw, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': 'attachment; filename="vera-supplier-order.xlsx"', 'Cache-Control': 'no-store'})
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
            if body.kind == 'delivery' and d.get('payment_status') != 'paid':
                raise HTTPException(409, 'The balance must be paid before any delivery or completion')
            if len({line.line_id for line in body.lines}) != len(body.lines):
                raise HTTPException(422, 'Each line may occur only once per batch')
            field = 'arrived' if body.kind == 'arrival' else 'delivered'
            if body.kind == 'delivery' and not all(l['arrived'] == l['quantity'] for l in d['lines']):
                raise HTTPException(409, 'The whole order must have arrived before delivery')
            submitted = {q.line_id: q.quantity for q in body.lines}
            expected = {l['id']: l['quantity'] - l[field] for l in d['lines'] if l['quantity'] > l[field]}
            if not expected:
                raise HTTPException(409, 'The whole order is already recorded for this fulfilment step')
            if submitted != expected:
                raise HTTPException(422, 'Record the whole order in one arrival or delivery action; partial quantities are not accepted')
            scope = []
            for line in d['lines']:
                quantity = expected.get(line['id'], 0)
                if quantity:
                    line[field] += quantity
                    scope.append({'line_id': line['id'], 'window_name': line['window_name'], 'quantity': quantity})
            if body.kind == 'arrival':
                d['status'] = 'delivered' if all(l['delivered'] == l['quantity'] for l in d['lines']) else ('partially_delivered' if any(l['delivered'] for l in d['lines']) else 'arrived')
            else:
                d['status'] = 'delivered'
            d['arrival_status'] = 'arrived'
            d['delivery_status'] = 'delivered' if all(l['delivered'] == l['quantity'] for l in d['lines']) else ('partially_delivered' if any(l['delivered'] for l in d['lines']) else 'not_delivered')
            event(d, body.kind, actor, batch_id=rid, lines=scope)
            put(c, 'project', d, d['customer_id'])
            if body.kind == 'arrival':
                nid = queue(c, d['customer_id'], 'VERA arrival: '+d['project_name'],
                            'All goods for this order have arrived:\n'+'\n'.join(f"{l['window_name']}: {l['quantity']}" for l in scope)+'\nPlease contact VERA to arrange collection or installation.', 'arrival:'+rid)
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

    @app.get('/api/operations/invoices/{iid}/mail-preview')
    def invoice_mail_preview(iid: str, actor=Depends(s.auth)):
        # Read-only: the exact email (HTML and text) a send would produce, and who would really receive it.
        from email_service import configuration
        state = configuration()[0]
        with s.db() as c:
            model = invoice_email(c, iid)
            customer_email = profile(c, get(c, iid, 'invoice')['customer_id'])['email']
        demo = state['mode'] == 'demo'
        return {'invoice_id': iid, 'invoice_number': model['number'], 'subject': model['subject'], 'body': model['text'],
                'html': model['html'], 'content_type': 'text/html', 'attachment': model['number'] + '.pdf',
                'customer_recipient': customer_email, 'email_mode': state['mode'],
                'delivery_enabled': bool(state['delivery_enabled'] and state['configured']),
                'delivered_to': state['demo_recipient'] if demo else customer_email}

    @app.get('/api/operations/invoices/{iid}/pdf')
    def invoice_pdf(iid: str, actor=Depends(s.auth)):
        from fastapi.responses import Response
        with s.db() as c:
            model = invoice_email(c, iid)
        return Response(invoice_mail.render_pdf(model), media_type='application/pdf',
                        headers={'Content-Disposition': f'inline; filename="{model["number"]}.pdf"'})

    @app.post('/api/operations/invoices/{iid}/send')
    def send_invoice(iid: str, actor=Depends(s.auth)):
        nid = 'invoice-mail:'+iid
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            d = get(c, iid, 'invoice')
            row = c.execute('SELECT 1 FROM operations_records WHERE id=?', (nid,)).fetchone()
            model = invoice_email(c, iid)
            if not row:
                queue(c, d['customer_id'], model['subject'], model['text'], nid, iid, html=model['html'])
            else:
                old = get(c, nid, 'notification')
                if old['status'] in ('not_configured', 'demo_suppressed', 'pending'):
                    # Never delivered: refresh to the current format and try again. Delivered mail is never re-sent.
                    old.update(subject=model['subject'], body=model['text'], html=model['html'], status='pending')
                    old.pop('error', None)
                    put(c, 'notification', old, d['customer_id'])
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
            if any(d['payment_status'] != 'deposit_received' or not all(line['arrived'] == line['quantity'] for line in d['lines']) for d in orders):
                raise HTTPException(409, 'Balance invoices are available only after every line has arrived and the deposit is confirmed')
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
            d = {'id': iid, 'invoice_number': invoice_mail.invoice_number({'kind': 'balance', 'order_ids': [o['id'] for o in orders], 'id': iid}, {o['id']: o.get('order_number') for o in orders}),
                 'customer_id': cid, 'kind': 'balance', 'order_ids': [o['id'] for o in orders], 'lines': lines,
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
            projects = {d['id']:d for d in records(c,'project')}
            result=[]
            for row in c.execute('SELECT * FROM providers ORDER BY name').fetchall():
                assigned = c.execute('SELECT order_id,template_id FROM order_providers WHERE provider_id=?',(row['id'],)).fetchall()
                result.append({**dict(row),'orders':[{'id':a['order_id'],'order_number':projects[a['order_id']].get('order_number'),
                    'project_name':projects[a['order_id']]['project_name'],'template_id':a['template_id']}
                    for a in assigned if a['order_id'] in projects]})
            return result

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
            result=[]
            revisions={d['template_id']:d for d in records(c,'provider_template_revision')}
            for row in c.execute('SELECT * FROM provider_templates ORDER BY provider_id,name').fetchall():
                if provider_id and row['provider_id']!=provider_id: continue
                meta=revisions.get(row['id'],{})
                result.append({**dict(row),'revision':meta.get('revision'), 'supersedes_id':meta.get('supersedes_id'),
                               'family_id':meta.get('family_id',row['id'])})
            return result

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
            valid_fields={'order_id','order_number','project_name','company','contact_name','company_address','site_address','phone','email',
                         'window_name','product_id','width_mm','height_mm','quantity','panel_count','options','arrived','delivered'}
            for field in body.column_mappings:
                if field not in valid_fields:
                    raise HTTPException(422,f'Unknown field: {field}')
            validate_template(body.sheet_name, body.column_mappings)
            family_id=None
            revision=1
            if body.supersedes_id:
                parent=c.execute('SELECT * FROM provider_templates WHERE id=? AND provider_id=?',(body.supersedes_id,body.provider_id)).fetchone()
                if not parent: raise HTTPException(404,'Previous template revision not found for this supplier')
                meta=c.execute('SELECT data FROM operations_records WHERE id=?',('provider-template-revision:'+str(body.supersedes_id),)).fetchone()
                family_id=json.loads(meta['data'])['family_id'] if meta else body.supersedes_id
                previous=[v.get('revision',1) for v in records(c,'provider_template_revision') if v.get('family_id')==family_id]
                revision=max(previous or [1])+1
            cursor=c.execute('INSERT INTO provider_templates(provider_id,name,sheet_name,column_mappings,created_at) VALUES(?,?,?,?,?)',
                     (body.provider_id,body.name,body.sheet_name,json.dumps(body.column_mappings),s.now()))
            tid=cursor.lastrowid
            put(c,'provider_template_revision',{'id':'provider-template-revision:'+str(tid),'template_id':tid,
                'family_id':family_id or tid,'revision':revision,'supersedes_id':body.supersedes_id,'created_at':s.now(),'actor':actor})
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
                event(d,'supplier_assigned',actor,provider_id=body.provider_id,template_id=body.template_id)
                put(c,'project',d,d['customer_id'])
                return {'order_id':oid,'provider_id':body.provider_id,'template_id':body.template_id,'updated':True}
            c.execute('INSERT INTO order_providers(order_id,provider_id,template_id,is_preferred,assigned_at) VALUES(?,?,?,?,?)',
                     (oid,body.provider_id,body.template_id,1 if body.is_preferred else 0,s.now()))
            event(d,'supplier_assigned',actor,provider_id=body.provider_id,template_id=body.template_id)
            put(c,'project',d,d['customer_id'])
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
