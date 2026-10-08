"""Real provider check on a NEW isolated DB with only generated fixtures.
Does not query the imported demo database or the shop database.
"""
import json
import os
from pathlib import Path
import subprocess
from sqlalchemy import select,func
import psycopg
from psycopg import sql
from app.infrastructure import database as db
from app.infrastructure.auth import create_user
from app.infrastructure.jobs import tick
from app.workflows.posting import Store
from app.ledger import identifier,now

ROOT=Path(__file__).resolve().parents[2]
access=json.loads((ROOT/'data/database-access.json').read_text())
name='kcd_ai_evaluation'
with psycopg.connect(host='127.0.0.1',port=5433,user='kcd_admin',password=access['admin'],dbname='postgres',autocommit=True) as c:
    if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():
        c.execute(sql.SQL('CREATE DATABASE {} OWNER kcd_app').format(sql.Identifier(name)))
url=db.engine_for().url.set(database=name).render_as_string(hide_password=False)
subprocess.run([str(ROOT/'backend/.venv/bin/alembic'),'upgrade','head'],cwd=ROOT/'backend',env={**os.environ,'KCD_DATABASE_URL':url},check=True)
engine=db.engine_for(url)
# Reject unexpected records. This evaluation DB must contain only this script's fixture.
with engine.connect() as c:
    if c.execute(select(func.count()).select_from(db.variants).where(db.variants.c.sku!='EVAL-GENERATED-001')).scalar_one():
        raise RuntimeError('Unexpected data in evaluation database; no provider call was made')
    if c.execute(select(func.count()).select_from(db.documents)).scalar_one():
        raise RuntimeError('Evaluation must contain no business transaction records')
store=Store(engine)
store.post('product',{'sku':'EVAL-GENERATED-001','name':'Generated evaluation widget','category':'Generated evaluation category','kind':'goods','unit':'piece','threshold':3},'evaluation-fixture','evaluation-script')
with engine.connect() as c:
    exists=c.execute(select(db.users.c.id).where(db.users.c.username=='partner')).first()
if not exists:create_user(engine,'partner',access['partner'],'partner')
rid=identifier()
with engine.begin() as c:
    c.execute(db.runs.insert().values(id=rid,goal='Inspect current exact-SKU shortages, save a shortage report and read it back. Include the saved report ID in final evidence.',actor='partner',created_at=now()))
tick(engine)
with engine.connect() as c:
    run=dict(c.execute(select(db.runs).where(db.runs.c.id==rid)).mappings().one())
    tools=c.execute(select(db.steps.c.tool).where(db.steps.c.run_id==rid).order_by(db.steps.c.sequence)).scalars().all()
result={k:run[k] for k in ('id','status','requests_used','tools_used','error','evidence')}|{'tools':tools,'data_origin':'Only hard-coded generated widget above; no imported/demo/shop records queried'}
(ROOT/'artifacts').mkdir(exist_ok=True)
(ROOT/'artifacts/live-worker-check.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
engine.dispose()
