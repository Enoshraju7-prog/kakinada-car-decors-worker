"""Disposable local partner review. Never imports or resets real shop data."""
import json
import os
from pathlib import Path
import psycopg
from psycopg import sql
from alembic import command
from alembic.config import Config
from app.infrastructure import database as db
from app.infrastructure.auth import create_user
from app.workflows.posting import Store
from sqlalchemy import select

ROOT=Path(__file__).resolve().parents[2]
NAME='kcd_partner_review'
NAMES=['Synthetic Alto left mirror','Synthetic Swift right mirror','Synthetic K10 left mirror',
       'Synthetic Bolero right mirror','Synthetic wiper 16 inch','Synthetic wiper 18 inch',
       'Synthetic car charger','Synthetic cleaning cloth','Synthetic car perfume','Synthetic steering cover']

def engine():
    base=db.engine_for()
    url=base.url.set(database=NAME).render_as_string(hide_password=False)
    base.dispose()
    return db.engine_for(url)

def setup():
    access=json.loads((ROOT/'data/database-access.json').read_text())
    with psycopg.connect(host='127.0.0.1',port=5433,user='kcd_admin',password=access['admin'],dbname='postgres',autocommit=True) as c:
        if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(NAME,)).fetchone():
            c.execute(sql.SQL('CREATE DATABASE {} OWNER kcd_app').format(sql.Identifier(NAME)))
    e=engine()
    os.environ['KCD_DATABASE_URL']=e.url.render_as_string(hide_password=False)
    command.upgrade(Config(str(ROOT/'backend/alembic.ini')),'head')
    with e.connect() as c:
        exists=c.execute(select(db.users.c.id).where(db.users.c.username=='partner')).first()
    if not exists:create_user(e,'partner',access['partner'],'partner')
    # Leave the catalogue empty so Add Item can be tested from a fresh shop.
    e.dispose()
    print('Partner review ready on its own local database; real shop preserved.')

if __name__=='__main__':setup()

def serve():
    import uvicorn
    from app.main import create_app
    uvicorn.run(create_app(engine(),mode='demo'),host='127.0.0.1',port=8002)

def seed_remaining():
    """Add nine synthetic ordered parts after the first UI receipt of 25."""
    e=engine()
    assert e.url.database==NAME
    store=Store(e)
    first=next((p for p in store.state()['products'] if p['name']==NAMES[0]),None)
    if not first or first['available']!=25:raise RuntimeError('Complete the first UI delivery of 25 before seeding the other nine')
    ids=[first['id']]
    for i,name in enumerate(NAMES[1:],2):
        ids.append(store.post('product',dict(sku=f'REVIEW-{i:02}',name=name,category='Demo accessories',family_name='Demo accessories',
            kind='goods',unit='piece',price_paise=20000,purchase_price_paise=10000),f'review-fixture-part-{i}','partner')['id'])
    bill=store.post('purchase',dict(supplier='Synthetic billed vendor',invoice_number='REVIEW-25-EACH',invoice_date='2026-10-07',
         lines=[dict(product_id=pid,quantity=25,unit='piece',cost_paise=10000) for pid in ids[1:]]),'review-fixture-bill','partner')
    metadata={'database':NAME,'product_ids':ids,'bill_id':bill['id'],'names':NAMES}
    (ROOT/'data/partner-review.json').write_text(json.dumps(metadata))
    e.dispose()
    print('10 synthetic types: 25 received without bill; 225 incoming on the synthetic bill. Confirm the remaining delivery in the browser.')
