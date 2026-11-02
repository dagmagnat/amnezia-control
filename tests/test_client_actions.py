from contextlib import closing
import sqlite3
import time
import unittest
from unittest.mock import patch
import test_api as base
import core
import state


class ClientActionsTests(unittest.TestCase):
    setUp=base.ApiTests.setUp
    tearDown=base.ApiTests.tearDown
    post=base.ApiTests.post

    def test_selected_deletion_revokes_only_selected_and_saves_keys(self):
        ids=self.post('clients',{'profile_id':self.profile['id'],'count':3}).json['ids']
        with state.connection() as con:
            original=[dict(r) for r in con.execute('SELECT * FROM clients ORDER BY id')]
        result=self.post('clients/bulk-delete',{'ids':[ids[0],ids[2]]})
        self.assertEqual(result.status_code,200,result.json);self.assertEqual(result.json['deleted'],2)
        self.assertEqual([r['id'] for r in self.client.get('/api/clients').json['clients']],[ids[1]])
        applied=self.engine.calls[-1][1]
        self.assertEqual({c['id'] for c in applied if not c['enabled']},{ids[0],ids[2]})
        snapshot=state.DATA/'client-delete-backups'/result.json['backup']
        with closing(sqlite3.connect(snapshot)) as con:
            saved=con.execute('SELECT id,private_key FROM clients ORDER BY id').fetchall()
        self.assertEqual(saved,[(c['id'],c['private_key']) for c in original])

    def test_multiple_profiles_fail_atomically_and_restore_all_peers(self):
        first=self.post('clients',{'profile_id':self.profile['id']}).json['ids'][0]
        second=self.post('clients',{'protocol':'wireguard'}).json['ids'][0]
        with patch.object(self.engine,'apply',side_effect=[None,core.Problem('Injected failure',503),None,None]) as apply:
            result=self.post('clients/bulk-delete',{'ids':[first,second]})
            self.assertEqual(result.status_code,503,result.json)
            self.assertEqual(apply.call_count,4)
            for call in apply.call_args_list[2:]:self.assertTrue(all(c['enabled'] for c in call.args[1]))
        with state.connection() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM clients WHERE enabled=1').fetchone()[0],2)

    def test_invalid_or_stale_selection_never_deletes(self):
        ident=self.post('clients',{'profile_id':self.profile['id']}).json['ids'][0]
        for ids in ([],None,'all',[True],[0],[ident,ident],[ident,999999]):
            result=self.post('clients/bulk-delete',{'ids':ids})
            self.assertIn(result.status_code,(400,409),result.json)
            self.assertEqual(len(self.client.get('/api/clients').json['clients']),1)
        visitor=base.web.app.test_client()
        self.assertEqual(visitor.post('/api/clients/bulk-delete',json={'ids':[ident]}).status_code,403)

    def test_status_never_reports_blocked_or_expired_client_online(self):
        ids=self.post('clients',{'profile_id':self.profile['id'],'count':5}).json['ids'];now=int(time.time())
        with state.connection() as con:
            con.execute('UPDATE clients SET handshake=?',(now,))
            con.execute('UPDATE clients SET enabled=0 WHERE id=?',(ids[1],))
            con.execute('UPDATE clients SET expires_at=? WHERE id=?',(str(now-10),ids[2]))
            con.execute('UPDATE clients SET quota_bytes=10,used_bytes=20 WHERE id=?',(ids[3],))
            con.execute('UPDATE clients SET handshake=? WHERE id=?',(now-300,ids[4]))
        rows=self.client.get('/api/clients').json['clients']
        self.assertEqual([c['status'] for c in rows],['online','disabled','expired','quota','offline'])
        self.assertEqual([c['online'] for c in rows],[True,False,False,False,False])


if __name__=='__main__':unittest.main(verbosity=2)
