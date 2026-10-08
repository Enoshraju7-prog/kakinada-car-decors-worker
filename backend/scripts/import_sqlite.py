"""One-way import into a fresh PostgreSQL ledger, preserving legacy IDs and replay records."""
import json
from pathlib import Path
import sqlite3
import sys
import uuid
from sqlalchemy import select, func

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.infrastructure import database as db
from app.ledger import Ledger, RuleError, normalized, now
from app.modules.catalog.service import legacy_product
from app.modules.inventory.service import move, reconcile


def migrate(source, engine):
    source = Path(source)
    if not source.is_file():
        raise RuntimeError("Source database does not exist")
    backup = source.parent / ("before-postgres-" + now().replace(":", "-") + ".sqlite3")
    Ledger(source).backup(backup)
    old = sqlite3.connect(backup)
    old.row_factory = sqlite3.Row
    try:
        with engine.begin() as conn:
            if conn.execute(select(func.count()).select_from(db.documents)).scalar() or conn.execute(select(func.count()).select_from(db.variants)).scalar():
                raise RuntimeError("Import requires a fresh target ledger; existing PostgreSQL records were preserved")
            for row in old.execute("SELECT * FROM products ORDER BY rowid"):
                p = dict(row)
                p["conversions"] = json.loads(p["conversions"])
                legacy_product(conn, p, "local-pilot", p["id"])
            for row in old.execute("SELECT * FROM transactions ORDER BY rowid"):
                d = dict(row)
                d["data"] = json.loads(d["data"])
                conn.execute(db.documents.insert().values(**d))
                if d["kind"] == "purchase":
                    info = d["data"]
                    alias = normalized(info["supplier"])
                    sid = str(uuid.uuid5(uuid.NAMESPACE_URL, "kcd:legacy-supplier:" + alias))
                    if not conn.execute(select(db.suppliers.c.id).where(db.suppliers.c.id == sid)).first():
                        conn.execute(db.suppliers.insert().values(id=sid, name=info["supplier"]))
                        conn.execute(db.aliases.insert().values(supplier_id=sid, alias_key=alias, confirmed_by="local-pilot"))
                    conn.execute(db.purchase_headers.insert().values(id=d["id"], supplier_id=sid,
                                 invoice_key=normalized(info["invoice_number"]), financial_year=info["financial_year"], invoice_date=info["invoice_date"]))
                if d["kind"] == "receipt":
                    conn.execute(db.receipt_headers.insert().values(id=d["id"], purchase_id=d["parent_id"],
                                 location_id=db.LOCATION_ID, confirmed_by=d["actor"]))
            for row in old.execute("SELECT * FROM lines ORDER BY rowid"):
                line = dict(row)
                line["snapshot"] = json.loads(line["snapshot"])
                conn.execute(db.lines.insert().values(**line, quarantined=0))
            for row in old.execute("SELECT * FROM movements ORDER BY rowid"):
                m = dict(row)
                move(conn, m["transaction_id"], m["line_id"], m["product_id"], db.LOCATION_ID,
                     m["available_delta"], m["damaged_delta"], 0, m["actor"], "legacy:" + m["transaction_id"],
                     movement_id=m["id"], created_at=m["created_at"])
            for row in old.execute("SELECT * FROM requests"):
                conn.execute(db.requests.insert().values(key=row["key"], fingerprint=row["fingerprint"],
                             response=json.loads(row["response"]), actor="local-pilot", legacy=1))
            result = reconcile(conn)
            for row in old.execute("SELECT p.id, COALESCE(SUM(m.available_delta),0) a, COALESCE(SUM(m.damaged_delta),0) d FROM products p LEFT JOIN movements m ON m.product_id=p.id WHERE p.kind='goods' GROUP BY p.id"):
                b = conn.execute(select(db.balances).where(db.balances.c.variant_id == row["id"])).mappings().one()
                if (b["available"], b["damaged"]) != (row["a"], row["d"]):
                    raise RuntimeError("Legacy-to-PostgreSQL balance mismatch; import rolled back")
            if not result["ok"]:
                raise RuntimeError("Projection mismatch; import rolled back")
            conn.execute(db.audit.insert().values(id=str(uuid.uuid4()), actor="migration", event="sqlite_import", source_id=str(source),
                         created_at=now(), data={"backup": str(backup), "reconciliation": result}))
    finally:
        old.close()
    return {"backup": str(backup), "reconciliation": result}


if __name__ == "__main__":
    result = migrate(Path(sys.argv[1]), db.engine_for())
    print(json.dumps(result, indent=2))
