"""Invented demonstration workbook: no customer prices or records."""
import io,zipfile
from decimal import Decimal
from xml.etree import ElementTree as ET
from excel_rules import column

CODES=['Shutters_PVC','Shutters_PVC_Eco','Shutters_Pinewood','Shutters_Basswood','Shutters_Aluminium',
       'Roller_Blinds_BO_VIBE','Roller_Blinds_BO_LeReve','Roller_Blinds_BO_Skye','Roller_Blinds_BO_Karma','Roller_Blinds_BO_Mantra',
       'Roller_Blinds_Sunscreen','Roller_Blinds_LF_LeReve','Roller_Blinds_LF_Skye','Roller_Blinds_LF_Mantra',
       'Venetian_Blinds_PVC','Venetian_Blinds_Wood','Venetian_Blinds_Aluminium_25mm','Venetian_Blinds_Aluminium_50mm',
       'Vertical_Blinds_VIBE_89mm','Vertical_Blinds_VIBE_100mm','Vertical_Blinds_Karma_89mm','Exterior_Blinds_Mesh','Exterior_Blinds_ClearPVC']

def fixture():
    """Entirely invented price values; recognizable template layout only."""
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    cells={name:{} for name in ['Product Listing','Pricing','Order','In Put']}
    names={}
    for n,code in enumerate(CODES,2):
        cells['Product Listing']['A'+str(n)]=code
        cells['Product Listing']['B'+str(n)]='White TEST'
        names[code]="'Product Listing'!$B$"+str(n)
        if n<=6:
            cells['Pricing']['A'+str(483+n)]=code
            cells['Pricing']['B'+str(483+n)]='100'
        else:
            names[code+'_w']='Pricing!$B$1:$C$1';names[code+'_h']='Pricing!$A$2:$A$3';names[code+'_Price']='Pricing!$B$2:$C$3'
        cells['Pricing']['A'+str(489+n)]=code
        cells['Pricing']['B'+str(489+n)]='10'
    # The client workbook defines Fitting as the row B101:D101. The demo used a single cell, so it
    # offered one fitting option and refused the other two — a demo-only gap that reads as a product bug.
    cells['Product Listing']['B101']='In Fit';cells['Product Listing']['C101']='Out Fit'
    cells['Product Listing']['D101']='Make Size';names['Fitting']="'Product Listing'!$B$101:$D$101"
    for col in range(2,10):cells['Product Listing'][column(col)+'102']=str(Decimal(col-1)/20)
    cells['Pricing'].update({'B1':'500','C1':'1000','A2':'500','A3':'1000','B2':'100','C2':'150','B3':'200','C3':('ROUNDUP(B2*1.35,0)','0')})
    cells['In Put'].update({'Q33':('(Q31+N(Q32))*0.15',None),'Q32':('IF(Order!I4,MAX(SUM(Order!X8:X500),150),"Supply Only")',None)})
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        wb=ET.Element('workbook',xmlns=ns);sh=ET.SubElement(wb,'sheets')
        rel=ET.Element('Relationships',xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        for i,(name,values) in enumerate(cells.items(),1):
            ET.SubElement(sh,'sheet',{'name':name,'sheetId':str(i),'{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id':'r'+str(i)})
            ET.SubElement(rel,'Relationship',Id='r'+str(i),Target='worksheets/sheet'+str(i)+'.xml')
            sheet=ET.Element('worksheet',xmlns=ns);data=ET.SubElement(sheet,'sheetData')
            for ref,val in values.items():
                row=ET.SubElement(data,'row',r='1');cell=ET.SubElement(row,'c',r=ref)
                if isinstance(val,tuple):
                    ET.SubElement(cell,'f').text=val[0]
                    if val[1] is not None:ET.SubElement(cell,'v').text=val[1]
                else:
                    cell.set('t','inlineStr'); inline=ET.SubElement(cell,'is');ET.SubElement(inline,'t').text=val
            z.writestr('xl/worksheets/sheet'+str(i)+'.xml',ET.tostring(sheet))
        defs=ET.SubElement(wb,'definedNames')
        for name,target in names.items():ET.SubElement(defs,'definedName',name=name).text=target
        z.writestr('xl/workbook.xml',ET.tostring(wb));z.writestr('xl/_rels/workbook.xml.rels',ET.tostring(rel))
    return out.getvalue()
