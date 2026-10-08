"""Persisted human clarifications; they cannot grant posting authority."""
import uuid
from sqlalchemy import select
from app.infrastructure import database as db
from app.infrastructure.auth import require_partner
from app.ledger import RuleError,now,required


def clarify(engine,run_id,message,key,user):
    require_partner(user)
    message=message.strip()
    if not message or len(message)>2000:raise RuleError('Clarification is required (up to 2000 characters)',422)
    event_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'run-clarification:'+run_id+':'+user['username']+':'+key))
    with engine.begin() as c:
        run=c.execute(select(db.runs).where(db.runs.c.id==run_id).with_for_update()).mappings().first()
        prior=c.execute(select(db.audit).where(db.audit.c.id==event_id)).mappings().first()
        if prior:
            if prior['data']['message']!=message:
                raise RuleError('This clarification key belongs to different details')
            return {'id':run_id,'status':run['status']}
        if not run or run['status'] not in {'needs_clarification','waiting_approval','failed'}:
            raise RuleError('Run is not waiting for clarification or recovery')
        if run['requests_used']>=10 or run['tools_used']>=20:
            raise RuleError('Run budget exhausted; start a new explicitly scoped goal',422)
        # Archive the conversation and requested approvals before a new planning attempt.
        c.execute(db.audit.insert().values(id=event_id,actor=user['username'],event='clarify_run',source_id=run_id,
            created_at=now(),data={'message':message,'previous_status':run['status'],'messages':run['messages'],'evidence':run['evidence']}))
        c.execute(db.runs.update().where(db.runs.c.id==run_id).values(status='pending',evidence=None,error=None,lease_until=0))
    return {'id':run_id,'status':'pending'}


def clarifications(c,run_id):
    return [{'actor':x['actor'],'message':x['data']['message'],'created_at':x['created_at']} for x in c.execute(
        select(db.audit).where(db.audit.c.event=='clarify_run',db.audit.c.source_id==run_id).order_by(db.audit.c.created_at)).mappings()]
