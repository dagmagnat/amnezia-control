import sqlite3
import time
import unittest
from contextlib import closing
from unittest.mock import patch
from types import SimpleNamespace
import test_api as base
import core
import state
import versions


class BulkActionsTests(unittest.TestCase):
    setUp=base.ApiTests.setUp
    tearDown=base.ApiTests.tearDown
    post=base.ApiTests.post

    def rows(self):
        with state.connection() as con: return [dict(r) for r in con.execute('SELECT * FROM clients ORDER BY id')]

    def action(self,ids,action,**fields): return self.post('clients/bulk-update',dict(ids=ids,action=action,**fields))

    def test_disable_enable_selected_in_all_generations_without_rekey(self):
        ids=self.post('clients',{'profile_id':self.profile['id'],'count':3}).json['ids']
        self.assertEqual(self.post('clients/add-version',{'ids':[ids[0]],'version':'2.0'}).status_code,200)
        before=self.rows()
        with state.connection() as con:
            configs=[versions.configuration(con,before[0],v['id']) for v in versions.options(con,before[0])]
            variant=[tuple(v) for v in con.execute('SELECT * FROM client_variants')]
        self.engine.calls.clear()
        result=self.action([ids[0],ids[2]],'disable')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['updated'],2)
        self.assertEqual([r['enabled'] for r in self.rows()],[0,1,0])
        self.assertEqual(len(self.engine.calls),2)
        self.assertEqual(len({p['id'] for p,_ in self.engine.calls}),2)
        for _,peers in self.engine.calls:
            self.assertTrue(all(not p['enabled'] for p in peers if p['id'] in [ids[0],ids[2]]))
        with closing(sqlite3.connect(state.DATA/'client-action-backups'/result.json['backup'])) as con:
            self.assertEqual(con.execute('SELECT SUM(enabled) FROM clients').fetchone()[0],3)
        self.assertEqual(self.action([ids[0],ids[2]],'enable').status_code,200)
        self.assertEqual(self.rows(),before)
        with state.connection() as con:
            self.assertEqual([versions.configuration(con,before[0],v['id']) for v in versions.options(con,before[0])],configs)
            self.assertEqual([tuple(v) for v in con.execute('SELECT * FROM client_variants')],variant)

    def test_extend_future_expired_and_unlimited_without_unpausing(self):
        ids=self.post('clients',{'profile_id':self.profile['id'],'count':4}).json['ids'];now=1800000000
        with state.connection() as con:
            for ident,expires,enabled in [(ids[0],now+100,1),(ids[1],now-100,1),(ids[2],0,1),(ids[3],now-100,0)]:
                con.execute('UPDATE clients SET expires_at=?,enabled=?,blocked_reason=? WHERE id=?',(str(expires) if expires else '',enabled,'expired' if expires and expires<now else '',ident))
        with patch('client_actions.time',SimpleNamespace(time=lambda:now,strftime=time.strftime)): result=self.action(ids,'extend',days=30)
        self.assertEqual(result.status_code,200,result.json)
        rows=self.rows();self.assertEqual([r['expires_at'] for r in rows],[str(now+100+30*86400),str(now+30*86400),'',str(now+30*86400)])
        self.assertEqual([r['enabled'] for r in rows],[1,1,1,0]);self.assertTrue(all(not r['blocked_reason'] for r in rows))
        self.assertEqual(result.json['unchanged'],1);self.assertEqual(result.json['restricted'],1)

    def test_enabling_does_not_bypass_quota_or_expiry(self):
        ids=self.post('clients',{'profile_id':self.profile['id'],'count':2}).json['ids']
        with state.connection() as con:
            con.execute('UPDATE clients SET enabled=0')
            con.execute('UPDATE clients SET expires_at=? WHERE id=?',(str(int(time.time())-20),ids[0]))
            con.execute('UPDATE clients SET quota_bytes=1,used_bytes=2 WHERE id=?',(ids[1],))
        self.engine.calls.clear();result=self.action(ids,'enable')
        self.assertEqual(result.json['restricted'],2)
        self.assertEqual([r['blocked_reason'] for r in self.rows()],['expired','quota'])
        self.assertEqual(self.engine.calls,[])

    def test_set_and_clear_expiry_quota_and_reset_are_independent(self):
        ids=self.post('clients',{'profile_id':self.profile['id'],'count':2}).json['ids']
        future=int(time.time())+86400
        self.assertEqual(self.action([ids[0]],'set_expiry',expires_at=future).status_code,200)
        self.assertEqual([r['expires_at'] for r in self.rows()],[str(future),''])
        self.assertEqual(self.action([ids[0]],'clear_expiry').status_code,200)
        with state.connection() as con:
            con.execute('UPDATE clients SET used_bytes=100,last_rx=70,last_tx=30')
        self.assertEqual(self.action([ids[0]],'set_quota',quota_bytes=50).status_code,200)
        self.assertEqual(self.rows()[0]['blocked_reason'],'quota')
        self.assertEqual(self.rows()[0]['used_bytes'],100)
        self.assertEqual(self.action([ids[0]],'reset_usage').status_code,200)
        rows=self.rows();self.assertEqual([r['used_bytes'] for r in rows],[0,100]);self.assertEqual(rows[0]['last_rx'],70)
        self.assertEqual(rows[0]['blocked_reason'],'');self.assertEqual(rows[0]['quota_bytes'],50)
        self.assertEqual(self.action([ids[0]],'set_quota',quota_bytes=0).status_code,200)
        self.assertEqual(self.rows()[0]['quota_bytes'],0)

    def test_noop_does_not_write_backup_or_touch_runtime(self):
        ids=self.post('clients',{'profile_id':self.profile['id']}).json['ids'];self.engine.calls.clear()
        for action,fields in [('enable',{}),('extend',{'days':1}),('clear_expiry',{}),('reset_usage',{})]:
            result=self.action(ids,action,**fields)
            self.assertEqual(result.status_code,200,result.json);self.assertEqual(result.json['updated'],0)
            self.assertIsNone(result.json['backup'])
        self.assertEqual(self.engine.calls,[])

    def test_multi_interface_failure_rolls_back_every_client(self):
        ids=self.post('clients',{'profile_id':self.profile['id']}).json['ids']
        ids+=self.post('clients',{'protocol':'wireguard'}).json['ids'];before=self.rows()
        with patch.object(self.engine,'apply',side_effect=[None,core.Problem('Injected failure',503),None,None]) as apply:
            result=self.action(ids,'disable');self.assertEqual(result.status_code,503,result.json)
            self.assertEqual(apply.call_count,4)
            for call in apply.call_args_list[2:]: self.assertTrue(all(p['enabled'] for p in call.args[1]))
        self.assertEqual(self.rows(),before)

    def test_rollback_failure_is_reported(self):
        ids=self.post('clients',{'profile_id':self.profile['id']}).json['ids'];before=self.rows()
        with patch.object(self.engine,'apply',side_effect=core.Problem('Injected failure',503)):
            result=self.action(ids,'disable')
        self.assertEqual(result.status_code,503);self.assertIn('rollback needs attention',result.json['error'])
        self.assertEqual(self.rows(),before)

    def test_validation_and_auth_never_apply_partial_update(self):
        ids=self.post('clients',{'profile_id':self.profile['id']}).json['ids'];before=self.rows();self.engine.calls.clear()
        payloads=[None,[],{'ids':ids,'action':'missing'}, {'ids':ids,'action':[]},
                  {'ids':ids,'action':'disable','enabled':True}]
        payloads += [dict(ids=bad,action='disable') for bad in ([],None,'all',[True],[0],ids*2,ids+[99999])]
        payloads += [dict(ids=ids,action=action,**{field:value}) for action,field,value in [
            ('extend','days',True),('extend','days',0),('extend','days',3651),('extend','days',1.5),
            ('set_quota','quota_bytes',-1),('set_quota','quota_bytes',True),('set_expiry','expires_at',0)]]
        for payload in payloads:
            response=self.post('clients/bulk-update',payload)
            self.assertIn(response.status_code,(400,409),response.json)
            self.assertEqual(self.rows(),before)
        visitor=base.web.app.test_client();token=visitor.get('/api/me').json['csrf']
        self.assertEqual(visitor.post('/api/clients/bulk-update',json={'ids':ids,'action':'disable'},headers={'X-CSRF-Token':token}).status_code,401)
        self.assertEqual(self.client.post('/api/clients/bulk-update',json={'ids':ids,'action':'disable'}).status_code,403)
        self.assertEqual(self.engine.calls,[])

if __name__=='__main__': unittest.main(verbosity=2)
