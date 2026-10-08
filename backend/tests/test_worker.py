"""Controlled-model tests: real PostgreSQL/application tools, simulated provider responses."""
import asyncio
import uuid
from sqlalchemy import select
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse,ToolCallPart,ToolReturnPart
import test_postgres as fixtures
from app.agents.runtime import execute,resume
from app.infrastructure import database as db
from app.infrastructure.jobs import tick,consume_outbox
from app.workflows import drafts
from app.ledger import now,RuleError

class WorkerTests(fixtures.PostgreSQLTests):
    def run_record(self,goal='Inspect shortages and save a verified report',**extra):
        rid=str(uuid.uuid4())
        with self.engine.begin() as c:c.execute(db.runs.insert().values(id=rid,actor='partner',goal=goal,created_at=now(),**extra))
        return self.read_run(rid)
    def read_run(self,rid):
        with self.engine.connect() as c:return dict(c.execute(select(db.runs).where(db.runs.c.id==rid)).mappings().one())
    def shortage_model(self):
        def respond(messages,info):
            results=[p for m in messages for p in m.parts if isinstance(p,ToolReturnPart)]
            if not results:part=ToolCallPart('query_inventory',{'only_low_stock':True},'inventory')
            elif results[-1].tool_name=='query_inventory':part=ToolCallPart('save_shortage_report',{},'save')
            elif results[-1].tool_name=='save_shortage_report':part=ToolCallPart('read_report',{'report_id':results[-1].content['id']},'read')
            else:part=ToolCallPart('final_result',{'summary':'Saved and read back report','evidence_ids':[results[-1].content['id']],'unresolved':[]},'done')
            return ModelResponse(parts=[part])
        return FunctionModel(respond)
    def test_order_review_and_arrival_checklist_do_not_post_stock(self):
        from app.modules.purchasing.reviews import import_review
        from pydantic import ValidationError
        rid=str(uuid.uuid4())
        payload=dict(supplier='Synthetic mirrors',invoice_number='TEST-ORDER',order_date='2026-10-06',buyer_gstin='UNCONFIRMED',
            subtotal_paise=20000,igst_paise=3600,total_paise=23600,
            lines=[dict(description='Mirror awaiting exact side and unit',amount_paise=20000,quantity_candidate=2)],
            unresolved=['Confirm unit and exact variant','Goods have not arrived'])
        import_review(self.engine,rid,payload,'partner')
        import_review(self.engine,rid,payload,'partner')
        with self.assertRaises(ValidationError):import_review(self.engine,str(uuid.uuid4()),{**payload,'physical_arrival_confirmed':True},'partner')
        with self.assertRaises(ValidationError):import_review(self.engine,str(uuid.uuid4()),{**payload,'total_paise':1},'partner')
        with self.assertRaises(RuleError):import_review(self.engine,rid,{**payload,'invoice_number':'OTHER'},'partner')
        run=self.run_record('Save an arrival checklist for Synthetic mirrors')
        def respond(messages,info):
            results=[p for m in messages for p in m.parts if isinstance(p,ToolReturnPart)]
            if not results:part=ToolCallPart('query_order_reviews',{'supplier_query':'Synthetic mirrors'},'orders')
            elif results[-1].tool_name=='query_order_reviews':
                self.assertEqual(len(results[-1].content),1)
                part=ToolCallPart('save_arrival_checklist',{'order_review_ids':[rid]},'save')
            elif results[-1].tool_name=='save_arrival_checklist':part=ToolCallPart('read_report',{'report_id':results[-1].content['id']},'read')
            else:part=ToolCallPart('final_result',{'summary':'Saved arrival checks; no stock posted','evidence_ids':[results[-1].content['id']],'unresolved':[]},'done')
            return ModelResponse(parts=[part])
        asyncio.run(execute(self.engine,run,FunctionModel(respond)))
        self.assertEqual(self.read_run(run['id'])['status'],'complete')
        self.assertEqual(self.balance()['available'],0)
        with self.engine.connect() as c:
            self.assertEqual(len(c.execute(select(db.documents)).all()),0)
            self.assertEqual(len(c.execute(select(db.movements)).all()),0)
            self.assertEqual(len(c.execute(select(db.order_reviews)).all()),1)
            report=c.execute(select(db.reports.c.data)).scalar_one()
            self.assertFalse(report['stock_posted'])
            self.assertEqual(report['orders'][0]['payload']['unresolved'],payload['unresolved'])

    def test_shortage_tools_evidence(self):
        run=self.run_record();asyncio.run(execute(self.engine,run,self.shortage_model()))
        result=self.read_run(run['id']);self.assertEqual(result['status'],'complete');self.assertEqual(result['requests_used'],4)
        with self.engine.connect() as c:
            tools=c.execute(select(db.steps.c.tool).where(db.steps.c.run_id==run['id']).order_by(db.steps.c.sequence)).scalars().all()
            report=c.execute(select(db.reports)).mappings().one()
        self.assertEqual(tools,['query_inventory','save_shortage_report','read_report']);self.assertEqual(report['data'][0]['available'],0)
        self.assertEqual(result['evidence']['evidence_ids'],[report['id']])

    def test_intake_proposal_readback_and_partner_price_ownership(self):
        run=self.run_record('Prepare new parts from my typed buying list')
        def respond(messages,info):
            results=[p for m in messages for p in m.parts if isinstance(p,ToolReturnPart)]
            if not results:
                part=ToolCallPart('prepare_intake',dict(supplier='Synthetic',invoice_number='NEW-1',invoice_date='2026-10-08',source_note='Typed generated test',
                    lines=[dict(description='Exact new mirror',name='Exact new mirror',family_name='Mirrors',category='Mirrors',quantity=10,unit='piece',cost_paise=10000,selling_price_paise=99999)]),'propose')
            elif results[-1].tool_name=='prepare_intake':
                self.assertIsNone(results[-1].content['payload']['lines'][0]['selling_price_paise'])
                part=ToolCallPart('read_draft',dict(draft_id=results[-1].content['id']),'verify')
            else:
                part=ToolCallPart('final_result',dict(summary='Prepared items, not posted stock',evidence_ids=[results[-1].content['id']],unresolved=['Partner must set selling price']),'done')
            return ModelResponse(parts=[part])
        asyncio.run(execute(self.engine,run,FunctionModel(respond)))
        self.assertEqual(self.read_run(run['id'])['status'],'needs_clarification')
        self.assertEqual(len(self.store.state()['products']),1)
        with self.engine.connect() as c:self.assertEqual(len(c.execute(select(db.documents)).all()),0)
    def test_deferred_approval_restart_post_once(self):
        bill=self.bill(10)
        d=drafts.create_draft(self.engine,'receipt',{'purchase_id':bill['id'],'confirmed':True,'lines':[{'purchase_line_id':bill['lines'][0]['id'],'accepted':8,'damaged':1,'quarantined':0}]},'partner')
        run=self.run_record('Post the reviewed receipt and verify it')
        def respond(messages,info):
            results=[p for m in messages for p in m.parts if isinstance(p,ToolReturnPart)]
            if not results:part=ToolCallPart('post_approved_draft',{'draft_id':d['id'],'version':1},'approval')
            elif results[-1].tool_name=='post_approved_draft':part=ToolCallPart('verify_transaction',{'transaction_id':results[-1].content['id']},'verify')
            else:part=ToolCallPart('final_result',{'summary':'Posted and verified','evidence_ids':[results[-1].content['transaction']['id']],'unresolved':[]},'done')
            return ModelResponse(parts=[part])
        model=FunctionModel(respond);asyncio.run(execute(self.engine,run,model))
        self.assertEqual(self.read_run(run['id'])['status'],'waiting_approval');self.assertEqual(self.balance()['available'],0)
        with self.assertRaises(RuleError):resume(self.engine,run['id'],{'role':'staff','username':'staff'})
        resume(self.engine,run['id'],{'role':'partner','username':'partner'})
        asyncio.run(execute(self.engine,self.read_run(run['id']),model))
        self.assertEqual(self.read_run(run['id'])['status'],'complete');self.assertEqual(self.balance()['available'],8);self.assertEqual(self.balance()['damaged'],1)
        self.store.post('post_draft',{'id':d['id'],'version':1},'another-key','partner');self.assertEqual(self.balance()['available'],8)
    def test_unverified_model_claim_refused(self):
        run=self.run_record();model=FunctionModel(lambda messages,info:ModelResponse(parts=[ToolCallPart('final_result',{'summary':'Done','evidence_ids':[],'unresolved':[]})]))
        with self.assertRaises(RuleError):asyncio.run(execute(self.engine,run,model))
        self.assertEqual(self.balance()['available'],0)
    def test_budget_and_outage_manual_fallback(self):
        run=self.run_record(requests_used=10);called=[]
        tick(self.engine,FunctionModel(lambda messages,info:called.append(1)))
        self.assertEqual(self.read_run(run['id'])['status'],'failed');self.assertFalse(called)
        run=self.run_record('Provider outage')
        def outage(messages,info):raise ConnectionError('provider unavailable')
        tick(self.engine,FunctionModel(outage));self.assertEqual(self.read_run(run['id'])['status'],'failed')
        bill=self.bill(10);self.receive(bill,10);self.sell(3);self.assertEqual(self.balance()['available'],7)
    def test_expired_lease_and_outbox_dedup(self):
        run=self.run_record(status='running',lease_until=1);tick(self.engine,self.shortage_model());self.assertEqual(self.read_run(run['id'])['status'],'complete')
        while consume_outbox(self.engine):pass
        with self.engine.begin() as c:
            n=c.execute(select(db.consumed)).all();c.execute(db.outbox.update().values(status='pending',lease_until=0))
        while consume_outbox(self.engine):pass
        with self.engine.connect() as c:self.assertEqual(len(c.execute(select(db.consumed)).all()),len(n))
    def test_draft_edit_invalidates_approval(self):
        bill=self.bill();payload={'purchase_id':bill['id'],'confirmed':True,'lines':[{'purchase_line_id':bill['lines'][0]['id'],'accepted':8,'damaged':0}]}
        d=drafts.create_draft(self.engine,'receipt',payload,'staff');user={'role':'partner','username':'partner'}
        drafts.approve(self.engine,d['id'],1,user)
        changed={**payload,'lines':[{'purchase_line_id':bill['lines'][0]['id'],'accepted':7,'damaged':0}]}
        drafts.edit(self.engine,d['id'],1,changed,{'role':'staff','username':'staff'})
        with self.assertRaises(RuleError):self.store.post('post_draft',{'id':d['id'],'version':1},'stale','partner')
        with self.assertRaises(RuleError):self.store.post('post_draft',{'id':d['id'],'version':2},'unapproved','partner')
        drafts.approve(self.engine,d['id'],2,user);self.store.post('post_draft',{'id':d['id'],'version':2},'new-version','partner');self.assertEqual(self.balance()['available'],7)
    def test_typed_purchase_tool_persists_validated_line(self):
        fid=str(uuid.uuid4())
        with self.engine.begin() as c:c.execute(db.files.insert().values(id=fid,sha256='generated-test-hash',name='Generated test.pdf',media_type='application/pdf',path='/generated/test.pdf',actor='partner'))
        run=self.run_record('Prepare a typed generated purchase')
        def respond(messages,info):
            results=[p for m in messages for p in m.parts if isinstance(p,ToolReturnPart)]
            if not results:
                part=ToolCallPart('prepare_purchase',{'supplier':'Synthetic supplier','invoice_number':'TYPED-1','invoice_date':'2026-10-05','source_file_id':fid,
                    'lines':[{'product_id':self.pid,'quantity':10,'unit':'piece','cost_paise':10000}]},'prepare')
            elif results[-1].tool_name=='prepare_purchase':
                self.assertNotIn('error',results[-1].content)
                part=ToolCallPart('post_approved_draft',{'draft_id':results[-1].content['id'],'version':1},'approval')
            elif results[-1].tool_name=='post_approved_draft':
                part=ToolCallPart('verify_transaction',{'transaction_id':results[-1].content['id']},'verify')
            else:part=ToolCallPart('final_result',{'summary':'Typed bill posted and verified','evidence_ids':[results[-1].content['transaction']['id']],'unresolved':[]},'done')
            return ModelResponse(parts=[part])
        model=FunctionModel(respond);asyncio.run(execute(self.engine,run,model))
        self.assertEqual(self.read_run(run['id'])['status'],'waiting_approval')
        self.assertEqual(self.balance()['incoming'],0)
        resume(self.engine,run['id'],{'role':'partner','username':'partner'})
        asyncio.run(execute(self.engine,self.read_run(run['id']),model))
        self.assertEqual(self.read_run(run['id'])['status'],'complete')
        self.assertEqual((self.balance()['available'],self.balance()['incoming']),(0,10))
        with self.engine.connect() as c:
            args=c.execute(select(db.steps.c.arguments).where(db.steps.c.tool=='prepare_purchase')).scalar_one()
            self.assertEqual(args['lines'][0]['cost_paise'],10000)

    def test_slow_worker_not_duplicated_after_lease_expiry(self):
        import threading,concurrent.futures
        from unittest.mock import patch
        while consume_outbox(self.engine):pass
        entered=threading.Event();release=threading.Event();run=self.run_record();real=execute
        async def slow(engine,record,model):
            entered.set();release.wait(timeout=5)
            return await real(engine,record,model)
        with patch('app.agents.runtime.execute',side_effect=slow) as mocked,concurrent.futures.ThreadPoolExecutor(1) as pool:
            first=pool.submit(tick,self.engine,self.shortage_model(),run['id'])
            self.assertTrue(entered.wait(timeout=5))
            with self.engine.begin() as c:c.execute(db.runs.update().where(db.runs.c.id==run['id']).values(lease_until=1))
            self.assertFalse(tick(self.engine,self.shortage_model(),run['id']))
            self.assertEqual(mocked.call_count,1)
            release.set();self.assertTrue(first.result(timeout=5))
        self.assertEqual(self.read_run(run['id'])['status'],'complete')

    def test_clarification_replay_budget_and_permissions(self):
        from app.workflows.runs import clarify,clarifications
        run=self.run_record(status='needs_clarification',requests_used=5,tools_used=3,messages=[{'old':'evidence'}])
        user={'role':'partner','username':'partner'}
        with self.assertRaises(RuleError):clarify(self.engine,run['id'],'Exact SKU confirmed','note',{'role':'staff','username':'staff'})
        def send(_):return clarify(self.engine,run['id'],'Exact SKU confirmed','note',user)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(send,range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.read_run(run['id'])['requests_used'],5)
        with self.engine.connect() as c:
            self.assertEqual(len(clarifications(c,run['id'])),1)
            archived=c.execute(select(db.audit.c.data).where(db.audit.c.event=='clarify_run')).scalar_one()
            self.assertEqual(archived['messages'],[{'old':'evidence'}])
        with self.assertRaises(RuleError):clarify(self.engine,run['id'],'Changed note','note',user)
        exhausted=self.run_record(status='needs_clarification',requests_used=10)
        with self.assertRaises(RuleError):clarify(self.engine,exhausted['id'],'Confirmed','new',user)

    def test_run_creation_replay_and_nested_validation(self):
        auth=__import__('app.infrastructure.auth',fromlist=['create_user'])
        auth.create_user(self.engine,'partner','Test-password-123','partner')
        from app.main import create_app
        from fastapi.testclient import TestClient
        with TestClient(create_app(self.engine,'demo')) as client:
            u=client.post('/api/auth/login',json={'username':'partner','password':'Test-password-123'}).json()
            headers={'X-CSRF-Token':u['csrf'],'Idempotency-Key':'lost-goal-response'}
            payload={'goal':'Inspect generated stock. '+ 'Use confirmed quantities. '*12,'attachments':[]}
            a=client.post('/api/agent/runs',json=payload,headers=headers)
            b=client.post('/api/agent/runs',json=payload,headers=headers)
            self.assertEqual(a.status_code,200);self.assertEqual(a.json()['id'],b.json()['id'])
            self.assertEqual(client.post('/api/agent/runs',json={**payload,'goal':'Changed'},headers=headers).status_code,409)
            bill=self.bill()
            d=drafts.create_draft(self.engine,'receipt',{'purchase_id':bill['id'],'confirmed':True,'lines':[{'purchase_line_id':bill['lines'][0]['id'],'accepted':8}]},'partner')
            response=client.patch('/api/drafts/'+d['id'],headers=headers,json={'version':1,'payload':{'lines':[{'accepted':1.5}]}})
            self.assertEqual(response.status_code,422)
            self.assertEqual(self.balance()['available'],0)

# Exclude inherited tests here; their own class remains in test_postgres.py.
for _name in list(vars(fixtures.PostgreSQLTests)):
    if _name.startswith('test_'):setattr(WorkerTests,_name,None)
