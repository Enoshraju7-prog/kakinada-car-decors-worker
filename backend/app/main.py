from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from uuid import UUID
from fastapi import FastAPI, Header, Request, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, StrictInt, StrictBool, ValidationError
from sqlalchemy import select
from app.infrastructure import database as db
from app.infrastructure import auth
from app.workflows.posting import Store
from app.workflows import drafts
from app.modules.inventory.service import reconcile
from app.ledger import RuleError, identifier, now
from app.legacy_main import Input, Product, Purchase, PurchaseLine, Sale, StockReturn
from app.modules.sales.customers import CustomerDetails, CustomerPhone, lookup_customer, customer_history

ROOT = Path(__file__).resolve().parents[2]

class CustomerSale(Sale):
    customer: CustomerDetails | None = None

class QuickProduct(Product):
    family_name: str | None = Field(default=None, max_length=200)
    purchase_price_paise: StrictInt | None = Field(default=None, ge=0, le=1000000000)

class ReviewedPurchaseLine(PurchaseLine):
    source_index: StrictInt | None = Field(default=None, ge=0, le=99)

class ReviewedPurchase(Purchase):
    order_review_id: str | None = None
    review_confirmed: StrictBool = False
    lines: list[ReviewedPurchaseLine] = Field(min_length=1, max_length=100)


class ReceiptLine(Input):
    purchase_line_id: str
    accepted: StrictInt = Field(ge=0, le=1000000000)
    damaged: StrictInt = Field(default=0, ge=0, le=1000000000)
    quarantined: StrictInt = Field(default=0, ge=0, le=1000000000)


class Receipt(Input):
    purchase_id: str
    confirmed: StrictBool
    location_id: str = db.LOCATION_ID
    lines: list[ReceiptLine] = Field(min_length=1, max_length=100)


class UnbilledReceiptLine(Input):
    product_id: str
    unit: str
    accepted: StrictInt = Field(ge=0, le=1000000000)
    damaged: StrictInt = Field(default=0, ge=0, le=1000000000)
    quarantined: StrictInt = Field(default=0, ge=0, le=1000000000)
    cost_paise: StrictInt | None = Field(default=None, ge=0, le=1000000000)


class UnbilledReceipt(Input):
    supplier: str = Field(min_length=1, max_length=200)
    reference: str = Field(min_length=1, max_length=100)
    received_date: str
    evidence: str = Field(min_length=1, max_length=1000)
    confirmed: StrictBool
    location_id: str = db.LOCATION_ID
    lines: list[UnbilledReceiptLine] = Field(min_length=1, max_length=100)


class Category(Input):
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None
    threshold: StrictInt = Field(default=0, ge=0)


class Family(Input):
    name: str = Field(min_length=1, max_length=200)
    category_id: str
    brand: str = ""
    kind: Literal["goods", "service"] = "goods"


class Fitment(Input):
    make: str
    model: str
    generation: str = ""
    year_from: StrictInt | None = Field(default=None, ge=1900, le=2100)
    year_to: StrictInt | None = Field(default=None, ge=1900, le=2100)


class Variant(Input):
    product_id: str
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    unit: Literal["piece", "pair", "set", "kit", "box", "carton", "service"]
    model: str = ""
    color: str = ""
    compatibility: str = ""
    compatibility_status: Literal["unknown", "specific", "universal"] = "unknown"
    fitments: list[Fitment] = Field(default_factory=list, max_length=100)
    specification: str = ""
    price_paise: StrictInt = Field(default=0, ge=0)
    purchase_price_paise: StrictInt | None = Field(default=None, ge=0)
    threshold: StrictInt | None = Field(default=None, ge=0)
    conversions: dict[str, StrictInt] = Field(default_factory=dict)
    conversion_evidence: str = "Explicit catalogue confirmation"


class Login(Input):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class Prices(Input):
    id: str
    price_paise: StrictInt = Field(ge=0)
    purchase_price_paise: StrictInt | None = Field(default=None, ge=0)
    expected_price_paise: StrictInt = Field(ge=0)
    expected_purchase_price_paise: StrictInt | None = Field(default=None, ge=0)


