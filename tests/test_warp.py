import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import nullcontext
import test_api as base
import state
import warp


def result(stdout='',code=0): return SimpleNamespace(stdout=stdout,stderr='',returncode=code)


class WarpTests(unittest.TestCase):
    def setUp(self):
        base.ApiTests.setUp(self)
        self.folder=tempfile.TemporaryDirectory()
        self.path_patch=patch.object(warp,'DATA',Path(self.folder.name));self.path_patch.start()
        self.claim_patch=patch.object(warp,'claim_resources');self.claim_patch.start()
        self.lock_patch=patch.object(warp,'lock',side_effect=lambda **kw:nullcontext());self.lock_patch.start()

    def tearDown(self):
        self.lock_patch.stop();self.claim_patch.stop();self.path_patch.stop();self.folder.cleanup();base.ApiTests.tearDown(self)

    post=base.ApiTests.post

    def cfg(self,**kwargs): return warp.DEFAULT|{'profile_ids':[self.profile['id']]}|kwargs

    def test_default_is_off_and_status_exposes_no_keys(self):
        response=self.client.get('/api/warp');self.assertEqual(response.status_code,200)
        self.assertFalse(response.json['config']['enabled']);self.assertFalse(response.json['registered'])
        self.assertNotIn('private_key',json.dumps(response.json))
        with patch.object(warp,'run') as run:
            warp.reconcile();warp.guard_profile(self.profile)
            run.assert_not_called()

    def test_auth_and_csrf(self):
        visitor=base.web.app.test_client();csrf=visitor.get('/api/me').json['csrf']
        self.assertEqual(visitor.get('/api/warp').status_code,401)
        self.assertEqual(visitor.post('/api/warp/install',json={},headers={'X-CSRF-Token':csrf}).status_code,401)
        self.assertEqual(self.client.post('/api/warp/install',json={}).status_code,403)
        with patch.object(warp,'queue',return_value={'ok':True,'task_id':'test'}) as queue:
            self.assertEqual(self.post('warp/save',self.cfg()).status_code,202)
            self.assertEqual(queue.call_args.args,('save',self.cfg()))

    def test_invalid_settings_rejected(self):
        for cfg in [[],{'enabled':1},{'scope':'none'},{'protocol':'wireguard'},{'profile_ids':[True]},
                    {'profile_ids':[1,1]},{'profile_ids':[99999]},{'enabled':True},
                    {'dns':['127.0.0.1']},{'dns':['x; rm -rf /']},{'dns':['::1']},{'command':'curl x'}]:
            with self.assertRaises(base.core.Problem): warp.validate(cfg)
        for scope in ['all','selected']:
            self.assertEqual(warp.validate(self.cfg(enabled=True,scope=scope))['scope'],scope)

    def test_selected_guard_never_changes_host_output_or_main_default(self):
        cfg=self.cfg(enabled=True);warp.save('config.json',cfg)
        def fake(*args,**kwargs): return result('[]' if '-j' in args else '')
        with patch.object(warp,'run',side_effect=fake) as run:
            warp.guard(cfg)
            commands=[call.args for call in run.call_args_list]
        rule=next(c for c in commands if c[:3]==('ip','rule','add'))
        self.assertIn('iif',rule);self.assertIn(self.profile['interface'],rule)
        self.assertNotIn('OUTPUT',str(commands));self.assertNotIn(('table','main'),[c[-2:] for c in commands])
        self.assertTrue(any('unreachable' in c and warp.TABLE in c for c in commands))
        with patch.object(warp,'run') as run:
            warp.guard_profile(self.profile|{'id':9999});run.assert_not_called()

    def test_all_mode_guards_future_profiles_before_engine_sync(self):
        warp.save('config.json',self.cfg(enabled=True,scope='all'))
        calls=[]
        def fake(*args,**kwargs):calls.append(args);return result('[]')
        with patch.object(warp,'run',side_effect=fake),patch.object(state.ENGINE,'apply',side_effect=lambda *args:calls.append(('engine',))):
            with state.connection() as con: state.sync(con,self.profile)
        self.assertEqual(calls[-1],('engine',))
        self.assertTrue(any(c[:3]==('ip','rule','add') for c in calls[:-1]))

    def test_runtime_routes_match_only_selected_interfaces(self):
        cfg=self.cfg(enabled=True)
        def fake(*args,**kwargs):return result('[]' if '-j' in args else '')
        with patch.object(warp,'run',side_effect=fake) as run,patch.object(warp,'ipt',return_value=result(code=1)):
            warp.routing(cfg)
            commands=[c.args for c in run.call_args_list]
        rules=[c for c in commands if c[:3]==('ip','rule','add')]
        self.assertEqual(len(rules),1);self.assertIn(self.profile['interface'],rules[0])
        self.assertEqual(warp.read('routes.json',{})['profiles'][0]['id'],self.profile['id'])

    def test_disabling_cleans_owned_rules_even_after_failed_setup(self):
        cfg=self.cfg(enabled=False)
        rules=[{'priority':int(warp.PREF),'iif':self.profile['interface'],'table':int(warp.TABLE)},
               {'priority':123,'iif':'other','table':999}]
        def fake(*args,**kwargs):return result(json.dumps(rules) if '-j' in args else '')
        with patch.object(warp,'run',side_effect=fake) as run,patch.object(warp,'ipt'):
            warp.routing(cfg)
        commands=[c.args for c in run.call_args_list]
        deleted=[c for c in commands if c[:3]==('ip','rule','del')]
        self.assertEqual(len(deleted),1);self.assertIn(self.profile['interface'],deleted[0]);self.assertNotIn('other',deleted[0])

    def test_connected_requires_warp_trace_over_tunnel(self):
        with patch.object(warp,'cli',return_value=result('Status update: Connected')),patch.object(warp,'run',return_value=result('warp=off\n')):
            self.assertFalse(warp.check_connection())
        with patch.object(warp,'cli',return_value=result('Status update: Connected')),patch.object(warp,'run',return_value=result('warp=on\n')) as run:
            self.assertTrue(warp.check_connection());args=run.call_args.args
            self.assertIn('--interface',args);self.assertIn('CloudflareWARP',args)
            self.assertIn(warp.NS,args);self.assertNotIn('-k',args)

    def test_task_failure_records_error_without_secrets(self):
        warp.save('request.json',{'action':'save','payload':self.cfg(enabled=True)})
        warp.save('task.json',{'state':'queued','action':'save'})
        with self.assertRaises(base.core.Problem): warp.task()
        task=warp.read('task.json',{})
        self.assertEqual(task['state'],'failed');self.assertIn('Register WARP first',task['error'])
        self.assertFalse(warp.config()['enabled'])


    def test_reserved_policy_resources_are_not_overwritten(self):
        self.claim_patch.stop()
        for rules in [[{'priority':int(warp.PREF),'table':999}],[{'priority':20,'table':int(warp.TABLE)}]]:
            with patch.object(warp,'run',return_value=result(json.dumps(rules))) as run:
                with self.assertRaises(base.core.Problem):warp.claim_resources()
                self.assertFalse(any('replace' in c.args or 'add' in c.args for c in run.call_args_list))
        self.claim_patch.start()

    def test_transport_firewall_rules_precede_existing_rejects(self):
        commands=[]
        def fake(*args,**kw):
            commands.append(args)
            if args[:3]==('ip','netns','list'):return result(warp.NS)
            return result('[]' if '-j' in args else '',1 if '-C' in args else 0)
        with patch.object(warp,'run',side_effect=fake),patch.object(warp,'write_dns'):
            warp.network()
        host_forward=[c for c in commands if c[:3]==('iptables','-w','5') and 'FORWARD' in c]
        self.assertTrue(any('-I' in c and warp.HOST in c for c in host_forward))
        self.assertFalse(any('-A' in c for c in host_forward))

    def test_disable_saves_off_before_removing_rules(self):
        cfg=self.cfg(enabled=True);warp.save('config.json',cfg)
        warp.save('request.json',{'action':'save','payload':cfg|{'enabled':False}})
        with patch.object(warp,'run',return_value=result()),patch.object(warp,'cli'),patch.object(warp,'routing',side_effect=lambda cfg:self.assertFalse(warp.config()['enabled'])):
            warp.task()
        self.assertEqual(warp.read('task.json',{})['state'],'done')

    def test_daemon_failure_keeps_selected_interfaces_guarded(self):
        warp.save('registration.json',{'registered':True})
        warp.save('request.json',{'action':'save','payload':self.cfg(enabled=True)})
        with patch.object(warp,'guard') as guard,patch.object(warp,'run',side_effect=base.core.Problem('daemon failed',503)):
            with self.assertRaises(base.core.Problem):warp.task()
        self.assertTrue(warp.config()['enabled']);guard.assert_called_once()
        self.assertEqual(warp.read('task.json',{})['state'],'failed')

    def test_reconciler_reads_config_after_acquiring_lock(self):
        cfg=self.cfg(enabled=True);warp.save('config.json',cfg)
        def acquired(**kw):
            warp.save('config.json',cfg|{'enabled':False})
            return nullcontext()
        with patch.object(warp,'lock',side_effect=acquired),patch.object(warp,'run') as run:
            warp.reconcile();run.assert_not_called()


    def test_return_routes_precede_daemon_policy_without_changing_its_rules(self):
        cfg=self.cfg(enabled=True)
        def fake(*args,**kw):return result('[]' if '-j' in args else '')
        with patch.object(warp,'run',side_effect=fake) as run,patch.object(warp,'ipt',return_value=result(code=1)):
            warp.routing(cfg)
        commands=[c.args for c in run.call_args_list]
        self.assertTrue(any(c[:3]==('ip','-n',warp.NS) and 'replace' in c and c[-2:]==('table','local') for c in commands))
        self.assertFalse(any(c[:3]==('ip','-n',warp.NS) and 'rule' in c for c in commands))

    def test_selected_ipv6_is_blocked_and_disable_removes_only_owned_rule(self):
        with patch.object(warp,'run',return_value=result(code=1)) as run:
            warp.block_ipv6('test0')
        args=run.call_args.args
        self.assertEqual(args[:4],('ip6tables','-w','5','-I'))
        self.assertIn('test0',args);self.assertIn('ac-warp-ipv6',args)
        with patch.object(warp,'run',return_value=result()) as run:
            warp.block_ipv6('test0',False)
        self.assertIn('-D',run.call_args.args)

if __name__=='__main__':unittest.main(verbosity=2)
