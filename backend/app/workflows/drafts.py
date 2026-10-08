import hashlib
import json
from sqlalchemy import select
from app.infrastructure import database as db
from app.infrastructure.auth import require_partner
from app.ledger import RuleError, identifier, now


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def create_draft(engine, kind, payload, actor, draft_id=None):
    if kind not in {"purchase", "receipt", "intake"}:
        raise RuleError("Unsupported draft kind", 422)
    row = dict(id=draft_id or identifier(), kind=kind, payload=payload, version=1, status="pending", actor=actor, created_at=now())
    from sqlalchemy.dialects.postgresql import insert
    with engine.begin() as conn:
        created = conn.execute(insert(db.drafts).values(**row).on_conflict_do_nothing().returning(db.drafts.c.id)).first()
        if not created:
            old = dict(conn.execute(select(db.drafts).where(db.drafts.c.id == row["id"])).mappings().one())
            if old["kind"] != kind or old["payload"] != payload or old["actor"] != actor:
                raise RuleError("Draft identity is already used for different details")
            return old
    return row


def approve(engine, draft_id, version, user):
    require_partner(user)
    with engine.begin() as conn:
        draft = conn.execute(select(db.drafts).where(db.drafts.c.id == draft_id).with_for_update()).mappings().first()
        if not draft or draft["version"] != version or draft["status"] not in {"pending", "approved"}:
            raise RuleError("Draft changed or is already posted; reload before approving")
        if draft['kind'] == 'intake':
            from app.modules.purchasing.intake import ready
            ready(draft['payload'])
        conn.execute(db.drafts.update().where(db.drafts.c.id == draft_id).values(status="approved",
                     approved_by=user["username"], approved_hash=payload_hash(draft["payload"])))
        conn.execute(db.audit.insert().values(id=identifier(), actor=user["username"], event="approve_draft",
                     source_id=draft_id, created_at=now(), data={"version": version, "hash": payload_hash(draft["payload"])}))


def post_draft(store, conn, payload, actor, key):
    draft = conn.execute(select(db.drafts).where(db.drafts.c.id == payload["id"]).with_for_update()).mappings().first()
    if not draft or draft["version"] != payload["version"]:
        raise RuleError("Draft version changed")
    if draft["status"] == "posted":
        return store.read_transaction(conn, draft["posted_id"])
    if draft["status"] != "approved" or draft["approved_hash"] != payload_hash(draft["payload"]):
        raise RuleError("A partner must approve these exact draft details", 403)
    result = store.execute(conn, draft["kind"], draft["payload"], draft["approved_by"], key)
    conn.execute(db.drafts.update().where(db.drafts.c.id == draft["id"]).values(status="posted", posted_id=result["id"]))
    return result


def edit(engine, draft_id, version, payload, user):
    with engine.begin() as conn:
        draft=conn.execute(select(db.drafts).where(db.drafts.c.id==draft_id).with_for_update()).mappings().first()
        if not draft or draft['version']!=version or draft['status']=='posted':
            raise RuleError('Draft changed or is already posted; reload before editing')
        if user['role']!='partner' and (draft['kind']!='receipt' or draft['actor']!=user['username']):
            raise RuleError('You may edit only your receipt counts',403)
        conn.execute(db.drafts.update().where(db.drafts.c.id==draft_id).values(payload=payload,version=version+1,
                     status='pending',approved_by=None,approved_hash=None))
        conn.execute(db.audit.insert().values(id=identifier(),actor=user['username'],event='edit_draft',source_id=draft_id,
                     created_at=now(),data={'version':version+1,'hash':payload_hash(payload)}))
    return {'id':draft_id,'version':version+1}
