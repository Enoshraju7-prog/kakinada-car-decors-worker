"""Supplier bills establish incoming obligations; receipts establish physical stock."""
import re
from datetime import date
from sqlalchemy import select, text
from app.infrastructure import database as db
from app.modules.catalog.service import get_variant
from app.modules.inventory.service import lock_balances, move
from app.ledger import RuleError, identifier, integer, normalized, required


def check_lines(lines):
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
        raise RuleError("Add between 1 and 100 lines", 422)


def purchase(store, conn, data, actor, key):
    review_id = data.get('order_review_id')
    if review_id:
        review = conn.execute(select(db.order_reviews).where(db.order_reviews.c.id == review_id).with_for_update()).mappings().first()
        if not review:
            raise RuleError('Order review not found', 404)
        if conn.execute(select(db.documents.c.id).where(db.documents.c.kind == 'purchase',
                db.documents.c.data['order_review_id'].astext == review_id)).first():
            raise RuleError('This order already has a recorded bill; use its remaining delivery counts')
        source = review['payload']
        if data.get('review_confirmed') is not True or normalized(data['supplier']) != normalized(source['supplier']) or normalized(data['invoice_number']) != normalized(source['invoice_number']):
            raise RuleError('Confirm this exact supplier bill, invoice date, item variants and units', 422)
        grouped = [0] * len(source['lines'])
        for line in data['lines']:
            index = line.get('source_index')
            if type(index) is not int or not 0 <= index < len(grouped):
                raise RuleError('Every mapped variant must reference its original bill line', 422)
            grouped[index] += integer(line['quantity'], 'Ordered quantity', 1) * integer(line['cost_paise'], 'Purchase rate')
        if grouped != [l['amount_paise'] for l in source['lines']]:
            raise RuleError('Mapped quantities and rates must match every confirmed bill-line amount; split mixed items into exact variants', 422)
    name = required(data["supplier"], "Supplier")
    supplier_id = data.get("supplier_id")
    if not supplier_id:
        alias = normalized(name)
        # Serializes creation of a manual supplier identity, not every shop operation.
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:alias, 0))"), {"alias": alias})
        matches = conn.execute(select(db.aliases.c.supplier_id).where(db.aliases.c.alias_key == alias)).scalars().all()
        if len(matches) > 1:
            raise RuleError("Supplier alias is ambiguous; choose a confirmed supplier", 422)
        supplier_id = matches[0] if matches else identifier()
        if not matches:
            conn.execute(db.suppliers.insert().values(id=supplier_id, name=name))
            conn.execute(db.aliases.insert().values(supplier_id=supplier_id, alias_key=alias, confirmed_by=actor))
    if not conn.execute(select(db.suppliers.c.id).where(db.suppliers.c.id == supplier_id)).first():
        raise RuleError("Supplier not found", 404)
    inv = required(data["invoice_number"], "Invoice number")
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["invoice_date"]):
            raise ValueError()
        day = date.fromisoformat(data["invoice_date"])
    except (TypeError, ValueError):
        raise RuleError("Invoice date must be YYYY-MM-DD", 422)
    year = day.year if day.month >= 4 else day.year - 1
    fy = f"{year}-{year + 1}"
    check_lines(data["lines"])
    tx = store.document(conn, "purchase", {"supplier": name, "supplier_id": supplier_id, "invoice_number": inv,
        "invoice_date": day.isoformat(), "financial_year": fy, "purpose": "Incoming record; not a tax invoice",
        **({'order_review_id':review_id,'review_confirmed':True} if review_id else {}),
        **({'intake_evidence':data['intake_evidence']} if data.get('intake_evidence') else {})}, actor)
    conn.execute(db.purchase_headers.insert().values(id=tx, supplier_id=supplier_id, invoice_key=normalized(inv),
                 financial_year=fy, invoice_date=day.isoformat(), source_file_id=data.get("source_file_id")))
    for line in data["lines"]:
        p = get_variant(conn, line["product_id"])
        if p["kind"] != "goods":
            raise RuleError("Services cannot be received as stock", 422)
        qty = integer(line["quantity"], "Ordered quantity", 1)
        unit = required(line["unit"], "Supplier unit")
        factor = 1 if unit == p["unit"] else p["conversions"].get(unit)
        if factor is None:
            raise RuleError(f"Confirm {unit}-to-{p['unit']} conversion for {p['sku']}", 422)
        store.line(conn, tx, p, integer(qty * factor, "Base quantity", 1), price=integer(line.get("cost_paise", 0), "Cost"),
                   extra={"ordered_quantity": qty, "ordered_unit": unit, "factor": factor, "cost_basis": "per ordered supplier unit"})
    return tx


