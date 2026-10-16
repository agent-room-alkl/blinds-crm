"""Read-only import of the supplied order workbook. No VBA or formula eval().

Actual customer prices stay in the private database, never in source control.
Only recognized Pricing ROUNDUP formulas are evaluated; unsupported ones fail closed.
"""
import hashlib
import io
import re
import zipfile
from decimal import Decimal, ROUND_UP
from xml.etree import ElementTree as ET

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def column(n):
    out = ''
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def coordinate(ref):
    m = re.fullmatch(r'\$?([A-Z]+)\$?(\d+)', ref)
    if not m:
        raise ValueError('Invalid cell reference')
    n = 0
    for ch in m[1]:
        n = n * 26 + ord(ch) - 64
    return n, int(m[2])


def translate(formula, origin, target):
    oc, orow = coordinate(origin)
    tc, tr = coordinate(target)
    def shift(m):
        c, row = coordinate(m[0])
        return ('$' if m[1] else '') + column(c if m[1] else c+tc-oc) + ('$' if m[3] else '') + str(row if m[3] else row+tr-orow)
    return re.sub(r'(\$?)([A-Z]+)(\$?)(\d+)', shift, formula)


def workbook(raw):
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('Workbook exceeds 10MB')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if sum(i.file_size for i in z.infolist()) > 60 * 1024 * 1024 or len(z.infolist()) > 3000:
            raise ValueError('Workbook expands beyond allowed limits')
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(t.text or '' for t in si.findall('.//m:t', NS)) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        rels = {r.attrib['Id']: r.attrib['Target'].lstrip('/') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        names = {n.attrib['name']: n.text for n in wb.findall('m:definedNames/m:definedName', NS)}
        sheets = {}
        for sheet in wb.findall('m:sheets/m:sheet', NS):
            path = rels[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            if not path.startswith('xl/'):
                path = 'xl/' + path
            cells, shared, pending = {}, {}, []
            for c in ET.fromstring(z.read(path)).findall('.//m:sheetData/m:row/m:c', NS):
                ref = c.attrib['r']
                v = c.findtext('m:v', namespaces=NS)
                if c.attrib.get('t') == 's' and v is not None:
                    v = strings[int(v)]
                elif c.attrib.get('t') == 'inlineStr':
                    v = ''.join(t.text or '' for t in c.findall('.//m:t', NS))
                f = c.find('m:f', NS)
                formula = f.text if f is not None else None
                cells[ref] = {'value': v, 'formula': formula}
                if f is not None and f.attrib.get('t') == 'shared':
                    si = f.attrib['si']
                    if formula:
                        shared[si] = (ref, formula)
                    else:
                        pending.append((ref, si))
            for ref, si in pending:
                if si not in shared:
                    raise ValueError('Missing shared formula anchor')
                origin, formula = shared[si]
                cells[ref]['formula'] = translate(formula, origin, ref)
            sheets[sheet.attrib['name']] = cells
        return sheets, names


def numeric(cells, ref, stack=None):
    stack = set() if stack is None else stack
    if ref in stack:
        raise ValueError('Circular pricing formula')
    cell = cells.get(ref, {})
    if cell.get('formula'):
        m = re.fullmatch(r'ROUNDUP\((\$?[A-Z]+\$?\d+)\*([0-9.]+),([0-6])\)', cell['formula'].replace(' ', ''), re.I)
        if not m:
            raise ValueError('Unsupported Pricing formula at '+ref)
        value = numeric(cells, m[1].replace('$', ''), stack | {ref}) * Decimal(m[2])
        return value.quantize(Decimal(1).scaleb(-int(m[3])), rounding=ROUND_UP)
    try:
        result = Decimal(cell.get('value') or 'NaN')
    except Exception:
        raise ValueError('Non-numeric price at '+ref) from None
    if not result.is_finite() or result < 0:
        raise ValueError('Missing or negative price at '+ref)
    return result


def named_values(sheets, names, name, numeric_values=False):
    if name not in names:
        return []
    m = re.fullmatch(r"'?([^']+?)'?!([A-Z$]+\d+)(?::([A-Z$]+\d+))?", names[name])
    if not m or m[1] not in sheets:
        raise ValueError('Unsupported named range '+name)
    c1, r1 = coordinate(m[2]); c2, r2 = coordinate(m[3] or m[2])
    rows = []
    for row in range(r1, r2 + 1):
        vals = []
        for col in range(c1, c2 + 1):
            ref = column(col)+str(row)
            val = str(numeric(sheets[m[1]], ref)) if numeric_values else sheets[m[1]].get(ref, {}).get('value')
            vals.append(val)
        rows.append(vals)
    return rows


def parse_template(raw):
    sheets, names = workbook(raw)
    if not {'Product Listing', 'Pricing', 'Order', 'In Put'} <= sheets.keys():
        raise ValueError('Expected Product Listing, Pricing, Order and In Put sheets')
    listing, pricing, summary = sheets['Product Listing'], sheets['Pricing'], sheets['In Put']
    codes = [listing.get('A'+str(row), {}).get('value') for row in range(2, 25)]
    if any(not code or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,100}', code) for code in codes) or len(set(codes)) != len(codes):
        raise ValueError('Expected 23 distinct product codes in Product Listing A2:A24')
    tax_formula = summary.get('Q33', {}).get('formula', '')
    install_formula = summary.get('Q32', {}).get('formula', '')
    tax_match = re.fullmatch(r'\(Q31\+N\(Q32\)\)\*([0-9.]+)', tax_formula)
    minimum_match = re.fullmatch(r'IF\(Order!I4,MAX\(SUM\(Order!X8:X500\),([0-9.]+)\),"Supply Only"\)', install_formula)
    if not tax_match or not minimum_match:
        raise ValueError('Unrecognized order GST/installation rule; confirm the new template')
    version = hashlib.sha256(raw).hexdigest()
    warnings, products = [], []
    labels = {
        'frame': ('框型', 'Frame'), 'louver_size': ('叶片尺寸', 'Louver size'), 'colour': ('颜色', 'Colour'),
        'control_rod': ('控制杆', 'Control rod'), 'bracket_colour': ('支架颜色', 'Bracket colour'),
        'chain_colour': ('链颜色', 'Chain colour'), 'bottom_rail_colour': ('底轨颜色', 'Bottom rail colour'),
        'control_side': ('控制侧', 'Control side'), 'layout_code': ('布局代码', 'Layout code'),
        'opening_style': ('开合方式', 'Opening style'),
        'vt_post': ('竖柱', 'Vertical post'), 'ht_post': ('横柱', 'Horizontal post'), 'midrail': ('中横档', 'Midrail'),
        'fitting': ('安装尺寸类型', 'Fitting'), 'special_request': ('特殊要求', 'Special request')}
    def schema(key, choices=(), required=False):
        return {'key': key, 'label_zh': labels[key][0], 'label_en': labels[key][1], 'choices': list(choices),
                'required': required, 'type': 'select' if choices else 'text'}
    for code in codes:
        shutter = code.startswith('Shutters_')
        choices = {}
        for key, suffix in [('colour', ''), ('frame' if shutter else 'bracket_colour', 'C1'),
                            ('louver_size' if shutter else 'chain_colour', 'C2'), ('control_rod' if shutter else 'bottom_rail_colour', 'C4')]:
            vals = [str(v) for row in named_values(sheets, names, code+suffix) for v in row if v not in (None, '')]
            choices[key] = vals
        fields = [schema(k, v, bool(v)) for k, v in choices.items()]
        fields += [schema(k) for k in (['opening_style','layout_code','vt_post','ht_post','midrail'] if shutter else ['control_side'])]
        fit = [v for row in named_values(sheets, names, 'Fitting') for v in row if v]
        fields += [schema('fitting', fit, bool(fit)), schema('special_request')]
        install_row = next((row for row in range(491,515) if pricing.get('A'+str(row), {}).get('value') == code), None)
        p = {'source_code': code, 'kind': 'shutter' if shutter else 'blind', 'schema': fields, 'version': version,
             'options': {k: {v: {} for v in values} for k, values in choices.items() if values},
             'installation_rate': str(numeric(pricing, 'B'+str(install_row))) if install_row else None,
             'status': 'configured', 'warnings': []}
        if install_row is None:
            p['warnings'].append('Installation price is missing; installation quotes are blocked for this product')
        try:
            if shutter:
                rate_row = next((row for row in range(485,490) if pricing.get('A'+str(row), {}).get('value') == code), None)
                if rate_row is None:
                    raise ValueError('Missing shutter area rate')
                p.update(formula='excel_shutter', rate_per_m2=str(numeric(pricing, 'B'+str(rate_row))), minimum_area='0.5')
            else:
                widths = [v for row in named_values(sheets,names,code+'_w',True) for v in row]
                heights = [v for row in named_values(sheets,names,code+'_h',True) for v in row]
                matrix = named_values(sheets,names,code+'_Price',True)
                if not widths or not heights or len(matrix)!=len(heights) or any(len(row)!=len(widths) for row in matrix):
                    raise ValueError('Missing/inconsistent width/drop price matrix')
                if any(Decimal(a)>=Decimal(b) for axis in (widths, heights) for a,b in zip(axis,axis[1:])):
                    raise ValueError('Price matrix axes are not strictly increasing')
                p.update(formula='excel_matrix', widths=widths, heights=heights, matrix=matrix)
        except ValueError as e:
            p.update(status='rules_required', reason=str(e))
            warnings.append(code+': '+str(e))
        warnings.extend(code+': '+w for w in p['warnings'])
        products.append(p)
    return {'version': version, 'products': products, 'warnings': warnings, 'tax_rate': tax_match[1],
            'minimum_installation': minimum_match[1], 'discounts': [listing.get(column(c)+'102', {}).get('value') for c in range(2,10)],
            'source': 'Client order workbook; Product Listing / Pricing / Order / In Put'}


def up(v, places=2):
    return Decimal(v).quantize(Decimal(1).scaleb(-places), rounding=ROUND_UP)


def calculate_line(rule, line, adjustment=None):
    if rule['status'] != 'configured':
        raise ValueError(rule.get('reason', 'Product price rule is missing'))
    supplied = line['options']
    allowed = {f['key']: f for f in rule['schema']}
    if set(supplied)-allowed.keys():
        raise ValueError('Unsupported product fields')
    for key, field in allowed.items():
        value = supplied.get(key, '')
        if field['required'] and not value:
            raise ValueError('Complete '+field['label_en'])
        if value and field['choices'] and value not in field['choices']:
            raise ValueError('Unsupported '+field['label_en'])
        if len(value)>1000:
            raise ValueError('Configuration text is too long')
    a = adjustment or {}
    discount = Decimal(a.get('discount', '0'))
    surcharge = Decimal(a.get('product_surcharge', '0'))
    width, height = Decimal(line['width_mm']), Decimal(line['height_mm'])
    if rule['formula']=='excel_shutter':
        area = max(up(width*height/1000000), Decimal(rule['minimum_area']))
        base = area * Decimal(rule['rate_per_m2'])
    else:
        col = next((i for i,v in enumerate(rule['widths']) if Decimal(v)>=width),None)
        row = next((i for i,v in enumerate(rule['heights']) if Decimal(v)>=height),None)
        if col is None or row is None:
            raise ValueError('Dimensions exceed the confirmed price matrix')
        area, base = Decimal(1), Decimal(rule['matrix'][row][col])
    if base<=0:
        raise ValueError('The selected dimensions have no positive confirmed price')
    unit = up((base+surcharge)*(1-discount))
    install_rate = Decimal(rule['installation_rate']) if rule['installation_rate'] is not None else None
    install = None if install_rate is None else up(install_rate*(line.get('panel_count',1) if rule['kind']=='shutter' else 1)+Decimal(a.get('installation_surcharge','0')))
    return {'area': str(area), 'unit_price': str(unit), 'amount': str(unit*line['quantity']),
            'installation_amount': None if install is None else str(install*line['quantity']),
            'discount': str(discount), 'product_surcharge': str(surcharge), 'installation_surcharge': str(a.get('installation_surcharge','0'))}
