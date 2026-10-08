"""Consistent local PostgreSQL backup and independent fresh-database restore verification."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone
from sqlalchemy import select,text
from app.infrastructure import database as db
from app.modules.inventory.service import reconcile
import psycopg
from psycopg import sql

ROOT=Path(__file__).resolve().parents[2]
BIN=Path(os.getenv('KCD_PG_BIN','/opt/homebrew/opt/postgresql@18/bin'))

def evidence(c):
    balances=[dict(r) for r in c.execute(select(db.balances).order_by(db.balances.c.variant_id,db.balances.c.location_id)).mappings()]
    ids={t.name:list(c.execute(select(t.c.id).order_by(t.c.id)).scalars()) for t in (db.variants,db.documents,db.lines,db.movements)}
    replay=[dict(r) for r in c.execute(select(db.requests).order_by(db.requests.c.key)).mappings()]
    return {'balances':balances,'identity_digest':hashlib.sha256(json.dumps(ids,sort_keys=True).encode()).hexdigest(),
            'replay_digest':hashlib.sha256(json.dumps(replay,sort_keys=True).encode()).hexdigest(),
            'counts':{k:len(v) for k,v in ids.items()},'reconciliation':reconcile(c)}

def connection_args(url):
    if url.host!='127.0.0.1' or url.port!=5433 or not url.database.startswith('kcd_'):
        raise RuntimeError('This local runbook supports only the dedicated loopback project cluster')
    return ['-h',url.host,'-p',str(url.port),'-U',url.username,'-d',url.database]

def backup(engine):
    folder=ROOT/'backups';folder.mkdir(exist_ok=True)
    path=folder/(engine.url.database+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.dump')
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as c,c.begin():
        snapshot=c.execute(text('SELECT pg_export_snapshot()')).scalar_one()
        expected=evidence(c)
        subprocess.run([str(BIN/'pg_dump'),*connection_args(engine.url),'--format=custom','--snapshot',snapshot,'--file',str(path)],env={**os.environ,'PGPASSWORD':engine.url.password},check=True)
    path.chmod(0o600)
    manifest=path.with_suffix('.json');manifest.write_text(json.dumps({'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'evidence':expected},indent=2));manifest.chmod(0o600)
    return path

def verify_restore(path,engine):
    manifest=json.loads(path.with_suffix('.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['sha256']:raise RuntimeError('Backup checksum differs')
    access=json.loads((ROOT/'data/database-access.json').read_text())
    name='kcd_restore_'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')
    with psycopg.connect(host='127.0.0.1',port=5433,user='kcd_admin',password=access['admin'],dbname='postgres',autocommit=True) as c:
        c.execute(sql.SQL('CREATE DATABASE {} OWNER kcd_app').format(sql.Identifier(name)))
    target=engine.url.set(database=name)
    subprocess.run([str(BIN/'pg_restore'),*connection_args(target),'--no-owner','--exit-on-error',str(path)],env={**os.environ,'PGPASSWORD':target.password},check=True)
    restored=db.engine_for(target.render_as_string(hide_password=False))
    with restored.connect() as c:actual=evidence(c)
    restored.dispose()
    if actual!=manifest['evidence']:raise RuntimeError('Restored identities/replay records/balances differ; original DB remains unchanged')
    return {'database':name,'verified':True,**actual}

if __name__=='__main__':
    engine=db.engine_for()
    path=Path(sys.argv[1]) if len(sys.argv)>1 else backup(engine)
    result=verify_restore(path,engine)
    result['backup']=str(path)
    (ROOT/'artifacts/restore-verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2));engine.dispose()
