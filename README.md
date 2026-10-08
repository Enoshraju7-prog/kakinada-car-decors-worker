# Kakinada Car Decors — Autonomous AI Task Worker

A working inventory application with a bounded AI worker that uses real application tools. Built by Enosh for a continuing car-accessories business; the CentrAlign AI Engineering Intern submission is the first milestone.

**What the worker does:** takes a natural-language goal, reads a supplied bill, checks existing records, proposes exact parts and families, saves an editable intake draft and reads it back. A different goal checks exact-SKU shortages, saves a report and verifies it. A partner reviews uncertainty, sets selling prices and authorizes posting. A bill never proves goods arrived.

React shows it → FastAPI controls it → PostgreSQL remembers it → business services protect it → PydanticAI automates it → tests prove it.

This public snapshot contains working source and **synthetic evidence only**, without private shop history, credentials, supplier photographs or live database backups. The deployed shop pilot is private; reproduce the generated demo below rather than use real company data.

## Start here

- [Architecture, flow and design decisions](docs/ARCHITECTURE.md)
- [What was actually verified and what remains](docs/VERIFICATION.md)
- [Short demo walkthrough](docs/DEMO.md)
- [Models, APIs, components and AI assistance](docs/PROVENANCE.md)

## Setup and run

Requirements: Python 3.12+, uv, Node 22.12+ with npm, PostgreSQL 18 binaries. Local setup supports a project-owned loopback PostgreSQL cluster. On macOS it defaults to /opt/homebrew/opt/postgresql@18/bin; set KCD_PG_BIN for your installed binaries on another system. It is not a one-click cloud installer.

```bash
git clone https://github.com/Enoshraju7-prog/kakinada-car-decors-worker.git
cd kakinada-car-decors-worker/backend
uv sync --locked --extra ai
.venv/bin/python -m scripts.setup_local
cd ../frontend
npm ci --ignore-scripts
npm run build
cd ..
./dev.sh
```

Open http://127.0.0.1:8000. Local username is partner; the generated password is saved privately in data/local-access.txt. Setup writes ignored backend/.env and data/database-access.json, migrates separate demo/shop/test databases and preserves existing records. Never publish those files. The fresh demo database is empty.

For manual synthetic stock and sales, use Products → add a part; Receive stock → record incoming bill or counted no-bill delivery; approve physical counts; Make sale. Normal operations require no Azure service.

## AI demo with your own Azure access

Privately configure the names in backend/.env.example: Azure Claude endpoint/key/deployment and Azure Document Intelligence endpoint/key. No model or cloud resource is created automatically. The verified model deployment was Claude Sonnet 4.6. A trained custom document classifier is not required.

For a scoped, generated-only evaluation:

```bash
cd backend
.venv/bin/python -m scripts.evaluation setup
.venv/bin/python -m scripts.evaluation api
```

Open http://127.0.0.1:8001, sign in with the local partner account and use AI assistant. Attach output/pdf/generated-evaluation-bill.pdf and copy the invoice goal exactly:

> Process the attached generated evaluation bill. Match its printed SKU and unit to the catalogue, check duplicates, prepare its purchase draft, request partner approval, then post and read it back. Do not receive goods from the bill alone.

In another terminal, from backend, use the run ID displayed by the UI:

```bash
.venv/bin/python -m scripts.evaluation work RUN_ID
```

Review and approve the exact draft in the UI, then run the same scoped worker command again. If corrections are needed, saved revisions invalidate prior approval. Budget exhaustion stops the run; start a newly scoped goal rather than bypass limits.

For the second goal, copy exactly:

> Inspect the generated evaluation inventory for exact-SKU shortages, save a shortage report and read it back.

The scoped runner rejects unexpected catalogue records, files, goals and clarification notes. Literal fixture goals/notes are in backend/scripts/evaluation.py. For arbitrary generated tasks in your local demo, the normal worker is `.venv/bin/python -m app.infrastructure.jobs`; it processes that configured database. Start it only with data authorized for your providers. Provider outages leave manual entry and checkout available.

## Checks

```bash
cd backend
.venv/bin/python -c 'from dotenv import load_dotenv; load_dotenv(".env"); import unittest; result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover("tests")); raise SystemExit(not result.wasSuccessful())'
cd ../frontend
npm run build
npm run format:check
```

Tests require KCD_TEST_DATABASE_URL ending in /kcd_test and clear only that test database. Latest run: **56 tests passed**, with real PostgreSQL; frontend typecheck/build/format passed. Controlled-model tests are distinguished from actual Azure execution in the evidence notes.

**Fresh generated flow verified on October 8:** actual Azure extraction → editable new-SKU proposal → partner price review → actual model-selected posting tools and deferred approval → incoming purchase readback → browser receipt 10 → browser sale 3 → independently verified 7 remaining. [Saved stock evidence](artifacts/submission-oct8-stock.json). Manual physical counts and checkout were performed by the partner interface; the AI did not observe a real delivery.

## Assumptions and known limits

- Whole base units and explicitly confirmed pack conversions; mixed assortments need actual variant breakdown.
- Partner-first pilot. Staff backend permissions exist but their rollout is deferred.
- New catalogue proposals and buying interpretations require review; AI cannot reliably infer missing variants from generic descriptions.
- The first October 8 upload run asked unnecessary synthetic/tax questions. After partner correction/price review, a **fresh posting goal completed** through exact-version approval, new-SKU/incoming purchase creation and independent readback (4 requests / 3 tools). The original unresolved run is retained; prompts do not guarantee every resumed case.
- Actual earlier generated purchase approval/post/readback evidence exists separately. No claim that all document formats work.
- No arbitrary browser/desktop control: the worker operates through bounded APIs in this application, as the problem scope permits.
- Ten model-request slots and twenty tools per run; no unbounded self-repair. Leases/retries are implemented; a distributed durable workflow engine is deferred.
- Real tax invoices, valuation/profit graphs, email delivery, off-server backup automation and native mobile apps are not complete.
- Fresh cross-platform setup rehearsal and a recorded demo video remain to be completed. Docker is included but has not been verified by a local build.

Next: rehearse and record the verified intake → approved posting → physical receipt → sale walkthrough, broaden generated handwritten-bill cases, simplify partner corrections, measure hosting/AI cost and recovery, then improve reporting and mobile delivery. This project continues beyond the application deadline.

AI coding assistance is disclosed in provenance. Git authorship uses Enosh's identity without a bot contributor.
