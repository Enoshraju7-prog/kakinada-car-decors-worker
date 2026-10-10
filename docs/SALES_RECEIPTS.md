# Printable sales receipts

After **Confirm sale**, the saved-sale panel offers **View bill**, **Download PDF** and **Print**. Choose **A4 bill** or **80 mm receipt**. The same controls appear on sales in **Activity**. None of these actions creates a sale or changes stock.

## What is printed

KCD logo, shop name, receipt number, purchase date/time in IST, customer name/phone (or Walk-in), product/fitting names and SKUs, quantities/units, selling rates, line amounts, total and payment method. Customer address is intentionally omitted. Credit is labelled **UNPAID**. Other payment methods say **recorded**, reflecting the existing manual counter entry, not a verified payment-gateway event.

The heading says **Sales receipt**, with a short **Not a GST tax invoice** footer. Enosh requested removal of lengthy internal notes about configuration, history and returns. Legacy customer-linked receipts keep only a short current-profile note so contact details are not misrepresented as sale-time snapshots. No GST amount, GSTIN or HSN is inferred. Shop tax-invoice support remains a separate feature. Razorpay/Stripe links, verified payment IDs and settlement/refund tracking are not implemented by this receipt change.

## Immutable history and privacy

- Migration `0008` adds `sale_receipts`, keyed by the posted sale. Number, shop header and encrypted name/phone snapshot are saved in the same transaction as the sale and stock movements. A failed snapshot rolls the entire sale back. Repeat checkout requests reuse the original receipt.
- Numbers use `KCD-YYYYMMDD-{transaction sequence}` using the sale's IST date. Sequence gaps are allowed; these are not GST invoice numbers.
- Reprints use original sale line snapshots and original customer/shop snapshots. Changing a profile, selling price or shop configuration cannot rewrite an issued receipt. The table has the existing immutable-history database trigger.
- Customer snapshots use the existing Fernet key ring. They exclude address and stay outside transaction JSON, state endpoints, audit/outbox, AI tools and response/retry records. Existing customer-profile key rotation/backup requirements also apply to receipts.
- Authenticated partners can open customer receipts. Staff can open Walk-in receipts but cannot open customer-linked receipts, including legacy ones. PDFs are created in memory, never written to public storage or logs, and served with `Cache-Control: private, no-store`.
- Older sales are rendered without backfilling new receipt records. They use `KCD-LEGACY-{sequence}` and use current-profile details only where a saved customer link exists. At Enosh's request, customer-linked legacy sales show name/phone from the current saved profile, clearly labelled as such; historical contact accuracy cannot be guaranteed for these older sales. Legacy sales with no saved customer show that historical customer details were not captured. Reversed sales prominently show **VOID**. Returns/refunds do not silently rewrite the original sale.

## Server and printer setup

ReportLab 4.5.1 generates PDFs. The bundled DejaVu Sans fonts retain their licence in `backend/app/assets/fonts/LICENSE_DEJAVU`. A separate escaped HTML print view opens the browser's print dialog without relying on PDF-plugin scripting. Printing pages use only same-origin CSS/JavaScript under the existing content security policy.

Receipt endpoints:

- `GET /api/sales/{sale_id}/receipt.pdf?format=a4|80mm`
- `GET /api/sales/{sale_id}/receipt/print?format=a4|80mm`

Set `KCD_RECEIPT_SHOP_NAME`, `KCD_RECEIPT_SHOP_ADDRESS`, `KCD_RECEIPT_SHOP_PHONE` and `KCD_RECEIPT_SHOP_DETAILS_CONFIRMED=1` only after the partner confirms the real details. Unconfigured header fields are omitted. Configuration is captured for new sales only. Existing issued snapshots retain their original state; legacy sales without snapshots use the current header.

Enosh supplied a business card and authorized using its details, preserving the existing blue KCD receipt design. The local ignored `.env` now contains the supplied street address and shop phone. Enosh confirmed PIN 533003 on 10 October. The footer thanks the customer and invites them to call the saved shop number for more details or products. GSTIN/proprietor details were not added to the sales receipt. Real header details are not copied into public examples or repository defaults.

Use A4 for ordinary printers. For thermal printing, select the actual 80 mm printer/roll and disable browser headers/footers. The 80 mm PDF uses variable roll length up to 800 mm, then paginates; the HTML print view uses 250 mm segments. Driver support for custom paper lengths varies. No actual printer was available for verification in this session.

PDF generation is separate from checkout. Failure shows **Sale saved - retry bill**; use the receipt controls again, never confirm the sale again just to print. Browser popup blocking offers Download PDF as a fallback.

## Verification and rollout

Backend checks verify encryption/no PII leakage, original customer and shop snapshots after edits, retry reuse, access restrictions, rendering failure, rollback, credit/services, legacy sales, VOID reversals, escaped HTML, IST midnight and many-item PDFs in both widths. Existing concurrency/stock/replay tests also pass. Synthetic preview PDFs were rendered and inspected, including the final total page. Local browser checks confirmed the receipt controls, PDF opening and printable-page readback.

The local/demo/test databases are migrated; localhost was restarted on port 8003. Production is unchanged. Before deployment: review locally, confirm shop header details, test a physical printer, retain a database backup plus encryption keys separately, install locked dependencies, run migration `0008`, build frontend, restart services, and repeat authenticated receipt checks.
