from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.ledger import Ledger, RuleError

ROOT = Path(__file__).resolve().parents[2]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Product(Input):
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    brand: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=100)
    compatibility: str = Field(default="", max_length=200)
    specification: str = Field(default="", max_length=200)
    unit: Literal["piece", "pair", "set", "kit", "carton", "service"]
    kind: Literal["goods", "service"] = "goods"
    threshold: StrictInt = Field(default=0, ge=0, le=1000000000)
    price_paise: StrictInt = Field(default=0, ge=0, le=1000000000)
    conversions: dict[str, StrictInt] = Field(default_factory=dict)


class PurchaseLine(Input):
    product_id: str
    quantity: StrictInt = Field(ge=1, le=1000000000)
    unit: str
    cost_paise: StrictInt = Field(default=0, ge=0, le=1000000000)


class Purchase(Input):
    supplier: str = Field(min_length=1, max_length=200)
    invoice_number: str = Field(min_length=1, max_length=200)
    invoice_date: str
    lines: list[PurchaseLine] = Field(min_length=1, max_length=100)


class ReceiptLine(Input):
    purchase_line_id: str
    accepted: StrictInt = Field(ge=0, le=1000000000)
    damaged: StrictInt = Field(default=0, ge=0, le=1000000000)


class Receipt(Input):
    purchase_id: str
    confirmed: bool
    lines: list[ReceiptLine] = Field(min_length=1, max_length=100)


class SaleLine(Input):
    product_id: str
    quantity: StrictInt = Field(ge=1, le=1000000000)
    price_paise: StrictInt = Field(ge=0, le=1000000000)


class Sale(Input):
    payment: Literal["cash", "upi", "card", "credit"] = "cash"
    lines: list[SaleLine] = Field(min_length=1, max_length=100)


class ReturnLine(Input):
    sale_line_id: str
    quantity: StrictInt = Field(ge=1, le=1000000000)
    damaged: StrictInt = Field(default=0, ge=0, le=1000000000)


class StockReturn(Input):
    sale_id: str
    reason: str = Field(min_length=1, max_length=200)
    lines: list[ReturnLine] = Field(min_length=1, max_length=100)


def create_app(database: Path | None = None, mode: str | None = None):
    mode = mode or os.environ.get("KCD_MODE", "demo")
    if mode not in {"demo", "shop"}:
        raise RuntimeError("KCD_MODE must be demo or shop")
    database = database or Path(os.environ.get("KCD_DATABASE", str(ROOT / "data" / mode / "ledger.sqlite3")))

    @asynccontextmanager
    async def lifespan(application):
        application.state.ledger = Ledger(database)
        yield

    application = FastAPI(title="Kakinada Car Decors — local pilot", lifespan=lifespan)
    application.state.mode = mode

    @application.middleware("http")
    async def local_boundary(request: Request, call_next):
        # Same-origin browser writes only. No cookies/auth are used in this loopback pilot.
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            if origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin writes are disabled"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path not in {"/docs", "/redoc"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
            )
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(RuleError)
    async def rule_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @application.exception_handler(sqlite3.OperationalError)
    async def storage_error(request, exc):
        return JSONResponse({"detail": "Storage operation failed; no success is confirmed. Retry the same request key."}, status_code=503)

    @application.get("/api/state")
    def state():
        return {"mode": mode, "actor": "local-pilot", "tax_invoicing_enabled": False,
                **application.state.ledger.state()}

    @application.get("/api/transactions/{transaction_id}")
    def transaction(transaction_id: str):
        return application.state.ledger.transaction(transaction_id)

    def post(operation, payload, key):
        return application.state.ledger.post(operation, payload.model_dump(), key)

    @application.post("/api/products")
    def product(payload: Product, idempotency_key: str = Header(min_length=1, max_length=200)):
        return post("product", payload, idempotency_key)

    @application.post("/api/purchases")
    def purchase(payload: Purchase, idempotency_key: str = Header(min_length=1, max_length=200)):
        return post("purchase", payload, idempotency_key)

    @application.post("/api/receipts")
    def receipt(payload: Receipt, idempotency_key: str = Header(min_length=1, max_length=200)):
        return post("receipt", payload, idempotency_key)

    @application.post("/api/sales")
    def sale(payload: Sale, idempotency_key: str = Header(min_length=1, max_length=200)):
        return post("sale", payload, idempotency_key)

    @application.post("/api/returns")
    def stock_return(payload: StockReturn, idempotency_key: str = Header(min_length=1, max_length=200)):
        return post("return", payload, idempotency_key)

    @application.get("/api/health")
    def health():
        with application.state.ledger.connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok", "mode": mode, "schema_version": 1}

    @application.get("/")
    def index():
        if not (ROOT / "frontend" / "dist" / "index.html").is_file():
            return JSONResponse({"detail": "Build the frontend first: cd frontend && npm ci && npm run build"}, status_code=503)
        return FileResponse(ROOT / "frontend" / "dist" / "index.html")

    application.mount("/assets", StaticFiles(directory=ROOT / "frontend" / "dist" / "assets", check_dir=False), name="assets")
    return application


app = create_app()
