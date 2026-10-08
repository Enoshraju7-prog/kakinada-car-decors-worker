import concurrent.futures
import os
import threading
import unittest
from unittest.mock import patch
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, OperationalError
from fastapi.testclient import TestClient
from app.infrastructure import database as db
from app.infrastructure import auth
from app.workflows.posting import Store
from app.workflows import drafts
from app.modules.inventory.service import reconcile
from app.ledger import RuleError


class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.getenv('KCD_TEST_DATABASE_URL', '')
        if not url.endswith('/kcd_test'):
            raise RuntimeError('Tests require KCD_TEST_DATABASE_URL ending in /kcd_test')
        cls.engine = db.engine_for(url)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as c:
            tables = [t.name for t in db.metadata.sorted_tables if t.name not in {'units', 'locations'}]
            c.execute(text('TRUNCATE ' + ','.join(tables) + ' RESTART IDENTITY CASCADE'))
        self.store = Store(self.engine)
        self.i = 0
        self.pid = self.post('product', dict(sku='TEST',name='Synthetic',category='Mats',unit='piece',kind='goods',threshold=3,conversions={'pair':2}))['id']

    def post(self, op, data, key=None):
        self.i += 1
        return self.store.post(op, data, key or f'op-{self.i}')

    def bill(self, qty=10, **extra):
        return self.post('purchase', dict(supplier='Synthetic supplier',invoice_number='B-1',invoice_date='2026-10-04',
                         lines=[dict(product_id=self.pid,quantity=qty,unit='piece',cost_paise=500)], **extra))

    def receive(self, bill, qty, damaged=0, quarantined=0, key=None):
        return self.post('receipt', dict(purchase_id=bill['id'],confirmed=True,
                         lines=[dict(purchase_line_id=bill['lines'][0]['id'],accepted=qty,damaged=damaged,quarantined=quarantined)]), key)

    def sell(self, qty=1, key=None):
        return self.post('sale',dict(lines=[dict(product_id=self.pid,quantity=qty,price_paise=1000)]),key)

    def balance(self):
        return next(p for p in self.store.state()['products'] if p['id']==self.pid)

    def test_explicit_family_reused_without_merging_stock(self):
        a=self.post('product',dict(sku='FAMILY-A',name='Left mirror',family_name='Side mirrors',category='Mirrors',kind='goods',unit='piece',price_paise=1000))
        b=self.post('product',dict(sku='FAMILY-B',name='Right mirror',family_name=' side MIRRORS ',category='Mirrors',kind='goods',unit='piece',price_paise=2000))
        with self.engine.connect() as c:
            family_ids=list(c.execute(select(db.variants.c.product_id).where(db.variants.c.id.in_([a['id'],b['id']]))).scalars())
            self.assertEqual(len(set(family_ids)),1)
        self.assertNotEqual(a['id'],b['id'])
        self.assertEqual({p['available'] for p in self.store.state()['products'] if p['id'] in [a['id'],b['id']]},{0})

    def test_intake_approval_new_skus_incoming_only_and_duplicate_rollback(self):
        from app.modules.purchasing.intake import Intake
        payload=Intake(supplier='Synthetic intake vendor',invoice_number='AI-TEST-1',invoice_date='2026-10-08',source_note='Generated test',
            lines=[dict(description=name,name=name,family_name='Mirror glass',category='Mirrors',unit='piece',quantity=10,
                        cost_paise=10000,amount_paise=100000,selling_price_paise=20000) for name in ['Exact left glass','Exact right glass']]).model_dump()
        d=drafts.create_draft(self.engine,'intake',payload,'partner'); user={'role':'partner','username':'partner'}
        with self.assertRaises(RuleError):self.post('post_draft',dict(id=d['id'],version=1))
        drafts.approve(self.engine,d['id'],1,user)
        bill=self.post('post_draft',dict(id=d['id'],version=1),'intake-post')
        self.assertEqual(len(bill['lines']),2); self.assertEqual(bill['movements'],[])
        self.assertEqual(self.post('post_draft',dict(id=d['id'],version=1),'intake-post')['id'],bill['id'])
        ids=[l['product_id'] for l in bill['lines']]
        rows=[p for p in self.store.state()['products'] if p['id'] in ids]
        self.assertEqual([(p['available'],p['incoming']) for p in rows],[(0,10),(0,10)])
        with self.engine.connect() as c:
            self.assertEqual(len(set(c.execute(select(db.variants.c.product_id).where(db.variants.c.id.in_(ids))).scalars())),1)
        # A second draft with the same bill but different new names must roll back its catalogue writes too.
        duplicate={**payload,'lines':[{**l,'name':l['name']+' duplicate'} for l in payload['lines']]}
        d2=drafts.create_draft(self.engine,'intake',duplicate,'partner'); drafts.approve(self.engine,d2['id'],1,user)
        with self.assertRaises(RuleError):self.post('post_draft',dict(id=d2['id'],version=1))
        self.assertEqual(len(self.store.state()['products']),3)
        self.receive(bill,8); self.assertEqual(next(p for p in self.store.state()['products'] if p['id']==ids[0])['available'],8)

    def test_intake_unknowns_mismatch_and_stale_approval_blocked(self):
        from app.modules.purchasing.intake import Intake
        user={'role':'partner','username':'partner'}
        line=dict(description='Exact left mirror',name='Exact left mirror',family_name='Mirrors',category='Mirrors',unit='piece',
                  quantity=10,cost_paise=10000,amount_paise=100000,selling_price_paise=20000)
        for change in [{'unit':None},{'cost_paise':None},{'selling_price_paise':None},{'amount_paise':1},{'issues':['Confirm mixed variants']}]:
            p=Intake(supplier='Synthetic',invoice_number='INTAKE-UNCLEAR',invoice_date='2026-10-08',source_note='Generated',lines=[{**line,**change}]).model_dump()
            d=drafts.create_draft(self.engine,'intake',p,'partner')
            with self.assertRaises(RuleError):drafts.approve(self.engine,d['id'],1,user)
        p=Intake(supplier='Synthetic',invoice_number='INTAKE-OK',invoice_date='2026-10-08',source_note='Generated',lines=[line]).model_dump()
        d=drafts.create_draft(self.engine,'intake',p,'partner'); drafts.approve(self.engine,d['id'],1,user)
        drafts.edit(self.engine,d['id'],1,{**p,'invoice_number':'CHANGED'},user)
        with self.assertRaises(RuleError):self.post('post_draft',dict(id=d['id'],version=1))
        with self.assertRaises(RuleError):self.post('post_draft',dict(id=d['id'],version=2))
        self.assertEqual(len(self.store.state()['products']),1)

    def test_no_bill_posted_identity_is_immutable(self):
        receipt=self.post('unbilled_receipt',dict(supplier='Synthetic vendor',reference='IMMUTABLE-1',received_date='2026-10-07',
            evidence='Physically counted',confirmed=True,lines=[dict(product_id=self.pid,unit='piece',accepted=2,cost_paise=None)]))
        for statement in (db.unbilled_receipts.update().where(db.unbilled_receipts.c.id==receipt['id']).values(reference_key='changed'),
                          db.unbilled_receipts.delete().where(db.unbilled_receipts.c.id==receipt['id'])):
            with self.assertRaises(DBAPIError):
                with self.engine.begin() as c:c.execute(statement)
        self.assertEqual(self.balance()['available'],2)

    def test_no_bill_receiving_then_sale_replay_and_reconciliation(self):
        payload=dict(supplier='Synthetic no-bill vendor',reference='DEL-TEST-1',received_date='2026-10-07',
            evidence='Counted at shop; no bill supplied',confirmed=True,
            lines=[dict(product_id=self.pid,unit='piece',accepted=10,damaged=2,quarantined=1,cost_paise=None)])
        receipt=self.post('unbilled_receipt',payload,'no-bill-1')
        self.assertEqual(receipt['kind'],'receipt')
        self.assertEqual(receipt['data']['source_type'],'without_bill')
        self.assertFalse(receipt['data']['tax_invoice'])
        self.assertFalse(receipt['lines'][0]['snapshot']['cost_known'])
        self.assertEqual(self.post('unbilled_receipt',payload,'no-bill-1')['id'],receipt['id'])
        with self.assertRaises(RuleError):self.post('unbilled_receipt',payload,'different-key')
        self.sell(3)
        b=self.balance()
        self.assertEqual((b['available'],b['damaged'],b['quarantined'],b['incoming']),(7,2,1,0))
        restarted=Store(self.engine)
        self.assertEqual(restarted.transaction(receipt['id'])['movements'][0]['available_delta'],10)
        with self.engine.connect() as conn:
            self.assertTrue(reconcile(conn)['ok'])
            self.assertEqual(conn.execute(select(db.purchase_headers.c.id)).all(),[])

    def test_no_bill_rejects_unconfirmed_units_services_and_duplicate_rows(self):
        payload=dict(supplier='Synthetic',reference='NO-BILL',received_date='2026-10-07',evidence='Counted',confirmed=True,
            lines=[dict(product_id=self.pid,unit='piece',accepted=2,damaged=0,quarantined=0,cost_paise=500)])
        service=self.post('product',dict(sku='SERVICE',name='Fitting',category='Service',unit='service',kind='service'))['id']
        cases=[{**payload,'confirmed':False},{**payload,'received_date':'invalid'},
            {**payload,'lines':[dict(payload['lines'][0],unit='pair')]},
            {**payload,'lines':[dict(payload['lines'][0],product_id=service,unit='service')]},
            {**payload,'lines':payload['lines']*2}, {**payload,'lines':[dict(payload['lines'][0],accepted=0)]}]
        for case in cases:
            with self.assertRaises(RuleError):self.post('unbilled_receipt',case)
        self.assertEqual(self.balance()['available'],0)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(db.unbilled_receipts.c.id)).all(),[])

    def test_no_bill_partner_authorization_and_staff_cost_redaction(self):
        from app.main import create_app
        auth.create_user(self.engine,'staff','test-staff-password','staff')
        auth.create_user(self.engine,'partner','test-partner-password','partner')
        payload=dict(supplier='Synthetic',reference='NO-BILL-API',received_date='2026-10-07',evidence='Counted',confirmed=True,
            lines=[dict(product_id=self.pid,unit='piece',accepted=2,cost_paise=76543)])
        with TestClient(create_app(self.engine,'demo')) as client:
            staff=client.post('/api/auth/login',json=dict(username='staff',password='test-staff-password')).json()
            h={'X-CSRF-Token':staff['csrf'],'Idempotency-Key':'staff-no-bill'}
            self.assertEqual(client.post('/api/unbilled-receipts',json=payload,headers=h).status_code,403)
            partner=client.post('/api/auth/login',json=dict(username='partner',password='test-partner-password')).json()
            h={'X-CSRF-Token':partner['csrf'],'Idempotency-Key':'partner-no-bill'}
            response=client.post('/api/unbilled-receipts',json=payload,headers=h)
            self.assertEqual(response.status_code,200,response.text)
            tx=response.json()['id']
            client.post('/api/auth/login',json=dict(username='staff',password='test-staff-password'))
            for path in ['/api/state',f'/api/transactions/{tx}']:
                response=client.get(path)
                self.assertEqual(response.status_code,200,response.text)
                self.assertNotIn('76543',response.text)
                self.assertNotIn('cost_basis',response.text)

    def test_reviewed_order_partial_arrival_and_replay(self):
        import uuid
        from app.main import create_app
        from app.modules.purchasing.reviews import import_review
        rid=str(uuid.uuid4())
        payload=dict(supplier='Synthetic reviewed supplier',invoice_number='ARRIVAL-1',order_date='2026-10-06',buyer_gstin='UNCONFIRMED',subtotal_paise=10000,igst_paise=1800,total_paise=11800,
            lines=[dict(description='Exact item awaiting confirmation',amount_paise=10000,quantity_candidate=10)],unresolved=['Confirm variant and unit'])
        import_review(self.engine,rid,payload,'partner')
        data=dict(supplier=payload['supplier'],invoice_number=payload['invoice_number'],invoice_date='2026-10-06',order_review_id=rid,review_confirmed=True,
            lines=[dict(source_index=0,product_id=self.pid,quantity=10,unit='piece',cost_paise=1000)])
        with self.assertRaises(RuleError):self.post('purchase',{**data,'review_confirmed':False})
        with self.assertRaises(RuleError):self.post('purchase',{**data,'lines':[{**data['lines'][0],'cost_paise':1}]})
        bill=self.post('purchase',data,key='review-arrival')
        self.assertEqual(self.post('purchase',data,key='review-arrival')['id'],bill['id'])
        with self.assertRaises(RuleError):self.post('purchase',data,key='other-arrival')
        self.assertEqual(self.balance()['available'],0)
        self.assertEqual(self.balance()['incoming'],10)
        auth.create_user(self.engine,'partner','test-partner-password','partner')
        with TestClient(create_app(self.engine,'demo')) as client:
            client.post('/api/auth/login',json=dict(username='partner',password='test-partner-password'))
            review=client.get('/api/state').json()['order_reviews'][0]
            self.assertEqual(review['delivery_status'],'ready_to_count')
            self.assertEqual(review['purchase_id'],bill['id'])
            self.receive(bill,8,key='partial-delivery')
            self.receive(bill,8,key='partial-delivery')
            self.assertEqual(client.get('/api/state').json()['order_reviews'][0]['delivery_status'],'part_received')
            self.receive(bill,2)
            self.assertEqual(client.get('/api/state').json()['order_reviews'][0]['delivery_status'],'received')
        self.assertEqual(self.balance()['available'],10)
        with self.engine.connect() as c:self.assertTrue(reconcile(c)['ok'])

    def test_partner_prices_redaction_and_sale_snapshot(self):
        from app.main import create_app
        self.store.post('prices', dict(id=self.pid, price_paise=1000, purchase_price_paise=500,
            expected_price_paise=0, expected_purchase_price_paise=None), 'price-initial', 'partner')
        self.receive(self.bill(10),10)
        auth.create_user(self.engine,'staff','test-staff-password','staff')
        auth.create_user(self.engine,'partner','test-partner-password','partner')
        with TestClient(create_app(self.engine,'demo')) as client:
            user=client.post('/api/auth/login',json=dict(username='staff',password='test-staff-password')).json()
            headers={'X-CSRF-Token':user['csrf'],'Idempotency-Key':'staff-price'}
            for url in ['/api/state','/api/v1/inventory/balances','/api/v1/catalog/variants',f'/api/v1/catalog/variants/{self.pid}']:
                response=client.get(url)
                self.assertEqual(response.status_code,200,response.text)
                self.assertNotIn('purchase_price_paise',response.text)
            bad=dict(lines=[dict(product_id=self.pid,quantity=1,price_paise=1)])
            self.assertEqual(client.post('/api/sales',json=bad,headers=headers).status_code,403)
            self.assertEqual(self.balance()['available'],10)
            good=dict(lines=[dict(product_id=self.pid,quantity=1,price_paise=1000)])
            sale=client.post('/api/sales',json=good,headers=headers).json()
            self.assertEqual(client.post('/api/sales',json=good,headers=headers).json()['id'],sale['id'])
            self.assertEqual(self.balance()['available'],9)
            price=dict(id=self.pid,price_paise=1200,purchase_price_paise=550,expected_price_paise=1000,expected_purchase_price_paise=500)
            self.assertEqual(client.post('/api/prices',json=price,headers={**headers,'Idempotency-Key':'staff-price-edit'}).status_code,403)
            self.assertEqual(client.get('/api/partner-alerts').status_code,403)
            self.assertEqual(client.patch(f"/api/transactions/{sale['id']}",json=good,headers=headers).status_code,405)
            client.cookies.clear()
            user=client.post('/api/auth/login',json=dict(username='partner',password='test-partner-password')).json()
            headers={'X-CSRF-Token':user['csrf'],'Idempotency-Key':'partner-price-edit'}
            self.assertEqual(client.post('/api/prices',json=price,headers=headers).status_code,200)
            self.assertEqual(client.post('/api/prices',json=price,headers=headers).status_code,200)
            self.assertEqual(client.post('/api/prices',json=price,headers={**headers,'Idempotency-Key':'stale-edit'}).status_code,409)
            saved=client.get(f"/api/transactions/{sale['id']}").json()
            self.assertEqual(saved['lines'][0]['price_paise'],1000)
            self.assertEqual(saved['total_paise'],1000)
            self.assertEqual(self.balance()['purchase_price_paise'],550)

    def test_sale_and_correction_alerts_shared_with_three_partners(self):
        from app.main import create_app
        self.receive(self.bill(2),2)
        sale=self.sell(1,key='sale-replay')
        self.sell(1,key='sale-replay')
        correction=self.post('reversal',dict(transaction_id=sale['id'],reason='Synthetic mistaken sale',evidence='Test review'))
        for username in ['partner-one','partner-two','partner-three']:
            auth.create_user(self.engine,username,'test-partner-password','partner')
        feeds=[]
        with TestClient(create_app(self.engine,'demo')) as client:
            for username in ['partner-one','partner-two','partner-three']:
                client.cookies.clear()
                client.post('/api/auth/login',json=dict(username=username,password='test-partner-password'))
                feeds.append(client.get('/api/partner-alerts').json())
        self.assertEqual(feeds[0],feeds[1]);self.assertEqual(feeds[1],feeds[2])
        self.assertEqual(sum(e['event']=='sale' for e in feeds[0]),1)
        self.assertTrue(any(e['source_id']==correction['id'] and e['event']=='reversal' for e in feeds[0]))
        self.assertTrue(self.store.transaction(sale['id'])['reversed'])
        self.assertEqual(self.balance()['available'],2)

    def test_receive_sell_restart_readback_replays_projection(self):
        b=self.bill()
        self.receive(b,10,key='receipt')
        self.receive(b,10,key='receipt')
        sale=self.sell(3,key='lost-response')
        self.sell(3,key='lost-response')
        self.assertEqual(self.balance()['available'],7)
        restarted=Store(db.engine_for(os.environ['KCD_TEST_DATABASE_URL']))
        try:self.assertEqual(restarted.state()['products'][0]['available'],7)
        finally:restarted.engine.dispose()
        self.assertEqual(sum(m['available_delta'] for m in self.store.state()['movements']),7)
        self.assertEqual(self.store.transaction(sale['id']),sale)
        with self.engine.connect() as c:
            self.assertTrue(reconcile(c)['ok'])
        with self.assertRaises(RuleError):
            self.sell(2,key='lost-response')
        self.sell(4)
        self.assertTrue(self.balance()['low_stock'])

    def test_partial_receipt_damage_quarantine_conversion(self):
        b=self.bill()
        self.receive(b,8)
        self.assertEqual((self.balance()['available'],self.balance()['incoming']),(8,2))
        self.receive(b,0,1,1)
        self.assertEqual((self.balance()['damaged'],self.balance()['quarantined'],self.balance()['incoming']),(1,1,0))
        with self.assertRaises(RuleError):
            self.post('purchase',dict(supplier='Synthetic supplier',invoice_number='B-2',invoice_date='2026-10-04',lines=[dict(product_id=self.pid,quantity=5,unit='carton')]))
        b=self.post('purchase',dict(supplier='Synthetic supplier',invoice_number='B-3',invoice_date='2026-10-04',lines=[dict(product_id=self.pid,quantity=5,unit='pair')]))
        self.assertEqual(b['lines'][0]['quantity'],10)

    def test_concurrent_last_item(self):
        self.receive(self.bill(1),1)
        barrier=threading.Barrier(2)
        def sell(key):
            barrier.wait()
            try:
                return self.store.post('sale',dict(lines=[dict(product_id=self.pid,quantity=1,price_paise=100)]),key)['id']
            except RuleError:
                return None
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(sell,['a','b']))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.balance()['available'],0)

    def test_concurrent_receipt(self):
        b=self.bill()
        barrier=threading.Barrier(2)
        def receive(key):
            barrier.wait()
            try:
                return self.receive(b,8,key=key)['id']
            except RuleError:
                return None
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(receive,['a','b']))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.balance()['available'],8)

    def test_duplicate_rows_and_service(self):
        self.receive(self.bill(1),1)
        with self.assertRaises(RuleError):
            self.post('sale',dict(lines=[dict(product_id=self.pid,quantity=1,price_paise=100)]*2))
        self.assertEqual(self.balance()['available'],1)
        svc=self.post('product',dict(sku='FIT',name='Fitting',category='Services',kind='service',unit='service'))['id']
        self.assertEqual(self.post('sale',dict(lines=[dict(product_id=svc,quantity=1,price_paise=300)]))['movements'],[])

    def test_duplicate_bill_and_return_limits(self):
        b=self.bill()
        with self.assertRaises(RuleError):
            self.post('purchase',dict(supplier=' SYNTHETIC  supplier ',invoice_number=' b-1 ',invoice_date='2026-10-04',lines=[dict(product_id=self.pid,quantity=10,unit='piece')]))
        self.receive(b,10)
        s=self.sell(2)
        data=dict(sale_id=s['id'],reason='Damaged',lines=[dict(sale_line_id=s['lines'][0]['id'],quantity=2,damaged=1)])
        self.post('return',data)
        self.assertEqual((self.balance()['available'],self.balance()['damaged']),(9,1))
        with self.assertRaises(RuleError):
            self.post('return',data)

    def test_reversal_and_count_adjustment(self):
        b=self.bill()
        r=self.receive(b,8)
        reversal=self.post('reversal',dict(transaction_id=r['id'],reason='Wrong count',evidence='Partner recount'))
        self.assertEqual((self.balance()['available'],self.balance()['incoming']),(0,10))
        self.assertEqual(reversal['movements'][0]['reversal_of'],r['movements'][0]['id'])
        self.receive(b,10)
        self.post('adjustment',dict(product_id=self.pid,available=9,damaged=1,quarantined=0,reason='Damage',evidence='Recount'))
        with self.engine.connect() as c:
            self.assertTrue(reconcile(c)['ok'])
        with self.assertRaises(RuleError):
            self.post('reversal',dict(transaction_id=b['id'],reason='Wrong',evidence='Count'))

    def test_immutable_database_history(self):
        r=self.receive(self.bill(),10)
        with self.assertRaises(DBAPIError), self.engine.begin() as c:
            c.execute(db.movements.update().where(db.movements.c.id==r['movements'][0]['id']).values(available_delta=999))
        self.assertEqual(self.balance()['available'],10)

    def test_drafts_stale_approval_and_once(self):
        b=self.bill()
        d=drafts.create_draft(self.engine,'receipt',dict(purchase_id=b['id'],confirmed=True,lines=[dict(purchase_line_id=b['lines'][0]['id'],accepted=8)]),'staff')
        with self.assertRaises(RuleError):
            self.post('post_draft',dict(id=d['id'],version=1))
        drafts.approve(self.engine,d['id'],1,dict(username='partner',role='partner'))
        first=self.post('post_draft',dict(id=d['id'],version=1))
        self.assertEqual(first['id'],self.post('post_draft',dict(id=d['id'],version=1))['id'])
        self.assertEqual(self.balance()['available'],8)
        with self.assertRaises(RuleError):
            drafts.approve(self.engine,d['id'],2,dict(username='partner',role='partner'))

    def test_permissions_and_cost_redaction(self):
        auth.create_user(self.engine,'staff','Test-password-123','staff')
        from app.main import create_app
        with TestClient(create_app(self.engine,'demo')) as client:
            self.assertEqual(client.get('/api/state').status_code,401)
            u=client.post('/api/auth/login',json=dict(username='staff',password='Test-password-123')).json()
            b=self.bill()
            response=client.get('/api/transactions/'+b['id']).json()
            self.assertNotIn('price_paise',response['lines'][0])
            self.assertNotIn('total_paise',response)
            self.assertNotIn('cost_basis',response['lines'][0]['snapshot'])
            headers={'X-CSRF-Token':u['csrf'],'Idempotency-Key':'staff-op'}
            self.assertEqual(client.post('/api/receipts',headers=headers,json=dict(purchase_id=b['id'],confirmed=True,lines=[dict(purchase_line_id=b['lines'][0]['id'],accepted=8)])).status_code,403)
            self.assertEqual(client.post('/api/sales',json={'lines':[]},headers={'Idempotency-Key':'no-csrf'}).status_code,403)

    def test_real_postgres_deadlock_retries_whole_sale(self):
        self.receive(self.bill(10),10)
        other=self.post('product',dict(sku='SECOND',name='Synthetic second',category='Mats',unit='piece',kind='goods'))['id']
        barrier=threading.Barrier(2);attempts={};mutex=threading.Lock();real=self.store.execute
        def contend(conn,operation,payload,actor,key):
            if operation=='sale':
                with mutex:
                    attempts[key]=attempts.get(key,0)+1;attempt=attempts[key]
                order=[self.pid,other] if key=='deadlock-a' else [other,self.pid]
                conn.execute(text("SET LOCAL lock_timeout='5s'"))
                conn.execute(select(db.balances).where(db.balances.c.variant_id==order[0]).with_for_update()).all()
                if attempt==1:barrier.wait(timeout=5)
                conn.execute(select(db.balances).where(db.balances.c.variant_id==order[1]).with_for_update()).all()
            return real(conn,operation,payload,actor,key)
        with patch.object(self.store,'execute',side_effect=contend),concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda key:self.sell(1,key),['deadlock-a','deadlock-b']))
        self.assertEqual(len({r['id'] for r in results}),2)
        self.assertEqual(sorted(attempts.values()),[1,2])
        self.assertEqual(self.balance()['available'],8)
        with self.engine.connect() as c:self.assertTrue(reconcile(c)['ok'])

    def test_migration_preserves_ids_and_replay(self):
        import tempfile
        from pathlib import Path
        from app.ledger import Ledger
        from scripts.import_sqlite import migrate
        with self.engine.begin() as c:
            tables=[t.name for t in db.metadata.sorted_tables if t.name not in {'units','locations'}]
            c.execute(text('TRUNCATE '+','.join(tables)+' RESTART IDENTITY CASCADE'))
        with tempfile.TemporaryDirectory() as folder:
            legacy=Ledger(Path(folder)/'legacy.sqlite3')
            pid=legacy.post('product',dict(sku='OLD',name='Synthetic old',category='Mats',unit='piece',kind='goods'),'old-product')['id']
            bill=legacy.post('purchase',dict(supplier='Synthetic supplier',invoice_number='OLD-1',invoice_date='2026-10-04',lines=[dict(product_id=pid,quantity=10,unit='piece')]),'old-bill')
            payload=dict(purchase_id=bill['id'],confirmed=True,lines=[dict(purchase_line_id=bill['lines'][0]['id'],accepted=10)])
            receipt=legacy.post('receipt',payload,'old-receipt')
            result=migrate(legacy.path,self.engine)
            self.assertTrue(result['reconciliation']['ok'])
            self.assertEqual(self.store.state()['products'][0]['id'],pid)
            self.assertEqual(self.store.transaction(receipt['id'])['movements'][0]['id'],receipt['movements'][0]['id'])
            self.assertEqual(self.store.post('receipt',payload,'old-receipt')['id'],receipt['id'])
            self.assertEqual(self.store.state()['products'][0]['available'],10)
            with self.assertRaises(RuntimeError):migrate(legacy.path,self.engine)

    def test_transient_deadlock_retry(self):
        class Cause(Exception):
            sqlstate='40P01'
        real=self.engine.begin
        calls=[0]
        def fail_once():
            calls[0]+=1
            if calls[0]==1:
                raise OperationalError('deadlock',{},Cause())
            return real()
        with patch.object(self.engine,'begin',side_effect=fail_once):
            self.bill()
        self.assertEqual(calls[0],2)
