"""Build a clean, macro-free supplier order using the VERA Order sheet fields."""
import io
import re
import zipfile
from xml.etree import ElementTree as ET

from excel_rules import column


def export_supplier(project, customer, max_lines=29):
    lines = project.get('lines') or []
    if len(lines) > max_lines:
        raise ValueError(f'Supplier template supports at most {max_lines} window rows')

    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ET.register_namespace('', ns)
    rows = [
        ['', 'Customer Name', customer.get('contact_name', ''), '', '', '', '', 'Type', (customer.get('customer_type') or 'wholesale').title(), '', '', '', '', 'Order Number', project.get('order_number') or project.get('project_name', '')],
        ['', 'Company Name', project.get('company', ''), '', '', '', '', 'Refer By', '', '', '', '', '', '', ''],
        ['', 'Phone', project.get('phone', ''), '', '', '', '', '', '', '', '', '', '', '', ''],
        ['', 'Address', project.get('company_address', ''), '', '', '', '', 'Installed', 'Yes' if project.get('installation_required') else 'No', '', '', '', '', '', ''],
        ['', 'Delivery / site address', project.get('site_address', ''), '', '', '', '', 'Estimated lead time', project.get('lead_time', {}).get('text', '10–12 weeks from order confirmation')],
        ['Blinds', 'Window Location', 'Width\n(mm)', 'Drop\n(mm)', 'Product', '', "Panel\nQ'ty", 'Control Side', '', '', '', 'Bracket Colour', 'Chain Colour', 'Main Colour', 'Bottom Rail Colour', 'In/Out\nFit', 'Special Request'],
        ['Shutters', 'Window Location', 'Width\n(mm)', 'Drop\n(mm)', 'Product', 'Open Method', "Panel\nQ'ty", 'Layout Code', 'VT\nPost', 'HT\nPost', 'Midrail', 'Frame', 'Louver Size', 'Colour', 'Control Rod', 'Fitting', 'Special Request'],
    ]

    shutter_keys = {'opening_style', 'layout_code', 'vt_post', 'ht_post', 'midrail', 'frame', 'louver_size', 'colour', 'control_rod', 'fitting', 'special_request'}
    blind_keys = {'control_side', 'bracket_colour', 'chain_colour', 'colour', 'bottom_rail_colour', 'fitting', 'special_request'}
    for line in lines:
        category = str(line.get('product_category') or '').lower()
        code = str(line.get('source_code') or '').lower()
        is_shutter = category in {'shutter', 'shutters'} or code.startswith('shutters_')
        keys = shutter_keys if is_shutter else blind_keys
        options = line.get('options') or {}
        known = {key: options.get(key, '') for key in keys}
        extra = [f'{key}: {value}' for key, value in options.items() if key not in keys and value]
        special = '; '.join(v for v in [known.get('special_request', ''), *extra] if v)
        if is_shutter:
            values = ['Shutters', line.get('window_name', ''), line.get('width_mm', ''), line.get('height_mm', ''),
                      line.get('source_code') or line.get('product_name') or line.get('product_id', ''),
                      known['opening_style'], line.get('panel_count', 1), known['layout_code'], known['vt_post'],
                      known['ht_post'], known['midrail'], known['frame'], known['louver_size'], known['colour'],
                      known['control_rod'], known['fitting'], special]
        else:
            values = ['Blinds', line.get('window_name', ''), line.get('width_mm', ''), line.get('height_mm', ''),
                      line.get('source_code') or line.get('product_name') or line.get('product_id', ''), '',
                      line.get('panel_count', 1), known['control_side'], '', '', '', known['bracket_colour'],
                      known['chain_colour'], known['colour'], known['bottom_rail_colour'], known['fitting'], special]
        rows.append(values)

    sheet = ET.Element('{'+ns+'}worksheet')
    views = ET.SubElement(sheet, '{'+ns+'}sheetViews')
    view = ET.SubElement(views, '{'+ns+'}sheetView', {'workbookViewId': '0', 'showGridLines': '0'})
    ET.SubElement(view, '{'+ns+'}pane', {'ySplit': '7', 'topLeftCell': 'A8', 'activePane': 'bottomLeft', 'state': 'frozen'})
    cols = ET.SubElement(sheet, '{'+ns+'}cols')
    for index, width in enumerate([12, 24, 14, 14, 24, 20, 12, 20, 16, 16, 16, 20, 20, 20, 22, 20, 48], 1):
        ET.SubElement(cols, '{'+ns+'}col', {'min': str(index), 'max': str(index), 'width': str(width), 'customWidth': '1'})
    data = ET.SubElement(sheet, '{'+ns+'}sheetData')
    for row_index, values in enumerate(rows, 1):
        row = ET.SubElement(data, '{'+ns+'}row', {'r': str(row_index), 'ht': '30', 'customHeight': '1'})
        for col_index, value in enumerate(values, 1):
            if value in (None, ''):
                continue
            numeric = row_index >= 8 and col_index in (3, 4, 7)
            cell = ET.SubElement(row, '{'+ns+'}c', {'r': column(col_index)+str(row_index), **({} if numeric else {'t': 'inlineStr'}), 's': '1' if row_index in (6, 7) else '0'})
            if numeric:
                ET.SubElement(cell, '{'+ns+'}v').text = str(value)
            else:
                inline = ET.SubElement(cell, '{'+ns+'}is')
                ET.SubElement(inline, '{'+ns+'}t').text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value))
    ET.SubElement(sheet, '{'+ns+'}pageMargins', {'left': '0.25', 'right': '0.25', 'top': '0.5', 'bottom': '0.5', 'header': '0.2', 'footer': '0.2'})
    ET.SubElement(sheet, '{'+ns+'}pageSetup', {'orientation': 'landscape', 'paperSize': '9', 'fitToWidth': '1', 'fitToHeight': '0'})

    styles = f'''<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF183B2C"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    package = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Order" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml': styles,
        'xl/worksheets/sheet1.xml': ET.tostring(sheet, encoding='utf-8'),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in package.items():
            archive.writestr(name, content)
    return output.getvalue()
