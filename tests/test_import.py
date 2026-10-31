"""Migration regression tests: identities, preview, failure and archive boundaries."""
import io
import unittest
import json
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import patch
import test_api as base
import importer
import core
import state

class ImportTests(unittest.TestCase):
    setUp=base.ApiTests.setUp
    tearDown=base.ApiTests.tearDown
    post=base.ApiTests.post
    # Reuse auth/engine fixture, not inherited API cases.
    def request_import(self, stage, files, options=None):
        data=dict(options or {});data['files']=[(io.BytesIO(text if isinstance(text,bytes) else text.encode()),name) for name,text in files.items()]
        return self.client.post('/api/import/'+stage,data=data,headers={'X-CSRF-Token':self.csrf})
    def fixture(self, version='wg', private=True):
        server,_=core.keys('wg');client,public=core.keys('wg');psk=core.key(base.fake_command('wg','genpsk'))
        params=core.parameters(version) if version!='wg' else {}
        comment=('# PrivateKey = '+client+'\n') if private else ''
        text='[Interface]\nPrivateKey = '+server+'\nAddress = 10.88.1.1/24\nListenPort = 53080\nMTU = 1420\n'+''.join(k+' = '+v+'\n' for k,v in params.items())
        text+='PostUp = curl https://never-execute.invalid\nPostUp = rm -f never\n# Client = Phone\n'+comment+'[Peer]\nPublicKey = '+public+'\nPresharedKey = '+psk+'\nAllowedIPs = 10.88.1.2/32\n'
        server_public=base.fake_command('wg','pubkey',input=server+'\n')
        conf='[Interface]\nPrivateKey = '+client+'\nAddress = 10.88.1.2/24\nDNS = 9.9.9.9\nMTU = 1320\n'+''.join(k+' = '+v+'\n' for k,v in params.items())
        conf+='[Peer]\nPublicKey = '+server_public+'\nPresharedKey = '+psk+'\nEndpoint = vpn.example.com:53080\nAllowedIPs = 0.0.0.0/0\nPersistentKeepalive = 15\n'
        return {'vpn.conf':text,'phone.conf':conf},server,client
    def options(self):return {'mode':'server','server_file':'vpn.conf','endpoint':'vpn.example.com:53080'}
    def test_server_and_client_exact_import_and_idempotence(self):
        files,server,client=self.fixture('3.1'); opts=self.options()
        result=self.request_import('preview',files,opts);self.assertEqual(result.status_code,200,result.json)
        self.assertTrue(result.json['can_apply'],result.json);self.assertEqual(result.json['counts']['create'],1)
        self.assertNotIn(server,result.text);self.assertNotIn(client,result.text)
        self.assertEqual(self.client.get('/api/clients').json['clients'],[])
        opts['token']=result.json['token']; applied=self.request_import('apply',files,opts)
        self.assertEqual(applied.status_code,201,applied.json)
        with state.connection() as con:
            p=dict(con.execute('SELECT * FROM profiles WHERE id=?',(applied.json['profile_id'],)).fetchone())
            row=dict(con.execute('SELECT * FROM clients').fetchone())
            self.assertEqual(p['private_key'],server);self.assertEqual(row['private_key'],client);self.assertEqual(p['mtu'],1420)
        exported=core.parse_config(self.client.get('/api/clients/'+str(row['id'])+'/config').text)
        self.assertEqual(exported,core.parse_config(files['phone.conf']))
        again=self.request_import('preview',files,self.options());self.assertEqual(again.json['counts']['skip'],1,again.json)
        self.assertTrue((state.DATA/'import-backups'/applied.json['backup']).exists())
    def test_private_comment_and_missing_client_key(self):
        for has_key in (True,False):
            files,server,client=self.fixture(private=has_key);files.pop('phone.conf')
            result=self.request_import('preview',files,self.options())
            self.assertTrue(result.json['can_apply'],result.json)
            self.assertEqual(result.json['clients'][0]['downloadable'],has_key)
            self.assertFalse(result.json['clients'][0]['original_config'])
    def test_changed_plan_and_engine_failure_do_not_import(self):
        files,_,_=self.fixture();opts=self.options();result=self.request_import('preview',files,opts)
        opts['token']=result.json['token'];files['phone.conf']=files['phone.conf'].replace('9.9.9.9','1.1.1.1')
        self.assertEqual(self.request_import('apply',files,opts).status_code,409)
        opts['token']=self.request_import('preview',files,opts).json['token']
        self.engine.fail=True
        with patch.object(importer,'cleanup_profile') as cleanup:
            applied=self.request_import('apply',files,opts);self.assertEqual(applied.status_code,503,applied.json);cleanup.assert_called_once()
        self.assertEqual(self.client.get('/api/clients').json['clients'],[])
        self.assertEqual(len(self.client.get('/api/summary').json['profiles']),1)
    def test_original_comment_key_mismatch_blocks(self):
        files,_,client=self.fixture();files.pop('phone.conf');bad,_=core.keys('wg')
        files['vpn.conf']=files['vpn.conf'].replace('# PrivateKey = '+client,'# PrivateKey = '+bad)
        result=self.request_import('preview',files,self.options())
        self.assertFalse(result.json['can_apply']);self.assertIn('mismatch',' '.join(result.json['errors']))
    def test_repeated_peer_sections_and_archive_path_checks(self):
        files,_,_=self.fixture();buf=io.BytesIO()
        with tarfile.open(fileobj=buf,mode='w:gz') as archive:
            for name,text in files.items():
                raw=text.encode();item=tarfile.TarInfo(name);item.size=len(raw);archive.addfile(item,io.BytesIO(raw))
        result=self.request_import('preview',{'backup.tar.gz':buf.getvalue()},self.options())
        self.assertTrue(result.json['can_apply'],result.json)
        for path in ('../outside.conf','/etc/evil.conf','C:/evil.conf'):
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:z.writestr(path,'[Interface]')
            self.assertEqual(self.request_import('preview',{'bad.zip':out.getvalue()},self.options()).status_code,400)
        out=io.BytesIO()
        with tarfile.open(fileobj=out,mode='w:gz') as archive:
            item=tarfile.TarInfo('link.conf');item.type=tarfile.SYMTYPE;item.linkname='/etc/shadow';archive.addfile(item)
        self.assertEqual(self.request_import('preview',{'bad.tgz':out.getvalue()},self.options()).status_code,400)
    def test_complete_adopted_peer_without_duplicate(self):
        files,_,client=self.fixture('3.1');opts=self.options();opts['token']=self.request_import('preview',files,opts).json['token']
        self.assertEqual(self.request_import('apply',files,opts).status_code,201)
        with state.connection() as con:
            con.execute("UPDATE clients SET private_key='',config='' ");pid=con.execute('SELECT profile_id FROM clients').fetchone()[0]
        opts={'mode':'clients','profile_id':pid}
        conf={'phone.conf':files['phone.conf']};result=self.request_import('preview',conf,opts)
        self.assertEqual(result.json['counts']['complete'],1,result.json)
        opts['token']=result.json['token'];self.assertEqual(self.request_import('apply',conf,opts).status_code,201)
        rows=self.client.get('/api/clients').json['clients'];self.assertEqual(len(rows),1);self.assertTrue(rows[0]['downloadable'])
    def test_wg_compatible_legacy_amnezia_fields_preserved(self):
        files,_,_=self.fixture()
        legacy='Jc = 100\nJmin = 20\nJmax = 100\nS1 = 0\nS2 = 0\nH1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\nI1 = <b 0x123456>\n'
        files['phone.conf']=files['phone.conf'].replace('[Peer]',legacy+'[Peer]')
        opts=self.options();result=self.request_import('preview',files,opts);self.assertTrue(result.json['can_apply'],result.json)
        opts['token']=result.json['token'];self.assertEqual(self.request_import('apply',files,opts).status_code,201)
        row=self.client.get('/api/clients').json['clients'][0]
        self.assertEqual(row['protocol'],'amneziawg')
        exported=self.client.get('/api/clients/'+str(row['id'])+'/config').text
        self.assertEqual(core.parse_config(exported),core.parse_config(files['phone.conf']))
    def test_unsafe_or_modern_awg_cannot_be_downgraded(self):
        files,_,_=self.fixture();files['phone.conf']=files['phone.conf'].replace('[Peer]','Jc = 4\nJmin = 40\nJmax = 120\nS1 = 64\nS2 = 64\nH1 = 100\nH2 = 200\nH3 = 300\nH4 = 400\n[Peer]')
        result=self.request_import('preview',files,self.options());self.assertFalse(result.json['can_apply'])
        files['phone.conf']=files['phone.conf'].replace('[Peer]','PostUp = echo unsafe\n[Peer]')
        result=self.request_import('preview',files,self.options());self.assertIn('hooks',' '.join(result.json['errors']))

    def test_one_auto_selected_server_token_and_reused_peer_key(self):
        files,_,_=self.fixture();opts={'mode':'server','endpoint':'vpn.example.com:53080'}
        plan=self.request_import('preview',files,opts).json
        opts['server_file']='vpn.conf';opts['token']=plan['token']
        self.assertEqual(self.request_import('apply',files,opts).status_code,201)
        files={name:text.replace('10.88.1.','10.89.1.').replace('53080','53081') for name,text in files.items()}
        opts={'mode':'server','endpoint':'vpn.example.com:53081'}
        plan=self.request_import('preview',files,opts).json
        self.assertTrue(plan['can_apply'],plan);opts['token']=plan['token']
        self.assertEqual(self.request_import('apply',files,opts).status_code,201)
        self.assertEqual(len(self.client.get('/api/clients').json['clients']),2)

    def test_archive_expansion_and_damaged_input(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:archive.writestr('large.conf',b'x'*(2*1024*1024+1))
        self.assertEqual(self.request_import('preview',{'large.zip':out.getvalue()},self.options()).status_code,400)
        self.assertEqual(self.request_import('preview',{'bad.zip':b'broken'},self.options()).status_code,400)
        self.assertEqual(self.request_import('preview',{'unknown.conf':b'\xff\xfe'},self.options()).status_code,400)

    def test_existing_profile_rollback_marks_new_peers_disabled(self):
        created=self.post('clients',{'profile_id':self.profile['id']}).json['ids'][0]
        text=self.client.get('/api/clients/'+str(created)+'/config').text
        private,_=core.keys('awg')
        interface,peer=core.parse_config(text)
        text=text.replace(interface['PrivateKey'],private).replace(interface['Address'],'10.77.1.90/32')
        files={'new.conf':text};opts={'mode':'clients','profile_id':self.profile['id']}
        plan=self.request_import('preview',files,opts).json;self.assertTrue(plan['can_apply'],plan);opts['token']=plan['token']
        with patch.object(self.engine,'apply',side_effect=[core.Problem('Injected partial failure',503),None]) as apply:
            result=self.request_import('apply',files,opts);self.assertEqual(result.status_code,503,result.json)
            restored=apply.call_args_list[-1].args[1]
            self.assertTrue(any(p['address']=='10.77.1.90/32' and not p['enabled'] for p in restored))
            self.assertTrue(any(p['enabled'] for p in restored))
        self.assertEqual(len(self.client.get('/api/clients').json['clients']),1)

if __name__=='__main__':
    import unittest
    unittest.main(verbosity=2)
