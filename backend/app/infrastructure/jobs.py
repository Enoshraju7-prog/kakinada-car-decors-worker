"""Single small worker with persisted leases; no notification runs inside stock transactions."""
import asyncio
import time
from sqlalchemy import select, or_, text
from app.infrastructure import database as db
from app.ledger import now


def consume_outbox(engine):
    with engine.begin() as c:
        event=c.execute(select(db.outbox).where(db.outbox.c.status!='done',db.outbox.c.attempts<3,
            db.outbox.c.lease_until<int(time.time())).order_by(db.outbox.c.id).with_for_update(skip_locked=True).limit(1)).mappings().first()
        if not event:
            return False
        from sqlalchemy.dialects.postgresql import insert
        # First consumer is durable local event history only. No external sends are enabled.
        c.execute(insert(db.consumed).values(event_id=event['id'],consumer='local-history',created_at=now()).on_conflict_do_nothing())
        c.execute(db.outbox.update().where(db.outbox.c.id==event['id']).values(status='done',attempts=event['attempts']+1))
    return True


def tick(engine,agent_model=None,run_id=None):
    from app.agents.runtime import execute
    # The persisted lease enables recovery; a session advisory lock prevents a
    # still-alive slow worker being duplicated after its lease expires.
    with engine.connect() as owner:
        run=None
        with owner.begin():
            query=(select(db.runs).where(or_(db.runs.c.status=='pending',
                (db.runs.c.status=='running') & (db.runs.c.lease_until<int(time.time()))))
                .order_by(db.runs.c.created_at).with_for_update(skip_locked=True).limit(16))
            if run_id:query=query.where(db.runs.c.id==run_id)
            for candidate in owner.execute(query).mappings():
                locked=owner.execute(text('SELECT pg_try_advisory_lock(hashtextextended(:id,0))'),{'id':candidate['id']}).scalar_one()
                if locked:
                    run=dict(candidate)
                    owner.execute(db.runs.update().where(db.runs.c.id==run['id']).values(status='running',lease_until=int(time.time())+300))
                    break
        if not run:return consume_outbox(engine)
        try:
            asyncio.run(execute(engine,run,agent_model))
        except Exception as exc:
            from app.ledger import RuleError
            message='Run budget exhausted; review saved evidence and start a new scoped goal if needed' if type(exc).__name__=='UsageLimitExceeded' else str(exc) if isinstance(exc,RuleError) else type(exc).__name__ + ': external execution failed; review configuration and retry safely'
            with engine.begin() as c:
                c.execute(db.runs.update().where(db.runs.c.id==run['id']).values(status='failed',error=message,lease_until=0))
        finally:
            owner.execute(text('SELECT pg_advisory_unlock(hashtextextended(:id,0))'),{'id':run['id']})
            owner.commit()
    return True


def main():
    engine=db.engine_for()
    print('KCD worker started. Application tools only; no external notifications.')
    while True:
        if not tick(engine):
            time.sleep(1)


if __name__=='__main__':
    main()

