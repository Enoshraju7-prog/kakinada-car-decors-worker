"""Synthetic fixtures only; no shop/customer records are exported."""
from io import BytesIO
import unittest
from pypdf import PdfReader
from app.modules.sales.receipts import render_pdf, render_print_html


def sample_receipt(count=10):
    lines = [{'quantity': 25, 'price_paise': 12099 + i,
              'snapshot': {'name':f'Synthetic item {i+1:02d} - Microfiber cleaning cloth blue 40×40 cm with a long exact variant name',
                           'sku':f'DEMO-{i+1:03d}', 'unit':'piece', 'kind':'goods'}} for i in range(count)]
    return {'sale_id':'synthetic', 'number':'KCD-DEMO-000001',
            'shop':{'name':'Kakinada Car Decors','address':'Synthetic address for layout review only',
                    'phone':'0000000000','confirmed':False},
            'customer':{'name':'Synthetic Customer','phone':'+910000000000'},
            'legacy':False,'void':False,'created_at':'2026-10-09T18:30:00+00:00',
            'payment':'credit','total_paise':sum(l['quantity']*l['price_paise'] for l in lines),'lines':lines}


class ReceiptLayoutTests(unittest.TestCase):
    def test_long_names_multi_page_layout_and_ist_midnight(self):
        receipt = sample_receipt(60)
        for paper in ('a4','80mm'):
            pdf = PdfReader(BytesIO(render_pdf(receipt,paper)))
            self.assertGreater(len(pdf.pages),1)
            self.assertAlmostEqual(float(pdf.pages[0].mediabox.width),80*72/25.4 if paper=='80mm' else 210*72/25.4, places=1)
            contents = '\n'.join(page.extract_text() for page in pdf.pages)
            self.assertIn('10 Oct 2026, 12:00 AM IST',contents)
            self.assertIn('UNPAID',contents)
            for line in receipt['lines']:
                self.assertIn(line['snapshot']['sku'],contents)

    def test_print_markup_escapes_customer_and_product(self):
        receipt = sample_receipt(1)
        receipt['customer']['name'] = '<img src=x onerror=alert(1)>'
        receipt['lines'][0]['snapshot']['name'] = '<script>alert(2)</script>'
        html = render_print_html(receipt,'80mm')
        self.assertNotIn('<img src=x',html)
        self.assertNotIn('<script>alert(2)',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('receipt-print.js',html)
