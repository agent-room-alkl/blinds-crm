"""Invoice presentation: readable numbers, plain-text and HTML email bodies, and a PDF copy.

Everything here is derived from stored invoice/order/customer facts. No payment details are invented:
the footer is configurable with VERA_INVOICE_FOOTER and otherwise only asks the customer to contact VERA.
"""
import io
import os
import re
from decimal import Decimal
from html import escape

BRAND = 'VERA Shading Solutions'
DEFAULT_FOOTER = 'Please contact VERA to arrange payment. Questions about this invoice are welcome by reply to this email.'
_CJK = re.compile(r'([⺀-鿿＀-￯]+)')


def footer():
    return os.getenv('VERA_INVOICE_FOOTER', '').strip() or DEFAULT_FOOTER


def money(value):
    return f'{Decimal(str(value)):,.2f}'


def invoice_number(invoice, order_numbers):
    """Deposit V0000101-D, balance V0000105-B. Derived from the order number, so it is stable and needs no migration.
    A balance invoice covering several orders is named after its first order; each order has at most one balance invoice."""
    letter = 'D' if invoice.get('kind') == 'deposit' else 'B'
    numbers = sorted(order_numbers.get(oid) or '' for oid in invoice.get('order_ids', []))
    first = next((n for n in numbers if n), '')
    if not first:
        first = re.sub(r'[^A-Za-z0-9]', '', str(invoice.get('id', '')))[-8:].upper() or 'INVOICE'
    return f'{first}-{letter}'


def build(invoice, customer, orders):
    """invoice: stored invoice dict; customer: portal profile dict; orders: {order_id: project dict}."""
    numbers = {oid: o.get('order_number') for oid, o in orders.items()}
    number = invoice_number(invoice, numbers)
    deposit = invoice.get('kind') == 'deposit'
    currency = invoice.get('currency', 'NZD')
    rows = []
    for line in invoice.get('lines', []):
        order = orders.get(line['order_id'], {})
        rows.append({
            'order': order.get('order_number') or line['order_id'],
            'project': order.get('project_name', ''),
            'site': order.get('site_address', ''),
            'order_total': order.get('total'),
            'amount': line['amount'],
        })
    due = Decimal(invoice['amount'])
    gross = Decimal(invoice['gross']) if invoice.get('gross') else sum((Decimal(r['amount']) for r in rows), Decimal(0))
    rebate = max(gross - due, Decimal(0))
    model = {
        'number': number,
        'kind': 'Deposit invoice' if deposit else 'Balance invoice',
        'date': str(invoice.get('created_at', ''))[:10],
        'currency': currency,
        'tax_basis': str(invoice.get('tax_basis', '')).replace('_', ' '),
        'company': customer.get('company', ''),
        'contact': customer.get('contact_name', ''),
        'address': customer.get('company_address', ''),
        'rows': rows,
        'gross': money(gross),
        'rebate': money(rebate) if rebate > 0 else '',
        'due': money(due),
        'basis': (f"Deposit of {Decimal(invoice.get('deposit_rate', '0.6')) * 100:.0f}% of the order total."
                  if deposit else 'Order total less the deposit already paid.'),
        'footer': footer(),
    }
    model['subject'] = f"VERA invoice {number}"
    model['text'] = _text(model)
    model['html'] = _html(model)
    return model


def _text(m):
    lines = [f"{BRAND}", f"{m['kind']} {m['number']}", f"Date: {m['date']}", '',
             f"Bill to: {m['company']}" + (f" ({m['contact']})" if m['contact'] else '')]
    if m['address']:
        lines.append(m['address'])
    lines.append('')
    for r in m['rows']:
        lines.append(f"{r['order']}  {r['project']}  {m['currency']} {money(r['amount'])}")
    lines.append('')
    if m['rebate']:
        lines += [f"Subtotal: {m['currency']} {m['gross']}", f"Rebate applied: -{m['currency']} {m['rebate']}"]
    lines += [f"Amount due: {m['currency']} {m['due']}", m['basis'], '', m['footer'], 'The PDF invoice is attached.']
    return '\n'.join(lines)


