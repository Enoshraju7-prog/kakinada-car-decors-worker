"""Only posting workflows call these mutation functions, inside their transaction."""
from sqlalchemy import select, func
from app.infrastructure import database as db
from app.ledger import RuleError, identifier, now


def lock_balances(conn, variant_ids, location_id):
    rows = conn.execute(select(db.balances).where(db.balances.c.variant_id.in_(sorted(set(variant_ids))),
                        db.balances.c.location_id == location_id).order_by(db.balances.c.variant_id).with_for_update()).mappings().all()
    return {r["variant_id"]: dict(r) for r in rows}


def move(conn, tx, line, variant_id, location_id, available, damaged, quarantined, actor, key, reversal_of=None,
         movement_id=None, created_at=None):
    balance = conn.execute(select(db.balances).where(db.balances.c.variant_id == variant_id,
                           db.balances.c.location_id == location_id).with_for_update()).mappings().first()
    if not balance:
        raise RuleError("Goods SKU/location balance not found", 422)
    changes = {"available": available, "damaged": damaged, "quarantined": quarantined}
    updated = {k: balance[k] + v for k, v in changes.items()}
    if min(updated.values()) < 0:
        raise RuleError("Stock changed; this operation would make a stock bucket negative")
    conn.execute(db.movements.insert().values(id=movement_id or identifier(), transaction_id=tx, line_id=line,
                 product_id=variant_id, location_id=location_id, available_delta=available, damaged_delta=damaged,
                 quarantined_delta=quarantined, actor=actor, created_at=created_at or now(), operation_id=key,
                 reversal_of=reversal_of))
    conn.execute(db.balances.update().where(db.balances.c.variant_id == variant_id,
                 db.balances.c.location_id == location_id).values(**updated))


def reconcile(conn):
    failures = []
    for b in conn.execute(select(db.balances)).mappings():
        values = conn.execute(select(func.coalesce(func.sum(db.movements.c.available_delta), 0),
            func.coalesce(func.sum(db.movements.c.damaged_delta), 0),
            func.coalesce(func.sum(db.movements.c.quarantined_delta), 0)).where(
            db.movements.c.product_id == b["variant_id"], db.movements.c.location_id == b["location_id"])).one()
        if tuple(b[x] for x in ("available", "damaged", "quarantined")) != tuple(values):
            failures.append({"variant_id": b["variant_id"], "location_id": b["location_id"], "ledger": [int(x) for x in values]})
    return {"ok": not failures, "mismatches": failures}
