"""Receipts read posted sales. Rendering never posts or changes inventory."""
from datetime import datetime
from html import escape
from io import BytesIO
import json
import os
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

from cryptography.fernet import InvalidToken
from sqlalchemy import select
from app.infrastructure import database as db
from app.ledger import RuleError
from app.modules.sales.customers import cipher, details

ASSETS = Path(__file__).resolve().parents[2] / 'assets'
FONT_LOCK = Lock()


def shop_header():
    result = {k: os.getenv(env, default).strip() for k, env, default in (
        ('name', 'KCD_RECEIPT_SHOP_NAME', 'Kakinada Car Decors'),
        ('address', 'KCD_RECEIPT_SHOP_ADDRESS', ''),
        ('phone', 'KCD_RECEIPT_SHOP_PHONE', ''))}
    if not result['name'] or any(len(v) > 500 for v in result.values()):
        raise RuleError('Check the shop receipt header configuration', 503)
    result['confirmed'] = bool(os.getenv('KCD_RECEIPT_SHOP_DETAILS_CONFIRMED') == '1'
                               and result['address'] and result['phone'])
    return result


def ist(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Kolkata'))


def save_receipt(conn, sale_id, customer_id):
    sale = conn.execute(select(db.documents).where(db.documents.c.id == sale_id)).mappings().one()
    encrypted = None
    if customer_id:
        customer = details(conn.execute(select(db.customers).where(db.customers.c.id == customer_id)).mappings().one())
        # Address is deliberately absent from the issued receipt snapshot.
        encrypted = cipher().encrypt(json.dumps({k: customer[k] for k in ('name', 'phone')}).encode()).decode()
    conn.execute(db.sale_receipts.insert().values(id=sale_id,
        number=f"KCD-{ist(sale['created_at']):%Y%m%d}-{sale['sequence']:06d}",
        shop_header=shop_header(), encrypted_customer=encrypted))


def read_receipt(conn, sale_id, role):
    sale = conn.execute(select(db.documents).where(db.documents.c.id == sale_id,
        db.documents.c.kind == 'sale')).mappings().first()
    if not sale:
        raise RuleError('Sale not found', 404)
    saved = conn.execute(select(db.sale_receipts).where(db.sale_receipts.c.id == sale_id)).mappings().first()
    linked_customer = conn.execute(select(db.customer_sales.c.customer_id).where(db.customer_sales.c.id == sale_id)).scalar()
    if (linked_customer or (saved and saved['encrypted_customer'])) and role != 'partner':
        raise RuleError('Only partners can open receipts containing customer details', 403)
    customer = None
    if saved and saved['encrypted_customer']:
        try:
            customer = json.loads(cipher().decrypt(saved['encrypted_customer'].encode()))
        except (InvalidToken, json.JSONDecodeError):
            raise RuleError('Customer receipt could not be opened. Contact a partner.', 503) from None
    elif not saved and linked_customer:
        # Legacy receipts have no sale-time snapshot. Label current-profile data explicitly.
        profile = details(conn.execute(select(db.customers).where(db.customers.c.id == linked_customer)).mappings().one())
        customer = {k: profile[k] for k in ('name', 'phone')}
    lines = [dict(line) for line in conn.execute(select(db.lines).where(db.lines.c.transaction_id == sale_id)
                                                .order_by(db.lines.c.sequence)).mappings()]
    if sum(line['quantity'] * line['price_paise'] for line in lines) != sale['total_paise']:
        raise RuleError('Receipt totals could not be verified. Contact a partner.', 503)
    return {'sale_id': sale_id, 'number': saved['number'] if saved else f"KCD-LEGACY-{sale['sequence']:06d}",
            'shop': saved['shop_header'] if saved else shop_header(), 'customer': customer,
            'legacy': not saved, 'created_at': sale['created_at'], 'lines': lines,
            'total_paise': sale['total_paise'], 'payment': sale['data']['payment'],
            'void': bool(conn.execute(select(db.documents.c.id).where(db.documents.c.kind == 'reversal',
                         db.documents.c.parent_id == sale_id)).first())}


def amount(paise):
    # Integer-only arithmetic, including very large amounts.
    return f"{paise // 100:,}.{paise % 100:02d}"


def notes(receipt):
    result = ['Not a GST tax invoice.']
    if receipt['legacy'] and receipt['customer']:
        result.append('Customer details are from the current saved profile.')
    result.append('Thank you for shopping with us. We look forward to seeing you again!')
    if receipt['shop'].get('phone'):
        result.append('For more details or products, call '+receipt['shop']['phone']+'.')
    return result


def render_pdf(receipt, paper):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether

    with FONT_LOCK:
        for name, file in [('KCDReceipt', 'DejaVuSans.ttf'), ('KCDReceiptBold', 'DejaVuSans-Bold.ttf')]:
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(ASSETS / 'fonts' / file)))
        pdfmetrics.registerFontFamily('KCDReceipt', normal='KCDReceipt', bold='KCDReceiptBold')
    thermal = paper == '80mm'
    width = 80 * mm if thermal else A4[0]
    margin = 4 * mm if thermal else 17 * mm
    usable = width - 2 * margin
    size = 8 if thermal else 9
    styles = {
        'body': ParagraphStyle('body', fontName='KCDReceipt', fontSize=size, leading=size+4, spaceAfter=4),
        'title': ParagraphStyle('title', fontName='KCDReceiptBold', fontSize=12 if thermal else 19, leading=16 if thermal else 24, spaceAfter=6),
        'small': ParagraphStyle('small', fontName='KCDReceipt', fontSize=7 if thermal else 8, leading=10 if thermal else 12, spaceAfter=3),
        'right': ParagraphStyle('right', fontName='KCDReceipt', fontSize=size, leading=size+4, alignment=TA_RIGHT),
    }
    def p(text, style='body'):
        return Paragraph(escape(str(text)).replace('\n', '<br/>'), styles[style])
    story = [Image(str(ASSETS / 'kcd-icon.png'), width=13*mm, height=13*mm, hAlign='LEFT'),
             Spacer(1, 3*mm), p(receipt['shop']['name'], 'title'), p('SALES RECEIPT', 'small')]
    if receipt['void']: story.append(p('VOID - SALE REVERSED', 'title'))
    for field in ('address', 'phone'):
        if receipt['shop'][field]: story.append(p(receipt['shop'][field], 'small'))
    story += [Spacer(1, 3*mm), p(receipt['number']), p(ist(receipt['created_at']).strftime('%d %b %Y, %I:%M %p IST'))]
    if receipt['customer']:
        story += [p('Customer: ' + receipt['customer']['name']), p('Phone: ' + receipt['customer']['phone'])]
    else:
        story.append(p('Customer: Not recorded' if receipt['legacy'] else 'Customer: Walk-in customer'))
    story.append(Spacer(1, 4*mm))
    if thermal:
        for i, line in enumerate(receipt['lines'], 1):
            item = [p(f"{i}. {line['snapshot']['name']}"), p('SKU: '+line['snapshot']['sku'], 'small')]
            row = Table([[p(f"{line['quantity']} {line['snapshot']['unit']} x INR {amount(line['price_paise'])}"),
                          p('INR '+amount(line['quantity']*line['price_paise']), 'right')]],
                        colWidths=[usable*.62, usable*.38])
            row.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
                                     ('RIGHTPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
            story.append(KeepTogether(item+[row, Spacer(1, 2*mm)]))
    else:
        rows = [[p(x) for x in ['#', 'Product / fitting', 'Quantity', 'Rate (INR)', 'Amount (INR)']]]
        for i, line in enumerate(receipt['lines'], 1):
            rows.append([p(i), p(line['snapshot']['name']+'\nSKU: '+line['snapshot']['sku']),
                         p(f"{line['quantity']} {line['snapshot']['unit']}"), p(amount(line['price_paise']), 'right'),
                         p(amount(line['quantity']*line['price_paise']), 'right')])
        table = Table(rows, colWidths=[usable*.05,usable*.43,usable*.14,usable*.18,usable*.20], repeatRows=1)
        table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf1fb')),
            ('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#3d69de')),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#dddddd')),
            ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
        story.append(table)
    story += [Spacer(1, 4*mm), p('TOTAL INR '+amount(receipt['total_paise']), 'title'),
              p('Payment: '+receipt['payment'].upper()+ (' - UNPAID' if receipt['payment']=='credit' else ' - recorded')),
              Spacer(1, 3*mm)] + [p(note, 'small') for note in notes(receipt)]
    height = A4[1]
    if thermal:
        # Variable roll length, capped for long receipts (which paginate).
        measured = 0
        for flow in story:
            if isinstance(flow, KeepTogether):
                measured += sum(child.wrap(usable, 10000)[1] + child.getSpaceAfter() for child in flow._content)
            else:
                measured += flow.wrap(usable, 10000)[1] + flow.getSpaceAfter()
        height = min(800*mm, max(120*mm, measured + 2*margin + 15*mm))
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=(width,height), leftMargin=margin,rightMargin=margin,
        topMargin=margin,bottomMargin=margin+7*mm, title=receipt['number'],author=receipt['shop']['name'],
        pageCompression=1)
    def footer(canvas, document):
        canvas.setFont('KCDReceipt', 6 if thermal else 7)
        canvas.drawString(margin, 5*mm, receipt['number'])
        canvas.drawRightString(width-margin, 5*mm, f'Page {document.page}')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def render_print_html(receipt, paper):
    """Separate printable page avoids relying on browser PDF-plugin APIs."""
    e = lambda value: escape(str(value), quote=True)
    shop = receipt['shop']
    customer = receipt['customer']
    rows = ''.join(f"<tr><td>{i}</td><td>{e(l['snapshot']['name'])}<small>{e(l['snapshot']['sku'])}</small></td>"
                   f"<td>{l['quantity']} {e(l['snapshot']['unit'])}</td><td>{amount(l['price_paise'])}</td>"
                   f"<td>{amount(l['quantity']*l['price_paise'])}</td></tr>" for i,l in enumerate(receipt['lines'],1))
    contact = ''.join(f'<p>{e(shop[k])}</p>' for k in ('address','phone') if shop[k])
    who = f"<p>Customer: {e(customer['name'])}</p><p>Phone: {e(customer['phone'])}</p>" if customer else (
        '<p>Customer: Not recorded</p>' if receipt['legacy'] else '<p>Customer: Walk-in customer</p>')
    note_html = ''.join(f'<p>{e(note)}</p>' for note in notes(receipt))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(receipt['number'])}</title><link rel="stylesheet" href="/assets/receipt-print.css"><script src="/assets/receipt-print.js" defer></script></head>
<body class="{'thermal' if paper=='80mm' else 'a4'}"><nav><button id="print">Print receipt</button><p>Choose {'80 mm paper' if paper=='80mm' else 'A4 paper'} and turn off browser headers and footers.</p></nav>
<main><header><img src="/assets/kcd-icon.png" alt="KCD"><h1>{e(shop['name'])}</h1><p>SALES RECEIPT</p>{contact}</header>
{'<h2>VOID - SALE REVERSED</h2>' if receipt['void'] else ''}<p>{e(receipt['number'])}</p><p>{ist(receipt['created_at']).strftime('%d %b %Y, %I:%M %p IST')}</p>{who}
<table><thead><tr><th>#</th><th>Product / fitting</th><th>Quantity</th><th>Rate (INR)</th><th>Amount (INR)</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Total INR {amount(receipt['total_paise'])}</h2><p>Payment: {e(receipt['payment'].upper())}{' - UNPAID' if receipt['payment']=='credit' else ' - recorded'}</p>
<footer>{note_html}</footer></main></body></html>'''
