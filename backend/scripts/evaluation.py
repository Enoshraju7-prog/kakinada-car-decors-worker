"""Isolated generated-fixture evaluation; never connects to a shop/demo ledger.
The scoped worker accepts only the exact generated goals/files below.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from sqlalchemy import select
from app.infrastructure import database as db
from app.ledger import now

ROOT=Path(__file__).resolve().parents[2]
NAME='kcd_evaluation_oct5'
GOALS={
 'invoice':'Process the attached generated evaluation bill. Match its printed SKU and unit to the catalogue, check duplicates, prepare its purchase draft, request partner approval, then post and read it back. Do not receive goods from the bill alone.',
 'shortage':'Inspect the generated evaluation inventory for exact-SKU shortages, save a shortage report and read it back.',
 'ambiguous':'Prepare a purchase for the generated evaluation supplier, invoice EVAL-AMBIGUOUS-001 dated 2026-10-05, one Generated mat at INR 100 per set. The variant is unknown. Ask for the exact SKU rather than guessing; do not post.',
 'receipt':'For the generated evaluation bill EVAL-BILL-001, prepare a physical receipt of 8 accepted, 1 damaged and 0 quarantined pieces of EVAL-GENERATED-001. These are explicitly supplied generated physical counts. Request partner approval, post once, and verify the saved receipt and stock.',
}
NOTES={
 'Use the printed exact SKU EVAL-GENERATED-001, 10 piece at INR 100 each from the generated bill. Recheck the catalogue and continue; do not infer receipt.',
 'The confirmed exact SKU is EVAL-MAT-5D. Use one set at INR 100, prepare the draft, and stop before posting.',
 'The reviewed purchase draft is version 2. Read the saved draft and request approval for this version before posting.',
}
PRODUCTS=[
 {'sku':'EVAL-GENERATED-001','name':'Generated evaluation widget','category':'Generated fixtures','brand':'Generated','kind':'goods','unit':'piece','threshold':3,'price_paise':20000},
 {'sku':'EVAL-MAT-5D','name':'Generated mat 5D','category':'Generated fixtures','brand':'Generated','kind':'goods','unit':'set','threshold':1,'price_paise':10000},
 {'sku':'EVAL-MAT-7D','name':'Generated mat 7D','category':'Generated fixtures','brand':'Generated','kind':'goods','unit':'set','threshold':1,'price_paise':10000},
 {'sku':'EVAL-FITTING','name':'Generated fitting','category':'Generated services','brand':'Generated','kind':'service','unit':'service','threshold':0,'price_paise':30000},
]

def engine():
    url=db.engine_for().url.set(database=NAME).render_as_string(hide_password=False)
    return db.engine_for(url)

def setup():
    import psycopg
    from psycopg import sql
    access=json.loads((ROOT/'data/database-access.json').read_text())
    with psycopg.connect(host='127.0.0.1',port=5433,user='kcd_admin',password=access['admin'],dbname='postgres',autocommit=True,connect_timeout=5) as c:
        if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(NAME,)).fetchone():
            c.execute(sql.SQL('CREATE DATABASE {} OWNER kcd_app').format(sql.Identifier(NAME)))
    e=engine()
    subprocess.run([str(ROOT/'backend/.venv/bin/alembic'),'upgrade','head'],cwd=ROOT/'backend',env={**os.environ,'KCD_DATABASE_URL':e.url.render_as_string(hide_password=False)},check=True)
    from app.workflows.posting import Store
    from app.infrastructure.auth import create_user
    for p in PRODUCTS:Store(e).post('product',p,'generated-fixture:'+p['sku'],'evaluation-script')
    for user in ('partner','staff'):
        with e.connect() as c:exists=c.execute(select(db.users.c.id).where(db.users.c.username==user)).first()
        if not exists:create_user(e,user,access[user],user)
    print('Isolated generated evaluation database ready; existing shop/demo preserved.')
    e.dispose()

def guard(e,run_id):
    if e.url.database!=NAME:raise RuntimeError('Evaluation database required')
    with e.connect() as c:
        expected={p['sku']:p for p in PRODUCTS}
        from app.modules.catalog.service import get_variant
        for row in c.execute(select(db.variants)).mappings():
            p=get_variant(c,row['id']);p['threshold']=c.execute(select(db.policies.c.threshold).where(db.policies.c.variant_id==row['id'],db.policies.c.location_id==db.LOCATION_ID)).scalar() or 0;fixture=expected.get(p['sku'])
            if not fixture or any(p[k]!=v for k,v in fixture.items()):raise RuntimeError('Unexpected catalogue data; no provider call made')
        allowed_hashes={hashlib.sha256((ROOT/'output/pdf/generated-evaluation-bill.pdf').read_bytes()).hexdigest()}
        for f in c.execute(select(db.files)).mappings():
            if f['sha256'] not in allowed_hashes or hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()!=f['sha256']:
                raise RuntimeError('Only the explicitly generated PDF is allowed')
        run=c.execute(select(db.runs).where(db.runs.c.id==run_id)).mappings().one()
        if run['goal'] not in GOALS.values():raise RuntimeError('Scoped evaluation accepts only the literal generated goals')
        from app.workflows.runs import clarifications
        if any(n['message'] not in NOTES for n in clarifications(c,run_id)):
            raise RuntimeError('Only literal generated clarification notes are allowed')
        # Every prior source must be generated by this fixture or the controlled browser checks.
        for d in c.execute(select(db.documents)).mappings():
            if d['kind']=='purchase' and (d['data'].get('supplier')!='GENERATED EVALUATION SUPPLIER' or not d['data'].get('invoice_number','').startswith('EVAL-')):
                raise RuntimeError('Unexpected purchase data; no provider call made')
    return run

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['setup','api','work']);parser.add_argument('run_id',nargs='?');args=parser.parse_args()
    if args.action=='setup':setup();return
    e=engine()
    if args.action=='api':
        os.environ['KCD_DATABASE_URL']=e.url.render_as_string(hide_password=False)
        os.environ['KCD_MODE']='demo'
        import uvicorn
        uvicorn.run('app.main:app',host='127.0.0.1',port=8001)
    else:
        if not args.run_id:parser.error('work requires a single run ID')
        guard(e,args.run_id)
        from app.infrastructure.jobs import tick
        tick(e,run_id=args.run_id)
        with e.connect() as c:
            r=c.execute(select(db.runs).where(db.runs.c.id==args.run_id)).mappings().one()
            print(json.dumps({k:r[k] for k in ('id','status','requests_used','tools_used','error','evidence')},indent=2))
    e.dispose()

if __name__=='__main__':main()
