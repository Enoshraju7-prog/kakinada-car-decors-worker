"""One application operation owns one transaction; API and agent share this boundary."""
import hashlib
import json
import time
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, OperationalError
from app.infrastructure import database as db
from app.modules.catalog import service as catalog
from app.modules.inventory import service as inventory
from app.ledger import RuleError, identifier, now, required


def fingerprint(operation, payload, actor):
    if operation == 'sale' and payload.get('customer'):
        from app.modules.sales.customers import phone_key
        # A keyed digest prevents offline guessing of contact details in retry records.
        return phone_key(json.dumps([operation, payload, actor], sort_keys=True, separators=(",", ":")))
    return hashlib.sha256(json.dumps([operation, payload, actor], sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Store:
    def __init__(self, engine=None):
        self.engine = engine or db.engine_for()

    def post(self, operation, payload, key, actor="local-pilot"):
        key = required(key, "Request key")
        digest = fingerprint(operation, payload, actor)
        for attempt in range(3):
            try:
                with self.engine.begin() as conn:
                    claimed = conn.execute(insert(db.requests).values(key=key, fingerprint=digest, actor=actor)
                                           .on_conflict_do_nothing().returning(db.requests.c.key)).first()
                    if not claimed:
                        old = conn.execute(select(db.requests).where(db.requests.c.key == key)).mappings().one()
                        expected = fingerprint(operation, payload, "local-pilot") if old["legacy"] else digest
                        if old["fingerprint"] != expected:
                            raise RuleError("This request key belongs to different details or another actor")
                        return old["response"]
                    result = self.execute(conn, operation, payload, actor, key)
                    conn.execute(db.audit.insert().values(id=identifier(), actor=actor, event=operation,
                                 source_id=result["id"], created_at=now(), data={"operation_id": key, **({"before": result["before"], "price_paise": result["price_paise"], "purchase_price_paise": result["purchase_price_paise"]} if operation == "prices" else {})}))
                    conn.execute(db.outbox.insert().values(id=identifier(), event=operation, source_id=result["id"], payload={"id": result["id"]}))
                    conn.execute(db.requests.update().where(db.requests.c.key == key).values(response=result))
                return result
            except IntegrityError as exc:
                raise RuleError("Duplicate SKU/bill, invalid source, or invalid quantities") from exc
            except OperationalError as exc:
                code = getattr(exc.orig, "sqlstate", None)
                if code not in {"40001", "40P01", "55P03"} or attempt == 2:
                    raise RuleError("Storage success is unconfirmed; retry the same operation key", 503) from exc
                time.sleep(0.05 * (attempt + 1))

    def execute(self, conn, operation, payload, actor, key):
        if operation == 'agent_run':
            for file_id in payload['attachments']:
                if not conn.execute(select(db.files.c.id).where(db.files.c.id==file_id)).first():
                    raise RuleError('Attachment not found',404)
            goal=payload['goal'].strip()
            if not goal or len(goal)>2000:raise RuleError('Goal is required (up to 2000 characters)',422)
            run_id=identifier()
            conn.execute(db.runs.insert().values(id=run_id,goal=goal,attachments=payload['attachments'],actor=actor,created_at=now()))
            return {'id':run_id}
        from app.workflows.drafts import post_draft
        if operation == "post_draft":
            return post_draft(self, conn, payload, actor, key)
        if operation == 'intake':
            from app.modules.purchasing.intake import post
            return self.read_transaction(conn, post(self, conn, payload, actor, key))
        from app.modules.purchasing.service import purchase, receipt, unbilled_receipt
        from app.modules.sales.service import sale, stock_return, adjustment, reverse
        handlers = {"purchase": purchase, "receipt": receipt, "sale": sale, "return": stock_return,
                    "adjustment": adjustment, "reversal": reverse, "unbilled_receipt": unbilled_receipt}
        if operation == "product":
            return catalog.legacy_product(conn, payload, actor)
        if operation == "category":
            return catalog.category(conn, payload)
        if operation == "family":
            return catalog.product(conn, payload)
        if operation == "variant":
            return catalog.variant(conn, payload, actor)
        if operation == 'prices':
            return catalog.prices(conn, payload)
        tx = handlers[operation](self, conn, payload, actor, key)
        return self.read_transaction(conn, tx)

    def document(self, conn, kind, data, actor, parent=None, total=0, tx_id=None):
        tx = tx_id or identifier()
        conn.execute(db.documents.insert().values(id=tx, kind=kind, parent_id=parent, actor=actor,
                     created_at=now(), data=data, total_paise=total))
        return tx

    def line(self, conn, tx, product, quantity, damaged=0, quarantined=0, price=0, parent=None, extra=None):
        line = identifier()
        snapshot = {"sku": product["sku"], "name": product["name"], "unit": product["unit"],
                    "kind": product["kind"], **(extra or {})}
        conn.execute(db.lines.insert().values(id=line, transaction_id=tx, product_id=product["id"],
                     parent_line_id=parent, quantity=quantity, damaged=damaged, quarantined=quarantined,
                     price_paise=price, snapshot=snapshot))
        return line

    def source(self, conn, source_id, kind):
        row = conn.execute(select(db.documents).where(db.documents.c.id == source_id).with_for_update()).mappings().first()
        if not row or row["kind"] != kind:
            raise RuleError(f"Expected a valid {kind} source", 422)
        if conn.execute(select(db.documents.c.id).where(db.documents.c.kind == "reversal", db.documents.c.parent_id == source_id)).first():
            raise RuleError("This source has been reversed")
        return row

    def linked(self, conn, line_id, kind):
        reversed_ids = select(db.documents.c.parent_id).where(db.documents.c.kind == "reversal")
        return int(conn.execute(select(func.coalesce(func.sum(db.lines.c.quantity), 0)).join(db.documents).where(
            db.lines.c.parent_line_id == line_id, db.documents.c.kind == kind,
            db.documents.c.id.not_in(reversed_ids))).scalar_one())

    def read_transaction(self, conn, tx):
        row = conn.execute(select(db.documents).where(db.documents.c.id == tx)).mappings().first()
        if not row:
            raise RuleError("Transaction not found", 404)
        result = dict(row)
        result["lines"] = [dict(x) for x in conn.execute(select(db.lines).where(db.lines.c.transaction_id == tx).order_by(db.lines.c.sequence)).mappings()]
        for line in result["lines"]:
            if row["kind"] == "purchase":
                line["received"] = self.linked(conn, line["id"], "receipt")
                line["outstanding"] = line["quantity"] - line["received"]
            if row["kind"] == "sale":
                line["returned"] = self.linked(conn, line["id"], "return")
        result["movements"] = [dict(x) for x in conn.execute(select(db.movements).where(db.movements.c.transaction_id == tx).order_by(db.movements.c.sequence)).mappings()]
        result["reversed"] = bool(conn.execute(select(db.documents.c.id).where(db.documents.c.kind == "reversal", db.documents.c.parent_id == tx)).first())
        return result

    def transaction(self, tx):
        with self.engine.connect() as conn:
            return self.read_transaction(conn, tx)

    def inventory(self, conn, location_id=db.LOCATION_ID, q='', offset=0, limit=None):
        # Aggregate receipts by their original purchase line, excluding reversals.
        reversed_ids=select(db.documents.c.parent_id).where(db.documents.c.kind=='reversal')
        received=select(db.lines.c.parent_line_id.label('source'),func.sum(db.lines.c.quantity).label('qty')).join(db.documents).where(
            db.documents.c.kind=='receipt',db.documents.c.id.not_in(reversed_ids)).group_by(db.lines.c.parent_line_id).subquery()
        incoming=select(db.lines.c.product_id.label('variant'),func.sum(db.lines.c.quantity-func.coalesce(received.c.qty,0)).label('qty'))            .select_from(db.lines.join(db.documents,db.lines.c.transaction_id==db.documents.c.id).outerjoin(received,received.c.source==db.lines.c.id))            .where(db.documents.c.kind=='purchase',db.documents.c.id.not_in(reversed_ids)).group_by(db.lines.c.product_id).subquery()
        joined=db.variants.join(db.products,db.variants.c.product_id==db.products.c.id).join(db.categories,db.products.c.category_id==db.categories.c.id)            .outerjoin(db.balances,(db.balances.c.variant_id==db.variants.c.id)&(db.balances.c.location_id==location_id))            .outerjoin(db.policies,(db.policies.c.variant_id==db.variants.c.id)&(db.policies.c.location_id==location_id)).outerjoin(incoming,incoming.c.variant==db.variants.c.id)
        query=select(db.variants,db.products.c.kind,db.products.c.brand,db.categories.c.name.label('category'),
            db.categories.c.threshold.label('category_threshold'),func.coalesce(db.policies.c.threshold,db.categories.c.threshold).label('threshold'),
            *[func.coalesce(db.balances.c[x],0).label(x) for x in ('available','damaged','quarantined')],
            func.coalesce(incoming.c.qty,0).label('incoming')).select_from(joined)
        if q:
            query=query.where(db.variants.c.sku.ilike('%'+q+'%')|db.variants.c.name.ilike('%'+q+'%'))
        total=conn.execute(select(func.count()).select_from(query.subquery())).scalar_one()
        query=query.order_by(db.variants.c.sku).offset(offset)
        if limit is not None:
            query=query.limit(limit)
        rows=[dict(r) for r in conn.execute(query).mappings()]
        ids=[r['id'] for r in rows]
        conversions={v:{} for v in ids}
        for v,u,f in conn.execute(select(db.conversions.c.variant_id,db.conversions.c.from_unit,db.conversions.c.factor).where(db.conversions.c.variant_id.in_(ids))):
            conversions[v][u]=f
        for r in rows:
            r['incoming']=int(r['incoming'])
            r['conversions']=conversions[r['id']]
            r['low_stock']=r['kind']=='goods' and r['available']<=r['threshold']
        return {'items':rows,'total':total}

    def incoming(self, conn, offset=0, limit=50):
        reversed_ids=select(db.documents.c.parent_id).where(db.documents.c.kind=='reversal')
        receipts=select(db.lines.c.parent_line_id.label('source'),func.sum(db.lines.c.quantity).label('qty')).join(db.documents).where(
            db.documents.c.kind=='receipt',db.documents.c.id.not_in(reversed_ids)).group_by(db.lines.c.parent_line_id).subquery()
        pending=select(db.documents.c.id,db.documents.c.sequence).select_from(db.documents.join(db.lines,db.lines.c.transaction_id==db.documents.c.id)
            .outerjoin(receipts,receipts.c.source==db.lines.c.id)).where(db.documents.c.kind=='purchase',db.documents.c.id.not_in(reversed_ids),
            db.lines.c.quantity>func.coalesce(receipts.c.qty,0)).distinct().subquery()
        count=conn.execute(select(func.count()).select_from(pending)).scalar_one()
        ids=conn.execute(select(pending.c.id).order_by(pending.c.sequence).offset(offset).limit(limit)).scalars().all()
        return {'items':[self.read_transaction(conn,x) for x in ids],'total':count}

    def state(self, location_id=db.LOCATION_ID, offset=0, limit=50):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn, conn.begin():
            product_rows=self.inventory(conn,location_id)['items']
            ids=conn.execute(select(db.documents.c.id).order_by(db.documents.c.sequence.desc()).offset(offset).limit(limit)).scalars().all()
            incoming=self.incoming(conn)
            from sqlalchemy import cast, Date, TIMESTAMP
            today=cast(func.timezone('Asia/Kolkata',func.now()),Date)
            date=cast(func.timezone('Asia/Kolkata',cast(db.documents.c.created_at,TIMESTAMP(timezone=True))),Date)
            sales=conn.execute(select(func.count().label('count'),func.coalesce(func.sum(db.documents.c.total_paise),0).label('total_paise'))
                .where(db.documents.c.kind=='sale',date==today)).mappings().one()
            return {'today_sales':dict(sales),'products':product_rows,'transactions':[self.read_transaction(conn,x) for x in ids],
                    'incoming_transactions':incoming['items'],'incoming_count':incoming['total'],
                    'movements':[dict(x) for x in conn.execute(select(db.movements).order_by(db.movements.c.sequence.desc()).limit(limit)).mappings()],
                    'transaction_count':conn.execute(select(func.count()).select_from(db.documents)).scalar(),
                    'offset':offset,'limit':limit,'location_id':location_id}