def _html(m):
    e = escape
    green, ink, line = '#0f6e5c', '#1b2421', '#e1e8e3'
    rows = ''.join(
        f'<tr><td style="padding:12px 0;border-bottom:1px solid {line};font-size:14px;color:{ink}">'
        f'<strong>{e(str(r["order"]))}</strong><br><span style="color:#64766b;font-size:12px">{e(r["project"])}'
        f'{" · " + e(r["site"]) if r["site"] else ""}</span></td>'
        f'<td align="right" style="padding:12px 0;border-bottom:1px solid {line};font-size:14px;color:{ink};white-space:nowrap">'
        f'{e(m["currency"])} {money(r["amount"])}</td></tr>' for r in m['rows'])
    extra = ''
    if m['rebate']:
        extra = (f'<tr><td style="padding:8px 0;font-size:13px;color:#64766b">Subtotal</td><td align="right" style="padding:8px 0;font-size:13px;color:#64766b">{e(m["currency"])} {m["gross"]}</td></tr>'
                 f'<tr><td style="padding:4px 0 12px;font-size:13px;color:#64766b">Rebate applied</td><td align="right" style="padding:4px 0 12px;font-size:13px;color:#64766b">-{e(m["currency"])} {m["rebate"]}</td></tr>')
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;padding:0;background:#f4f7f5;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:{ink}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7f5;padding:24px 12px"><tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid {line}">
<tr><td style="background:{green};padding:26px 32px;color:#ffffff"><div style="font-size:12px;letter-spacing:.16em;opacity:.8">{e(BRAND.upper())}</div>
<div style="font-size:24px;font-weight:700;margin-top:6px">{e(m["kind"])}</div><div style="font-size:14px;opacity:.9;margin-top:2px">{e(m["number"])}</div></td></tr>
<tr><td style="padding:28px 32px 8px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td valign="top" style="font-size:13px;line-height:1.6"><div style="color:#64766b;font-size:11px;letter-spacing:.1em">BILL TO</div><strong>{e(m["company"])}</strong>{"<br>" + e(m["contact"]) if m["contact"] else ""}{"<br>" + e(m["address"]) if m["address"] else ""}</td>
<td valign="top" align="right" style="font-size:13px;line-height:1.6"><div style="color:#64766b;font-size:11px;letter-spacing:.1em">INVOICE DATE</div><strong>{e(m["date"])}</strong></td></tr></table></td></tr>
<tr><td style="padding:12px 32px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td style="padding:8px 0;border-bottom:2px solid {ink};font-size:11px;letter-spacing:.1em;color:#64766b">ORDER</td><td align="right" style="padding:8px 0;border-bottom:2px solid {ink};font-size:11px;letter-spacing:.1em;color:#64766b">AMOUNT</td></tr>
{rows}{extra}</table></td></tr>
<tr><td style="padding:8px 32px 24px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef6f2;border-radius:10px"><tr>
<td style="padding:16px 18px;font-size:13px;color:#34503f">Amount due<br><span style="font-size:11px;color:#64766b">{e(m["basis"])}</span></td>
<td align="right" style="padding:16px 18px;font-size:26px;font-weight:700;color:{green};white-space:nowrap">{e(m["currency"])} {m["due"]}</td></tr></table></td></tr>
<tr><td style="padding:0 32px 28px;font-size:13px;line-height:1.7;color:#4d6256">{e(m["footer"])}<br><span style="color:#64766b">The PDF invoice is attached to this email.</span></td></tr>
</table></td></tr></table></body></html>'''


def render_pdf(m):
    """A4 PDF with the same content as the email. CJK names use the built-in CID font, so no font files are shipped."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    try:
        pdfmetrics.getFont('STSong-Light')
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

    def P(text, style):
        safe = _CJK.sub(lambda g: f'<font name="STSong-Light">{g.group(1)}</font>', escape(str(text)))
        return Paragraph(safe, style)

    green, ink, muted = colors.HexColor('#0f6e5c'), colors.HexColor('#1b2421'), colors.HexColor('#64766b')
    base = ParagraphStyle('base', fontName='Helvetica', fontSize=10, leading=14, textColor=ink)
    small = ParagraphStyle('small', parent=base, fontSize=8.5, leading=11, textColor=muted)
    right = ParagraphStyle('right', parent=base, alignment=2)
    title = ParagraphStyle('title', parent=base, fontName='Helvetica-Bold', fontSize=22, leading=26, textColor=green)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"{m['kind']} {m['number']}", author=BRAND)
    story = [P(BRAND.upper(), small), P(m['kind'], title), P(m['number'], base), Spacer(1, 8 * mm)]
    head = Table([[P('BILL TO', small), P('INVOICE DATE', small)],
                  [P(m['company'], base), P(m['date'], right)]], colWidths=[110 * mm, 60 * mm])
    head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story.append(head)
    for extra in (m['contact'], m['address']):
        if extra:
            story.append(P(extra, small))
    story.append(Spacer(1, 8 * mm))
    data = [[P('ORDER', small), P('PROJECT', small), P('AMOUNT', ParagraphStyle('r', parent=small, alignment=2))]]
    for r in m['rows']:
        project = r['project'] + (f" - {r['site']}" if r['site'] else '')
        data.append([P(r['order'], base), P(project, base), P(f"{m['currency']} {money(r['amount'])}", right)])
    table = Table(data, colWidths=[32 * mm, 98 * mm, 40 * mm], repeatRows=1)
    table.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, 0), 1, ink), ('LINEBELOW', (0, 1), (-1, -1), 0.4, colors.HexColor('#dfe7e1')),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story += [table, Spacer(1, 4 * mm)]
    totals = []
    if m['rebate']:
        totals += [[P('Subtotal', base), P(f"{m['currency']} {m['gross']}", right)], [P('Rebate applied', base), P(f"-{m['currency']} {m['rebate']}", right)]]
    totals.append([P('<b>Amount due</b>', base), P(f"<b>{m['currency']} {m['due']}</b>", right)])
    t = Table(totals, colWidths=[130 * mm, 40 * mm])
    t.setStyle(TableStyle([('LINEABOVE', (0, -1), (-1, -1), 1, green), ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                           ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story += [t, Spacer(1, 3 * mm), P(m['basis'], small)]
    if m['tax_basis']:
        story.append(P(f"Pricing basis: {m['tax_basis']}", small))
    story += [Spacer(1, 12 * mm), P(m['footer'], base)]
    doc.build(story)
    return buf.getvalue()
