"""Macro-free operational workbook output from one frozen project snapshot.

No source workbook is copied, so old customer rows/VBA cannot enter the export.
Every text value is an inline string (not an Excel formula).
"""
import io
import math
import re
import zipfile
from xml.etree import ElementTree as ET
from excel_rules import column


def export_project(project, kind='production'):
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ET.register_namespace('',ns)
    title='Production information — DRAFT (supplier format not yet confirmed)' if kind=='production' else 'Installation and delivery job sheet'
    rows=[ [title],['Project / order',project['project_name']+' / '+project.get('order_number',project['id'])],
          ['Company / contact',project['company']+' / '+project['contact_name']],
          ['Company address',project['company_address']],['Site address',project['site_address']],
          ['Phone / email',project['phone']+' / '+project['email']],
          ['Window','Source product','Width mm','Drop mm','Windows quantity','Panels per window','Configuration','Arrived','Delivered']]
    for line in project['lines']:
        rows.append([line['window_name'],line.get('source_code',str(line['product_id'])),line['width_mm'],line['height_mm'],
                     line['quantity'],line.get('panel_count',1),'; '.join(k+': '+(v[:60]+'…' if len(v)>60 else v) for k,v in line['options'].items() if v),line['arrived'],line['delivered']])
    rows += [[],['Full configuration'],['Window','Field','Value']]
    detail_start=len(rows)+1
    for line in project['lines']:
        for key,value in line['options'].items():
            if value: rows.append([line['window_name'],key,value])
    detail_end=len(rows)
    if kind=='job':
        rows += [[],['Actual delivery / installation notes'],[],['Customer confirmation signature'],['Completion date'],['Feedback']]
    sheet=ET.Element('{'+ns+'}worksheet')
    views=ET.SubElement(sheet,'{'+ns+'}sheetViews'); view=ET.SubElement(views,'{'+ns+'}sheetView',{'workbookViewId':'0','showGridLines':'0'})
    ET.SubElement(view,'{'+ns+'}pane',{'ySplit':'7','topLeftCell':'A8','activePane':'bottomLeft','state':'frozen'})
    cols=ET.SubElement(sheet,'{'+ns+'}cols')
    for i,width in enumerate([24,36,18,18,18,18,80,14,14],1):
        ET.SubElement(cols,'{'+ns+'}col',{'min':str(i),'max':str(i),'width':str(width),'customWidth':'1'})
    data=ET.SubElement(sheet,'{'+ns+'}sheetData')
    for r,values in enumerate(rows,1):
        length=max((len(str(v)) for v in values),default=0)
        height=max(30,16*math.ceil(length/(150 if r<=6 or detail_start<=r<=detail_end else 85))+12)
        row=ET.SubElement(data,'{'+ns+'}row',{'r':str(r),'ht':str(min(height,409)),'customHeight':'1'})
        for col,v in enumerate(values,1):
            numeric=8<=r<=7+len(project['lines']) and col in (3,4,5,6,8,9)
            cell=ET.SubElement(row,'{'+ns+'}c',{'r':column(col)+str(r),'s':'1' if r==7 else '0',**({} if numeric else {'t':'inlineStr'})})
            if numeric:
                ET.SubElement(cell,'{'+ns+'}v').text=str(v)
            else:
                inline=ET.SubElement(cell,'{'+ns+'}is'); ET.SubElement(inline,'{'+ns+'}t').text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(v))
    merges=ET.SubElement(sheet,'{'+ns+'}mergeCells')
    for ref in ['A1:I1']+['B'+str(r)+':I'+str(r) for r in range(2,7)]+['C'+str(r)+':I'+str(r) for r in range(detail_start,detail_end+1)]:
        ET.SubElement(merges,'{'+ns+'}mergeCell',ref=ref)
    ET.SubElement(sheet,'{'+ns+'}pageSetup',{'orientation':'landscape','paperSize':'9','fitToWidth':'1','fitToHeight':'0'})
    styles=f'''<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF183B2C"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs></styleSheet>'''
    styles=styles.replace('</styleSheet>','<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    package={
        '[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml':f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Project" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml':styles,'xl/worksheets/sheet1.xml':ET.tostring(sheet,encoding='utf-8')}
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,content in package.items():
            z.writestr(name,content)
    return out.getvalue()
