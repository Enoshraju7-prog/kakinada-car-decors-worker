"""Deterministic inventory policy. No network or model calls belong here."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path


class RuleError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier():
    return str(uuid.uuid4())


def normalized(value):
    # Preserve punctuation: AB-1 and AB1 may be different invoice numbers.
    return re.sub(r"\s+", " ", value.strip()).casefold()


def integer(value, label, minimum=0):
    if type(value) is not int or value < minimum or value > 1_000_000_000:
        raise RuleError(f"{label} must be a whole number from {minimum} to 1000000000", 422)
    return value


def required(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise RuleError(f"{label} is required (up to 200 characters)", 422)
    return value.strip()


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError("Unsupported ledger schema version")
            conn.executescript(Path(__file__).with_name("schema.sql").read_text())

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        # Rollback journal avoids WAL-specific filesystem requirements for this pilot.
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    @contextmanager
    def connection(self, write=False):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def post(self, operation, payload, key, actor="local-pilot"):
        key = required(key, "Request key")
        actor = required(actor, "Actor")
        fingerprint = hashlib.sha256(json.dumps(
            [operation, payload, actor], sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
        try:
            with self.connection(write=True) as conn:
                previous = conn.execute("SELECT * FROM requests WHERE key=?", (key,)).fetchone()
                if previous:
                    if previous["fingerprint"] != fingerprint:
                        raise RuleError("This request key was already used for different details")
                    return json.loads(previous["response"])
                handlers = {"product": self._product, "purchase": self._purchase,
                            "receipt": self._receipt, "sale": self._sale, "return": self._return}
                result = handlers[operation](conn, payload, actor)
                # Read the persisted source and ledger inside the committing transaction.
                if operation != "product":
                    result = self._transaction(conn, result)
                conn.execute("INSERT INTO requests VALUES (?,?,?)", (key, fingerprint, json.dumps(result)))
            return result
        except sqlite3.IntegrityError as exc:
            raise RuleError("Duplicate SKU or supplier bill, or invalid linked record") from exc
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                raise RuleError("Ledger busy; retry the same request key", 503) from exc
            raise

    def _product(self, conn, data, actor):
        unit = data["unit"]
        kind = data["kind"]
        if unit not in {"piece", "pair", "set", "kit", "carton", "service"}:
            raise RuleError("Choose an explicit supported unit", 422)
        if kind not in {"goods", "service"} or (kind == "service") != (unit == "service"):
            raise RuleError("Services must use the service unit; goods must use a stock unit", 422)
        conversions = data.get("conversions", {})
        if not isinstance(conversions, dict):
            raise RuleError("Conversions must map confirmed pack units to integer base-unit factors", 422)
        for pack, factor in conversions.items():
            if pack not in {"piece", "pair", "set", "kit", "carton"} or pack == unit:
                raise RuleError("Pack unit must be a different supported stock unit", 422)
            integer(factor, "Confirmed conversion factor", 1)
        if kind == "service" and conversions:
            raise RuleError("Services have no stock conversions", 422)
        product_id = identifier()
        conn.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            product_id, required(data["sku"], "SKU").upper(), required(data["name"], "Name"),
            required(data["category"], "Category"), data.get("brand", ""), data.get("model", ""),
            data.get("compatibility", ""), data.get("specification", ""), unit, kind,
            integer(data.get("threshold", 0), "Threshold"), integer(data.get("price_paise", 0), "Price"),
            json.dumps(conversions), now()))
        return {"id": product_id, "sku": data["sku"].strip().upper()}

    def _get_product(self, conn, product_id):
        product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            raise RuleError("Product not found", 404)
        return dict(product)

    def _new_transaction(self, conn, kind, data, actor, parent=None, total=0):
        tx_id = identifier()
        conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?)", (
            tx_id, kind, parent, actor, now(), json.dumps(data), total))
        return tx_id

    def _line(self, conn, tx_id, product, quantity, damaged=0, price=0, parent=None, extra=None):
        line_id = identifier()
        snapshot = {"sku": product["sku"], "name": product["name"], "unit": product["unit"],
                    "kind": product["kind"], **(extra or {})}
        conn.execute("INSERT INTO lines VALUES (?,?,?,?,?,?,?,?)", (
            line_id, tx_id, product["id"], parent, quantity, damaged, price, json.dumps(snapshot)))
        return line_id

    def _movement(self, conn, tx_id, line_id, product_id, available, damaged, actor):
        conn.execute("INSERT INTO movements VALUES (?,?,?,?,?,?,?,?)", (
            identifier(), tx_id, line_id, product_id, available, damaged, actor, now()))

    def _balance(self, conn, product_id):
        return conn.execute("SELECT COALESCE(SUM(available_delta),0), COALESCE(SUM(damaged_delta),0) "
                            "FROM movements WHERE product_id=?", (product_id,)).fetchone()

    def _check_lines(self, lines):
        if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
            raise RuleError("Add between 1 and 100 lines", 422)

    def _purchase(self, conn, data, actor):
        supplier = required(data["supplier"], "Supplier")
        invoice = required(data["invoice_number"], "Invoice number")
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["invoice_date"]):
                raise ValueError("Expected ISO calendar date")
            invoice_date = date.fromisoformat(data["invoice_date"])
        except (TypeError, ValueError) as exc:
            raise RuleError("Invoice date must be YYYY-MM-DD", 422) from exc
        year = invoice_date.year if invoice_date.month >= 4 else invoice_date.year - 1
        self._check_lines(data["lines"])
        tx_id = self._new_transaction(conn, "purchase", {
            "supplier": supplier, "invoice_number": invoice, "invoice_date": invoice_date.isoformat(),
            "financial_year": f"{year}-{year+1}", "purpose": "Incoming stock record; not a tax invoice"}, actor)
        conn.execute("INSERT INTO purchase_identity VALUES (?,?,?,?)", (
            normalized(supplier), f"{year}-{year+1}", normalized(invoice), tx_id))
        for line in data["lines"]:
            product = self._get_product(conn, line["product_id"])
            if product["kind"] != "goods":
                raise RuleError("A fitting service cannot be received as stock", 422)
            quantity = integer(line["quantity"], "Ordered quantity", 1)
            unit = required(line["unit"], "Supplier unit")
            conversions = json.loads(product["conversions"])
            factor = 1 if unit == product["unit"] else conversions.get(unit)
            if factor is None:
                raise RuleError(f"Confirm the {unit}-to-{product['unit']} conversion for {product['sku']}", 422)
            base_quantity = integer(quantity * factor, "Base-unit quantity", 1)
            self._line(conn, tx_id, product, base_quantity,
                       price=integer(line.get("cost_paise", 0), "Cost per supplier unit"),
                       extra={"ordered_quantity": quantity, "ordered_unit": unit, "factor": factor,
                              "cost_basis": "per ordered supplier unit"})
        return tx_id

    def _source(self, conn, source_id, expected_kind):
        row = conn.execute("SELECT * FROM transactions WHERE id=?", (source_id,)).fetchone()
        if not row:
            raise RuleError("Source transaction not found", 404)
        if row["kind"] != expected_kind:
            raise RuleError(f"Expected a {expected_kind} source", 422)
        return dict(row)

    def _linked_quantity(self, conn, line_id, kind):
        return conn.execute("SELECT COALESCE(SUM(l.quantity),0) FROM lines l "
                            "JOIN transactions t ON t.id=l.transaction_id "
                            "WHERE l.parent_line_id=? AND t.kind=?", (line_id, kind)).fetchone()[0]

    def _receipt(self, conn, data, actor):
        self._source(conn, data["purchase_id"], "purchase")
        if data.get("confirmed") is not True:
            raise RuleError("Physical receipt must be explicitly confirmed", 422)
        self._check_lines(data["lines"])
        tx_id = self._new_transaction(conn, "receipt", {"confirmed": True}, actor, data["purchase_id"])
        for line in data["lines"]:
            source = conn.execute("SELECT * FROM lines WHERE id=? AND transaction_id=?", (
                line["purchase_line_id"], data["purchase_id"])).fetchone()
            if not source:
                raise RuleError("Purchase line not found on this bill", 422)
            accepted = integer(line["accepted"], "Accepted quantity")
            damaged = integer(line.get("damaged", 0), "Damaged quantity")
            quantity = integer(accepted + damaged, "Total received", 1)
            received = self._linked_quantity(conn, source["id"], "receipt")
            if received + quantity > source["quantity"]:
                raise RuleError("Receipt exceeds outstanding quantity on this bill")
            product = self._get_product(conn, source["product_id"])
            line_id = self._line(conn, tx_id, product, quantity, damaged, parent=source["id"])
            self._movement(conn, tx_id, line_id, product["id"], accepted, damaged, actor)
        return tx_id

    def _sale(self, conn, data, actor):
        payment = data.get("payment", "cash")
        if payment not in {"cash", "upi", "card", "credit"}:
            raise RuleError("Choose cash, UPI, card or credit", 422)
        self._check_lines(data["lines"])
        total = sum(integer(line["quantity"], "Sale quantity", 1) *
                    integer(line["price_paise"], "Sale price") for line in data["lines"])
        tx_id = self._new_transaction(conn, "sale", {"payment": payment,
            "payment_status": "unpaid" if payment == "credit" else "paid",
            "purpose": "Counter stock record; not a GST invoice"}, actor, total=total)
        for line in data["lines"]:
            product = self._get_product(conn, line["product_id"])
            quantity = integer(line["quantity"], "Sale quantity", 1)
            price = integer(line["price_paise"], "Sale price")
            if product["kind"] == "goods" and self._balance(conn, product["id"])[0] < quantity:
                raise RuleError(f"Not enough sellable stock for {product['sku']}")
            line_id = self._line(conn, tx_id, product, quantity, price=price)
            if product["kind"] == "goods":
                self._movement(conn, tx_id, line_id, product["id"], -quantity, 0, actor)
        return tx_id

    def _return(self, conn, data, actor):
        self._source(conn, data["sale_id"], "sale")
        reason = required(data["reason"], "Return reason")
        self._check_lines(data["lines"])
        tx_id = self._new_transaction(conn, "return", {"reason": reason,
            "purpose": "Stock return only; refund settlement is separate"}, actor, data["sale_id"])
        for line in data["lines"]:
            source = conn.execute("SELECT * FROM lines WHERE id=? AND transaction_id=?", (
                line["sale_line_id"], data["sale_id"])).fetchone()
            if not source:
                raise RuleError("Sale line not found on this sale", 422)
            quantity = integer(line["quantity"], "Return quantity", 1)
            damaged = integer(line.get("damaged", 0), "Damaged return quantity")
            if damaged > quantity:
                raise RuleError("Damaged quantity cannot exceed returned quantity", 422)
            if self._linked_quantity(conn, source["id"], "return") + quantity > source["quantity"]:
                raise RuleError("Cumulative return exceeds quantity sold")
            product = self._get_product(conn, source["product_id"])
            if product["kind"] == "service":
                raise RuleError("Fitting services cannot be returned to stock", 422)
            snapshot = json.loads(source["snapshot"])
            line_id = self._line(conn, tx_id, product, quantity, damaged,
                                 price=source["price_paise"], parent=source["id"], extra=snapshot)
            self._movement(conn, tx_id, line_id, product["id"], quantity-damaged, damaged, actor)
        return tx_id

    def _transaction(self, conn, tx_id):
        row = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
        if not row:
            raise RuleError("Transaction not found", 404)
        result = dict(row)
        result["data"] = json.loads(result["data"])
        result["lines"] = []
        for line in conn.execute("SELECT * FROM lines WHERE transaction_id=? ORDER BY rowid", (tx_id,)):
            detail = dict(line)
            detail["snapshot"] = json.loads(detail["snapshot"])
            if row["kind"] == "purchase":
                detail["received"] = self._linked_quantity(conn, line["id"], "receipt")
                detail["outstanding"] = line["quantity"] - detail["received"]
            if row["kind"] == "sale":
                detail["returned"] = self._linked_quantity(conn, line["id"], "return")
            result["lines"].append(detail)
        if row["kind"] in {"sale", "return"}:
            result["total_paise"] = sum(x["quantity"] * x["price_paise"] for x in result["lines"])
        result["movements"] = [dict(x) for x in conn.execute(
            "SELECT * FROM movements WHERE transaction_id=? ORDER BY rowid", (tx_id,))]
        return result

    def transaction(self, tx_id):
        with self.connection() as conn:
            return self._transaction(conn, tx_id)

    def state(self):
        with self.connection() as conn:
            products = []
            for row in conn.execute("SELECT * FROM products ORDER BY category,name"):
                product = dict(row)
                product["conversions"] = json.loads(product["conversions"])
                product["available"], product["damaged"] = self._balance(conn, product["id"])
                product["low_stock"] = product["kind"] == "goods" and product["available"] <= product["threshold"]
                product["incoming"] = conn.execute("SELECT COALESCE(SUM(l.quantity),0) FROM lines l "
                    "JOIN transactions t ON t.id=l.transaction_id WHERE t.kind='purchase' AND l.product_id=?",
                    (product["id"],)).fetchone()[0] - conn.execute(
                    "SELECT COALESCE(SUM(l.quantity),0) FROM lines l JOIN transactions t ON t.id=l.transaction_id "
                    "WHERE t.kind='receipt' AND l.product_id=?", (product["id"],)).fetchone()[0]
                products.append(product)
            transactions = [self._transaction(conn, x[0]) for x in conn.execute(
                "SELECT id FROM transactions ORDER BY rowid DESC")]
            return {"products": products, "transactions": transactions,
                    "movements": [dict(x) for x in conn.execute("SELECT * FROM movements ORDER BY rowid DESC")]}

    def backup(self, destination: Path):
        destination = Path(destination)
        if destination.resolve() == self.path.resolve() or destination.exists():
            raise RuleError("Backup destination must be a new file", 422)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = self.connect()
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")
        finally:
            target.close()
            source.close()
        return destination
