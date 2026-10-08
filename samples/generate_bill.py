"""Synthetic OCR fixture. No actual supplier, GSTIN, HSN or customer identity."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
root=Path(__file__).resolve().parents[1]
path=root/'output/pdf/generated-evaluation-bill.pdf'
path.parent.mkdir(parents=True,exist_ok=True)
c=canvas.Canvas(str(path),pagesize=(595,842))
c.setTitle('Generated evaluation invoice - synthetic')
c.setFillColor(HexColor('#163b2c'));c.rect(0,720,595,122,fill=1,stroke=0)
c.setFillColor(HexColor('#ffffff'));c.setFont('Helvetica-Bold',22);c.drawString(42,785,'GENERATED EVALUATION SUPPLIER')
c.setFont('Helvetica',12);c.drawString(42,755,'SYNTHETIC TEST INVOICE - NO REAL BUSINESS DATA')
c.setFillColor(HexColor('#26352b'));c.setFont('Helvetica-Bold',14);c.drawString(42,672,'Supplier invoice: EVAL-BILL-001')
c.setFont('Helvetica',12);c.drawString(42,643,'Invoice date: 04 October 2026');c.drawString(42,617,'Buyer: Generated evaluation buyer');c.drawString(42,591,'Currency: INR')
c.setFillColor(HexColor('#eef2ed'));c.rect(42,500,511,42,fill=1,stroke=0)
c.setFillColor(HexColor('#26352b'));c.setFont('Helvetica-Bold',11)
for x,t in [(54,'Description / SKU'),(313,'Quantity'),(385,'Unit'),(435,'Rate'),(492,'Amount')]:c.drawString(x,516,t)
c.setFont('Helvetica',10);c.drawString(54,471,'Generated evaluation widget');c.drawString(54,452,'EVAL-GENERATED-001');c.drawString(323,471,'10');c.drawString(383,471,'piece');c.drawString(438,471,'100.00');c.drawString(490,471,'1000.00')
c.setStrokeColor(HexColor('#d5ddd4'));c.line(42,425,553,425);c.setFont('Helvetica-Bold',14);c.drawRightString(550,386,'TOTAL INR 1000.00')
c.setFont('Helvetica',11);c.drawString(42,319,'Tax fields intentionally absent. This is an extraction fixture only.');c.drawString(42,296,'No GSTIN, HSN or tax rate is invented.');c.drawString(42,255,'An invoice does not confirm physical arrival of goods.');c.drawString(42,232,'Receipt counts must be recorded and approved separately.')
c.setFont('Helvetica',9);c.drawString(42,64,'Generated solely for the Kakinada Car Decors evaluation. Page 1 of 1.')
c.save()
