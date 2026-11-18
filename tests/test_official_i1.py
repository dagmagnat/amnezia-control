import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_api as base
import state, core
from client_defaults import OFFICIAL_I1

class OfficialSignatureTests(unittest.TestCase):
    setUp=base.ApiTests.setUp
    tearDown=base.ApiTests.tearDown
    post=base.ApiTests.post

    def test_official_reference_and_new_client_config_and_qr(self):
        reference=Path('docs/official-I1-Amnezia.txt').read_text(encoding='utf-8').strip()
        self.assertEqual(OFFICIAL_I1,reference)
        self.assertEqual(hashlib.sha256(reference.encode()).hexdigest(),'23241bf62ba6dd34379a4e129b4e4d7ca937481749a13c4626f5c3c573bc068c')
        core.parameters('3.1',{'I1':OFFICIAL_I1})
        ident=self.post('clients',{'protocol':'amneziawg','version':'3.1'}).json['ids'][0]
        before=list(self.engine.calls)
        text=self.client.get(f'/api/clients/{ident}/config').text
        self.assertIn('I1 = '+OFFICIAL_I1,text)
        import qrcode
        make=qrcode.make
        with patch.object(qrcode,'make',wraps=make) as qr:
            result=self.client.get(f'/api/clients/{ident}/qr')
            self.assertEqual(result.status_code,200)
            self.assertEqual(qr.call_args.args[0],text)
        self.assertEqual(before,self.engine.calls)

    def test_export_only_changes_i1_and_never_mutates_database(self):
        ident=self.post('clients',{'protocol':'amneziawg','version':'3.1'}).json['ids'][0]
        with state.connection() as con:
            row=dict(con.execute('SELECT * FROM clients WHERE id=?',(ident,)).fetchone())
            profile=dict(con.execute('SELECT * FROM profiles WHERE id=?',(row['profile_id'],)).fetchone())
            before_clients=[dict(r) for r in con.execute('SELECT * FROM clients')]
            before_profiles=[dict(r) for r in con.execute('SELECT * FROM profiles')]
        text=state.client_config(row,profile)
        with patch.object(state,'OFFICIAL_I1','<r 42>'):
            other=state.client_config(row,profile)
        self.assertEqual(text.replace(OFFICIAL_I1,'<r 42>'),other)
        with state.connection() as con:
            self.assertEqual(before_clients,[dict(r) for r in con.execute('SELECT * FROM clients')])
            self.assertEqual(before_profiles,[dict(r) for r in con.execute('SELECT * FROM profiles')])

    def test_old_generations_and_imports_and_custom_signatures_preserved(self):
        for version in ('1.0','1.5','2.0','3.0'):
            ident=self.post('clients',{'protocol':'amneziawg','version':version}).json['ids'][0]
            self.assertNotIn('I1 =',self.client.get(f'/api/clients/{ident}/config').text)
        ident=self.post('clients',{'protocol':'amneziawg','version':'3.1'}).json['ids'][0]
        with state.connection() as con:
            row=dict(con.execute('SELECT * FROM clients WHERE id=?',(ident,)).fetchone())
            profile=dict(con.execute('SELECT * FROM profiles WHERE id=?',(row['profile_id'],)).fetchone())
        original=state.client_config(row,profile)
        imported=original.replace('I1 = '+OFFICIAL_I1+'\n','')
        self.assertEqual(core.parse_config(state.client_config(row|{'config':imported},profile)),core.parse_config(imported))
        imported=original.replace(OFFICIAL_I1,'<r 30>')
        self.assertEqual(core.parse_config(state.client_config(row|{'config':imported},profile)),core.parse_config(imported))
        params=json.loads(profile['params']);params['I1']='<r 25>'
        self.assertIn('I1 = <r 25>',state.client_config(row,profile|{'params':json.dumps(params)}))

    def test_additional_generation_keeps_original_config(self):
        ident=self.post('clients',{'protocol':'amneziawg','version':'1.5'}).json['ids'][0]
        before=self.client.get(f'/api/clients/{ident}/config?variant=0').text
        r=self.post('clients/add-version',{'ids':[ident],'version':'3.1'})
        self.assertEqual(r.status_code,200)
        client=self.client.get('/api/clients').json['clients'][0]
        variant=client['versions'][1]['id']
        self.assertIn('I1 = '+OFFICIAL_I1,self.client.get(f'/api/clients/{ident}/config?variant={variant}').text)
        self.assertEqual(before,self.client.get(f'/api/clients/{ident}/config?variant=0').text)
