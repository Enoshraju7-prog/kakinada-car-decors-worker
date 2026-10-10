from collections import defaultdict
from sqlalchemy import select
from app.infrastructure import database as db
from app.modules.catalog.service import get_variant
from app.modules.inventory.service import lock_balances, move
from app.modules.purchasing.service import check_lines
from app.ledger import RuleError, integer, required


def sale(store, conn, data, actor, key):
    check_lines(data["lines"])
    payment = data.get("payment", "cash")
    if payment not in {"cash", "upi", "card", "credit"}:
        raise RuleError("Choose cash, UPI, card or credit", 422)
    ids = sorted({l['product_id'] for l in data['lines']})
    conn.execute(select(db.variants.c.id).where(db.variants.c.id.in_(ids)).order_by(db.variants.c.id).with_for_update()).all()
    products = {vid: get_variant(conn, vid) for vid in ids}
    role = conn.execute(select(db.users.c.role).where(db.users.c.username == actor)).scalar()
    quantities = defaultdict(int)
    for l in data["lines"]:
        quantities[l["product_id"]] += integer(l["quantity"], "Sale quantity", 1)
        integer(l["price_paise"], "Price")
        if role == 'staff' and l['price_paise'] != products[l['product_id']]['price_paise']:
            raise RuleError('A partner controls selling prices. Refresh to use the current price.', 403)
    location = data.get("location_id", db.LOCATION_ID)
    locked = lock_balances(conn, [x for x, p in products.items() if p["kind"] == "goods"], location)
    for vid, qty in quantities.items():
        if products[vid]["kind"] == "goods" and (vid not in locked or locked[vid]["available"] < qty):
            raise RuleError(f"Not enough sellable stock for {products[vid]['sku']}")
    total = sum(l["quantity"] * l["price_paise"] for l in data["lines"])
    customer_id = None
    if data.get('customer'):
        from app.modules.sales.customers import save_customer
        customer_id = save_customer(conn, data['customer'], actor)
    tx = store.document(conn, "sale", {"payment": payment, "payment_status": "unpaid" if payment == "credit" else "recorded",
        "location_id": location, "purpose": "Counter record; not a GST invoice"}, actor, total=total)
    if customer_id:
        conn.execute(db.customer_sales.insert().values(id=tx, customer_id=customer_id))
    for l in data["lines"]:
        p = products[l["product_id"]]
        line = store.line(conn, tx, p, l["quantity"], price=l["price_paise"])
        if p["kind"] == "goods":
            move(conn, tx, line, p["id"], location, -l["quantity"], 0, 0, actor, key)
    from app.modules.sales.receipts import save_receipt
    save_receipt(conn, tx, customer_id)
    return tx


def stock_return(store, conn, data, actor, key):
    sale_doc = store.source(conn, data["sale_id"], "sale")
    check_lines(data["lines"])
    ids = [l["sale_line_id"] for l in data["lines"]]
    if len(ids) != len(set(ids)):
        raise RuleError("Use one return row per sale line", 422)
    source = {r["id"]: r for r in conn.execute(select(db.lines).where(db.lines.c.id.in_(sorted(ids)),
              db.lines.c.transaction_id == data["sale_id"]).order_by(db.lines.c.id).with_for_update()).mappings()}
    if len(source) != len(ids):
        raise RuleError("Sale line does not belong to this sale", 422)
    location = sale_doc["data"].get("location_id", db.LOCATION_ID)
    lock_balances(conn, [r["product_id"] for r in source.values()], location)
    tx = store.document(conn, "return", {"reason": required(data["reason"], "Reason"),
        "purpose": "Goods return; payment refund is separate"}, actor, data["sale_id"])
    for l in data["lines"]:
        s = source[l["sale_line_id"]]
        qty = integer(l["quantity"], "Returned quantity", 1)
        damage = integer(l.get("damaged", 0), "Damaged")
        if damage > qty or qty + store.linked(conn, s["id"], "return") > s["quantity"]:
            raise RuleError("Return exceeds sold/returnable quantity")
        p = get_variant(conn, s["product_id"])
        if p["kind"] != "goods":
            raise RuleError("Services cannot be returned into stock", 422)
        line = store.line(conn, tx, p, qty, damage, price=s["price_paise"], parent=s["id"], extra=s["snapshot"])
        move(conn, tx, line, p["id"], location, qty - damage, damage, 0, actor, key)
    return tx


def adjustment(store, conn, data, actor, key):
    p = get_variant(conn, data["product_id"])
    if p["kind"] != "goods":
        raise RuleError("Services have no stock count", 422)
    location = data.get("location_id", db.LOCATION_ID)
    b = lock_balances(conn, [p["id"]], location).get(p["id"])
    if not b:
        raise RuleError("Location not found", 404)
    counts = {x: integer(data[x], f"Counted {x}") for x in ("available", "damaged", "quarantined")}
    deltas = {x: counts[x] - b[x] for x in counts}
    if not any(deltas.values()):
        raise RuleError("Count matches the ledger; no adjustment needed", 422)
    tx = store.document(conn, "adjustment", {"reason": required(data["reason"], "Reason"),
        "evidence": required(data["evidence"], "Count evidence"), "before": {x: b[x] for x in counts}, "counted": counts}, actor)
    line = store.line(conn, tx, p, max(1, sum(abs(x) for x in deltas.values())))
    move(conn, tx, line, p["id"], location, deltas["available"], deltas["damaged"], deltas["quarantined"], actor, key)
    return tx


def reverse(store, conn, data, actor, key):
    original = conn.execute(select(db.documents).where(db.documents.c.id == data["transaction_id"]).with_for_update()).mappings().first()
    if not original or original["kind"] == "reversal":
        raise RuleError("Choose an original posted transaction", 422)
    if conn.execute(select(db.documents.c.id).where(db.documents.c.parent_id == original["id"])).first():
        raise RuleError("Linked dependants exist; use a reviewed count adjustment")
    effects = conn.execute(select(db.movements).where(db.movements.c.transaction_id == original["id"])
                           .order_by(db.movements.c.sequence)).mappings().all()
    # All linked source lines are locked before balance rows, matching receipt/return posting.
    conn.execute(select(db.lines).where(db.lines.c.transaction_id == original["id"]).order_by(db.lines.c.id).with_for_update()).all()
    for location in sorted({m["location_id"] for m in effects}):
        lock_balances(conn, [m["product_id"] for m in effects if m["location_id"] == location], location)
    maxima = {}
    for m in effects:
        maxima[(m["product_id"], m["location_id"])] = m["sequence"]
    for (vid, location), sequence in maxima.items():
        if conn.execute(select(db.movements.c.id).where(db.movements.c.product_id == vid,
                        db.movements.c.location_id == location, db.movements.c.sequence > sequence)).first():
            raise RuleError("Later stock movements exist; use a reviewed count adjustment")
    tx = store.document(conn, "reversal", {"reason": required(data["reason"], "Reason"),
        "evidence": required(data["evidence"], "Evidence")}, actor, original["id"])
    for m in effects:
        p = get_variant(conn, m["product_id"])
        line = store.line(conn, tx, p, max(1, abs(m["available_delta"]) + abs(m["damaged_delta"]) + abs(m["quarantined_delta"])), parent=m["line_id"])
        move(conn, tx, line, p["id"], m["location_id"], -m["available_delta"], -m["damaged_delta"], -m["quarantined_delta"], actor, key, reversal_of=m["id"])
    return tx