class Version(Input):
    version: StrictInt = Field(ge=1)


class DraftEdit(Version):
    payload: dict


class Correction(Input):
    transaction_id: str
    reason: str = Field(min_length=1, max_length=200)
    evidence: str = Field(min_length=1, max_length=200)


class Count(Input):
    product_id: str
    location_id: str = db.LOCATION_ID
    available: StrictInt = Field(ge=0, le=1000000000)
    damaged: StrictInt = Field(ge=0, le=1000000000)
    quarantined: StrictInt = Field(ge=0, le=1000000000)
    reason: str = Field(min_length=1, max_length=200)
    evidence: str = Field(min_length=1, max_length=200)


class Clarification(Input):
    message: str = Field(min_length=1,max_length=2000)


class Goal(Input):
    goal: str = Field(min_length=1, max_length=2000)
    attachments: list[str] = Field(default_factory=list, max_length=10)


def create_app(engine=None, mode=None):
    mode = mode or os.getenv("KCD_MODE", "demo")
    if mode not in {"demo", "shop"}:
        raise RuntimeError("Choose demo or shop")
    engine = engine or db.engine_for()
    store = Store(engine)
    application = FastAPI(title="Kakinada Car Decors operating core")
    application.state.store = store

    @application.middleware("http")
    async def boundary(request, call_next):
        try:
            origin = request.headers.get("origin")
            if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin != str(request.base_url).rstrip("/"):
                raise RuleError("Cross-origin writes are disabled", 403)
            protected = request.url.path.startswith("/api/") and request.url.path not in {"/api/auth/login", "/api/health"}
            if protected:
                request.state.user = auth.principal(engine, request.cookies.get("kcd_session"))
                if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("x-csrf-token") != request.state.user["csrf"]:
                    raise RuleError("Refresh your session before writing", 403)
            response = await call_next(request)
        except RuleError as exc:
            response = JSONResponse({"detail": str(exc)}, status_code=exc.status)
        response.headers["Cache-Control"] = "private, no-store" if response.headers.get('Cache-Control', '').startswith('private') else "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path not in {"/docs", "/redoc"}:
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        return response

    @application.exception_handler(RuleError)
    async def rule_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @application.exception_handler(ValidationError)
    async def nested_validation_error(request, exc):
        return JSONResponse({'detail':'Check the draft fields, units and whole quantities'},status_code=422)

    @application.post("/api/auth/login")
    def sign_in(payload: Login):
        token, user = auth.login(engine, payload.username, payload.password)
        response = JSONResponse(user)
        response.set_cookie("kcd_session", token, httponly=True, samesite="strict", secure=os.getenv("KCD_HTTPS") == "1", max_age=28800)
        return response

    @application.get("/api/auth/me")
    def me(request: Request):
        return request.state.user

    @application.post("/api/auth/logout")
    def logout(request: Request):
        with engine.begin() as conn:
            conn.execute(db.sessions.delete().where(db.sessions.c.token_hash == hashlib.sha256(request.cookies["kcd_session"].encode()).hexdigest()))
        response = JSONResponse({"ok": True})
        response.delete_cookie("kcd_session")
        return response

    def post(operation, payload, key, user):
        if operation != "sale":
            auth.require_partner(user)
        data = payload.model_dump()
        if operation == 'sale' and data.get('customer') is None:
            data.pop('customer', None)  # Keep existing walk-in retry fingerprints.
        if operation == 'product':
            if data.get('purchase_price_paise') is None:
                data.pop('purchase_price_paise', None)
            if not data.get('family_name'):
                data.pop('family_name', None)
        if operation == 'purchase' and not data.get('order_review_id'):
            # Preserve the legacy request fingerprint for already saved retry keys.
            data.pop('order_review_id', None)
            data.pop('review_confirmed', None)
            for line in data['lines']:
                line.pop('source_index', None)
        result = store.post(operation, data, key, user["username"])
        # Separate connection proves the committed record is readable.
        return store.transaction(result["id"]) if operation in {"purchase", "receipt", "sale", "return", "adjustment", "reversal", "unbilled_receipt"} else result

    @application.get("/api/state")
    def state(request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        result = store.state(offset=offset, limit=limit)
        result['products'] = [auth.redact_catalogue(p, request.state.user['role']) for p in result['products']]
        if request.state.user['role'] == 'partner':
            with engine.connect() as conn:
                result['order_reviews'] = [dict(r) for r in conn.execute(select(db.order_reviews).order_by(db.order_reviews.c.created_at)).mappings()]
                for review in result['order_reviews']:
                    linked = conn.execute(select(db.documents.c.id).where(db.documents.c.kind == 'purchase',
                        db.documents.c.data['order_review_id'].astext == review['id'])).scalar()
                    review['purchase_id'] = linked
                    review['delivery_status'] = 'not_reached'
                    if linked:
                        saved = store.transaction(linked)
                        remaining = sum(l['outstanding'] for l in saved['lines'])
                        received = sum(l['received'] for l in saved['lines'])
                        review['delivery_status'] = 'received' if remaining == 0 else 'part_received' if received else 'ready_to_count'
        for field in ("transactions", "incoming_transactions"):
            result[field] = [auth.redact_transaction(t, request.state.user["role"]) for t in result[field]]
        return {"mode": mode, "actor": request.state.user["username"], "role": request.state.user["role"], "tax_invoicing_enabled": False, **result}

    @application.get("/api/transactions/{tx}")
    def transaction(tx: str, request: Request):
        return auth.redact_transaction(store.transaction(tx), request.state.user["role"])

    @application.post("/api/products")
    def add_product(payload: QuickProduct, request: Request, idempotency_key: str = Header(max_length=200)):
        return post("product", payload, idempotency_key, request.state.user)

    @application.post("/api/purchases")
    def add_purchase(payload: ReviewedPurchase, request: Request, idempotency_key: str = Header(max_length=200)):
        return post("purchase", payload, idempotency_key, request.state.user)

    @application.post("/api/receipts")
    def receive(payload: Receipt, request: Request, idempotency_key: str = Header(max_length=200)):
        return post("receipt", payload, idempotency_key, request.state.user)

    @application.post('/api/unbilled-receipts')
    def receive_without_bill(payload: UnbilledReceipt, request: Request, idempotency_key: str = Header(max_length=200)):
        return post('unbilled_receipt', payload, idempotency_key, request.state.user)

    @application.post("/api/sales")
    def sell(payload: CustomerSale, request: Request, idempotency_key: str = Header(max_length=200)):
        return post("sale", payload, idempotency_key, request.state.user)

    @application.post('/api/customers/lookup')
    def find_customer(payload: CustomerPhone, request: Request):
        auth.require_partner(request.state.user)
        with engine.connect() as conn:
            return {'customer': lookup_customer(conn, payload.phone)}

    @application.get('/api/customers/{customer_id}')
    def read_customer(customer_id: UUID, request: Request, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50)):
        auth.require_partner(request.state.user)
        with engine.connect() as conn:
            return customer_history(conn, str(customer_id), limit, offset)

    @application.get('/api/sales/{sale_id}/customer')
    def sale_customer(sale_id: UUID, request: Request):
        auth.require_partner(request.state.user)
        with engine.connect() as conn:
            customer_id = conn.execute(select(db.customer_sales.c.customer_id).where(db.customer_sales.c.id == str(sale_id))).scalar()
            return customer_history(conn, customer_id) if customer_id else {'customer': None, 'purchases': [], 'has_more': False}

    @application.get('/api/sales/{sale_id}/receipt.pdf')
    def sale_receipt_pdf(sale_id: UUID, request: Request,
                         paper: Literal['a4', '80mm'] = Query('a4', alias='format')):
        from app.modules.sales.receipts import read_receipt, render_pdf
        with engine.connect() as conn:
            receipt = read_receipt(conn, str(sale_id), request.state.user['role'])
        try:
            content = render_pdf(receipt, paper)
        except Exception:
            raise RuleError('Sale saved - retry bill. PDF could not be generated.', 503) from None
        return Response(content, media_type='application/pdf', headers={
            'Cache-Control': 'private, no-store',
            'Content-Disposition': f'inline; filename="{receipt["number"]}-{paper}.pdf"'})

    @application.get('/api/sales/{sale_id}/receipt/print')
    def sale_receipt_print(sale_id: UUID, request: Request,
                           paper: Literal['a4', '80mm'] = Query('a4', alias='format')):
        from app.modules.sales.receipts import read_receipt, render_print_html
        with engine.connect() as conn:
            receipt = read_receipt(conn, str(sale_id), request.state.user['role'])
        return HTMLResponse(render_print_html(receipt, paper), headers={'Cache-Control': 'private, no-store'})

    @application.post('/api/prices')
    def set_prices(payload: Prices, request: Request, idempotency_key: str = Header(max_length=200)):
        return post('prices', payload, idempotency_key, request.state.user)

    @application.get('/api/partner-alerts')
    def partner_alerts(request: Request):
        auth.require_partner(request.state.user)
        # The immutable audit event is the durable notification. Every partner sees it;
        # replaying a posting never creates a second notification.
        with engine.connect() as conn:
            events = conn.execute(select(db.audit.c.id, db.audit.c.actor, db.audit.c.event,
                db.audit.c.source_id, db.audit.c.created_at, db.documents.c.kind)
                .outerjoin(db.documents, db.documents.c.id == db.audit.c.source_id)
                .where(db.audit.c.event.in_(['sale', 'return', 'reversal', 'adjustment', 'prices', 'post_draft', 'unbilled_receipt']))
                .order_by(db.audit.c.created_at.desc(), db.audit.c.id.desc()).limit(50)).mappings()
            return [dict(e) for e in events if e['event'] != 'post_draft' or e['kind'] in {'sale', 'return', 'reversal', 'adjustment'}]

    @application.post("/api/returns")
    def returns(payload: StockReturn, request: Request, idempotency_key: str = Header(max_length=200)):
        return post("return", payload, idempotency_key, request.state.user)

    @application.post("/api/adjustments")
    def count(payload: Count, request: Request, idempotency_key: str = Header(max_length=200)):
        return post("adjustment", payload, idempotency_key, request.state.user)

    @application.post("/api/reversals")
    def reverse(payload: Correction, request: Request, idempotency_key: str = Header(max_length=200)):
        return post("reversal", payload, idempotency_key, request.state.user)

    @application.post("/api/v1/catalog/categories")
    def category(payload: Category, request: Request, idempotency_key: str = Header(max_length=200)):
        return post("category", payload, idempotency_key, request.state.user)

    @application.post("/api/v1/catalog/products")
    def family(payload: Family, request: Request, idempotency_key: str = Header(max_length=200)):
        return post("family", payload, idempotency_key, request.state.user)

    @application.post("/api/v1/catalog/variants")
    def variant(payload: Variant, request: Request, idempotency_key: str = Header(max_length=200)):
        return post("variant", payload, idempotency_key, request.state.user)

    @application.get("/api/v1/catalog/{resource}")
    def catalog_list(resource: Literal["categories", "products", "variants"], request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        table = {"categories": db.categories, "products": db.products, "variants": db.variants}[resource]
        with engine.connect() as conn:
            return [auth.redact_catalogue(r, request.state.user['role']) for r in conn.execute(select(table).order_by(table.c.id).offset(offset).limit(limit)).mappings()]

    @application.get("/api/v1/catalog/{resource}/{record_id}")
    def catalogue_record(resource: Literal['categories','products','variants'],record_id: str, request: Request):
        table={'categories':db.categories,'products':db.products,'variants':db.variants}[resource]
        with engine.connect() as conn:
            row=conn.execute(select(table).where(table.c.id==record_id)).mappings().first()
        if not row:
            raise RuleError('Catalogue record not found',404)
        return auth.redact_catalogue(row, request.state.user['role'])

    @application.get("/api/v1/inventory/balances")
    def inventory_balances(request: Request, location_id: str = db.LOCATION_ID, q: str = "", offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        with engine.connect() as conn:
            result = store.inventory(conn,location_id,q,offset,limit)
        result['items'] = [auth.redact_catalogue(p, request.state.user['role']) for p in result['items']]
        return result

    @application.get("/api/v1/inventory/movements")
    def movement_list(variant_id: str | None = None, location_id: str = db.LOCATION_ID, before: int | None = None, limit: int = Query(50, ge=1, le=100)):
        query = select(db.movements).where(db.movements.c.location_id == location_id)
        if variant_id:
            query = query.where(db.movements.c.product_id == variant_id)
        if before:
            query = query.where(db.movements.c.sequence < before)
        with engine.connect() as conn:
            return [dict(r) for r in conn.execute(query.order_by(db.movements.c.sequence.desc()).limit(limit)).mappings()]

    @application.get("/api/incoming")
    def incoming_list(request: Request, offset: int=Query(0,ge=0), limit: int=Query(50,ge=1,le=100)):
        with engine.connect() as conn:
            result=store.incoming(conn,offset,limit)
        result['items']=[auth.redact_transaction(t,request.state.user['role']) for t in result['items']]
        return result

    @application.get("/api/reconciliation")
    def reconciliation(request: Request):
        auth.require_partner(request.state.user)
        with engine.connect() as conn:
            return reconcile(conn)

    @application.post("/api/receipt-drafts")
    def receipt_draft(payload: Receipt, request: Request, idempotency_key: str = Header(max_length=200)):
        draft_id = str(__import__('uuid').uuid5(__import__('uuid').NAMESPACE_URL, request.state.user["username"] + ":receipt:" + idempotency_key))
        return drafts.create_draft(engine, "receipt", payload.model_dump(), request.state.user["username"], draft_id)

    @application.get("/api/drafts")
    def pending_drafts(request: Request):
        with engine.connect() as conn:
            query = select(db.drafts).where(db.drafts.c.status != "posted").order_by(db.drafts.c.created_at)
            if request.state.user["role"] == "staff":
                query = query.where(db.drafts.c.kind == "receipt")
            return [dict(x) for x in conn.execute(query).mappings()]

    @application.patch("/api/drafts/{draft_id}")
    def edit_draft(draft_id: str,payload: DraftEdit,request: Request):
        with engine.connect() as conn:
            kind=conn.execute(select(db.drafts.c.kind).where(db.drafts.c.id==draft_id)).scalar()
        if not kind:
            raise RuleError('Draft not found',404)
        from app.modules.purchasing.intake import Intake
        schema=Receipt if kind=='receipt' else Intake if kind=='intake' else Purchase
        source_file=payload.payload.get('source_file_id')
        cleaned=schema.model_validate(payload.payload if kind=='intake' else {k:v for k,v in payload.payload.items() if k!='source_file_id'}).model_dump()
        if kind=='purchase' and source_file:
            cleaned['source_file_id']=source_file
        return drafts.edit(engine,draft_id,payload.version,cleaned,request.state.user)

    @application.get("/api/drafts/{draft_id}")
    def draft_detail(draft_id: str, request: Request):
        with engine.connect() as conn:
            row=conn.execute(select(db.drafts).where(db.drafts.c.id==draft_id)).mappings().first()
        if not row:
            raise RuleError('Draft not found',404)
        if row['kind'] in {'purchase','intake'}:
            auth.require_partner(request.state.user)
        return dict(row)

    @application.post("/api/drafts/{draft_id}/approve")
    def approve_draft(draft_id: str, payload: Version, request: Request):
        drafts.approve(engine, draft_id, payload.version, request.state.user)
        return {"id": draft_id, "version": payload.version}

    @application.post("/api/drafts/{draft_id}/post")
    def post_draft(draft_id: str, payload: Version, request: Request):
        auth.require_partner(request.state.user)
        result = store.post("post_draft", {"id": draft_id, "version": payload.version}, f"draft:{draft_id}:v{payload.version}", request.state.user["username"])
        return store.transaction(result["id"])

    @application.post("/api/files")
    async def upload(request: Request, file: UploadFile = File()):
        auth.require_partner(request.state.user)
        body = await file.read(4 * 1024 * 1024 + 1)
        formats = {"application/pdf": (b"%PDF-", ".pdf"), "image/png": (b"\x89PNG\r\n\x1a\n", ".png"), "image/jpeg": (b"\xff\xd8\xff", ".jpg")}
        if file.content_type not in formats or len(body) > 4 * 1024 * 1024 or not body.startswith(formats[file.content_type][0]):
            raise RuleError("Upload a PDF, PNG or JPEG up to 4 MiB", 422)
        digest = hashlib.sha256(body).hexdigest()
        with engine.connect() as conn:
            old = conn.execute(select(db.files).where(db.files.c.sha256 == digest)).mappings().first()
            if old:
                return {"id": old["id"], "duplicate": True}
        file_id = identifier()
        folder = ROOT / "data" / mode / engine.url.database / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (file_id + formats[file.content_type][1])
        path.write_bytes(body)
        path.chmod(0o600)
        from sqlalchemy.dialects.postgresql import insert
        try:
            with engine.begin() as conn:
                saved=conn.execute(insert(db.files).values(id=file_id,sha256=digest,name=Path(file.filename or 'document').name,
                    media_type=file.content_type,path=str(path),actor=request.state.user['username']).on_conflict_do_nothing().returning(db.files.c.id)).scalar()
                if not saved:
                    saved=conn.execute(select(db.files.c.id).where(db.files.c.sha256==digest)).scalar_one()
            if saved!=file_id:
                path.unlink(missing_ok=True)
            return {'id':saved,'duplicate':saved!=file_id}
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @application.post("/api/agent/runs")
    def start_run(payload: Goal,request: Request,idempotency_key: str=Header(max_length=200)):
        auth.require_partner(request.state.user)
        return store.post('agent_run',payload.model_dump(),idempotency_key,request.state.user['username'])

    @application.post('/api/agent/runs/{run_id}/clarify')
    def clarify_run(run_id: str,payload: Clarification,request: Request,idempotency_key: str=Header(max_length=200)):
        from app.workflows.runs import clarify
        return clarify(engine,run_id,payload.message,idempotency_key,request.state.user)

    @application.get("/api/agent/runs")
    def list_runs(request: Request):
        auth.require_partner(request.state.user)
        with engine.connect() as conn:
            return [dict(x) for x in conn.execute(select(db.runs).order_by(db.runs.c.created_at.desc()).limit(50)).mappings()]

    @application.get("/api/agent/runs/{run_id}")
    def run_detail(run_id: str, request: Request):
        auth.require_partner(request.state.user)
        with engine.connect() as conn:
            run = conn.execute(select(db.runs).where(db.runs.c.id == run_id)).mappings().first()
            if not run:
                raise RuleError("Run not found", 404)
            from app.workflows.runs import clarifications
            return {**run, "clarifications":clarifications(conn,run_id), "steps": [dict(x) for x in conn.execute(select(db.steps).where(db.steps.c.run_id == run_id).order_by(db.steps.c.sequence)).mappings()]}

    @application.post("/api/agent/runs/{run_id}/resume")
    def resume_run(run_id: str, request: Request):
        auth.require_partner(request.state.user)
        from app.agents.runtime import resume
        return resume(engine, run_id, request.state.user)

    @application.get("/api/reports/{report_id}")
    def report(report_id: str, request: Request):
        auth.require_partner(request.state.user)
        with engine.connect() as conn:
            row=conn.execute(select(db.reports).where(db.reports.c.id==report_id)).mappings().first()
        if not row:
            raise RuleError('Report not found',404)
        return dict(row)

    @application.get("/api/health")
    def health():
        with engine.connect() as conn:
            revision = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
        return {"status": "ok", "mode": mode, "database": "PostgreSQL", "schema_version": revision}

    @application.get("/")
    def index():
        return FileResponse(ROOT / "frontend" / "dist" / "index.html")

    application.mount("/assets", StaticFiles(directory=ROOT / "frontend" / "dist" / "assets", check_dir=False), name="assets")
    return application


app = create_app()
