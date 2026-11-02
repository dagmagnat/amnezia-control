import io
import time
import unittest
import zipfile
from unittest.mock import patch
import test_api as base
import core
import state


class VersionTests(unittest.TestCase):
    setUp=base.ApiTests.setUp
    tearDown=base.ApiTests.tearDown
    post=base.ApiTests.post

    def prepare(self,count=1):
        ids=self.post('clients',{'protocol':'amneziawg','version':'1.5','count':count}).json['ids']
        with state.connection() as con: before=[dict(r) for r in con.execute('SELECT * FROM clients ORDER BY id')]
        return ids,before

    def test_original_identity_and_config_preserved_idempotent(self):
        ids,before=self.prepare(2)
        originals=[self.client.get(f'/api/clients/{i}/config').text for i in ids]
        result=self.post('clients/add-version',{'ids':ids,'version':'3.1'})
        self.assertEqual(result.status_code,200,result.json);self.assertEqual(result.json['created'],2)
        with state.connection() as con:
            self.assertEqual(before,[dict(r) for r in con.execute('SELECT * FROM clients ORDER BY id')])
        self.assertEqual(originals,[self.client.get(f'/api/clients/{i}/config').text for i in ids])
        self.assertEqual(self.post('clients/add-version',{'ids':ids,'version':'3.1'}).json['created'],0)
        rows=self.client.get('/api/clients').json['clients'];self.assertEqual(len(rows),2)
        for row in rows:
            variant=row['versions'][1]['id']
            text=self.client.get(f'/api/clients/{row["id"]}/config?variant={variant}').text
            self.assertIn('HeaderProtectionKey =',text);self.assertIn('RandomTrailers = on',text)
            self.assertNotIn(before[0]['private_key'],text)
            self.assertEqual(self.client.get(f'/api/clients/{row["id"]}/qr?variant={variant}').mimetype,'image/png')
        bundle=self.client.get('/api/clients/version-bundle?version=3.1&ids='+','.join(map(str,ids)))
        with zipfile.ZipFile(io.BytesIO(bundle.data)) as archive: self.assertEqual(len(archive.namelist()),2)
        self.assertEqual(self.client.get(f'/api/clients/{ids[0]}/config?variant={rows[1]["versions"][1]["id"]}').status_code,404)

    def test_shared_quota_disable_and_delete_revoke_every_version(self):
        ids,_=self.prepare();ident=ids[0]
        self.post('clients/add-version',{'ids':ids,'version':'3.1'})
        with state.connection() as con:
            original=dict(con.execute('SELECT * FROM clients WHERE id=?',(ident,)).fetchone())
            variant=dict(con.execute('SELECT * FROM client_variants WHERE client_id=?',(ident,)).fetchone())
            con.execute('UPDATE clients SET quota_bytes=100 WHERE id=?',(ident,))
        self.engine.samples={original['public_key']:{'rx':20,'tx':30,'handshake':0},variant['public_key']:{'rx':30,'tx':40,'handshake':int(time.time())}}
        state.refresh()
        row=self.client.get('/api/clients').json['clients'][0]
        self.assertEqual(row['used_bytes'],120);self.assertEqual(row['status'],'quota')
        for p,peers in self.engine.calls[-2:]: self.assertTrue(all(c['blocked_reason']=='quota' for c in peers))
        result=self.client.patch(f'/api/clients/{ident}',json={'quota_bytes':1000,'enabled':False},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(result.status_code,200,result.json)
        for p,peers in self.engine.calls[-2:]: self.assertTrue(all(not c['enabled'] for c in peers))
        self.assertEqual(self.post('clients/bulk-delete',{'ids':ids}).status_code,200)
        with state.connection() as con: self.assertEqual(con.execute('SELECT COUNT(*) FROM client_variants').fetchone()[0],0)

    def test_failed_addition_restores_original_database_and_target(self):
        ids,before=self.prepare()
        with patch.object(self.engine,'apply',side_effect=[core.Problem('Injected failure',503),None]) as apply:
            result=self.post('clients/add-version',{'ids':ids,'version':'3.1'})
            self.assertEqual(result.status_code,503,result.json)
            self.assertEqual(apply.call_count,2)
            self.assertTrue(all(not c['enabled'] for c in apply.call_args_list[-1].args[1]))
        with state.connection() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM client_variants').fetchone()[0],0)
            self.assertEqual(before,[dict(r) for r in con.execute('SELECT * FROM clients ORDER BY id')])

    def test_invalid_selection_generation_and_auth(self):
        ids,_=self.prepare()
        for payload in ({'ids':[],'version':'3.1'},{'ids':ids,'version':'2.5'},{'ids':[True],'version':'3.1'},{'ids':[9999],'version':'3.1'}):
            self.assertIn(self.post('clients/add-version',payload).status_code,(400,409))
        visitor=base.web.app.test_client()
        self.assertEqual(visitor.post('/api/clients/add-version',json={'ids':ids,'version':'3.1'}).status_code,403)

    def test_full_subnet_allocates_second_profile(self):
        ids,_=self.prepare()
        with state.connection() as con:
            con.execute('UPDATE profiles SET address=? WHERE id=?',('10.77.1.1/30',self.profile['id']))
            # Exhaust the only non-server host in this target /30.
        first=self.post('clients',{'profile_id':self.profile['id']}).json['ids'][0]
        result=self.post('clients/add-version',{'ids':ids,'version':'3.1'})
        self.assertEqual(result.status_code,200,result.json)
        with state.connection() as con:
            variant=con.execute('SELECT * FROM client_variants WHERE client_id=?',(ids[0],)).fetchone()
            self.assertNotEqual(variant['profile_id'],self.profile['id'])

    def test_adopted_client_without_private_key_gets_downloadable_variant(self):
        ident=self.post('clients',{'profile_id':self.profile['id']}).json['ids'][0]
        with state.connection() as con: con.execute("UPDATE clients SET private_key='' WHERE id=?",(ident,))
        result=self.post('clients/add-version',{'ids':[ident],'version':'3.1'})
        self.assertEqual(result.status_code,200,result.json);self.assertEqual(result.json['created'],1)
        self.assertEqual(self.post('clients/add-version',{'ids':[ident],'version':'3.1'}).json['created'],0)
        bundle=self.client.get(f'/api/clients/version-bundle?version=3.1&ids={ident}')
        self.assertEqual(bundle.status_code,200)
        with state.connection() as con:
            self.assertEqual(con.execute('SELECT private_key FROM clients WHERE id=?',(ident,)).fetchone()[0],'')

    def test_quota_sync_failure_rolls_back_all_generations(self):
        ids,_=self.prepare();ident=ids[0]
        self.post('clients/add-version',{'ids':ids,'version':'3.1'})
        with state.connection() as con:
            public=con.execute('SELECT public_key FROM client_variants WHERE client_id=?',(ident,)).fetchone()[0]
            con.execute('UPDATE clients SET quota_bytes=100 WHERE id=?',(ident,))
        self.engine.samples={public:{'rx':100,'tx':50,'handshake':0}}
        with patch.object(self.engine,'apply',side_effect=[None,core.Problem('Injected failure',503),None,None]) as apply:
            with self.assertRaises(core.Problem): state.refresh()
            self.assertEqual(apply.call_count,4)
            for call in apply.call_args_list[2:]: self.assertTrue(all(not c['blocked_reason'] for c in call.args[1]))
        row=self.client.get('/api/clients').json['clients'][0]
        self.assertEqual(row['used_bytes'],0);self.assertEqual(row['blocked_reason'],'')


if __name__=='__main__': unittest.main(verbosity=2)
