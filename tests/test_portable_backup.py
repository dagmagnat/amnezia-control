import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_api as fixtures

web, state, core = fixtures.web, fixtures.state, fixtures.core
import warp
from manage import provision


class PortableBackupTest(unittest.TestCase):
    password = 'test-password-123'

    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.folder = Path(folder)
        self.engine = fixtures.FakeEngine()
        self.engine.calls = []
        self.enterContext(patch.object(state, 'DATA', self.folder))
        self.enterContext(patch.object(state, 'DB', self.folder / 'control.db'))
        self.enterContext(patch.object(warp, 'DATA', self.folder / 'warp'))
        self.enterContext(patch.object(state, 'ENGINE', self.engine))
        self.enterContext(patch.object(core, 'command', fixtures.fake_command))
        self.enterContext(patch.object(web, 'command', fixtures.fake_command))
        self.enterContext(patch.object(core.shutil, 'which', lambda binary: binary))
        self.enterContext(patch.dict('os.environ', {'AC_CONFIG_ROOT': str(self.folder / 'etc')}))
        self.login('source')

    def login(self, user):
        state.initialize()
        with state.connection() as con:
            state.put(con, 'admin_user', user)
            state.put(con, 'admin_password', web.hash_password(self.password))
            state.put(con, 'panel_ip', '192.0.2.12' if user == 'source' else '192.0.2.42')
        self.client = web.app.test_client()
        csrf = self.client.get('/api/me').json['csrf']
        result = self.client.post('/api/login', json={'username': user, 'password': self.password},
                                  headers={'X-CSRF-Token': csrf})
        self.assertEqual(result.status_code, 200)
        self.csrf = result.json['csrf']

    def post(self, path, **kwargs):
        return self.client.post('/api/' + path, headers={'X-CSRF-Token': self.csrf}, **kwargs)

    def source_backup(self):
        profile = self.post('profiles', json={'name': 'Legacy', 'protocol': 'wireguard',
                            'endpoint': 'vpn.example.com:52080', 'port': 52080})
        self.assertEqual(profile.status_code, 201, profile.json)
        result = self.post('clients', json={'name': 'Router', 'profile_id': profile.json['id']})
        self.assertEqual(result.status_code, 201, result.json)
        client_id = self.client.get('/api/summary').json['clients'][0]['id']
        result = self.post('clients/add-version', json={'ids': [client_id], 'version': '3.1', 'set_primary': True})
        self.assertIn(result.status_code, (200, 201), result.json)
        warp.save('config.json', warp.DEFAULT | {'enabled': True, 'scope': 'all'})
        response = self.client.get('/api/backup/portable')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertNotIn(b'admin_password', response.data)
        return response.data

    def upload(self, route, raw, **extra):
        return self.post(route, data={'backup': (io.BytesIO(raw), 'panel.ac-backup.json'), **extra})

    def fresh_destination(self, starters=False):
        state.DB = self.folder / 'destination.db'
        warp.save('config.json', warp.DEFAULT)
        self.login('destination')
        if starters:
            provision('192.0.2.42')

    def test_roundtrip_preserves_identity_and_destination_access(self):
        raw = self.source_backup()
        original = json.loads(raw)
        self.assertFalse(self.upload('restore/preview', raw).json['can_restore'])
        self.fresh_destination(starters=True)
        preview = self.upload('restore/preview', raw)
        self.assertEqual(preview.status_code, 200, preview.json)
        self.assertTrue(preview.json['can_restore'])
        self.assertEqual(preview.json['variants'], 1)
        self.assertEqual(self.upload('restore', raw, password='wrong', digest=preview.json['digest']).status_code, 403)
        self.assertEqual(self.upload('restore', raw, password=self.password, digest='stale').status_code, 409)
        result = self.upload('restore', raw, password=self.password, digest=preview.json['digest'])
        self.assertEqual(result.status_code, 200, result.json)
        recovery = self.folder / result.json['recovery'] / 'control.db'
        self.assertTrue(recovery.is_file())
        restored = self.client.get('/api/backup/portable').json
        for table in ('clients', 'profiles', 'client_variants'):
            self.assertEqual(restored[table], original[table])
        self.assertFalse(warp.config()['enabled'])
        self.assertTrue(self.client.get('/api/warp').json['restore_pending'])
        self.assertEqual(restored['warp'], original['warp'])
        self.assertEqual(self.client.get('/api/me').json['user'], 'destination')
        self.assertEqual(self.client.get('/api/summary').json['panel']['ip'], '192.0.2.42')

    def test_failed_start_rolls_back_and_unsupported_file_is_rejected(self):
        raw = self.source_backup()
        self.fresh_destination()
        invalid = json.loads(raw)
        invalid['profiles'][0]['interface'] = '../../other'
        self.assertEqual(self.upload('restore/preview', json.dumps(invalid).encode()).status_code, 400)
        digest = self.upload('restore/preview', raw).json['digest']
        self.engine.fail = True
        result = self.upload('restore', raw, password=self.password, digest=digest)
        self.assertEqual(result.status_code, 503, result.json)
        self.assertIn('Changes rolled back', result.json['error'])
        panel = self.client.get('/api/summary').json
        self.assertEqual(panel['clients'], [])
        self.assertEqual(panel['profiles'], [])


if __name__ == '__main__':
    unittest.main()