def receipt(store, conn, data, actor, key):
    store.source(conn, data["purchase_id"], "purchase")
    if data.get("confirmed") is not True:
        raise RuleError("Confirm physical receipt explicitly", 422)
    check_lines(data["lines"])
    source_ids = [l["purchase_line_id"] for l in data["lines"]]
    if len(set(source_ids)) != len(source_ids):
        raise RuleError("Use one count row per purchase line", 422)
    source = {r["id"]: r for r in conn.execute(select(db.lines).where(db.lines.c.id.in_(sorted(source_ids)),
              db.lines.c.transaction_id == data["purchase_id"]).order_by(db.lines.c.id).with_for_update()).mappings()}
    if len(source) != len(source_ids):
        raise RuleError("Purchase line does not belong to this bill", 422)
    location = data.get("location_id", db.LOCATION_ID)
    lock_balances(conn, [r["product_id"] for r in source.values()], location)
    tx = store.document(conn, "receipt", {"confirmed": True, "location_id": location}, actor, data["purchase_id"])
    conn.execute(db.receipt_headers.insert().values(id=tx, purchase_id=data["purchase_id"], location_id=location, confirmed_by=actor))
    for count in data["lines"]:
        s = source[count["purchase_line_id"]]
        accepted = integer(count["accepted"], "Accepted")
        damaged = integer(count.get("damaged", 0), "Damaged")
        quarantine = integer(count.get("quarantined", 0), "Quarantined")
        qty = integer(accepted + damaged + quarantine, "Received", 1)
        if qty + store.linked(conn, s["id"], "receipt") > s["quantity"]:
            raise RuleError("Receipt exceeds outstanding quantity")
        p = get_variant(conn, s["product_id"])
        line = store.line(conn, tx, p, qty, damaged, quarantine, parent=s["id"])
        move(conn, tx, line, p["id"], location, accepted, damaged, quarantine, actor, key)
    return tx


def unbilled_receipt(store, conn, data, actor, key):
    """Partner-confirmed physical delivery; no invoice or tax claim is created."""
    if data.get('confirmed') is not True:
        raise RuleError('Confirm these goods physically arrived and were counted', 422)
    supplier = required(data['supplier'], 'Supplier / source')
    reference = required(data['reference'], 'Delivery reference')
    evidence = required(data['evidence'], 'Delivery evidence / reason no bill')
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', data['received_date']):
            raise ValueError()
        day = date.fromisoformat(data['received_date'])
    except (TypeError, ValueError):
        raise RuleError('Received date must be YYYY-MM-DD', 422)
    check_lines(data['lines'])
    ids = [l['product_id'] for l in data['lines']]
    if len(ids) != len(set(ids)):
        raise RuleError('Use one received-count row per exact product', 422)
    location = data.get('location_id', db.LOCATION_ID)
    lock_balances(conn, ids, location)
    tx = store.document(conn, 'receipt', {'source_type': 'without_bill', 'supplier': supplier,
        'reference': reference, 'received_date': day.isoformat(), 'evidence': evidence,
        'location_id': location, 'confirmed': True, 'tax_invoice': False}, actor)
    conn.execute(db.unbilled_receipts.insert().values(id=tx, supplier_key=normalized(supplier),
        reference_key=normalized(reference)))
    for count in data['lines']:
        p = get_variant(conn, count['product_id'])
        if p['kind'] != 'goods':
            raise RuleError('Only goods can be received; fitting is a service', 422)
        if count['unit'] != p['unit']:
            raise RuleError(f"Count {p['sku']} in its confirmed base unit: {p['unit']}", 422)
        accepted = integer(count['accepted'], 'Accepted')
        damaged = integer(count.get('damaged', 0), 'Damaged')
        quarantined = integer(count.get('quarantined', 0), 'On hold')
        quantity = integer(accepted + damaged + quarantined, 'Received', 1)
        cost = count.get('cost_paise')
        price = 0 if cost is None else integer(cost, 'Purchase cost')
        line = store.line(conn, tx, p, quantity, damaged, quarantined, price=price,
            extra={'cost_known': cost is not None, 'cost_basis': 'per base unit', 'source_type': 'without_bill'})
        move(conn, tx, line, p['id'], location, accepted, damaged, quarantined, actor, key)
    return tx
