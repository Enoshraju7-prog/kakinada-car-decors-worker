# Kakinada Car Decors

I built this app to help a car-accessories shop manage purchases, stock and sales. Partners can upload a supplier bill, review the items, confirm what arrived and sell from available stock. The AI assistant helps with reading bills and preparing the records.

## Start here

- **Live app:** [kcd.mmcarcarekakinada.co.in](https://kcd.mmcarcarekakinada.co.in/) - partner sign-in required.
- **Local app after setup:** [127.0.0.1:8000](http://127.0.0.1:8000/).
- **My current recording demo:** [127.0.0.1:8003](http://127.0.0.1:8003/) - a separate local database with generated test data. This address works only on the computer running it.
- [Demo prompts and recording script](docs/DEMO.md)
- [Architecture details](docs/ARCHITECTURE.md)
- [Test results](docs/VERIFICATION.md)
- [Libraries, models and AI coding assistance](docs/PROVENANCE.md)

The live app contains private shop records. This repository contains source code and generated test evidence. Localhost links are not public demos, and no passwords or API keys are included here.

## How the shop flow works

1. Upload a bill or type the items bought. The assistant reads it, checks existing products and prepares an editable draft.
2. The partner checks the products, quantities and buying rates, then sets selling prices and approves the draft.
3. The purchase is saved as **incoming stock**. It cannot be sold yet.
4. When the delivery reaches the shop, the partner counts it and approves the received goods. Accepted items become **available stock**.
5. Making a sale reduces available stock and saves the sale and stock history.

Goods without a bill can also be recorded through a partner-confirmed delivery. Damaged or on-hold items stay separate. A supplier bill by itself never confirms delivery.

## Architecture in simple terms

**React shows it → FastAPI controls it → PostgreSQL remembers it → business services protect it → PydanticAI automates it → tests prove it.**

- **React:** the screens partners use to upload bills, review drafts, receive goods and make sales.
- **FastAPI + Pydantic:** receive requests and check their fields before passing them to the business code.
- **PostgreSQL + SQLAlchemy:** save products, purchases, receipts, sales and the history of stock changes. Alembic handles database updates.
- **Business services:** enforce stock limits, approvals and duplicate protection. Normal stock and sales operations work without AI.
- **PydanticAI worker:** reads a task and chooses the next tool from the results it sees. Progress and tool results are saved in PostgreSQL.
- **Azure services:** Claude Sonnet 4.6 is the model; Document Intelligence extracts invoice fields.

### What are the AI's tools?

They are functions I define, such as `lookup_catalogue`, `prepare_intake`, `read_draft` and `verify_transaction`. Pydantic describes the fields each function expects. The model decides which function to call; the application checks the request and does the work.

For example, “read this bill and prepare a purchase” can lead to extraction, duplicate checks, product lookup and saving a draft. Posting needs partner approval. The worker then reads the saved result back before saying it is done. A stock-report request uses the same worker with different tools.

### Deployment

The private pilot runs on a DigitalOcean server with the app, PostgreSQL and a separate Python worker. HTTPS protects the website; database access stays private. A backup was restored and checked before the latest release. Azure handles model and document calls. Credentials stay outside GitHub.

## Setup and run

You need Python 3.12+, uv, Node 22.12+ with npm, and PostgreSQL 18 binaries. On macOS, the setup script uses `/opt/homebrew/opt/postgresql@18/bin`. Set `KCD_PG_BIN` if your PostgreSQL binaries are elsewhere.

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

Open [localhost:8000](http://127.0.0.1:8000/). The username is `partner`; setup saves the generated password privately in `data/local-access.txt`. It also creates ignored configuration files and separate demo, shop and test databases. Existing records are preserved.

To use AI, privately configure the Azure values listed in `backend/.env.example`. This code does not create an Azure resource or provide API keys. In another terminal, start the worker for the database configured in that file:

```bash
cd backend
.venv/bin/python -m app.infrastructure.jobs
```

Use generated bills for testing. Manual product entry, receiving and sales work without Azure.

### Repeat the controlled generated test

```bash
cd backend
.venv/bin/python -m scripts.evaluation setup
.venv/bin/python -m scripts.evaluation api
```

Open [localhost:8001](http://127.0.0.1:8001/), sign in and attach `output/pdf/generated-evaluation-bill.pdf` in AI assistant. Use this exact prompt:

> Process the attached generated evaluation bill. Match its printed SKU and unit to the catalogue, check duplicates, prepare its purchase draft, request partner approval, then post and read it back. Do not receive goods from the bill alone.

Copy the run ID shown on screen and run:

```bash
.venv/bin/python -m scripts.evaluation work RUN_ID
```

Review the draft in the app. Approve it, then run the same command again to continue. This evaluation runner accepts only its generated fixtures and exact test goals. The normal worker accepts other natural-language goals. The local port 8003 demo is an already-configured recording workspace, not something these setup commands create.

## What I tested

- **56 backend tests passed** using PostgreSQL. Frontend typecheck, build and formatting passed.
- Actual Azure extraction saved a generated bill as an editable draft.
- After partner review, the AI requested approval, posted the purchase and verified it.
- The browser received **10**, sold **3** and showed **7 left**. Independent database checks matched the stock history.
- A separate AI goal created and read back a shortage report.

[Saved flow evidence](artifacts/submission-oct8-stock.json). Physical counts and checkout were entered through the partner interface; the AI did not observe a delivery.

Run the checks:

```bash
cd backend
.venv/bin/python -c 'from dotenv import load_dotenv; load_dotenv(".env"); import unittest; result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover("tests")); raise SystemExit(not result.wasSuccessful())'
cd ../frontend
npm run build
npm run format:check
```

Backend tests require a separate `KCD_TEST_DATABASE_URL` ending in `/kcd_test`; they clear that test database.

## Current limits and next work

Handwritten bills and vague product names can confuse the AI. One upload run saved a draft but kept asking unnecessary questions; I kept that failure in the evidence. A later reviewed posting task completed successfully. I do not claim every invoice will work.

The worker uses this app's tools, with a limit of 10 model requests and 20 tool calls per run. It cannot control arbitrary websites. Partners confirm uncertain variants, units, prices and physical deliveries. Unknown pack conversions are rejected.

Next I want to simplify corrections, test more bills, improve mobile receiving and add email alerts and profit reports. Real tax invoicing, email delivery and native mobile apps are not complete. Fresh setup on other operating systems and a local Docker build still need verification.

**Tech stack:** Python | FastAPI | Pydantic | PydanticAI | PostgreSQL | SQLAlchemy | Alembic | React | TypeScript | Vite | Tailwind | Azure AI | DigitalOcean

Codex helped with implementation, debugging, testing and documentation. Components and references are listed in [provenance](docs/PROVENANCE.md).
