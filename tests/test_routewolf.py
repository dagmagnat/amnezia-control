import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_api as base
import core
import routewolf
import state


class RouteWolfApiTests(unittest.TestCase):
    setUp = base.ApiTests.setUp
    tearDown = base.ApiTests.tearDown
    post = base.ApiTests.post

    def test_wrapped_profile_exports_separate_credentials_and_no_phone_qr(self):
        with state.connection() as con:
            state.put(con, 'vpn_host', 'vpn.example.com')
        with patch.object(routewolf, 'bind_host', return_value='192.0.2.4'):
            wrapped = self.post('clients', {'protocol': 'routewolf', 'count': 2})
            direct = self.post('clients', {'protocol': 'wireguard'})
        self.assertEqual(wrapped.status_code, 201, wrapped.json)
        self.assertEqual(direct.status_code, 201, direct.json)
        self.assertEqual(wrapped.json['udp_port'], 51988)
        profiles = self.client.get('/api/summary').json['profiles']
        transport_profile = next(p for p in profiles if p['id'] == wrapped.json['profile_id'])
        self.assertEqual(transport_profile['protocol'], 'wireguard')
        self.assertEqual(transport_profile['version'], 'routewolf')
        self.assertNotEqual(transport_profile['port'], transport_profile['udp_port'])
        keys = set()
        for ident in wrapped.json['ids']:
            export = self.client.get(f'/api/clients/{ident}/config')
            self.assertIn('Endpoint = vpn.example.com:51988', export.text)
            self.assertIn('-routewolf.conf', export.headers['Content-Disposition'])
            keys.add(export.text.split('[RouteWolf]\nKey = ')[1].strip())
            self.assertEqual(self.client.get(f'/api/clients/{ident}/qr').status_code, 409)
        self.assertEqual(len(keys), 2)
        self.assertTrue(all(len(key) == 64 for key in keys))
        ident = direct.json['ids'][0]
        self.assertNotIn('[RouteWolf]', self.client.get(f'/api/clients/{ident}/config').text)
        self.assertEqual(self.client.get(f'/api/clients/{ident}/qr').mimetype, 'image/png')

    def test_keys_change_without_restarting_other_clients(self):
        profile = {'protocol': 'wireguard', 'version': 'routewolf', 'interface': 'acwg9',
                   'port': 52001, 'endpoint': 'vpn.example.com:51988'}
        peers = [{'preshared_key': base64.b64encode(bytes([i]) * 32).decode(), 'enabled': 1} for i in (1, 2)]
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(routewolf, 'CONFIG_DIR', Path(folder)), patch.object(routewolf, 'install_binary'), \
                 patch.object(routewolf, 'bind_host', return_value='192.0.2.4'), patch.object(core, 'command') as command:
                routewolf.sync(profile, peers)
                path = Path(folder) / 'acwg9.json'
                self.assertEqual(len(json.loads(path.read_text())['Keys']), 2)
                peers[0]['enabled'] = 0
                routewolf.sync(profile, peers)
                self.assertEqual(json.loads(path.read_text())['Keys'], [routewolf.key_for_peer(peers[1]['preshared_key'])])
                self.assertNotIn('restart', [call.args[1] for call in command.call_args_list])
