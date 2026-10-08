# Verification and limits — 8 October 2026

## Automated checks

56 checks passed in 4.551 seconds against the dedicated PostgreSQL test database. This includes concurrent sale of the final unit, concurrent partial receipts, duplicate/replayed posting, no-bill receiving, service lines without movements, returns, immutable records, deadlock retry, ledger/balance reconciliation, stale approvals, API role/cost protection, worker leases, outage fallback and readback gating. Worker tests use controlled model responses with real database operations; they are not actual-provider reliability measurements.

Frontend typecheck/build and formatting passed. The renderer loads in its own chunk. Browser inspection confirmed proper headings, emphasis, semantic table headers/cells and editable intake proposals without raw Markdown delimiters. The browser automation could not select the local upload file because the extension lacked file-URL permission; the actual multipart upload endpoint was exercised instead. This is not a claim that automated file selection passed.

## Actual providers, generated data only

- artifacts/submission-oct8-invoice.json: fresh generated PDF uploaded through the application; actual classification and Document Intelligence extraction; model selected seven tools and saved/read back an intake proposal. The resumed run used nine request slots/eight tools and still raised unnecessary synthetic/tax questions. It did not post. This failure is retained as evidence.
- artifacts/submission-oct8-review.json: a fresh, explicitly scoped goal read back the saved proposal successfully, using two requests/one tool. No unnecessary synthetic/tax clarification was returned. Preparation/review completion is distinct from purchase posting.
- artifacts/submission-oct8-shortage.json: four requests/three tools; query_inventory → save_shortage_report → read_report; complete with a saved report ID. The empty catalogue was accurately reported. An empty report is not evidence of a populated low-stock scenario.
- artifacts/live-invoice-check-oct5.json: earlier generated purchase approval/posting/readback evidence using existing catalogue/draft and cached real extraction. It is not the October 8 new-product intake run.
- artifacts/live-worker-check.json: earlier actual shortage goal on a generated saved SKU.

No private supplier bills, shop credentials, actual stock or business identifiers appear in these evaluator materials. No application form or demo video was submitted by these checks.

- artifacts/submission-oct8-posting.json: fresh goal read the partner-priced intake v2, requested approval and resumed from browser approval. Actual model tools posted the new-SKU purchase and verified it: complete, four requests/three tools. Incoming 10, available 0, no stock movements at purchase.
- artifacts/submission-oct8-stock.json: browser physical-count simulation received ten and browser checkout sold three. Independent API and database queries confirmed seven available, zero incoming and exactly +10/-3 movements. All buckets reconciled. These are explicitly generated counts, not actual physical delivery.
- Checkbox clipping was fixed and inspected in the browser: 14px tick centered within the 19px box. Synthetic screenshots are included.

## What remains

The fresh new-SKU intake approval/posting and physical receipt/sale continuation passed. Rehearse fresh evaluator setup and record a concise screen demo. Broaden documents and error cases against live providers; prompts alone cannot guarantee model interpretation. Email delivery, off-server backup automation, tax invoicing and native mobile apps remain unfinished.
