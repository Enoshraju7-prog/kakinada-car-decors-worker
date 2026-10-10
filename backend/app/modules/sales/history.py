"""Read-only sales history. Customer contacts never enter model tool results."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import DateTime, cast, select
from app.infrastructure import database as db
from app.ledger import RuleError


def sales_history(conn, start_date: date, end_date: date, sale_id: str | None = None, offset: int = 0):
    if end_date < start_date or (end_date - start_date).days > 365:
        raise RuleError('Choose an ordered date range of at most 366 days', 422)
    if offset < 0 or offset > 1000000:
        raise RuleError('Invalid sales history offset', 422)
    zone = ZoneInfo('Asia/Kolkata')
    lower = datetime.combine(start_date, time.min, zone).astimezone(timezone.utc)
    upper = datetime.combine(end_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    # Imported timestamps can carry different UTC offsets. Compare instants, not text.
    timestamp = cast(db.documents.c.created_at, DateTime(timezone=True))
    query = select(db.documents).where(db.documents.c.kind == 'sale', timestamp >= lower, timestamp < upper)
    if sale_id:
        query = query.where(db.documents.c.id == sale_id)
    sales = conn.execute(query.order_by(db.documents.c.sequence)).mappings().all()
    ids = [s['id'] for s in sales]
    voids = set(conn.execute(select(db.documents.c.parent_id).where(
        db.documents.c.kind == 'reversal', db.documents.c.parent_id.in_(ids))).scalars()) if ids else set()
    page = sales[offset:offset+50]
    page_ids = [s['id'] for s in page]
    customers = dict(conn.execute(select(db.customer_sales.c.id, db.customer_sales.c.customer_id)
                                 .where(db.customer_sales.c.id.in_(page_ids))).all()) if page_ids else {}
    receipts = dict(conn.execute(select(db.sale_receipts.c.id, db.sale_receipts.c.number)
                                .where(db.sale_receipts.c.id.in_(page_ids))).all()) if page_ids else {}
    items = {sid: [] for sid in page_ids}
    returned = {}
    if page_ids:
        reversals = db.documents.alias('return_reversals')
        for row in conn.execute(select(db.lines.c.parent_line_id, db.lines.c.quantity).join(
            db.documents, db.documents.c.id == db.lines.c.transaction_id).where(
            db.documents.c.kind == 'return', db.documents.c.parent_id.in_(page_ids),
            ~db.documents.c.id.in_(select(reversals.c.parent_id).where(
                reversals.c.kind == 'reversal', reversals.c.parent_id.is_not(None))))).mappings():
            returned[row['parent_line_id']] = returned.get(row['parent_line_id'], 0) + row['quantity']
        for line in conn.execute(select(db.lines).where(db.lines.c.transaction_id.in_(page_ids))
                                 .order_by(db.lines.c.sequence)).mappings():
            items[line['transaction_id']].append({'name': line['snapshot']['name'], 'sku': line['snapshot']['sku'],
                'unit': line['snapshot']['unit'], 'quantity': line['quantity'], 'rate_paise': line['price_paise'],
                'total_paise': line['quantity'] * line['price_paise'], 'returned_quantity': returned.get(line['id'], 0)})
    active = [s for s in sales if s['id'] not in voids]
    return {'kind': 'sales_history', 'timezone': 'Asia/Kolkata', 'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(), 'sale_id_filter': sale_id, 'offset': offset,
        'has_more': offset+50 < len(sales), 'next_offset': offset+50 if offset+50 < len(sales) else None,
        'sale_count': len(sales), 'void_count': len(voids),
        'recorded_sales_total_paise': sum(s['total_paise'] for s in active),
        'credit_sales_total_paise': sum(s['total_paise'] for s in active if s['data']['payment'] == 'credit'),
        'totals_note': 'Original sale totals excluding VOID sales; returns are shown per item. This is not net revenue or verified payment settlement.',
        'sales': [{'order_id': s['id'], 'receipt_number': receipts.get(s['id'], f"KCD-LEGACY-{s['sequence']:06d}"),
            'purchased_at_ist': datetime.fromisoformat(s['created_at'].replace('Z', '+00:00')).astimezone(zone).isoformat(),
            'customer_reference': customers.get(s['id']),
            'customer_type': 'Saved customer' if s['id'] in customers else 'Walk-in / customer not recorded',
            'status': 'VOID' if s['id'] in voids else 'recorded', 'payment': s['data']['payment'],
            'total_paise': s['total_paise'], 'items': items[s['id']]} for s in page]}
