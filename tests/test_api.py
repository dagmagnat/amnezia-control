import base64
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

TEMP=tempfile.TemporaryDirectory()
os.environ['AMNEZIA_CONTROL_DATA']=TEMP.name
os.environ['AC_CONFIG_ROOT']=str(Path(TEMP.name)/'etc')
os.environ['AMNEZIA_CONTROL_SECRET']='test-secret-please-do-not-use'
sys.path[:0]=[str(Path('work/test-deps').resolve()),str(Path('backend').resolve())]
import core
import state
import app as web

counter=0
def fake_command(*args,input=None):
    global counter
    if args[-1]=='genkey' or args[-1]=='genpsk':
        counter+=1;return base64.b64encode(bytes([counter%255+1])*32).decode()
    if args[-1]=='pubkey': return base64.b64encode(__import__('hashlib').sha256(input.strip().encode()).digest()).decode()
    return ''

class FakeEngine:
    fail=False
    samples={}
    calls=[]
    def apply(self,p,peers):
        if self.fail: raise core.Problem('Injected engine failure',503)
        self.calls.append((p,peers))
    def stats(self,p): return self.samples,''

class ApiTests(unittest.TestCase):
    def setUp(self):
        state.DB=Path(TEMP.name)/('test-'+secrets_token()+'.db')
        state.initialize()
        with state.connection() as con:
            state.put(con,'admin_user','test');state.put(con,'admin_password',web.hash_password('test-password-123'))
        self.engine=FakeEngine();self.engine.samples={};self.engine.calls=[]
        self.patches=[patch.object(state,'ENGINE',self.engine),patch.object(core,'command',fake_command),patch.object(web,'command',fake_command),patch.object(web.shutil,'which',lambda x:'/usr/bin/'+x)]
        for p in self.patches:p.start()
        self.client=web.app.test_client();self.csrf=self.client.get('/api/me').json['csrf']
        response=self.post('login',{'username':'test','password':'test-password-123'})
        self.csrf=response.json['csrf']
        self.post('profiles',{'name':'AWG','protocol':'amneziawg','version':'3.1','endpoint':'vpn.example.com:51821','port':51821})
        self.profile=self.client.get('/api/summary').json['profiles'][0]
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def post(self,path,payload): return self.client.post('/api/'+path,json=payload,headers={'X-CSRF-Token':self.csrf})
    def test_login_csrf_no_demo(self):
        visitor=web.app.test_client()
        self.assertEqual(visitor.get('/api/clients').status_code,401)
        self.assertEqual(visitor.post('/api/clients',json={}).status_code,403)
        summary=self.client.get('/api/summary').json
        self.assertEqual(summary['clients'],[])
        self.assertNotIn('private_key',summary['profiles'][0])
        with self.client.get('/') as response: self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/api/missing').status_code,404)
    def test_client_lifecycle_and_download(self):
        r=self.post('clients',{'profile_id':self.profile['id'],'count':2})
        self.assertEqual(r.status_code,201,r.json)
        rows=self.client.get('/api/clients').json['clients'];self.assertEqual([x['name'] for x in rows],['User 01','User 02'])
        ident=rows[0]['id'];self.assertNotIn('private_key',rows[0])
        content=self.client.get(f'/api/clients/{ident}/config').text
        self.assertIn('HeaderProtectionKey =',content);self.assertIn('Endpoint = vpn.example.com:51821',content)
        self.assertEqual(self.client.get(f'/api/clients/{ident}/qr').mimetype,'image/png')
        edit=self.client.patch(f'/api/clients/{ident}',json={'name':'Телефон','enabled':False,'endpoint':'vpn.рф:5555'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(edit.status_code,200,edit.json)
        self.assertIn('xn--',self.client.get(f'/api/clients/{ident}/config').text)
        self.assertEqual(self.client.delete(f'/api/clients/{ident}',headers={'X-CSRF-Token':self.csrf}).status_code,200)
        r=self.post('clients',{'profile_id':self.profile['id']})
        self.assertEqual(self.client.get('/api/clients').json['clients'][-1]['name'],'User 03')
    def test_failure_rolls_back_no_fake_key(self):
        self.engine.fail=True
        self.assertEqual(self.post('clients',{'profile_id':self.profile['id']}).status_code,503)
        self.assertEqual(self.client.get('/api/clients').json['clients'],[])
        with patch.object(core,'command',side_effect=core.Problem('wg missing',503)):
            self.engine.fail=False
            self.assertEqual(self.post('clients',{'profile_id':self.profile['id']}).status_code,503)
    def test_quota_expiry_and_reenable(self):
        r=self.post('clients',{'profile_id':self.profile['id'],'quota_bytes':100,'expires_at':int(time.time())+500});ident=r.json['ids'][0]
        row=self.client.get('/api/clients').json['clients'][0]
        self.engine.samples={row['public_key']:{'rx':60,'tx':50,'handshake':int(time.time())}}
        state.refresh(); row=self.client.get('/api/clients').json['clients'][0]
        self.assertEqual(row['used_bytes'],110);self.assertEqual(row['blocked_reason'],'quota')
        r=self.client.patch(f'/api/clients/{ident}',json={'quota_bytes':1000},headers={'X-CSRF-Token':self.csrf});self.assertEqual(r.status_code,200)
        self.assertEqual(self.client.get('/api/clients').json['clients'][0]['blocked_reason'],'')
        self.engine.samples={row['public_key']:{'rx':10,'tx':5,'handshake':0}}
        state.refresh();self.assertEqual(self.client.get('/api/clients').json['clients'][0]['used_bytes'],125)
    def test_import_rejects_wrong_server_and_hooks(self):
        private,public=core.keys('awg')
        text='[Interface]\nPrivateKey = '+private+'\nAddress = 10.77.1.10/32\n\n[Peer]\nPublicKey = '+public+'\nEndpoint = example.com:51821\nAllowedIPs = 0.0.0.0/0\n'
        r=self.client.post('/api/import',data={'profile_id':self.profile['id'],'file':(io.BytesIO(text.encode()),'phone.conf')},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(r.status_code,409,r.json)
        with self.assertRaises(core.Problem):core.parse_config(text.replace('Address =','PostUp = curl evil\nAddress ='))
    def test_password_and_backup(self):
        r=self.client.patch('/api/settings',json={'current_password':'wrong','password':'new-secret-password'},headers={'X-CSRF-Token':self.csrf});self.assertEqual(r.status_code,403)
        r=self.client.get('/api/backup');self.assertEqual(r.status_code,200);self.assertIn('CREATE TABLE profiles',r.text)
    def test_profile_validation_and_unknown_versions(self):
        r=self.post('profiles',{'protocol':'amneziawg','version':'2.5','endpoint':'a.com:1234','port':1234});self.assertEqual(r.status_code,400)
        with self.assertRaises(core.Problem):core.endpoint('example.com:22\nPrivateKey=secret')
        with self.assertRaises(core.Problem):core.parameters('3.1',{'S1':'0'})
    def test_true_wireguard_config_no_awg_fields(self):
        r=self.post('profiles',{'protocol':'wireguard','endpoint':'host.example:51822','port':51822})
        self.assertEqual(r.status_code,201,r.json)
        r=self.post('clients',{'profile_id':r.json['id'],'name':'WG phone'})
        content=self.client.get('/api/clients/'+str(r.json['ids'][0])+'/config').text
        self.assertNotIn('HeaderProtectionKey',content);self.assertNotIn('Jc',content)

class CoreTests(unittest.TestCase):
    def test_nat_is_in_correct_table(self):
        p={'private_key':'secret','port':1234,'interface':'acwg1','address':'10.77.1.1/24','params':'{}'}
        text=core.interface_text(p,[])
        self.assertIn('iptables -t nat -C POSTROUTING',text)
        self.assertIn('SaveConfig = false',text)


def secrets_token():return __import__('secrets').token_hex(5)

# Additional regression cases for migration and key preservation.
class MigrationTests(unittest.TestCase):
    def test_legacy_server_identity_is_preserved(self):
        old=state.DB;state.DB=Path(TEMP.name)/'legacy.db'
        root=Path(TEMP.name)/'migration-etc'
        private=base64.b64encode(b'z'*32).decode()
        conf=root/'wireguard'/'awg0.conf';conf.parent.mkdir(parents=True,exist_ok=True)
        conf.write_text('[Interface]\nPrivateKey = '+private+'\nAddress = 10.8.0.1/24\nListenPort = 51820\n',encoding='utf-8')
        try:
            with state.connection() as con:
                con.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                state.put(con,'vpn_engine','amneziawg');state.put(con,'vpn_interface','awg0');state.put(con,'endpoint','vpn.example:51820')
            with patch.dict(os.environ,{'AC_CONFIG_ROOT':str(root)}),patch.object(state,'command',fake_command):
                state.initialize();state.initialize()
            with state.connection() as con:
                rows=con.execute('SELECT * FROM profiles').fetchall()
                self.assertEqual(len(rows),1);self.assertEqual(rows[0]['private_key'],private)
                self.assertEqual(rows[0]['version'],'legacy')
            self.assertIn(private,conf.read_text())
        finally:state.DB=old

class ImportSuccessTests(unittest.TestCase):
    setUp=ApiTests.setUp
    tearDown=ApiTests.tearDown
    post=ApiTests.post
    def test_valid_import_preserves_client_private_key_and_routes(self):
        private,_=core.keys('awg')
        params=json.loads(self.profile['params'])
        text='[Interface]\nPrivateKey = '+private+'\nAddress = 10.77.1.50/32\nDNS = 9.9.9.9\n'
        text+='\n'.join(k+' = '+v for k,v in params.items())
        text+='\n[Peer]\nPublicKey = '+self.profile['public_key']+'\nEndpoint = vpn.example.com:51821\nAllowedIPs = 1.1.1.1/32\n'
        r=self.client.post('/api/import',data={'profile_id':self.profile['id'],'file':(io.BytesIO(text.encode()),'phone.conf')},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(r.status_code,201,r.json)
        exported=self.client.get('/api/clients/'+str(r.json['id'])+'/config').text
        self.assertIn(private,exported);self.assertIn('AllowedIPs = 1.1.1.1/32',exported);self.assertIn('DNS = 9.9.9.9',exported)


class AutoClientTests(unittest.TestCase):
    setUp=ApiTests.setUp
    tearDown=ApiTests.tearDown
    post=ApiTests.post
    def test_legacy_is_not_reused_for_amnezia(self):
        with state.connection() as con:
            con.execute("UPDATE profiles SET version='legacy',params='{}',name='Existing VPN' WHERE id=?",(self.profile['id'],))
        response=self.post('clients',{'protocol':'amneziawg','version':'3.1','count':2})
        self.assertEqual(response.status_code,201,response.json)
        self.assertNotEqual(response.json['profile_id'],self.profile['id'])
        for ident in response.json['ids']:
            text=self.client.get(f'/api/clients/{ident}/config').text
            for field in ['HeaderProtectionKey =','ContentPaddingAddition =','RandomTrailers = on','S4 =']:self.assertIn(field,text)
        with state.connection() as con:
            self.assertEqual(con.execute('SELECT version FROM profiles WHERE id=?',(self.profile['id'],)).fetchone()['version'],'legacy')
    def test_reuses_one_connection_for_generation_and_all_versions(self):
        for version in ['1.0','1.5','2.0','3.0','3.1']:
            first=self.post('clients',{'protocol':'amneziawg','version':version})
            self.assertEqual(first.status_code,201,first.json)
            second=self.post('clients',{'protocol':'amneziawg','version':version})
            self.assertEqual(first.json['profile_id'],second.json['profile_id'])
            text=self.client.get('/api/clients/'+str(first.json['ids'][0])+'/config').text
            self.assertIn('Jc =',text)
            if version in ('2.0','3.0','3.1'):self.assertIn('S3 =',text)
        standard=self.post('clients',{'protocol':'wireguard'})
        self.assertEqual(standard.status_code,201,standard.json)
        self.assertNotIn('Jc =',self.client.get('/api/clients/'+str(standard.json['ids'][0])+'/config').text)
    def test_engine_failure_has_no_protocol_fallback(self):
        self.engine.fail=True
        response=self.post('clients',{'protocol':'amneziawg','version':'2.0'})
        self.assertEqual(response.status_code,503,response.json)
        with state.connection() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM profiles').fetchone()[0],1)
        self.assertEqual(self.client.get('/api/clients').json['clients'],[])




class TunnelParserTests(unittest.TestCase):
    def test_generated_config_accepts_repeated_firewall_hooks(self):
        from tunnel import read_network_settings
        p={'private_key':'not-used-here','port':51821,'interface':'acawg2','address':'10.77.1.1/24','params':'{}'}
        text=core.interface_text(p,[])
        self.assertGreater(text.count('PostUp ='),1)
        fields=read_network_settings(text)
        self.assertEqual(fields,{'Address':'10.77.1.1/24','ListenPort':'51821','MTU':'1380'})
        self.assertNotIn('PostUp',fields)

if __name__=='__main__':unittest.main(verbosity=2)
