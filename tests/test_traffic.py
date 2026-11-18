import json
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_api as base
import state
import traffic


class TrafficTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.p=patch.object(traffic,'path',lambda:Path(self.temp.name)/'traffic.db');self.p.start()
        traffic._baselines={};traffic._sessions={};traffic._last=0
        traffic.initialize()
    def tearDown(self):
        self.p.stop();self.temp.cleanup()
    def sample(self, now, rx, tx, peer='one', client=1, hs=None):
        return (peer,client,{'rx':rx,'tx':tx,'handshake':now if hs is None else hs},True)
    def test_initial_baseline_direction_variants_and_sessions(self):
        traffic.record([self.sample(1000,1000000,9000000)],now=1000)
        self.assertFalse(traffic.report(now=1000)['points'])
        traffic.record([self.sample(1010,1001000,9005000),self.sample(1010,400,600,'two')],now=1010)
        r=traffic.report(now=1010);c=r['clients'][0]
        self.assertEqual((c['upload_bps'],c['download_bps']),(100,500))
        self.assertEqual(c['average_download_bps'],500)
        traffic.record([self.sample(1020,1002000,9006000),self.sample(1020,600,1000,'two')],now=1020)
        r=traffic.report(now=1020)
        self.assertEqual(sum(p['upload'] for p in r['points']),2200)
        self.assertEqual(r['clients'][0]['download_bps'],140)
        self.assertEqual(r['points'][0]['online_max'],1)
    def test_individual_history_isolated_and_variants_aggregated(self):
        traffic.record([self.sample(1000,0,0),self.sample(1000,0,0,'variant'),self.sample(1000,0,0,'other',2)],now=1000)
        traffic.record([self.sample(1010,100,200),self.sample(1010,300,400,'variant'),self.sample(1010,999,888,'other',2)],now=1010)
        one=traffic.report(now=1010,client_id=1)
        self.assertEqual(len(one['clients']),1)
        self.assertEqual(one['points'][0]['upload'],400)
        self.assertEqual(one['points'][0]['download'],600)
        self.assertEqual(one['clients'][0]['session_count'],1)
        self.assertEqual(one['clients'][0]['total_online_seconds'],10)
        self.assertEqual(traffic.report(now=1010,client_id=2)['points'][0]['upload'],999)

    def test_time_sessions_offline_gap_and_restart(self):
        traffic.record([self.sample(1000,0,0)],now=1000)
        traffic.record([self.sample(1010,10,20)],now=1010)
        traffic.record([self.sample(1020,10,20,hs=1)],now=1020)
        c=traffic.report(now=1020)['clients'][0]
        self.assertEqual(c['total_online_seconds'],10)
        self.assertEqual(c['session_seconds'],0)
        traffic.record([self.sample(1030,20,40)],now=1030)
        traffic.record([self.sample(1040,30,60)],now=1040)
        c=traffic.report(now=1040)['clients'][0]
        self.assertEqual(c['session_count'],2)
        self.assertEqual(c['average_session_seconds'],10)
        traffic.initialize()
        traffic.record([self.sample(1200,200,400)],now=1200)
        c=traffic.report(now=1200)['clients'][0]
        self.assertEqual(c['total_online_seconds'],20)
        self.assertEqual(c['session_count'],3)
        self.assertEqual(c['session_seconds'],0)

    def test_unavailable_peer_does_not_bridge_session_time(self):
        traffic.record([self.sample(1000,0,0)],now=1000)
        traffic.record([],now=1010,partial=True)
        traffic.record([self.sample(1020,1000,2000)],now=1020)
        c=traffic.report(now=1020)['clients'][0]
        self.assertEqual(c['session_seconds'],0)
        self.assertEqual(c['total_online_seconds'],0)
        self.assertEqual(c['session_count'],2)

    def test_individual_history_retention_and_failed_write(self):
        traffic.record([self.sample(1000,0,0)],now=1000)
        traffic.record([self.sample(1010,10,20)],now=1010)
        before=traffic._last
        with patch.object(traffic,'connect',side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):traffic.record([self.sample(1020,20,40)],now=1020)
        self.assertEqual(traffic._last,before)
        self.assertEqual(traffic.report(now=1010)['clients'][0]['total_online_seconds'],10)
        traffic.record([self.sample(40*86400,20,40)],now=40*86400)
        with closing(traffic.connect()) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM client_buckets').fetchone()[0],0)

    def test_restart_keeps_maximum_but_not_synthetic_current_speed(self):
        traffic.record([self.sample(1000,1000,2000)],now=1000)
        traffic.record([self.sample(1010,2000,4000)],now=1010)
        traffic._baselines={};traffic._sessions={};traffic._last=0
        traffic.initialize()
        traffic.record([self.sample(1020,3000,6000)],now=1020)
        c=traffic.report(now=1020)['clients'][0]
        self.assertEqual(c['peak_upload_bps'],100)
        self.assertEqual(c['upload_bps'],0)
        self.assertEqual(c['session_seconds'],0)

    def test_reset_gap_missing_and_stale(self):
        traffic.record([self.sample(1000,100,200)],now=1000)
        traffic.record([self.sample(1010,10,20)],now=1010)
        self.assertEqual(traffic.report(now=1010)['clients'][0]['upload_bps'],1)
        traffic.record([self.sample(1200,999999,999999)],now=1200)
        self.assertEqual(traffic.report(now=1200)['clients'][0]['upload_bps'],0)
        traffic.record([],now=1210,partial=True)
        traffic.record([self.sample(1220,1999999,1999999)],now=1220)
        self.assertEqual(traffic.report(now=1220)['clients'][0]['upload_bps'],0)
        self.assertTrue(traffic.report(now=1300)['stale'])
    def test_bounded_rollups_peaks_not_sum_of_separate_peaks(self):
        traffic.record([self.sample(1000,0,0)],now=1000)
        traffic.record([self.sample(1010,1000,0)],now=1010)
        traffic.record([self.sample(1020,1000,2000)],now=1020)
        r=traffic.report('month',now=1020)
        self.assertEqual(r['points'][0]['peak_total'],200)
        self.assertEqual(r['points'][0]['upload'],1000)
        traffic.record([self.sample(40*86400,9999,9999)],now=40*86400)
        with closing(traffic.connect()) as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM buckets').fetchone()[0],0)


class TrafficApiTests(unittest.TestCase):
    setUp=base.ApiTests.setUp
    tearDown=base.ApiTests.tearDown
    post=base.ApiTests.post
    def test_auth_and_invalid_period(self):
        self.assertEqual(base.web.app.test_client().get('/api/traffic').status_code,401)
        self.assertEqual(self.client.get('/api/traffic?period=invalid').status_code,400)
    def test_telemetry_failure_does_not_break_quota_polling(self):
        before=list(self.engine.calls)
        with patch.object(traffic,'record',side_effect=OSError('disk full')):
            state.refresh()
        self.assertEqual(self.client.get('/api/summary').status_code,200)
        self.assertEqual(self.engine.calls,before)  # No configuration calls from statistics.
    def test_endpoint_redacts_deleted_clients(self):
        with patch.object(traffic,'report',return_value={'clients':[{'id':999,'upload_bps':1}],'points':[]}):
            self.assertEqual(self.client.get('/api/traffic').json['clients'],[])

    def test_individual_api_validates_identity(self):
        self.assertEqual(self.client.get('/api/traffic?client_id=-1').status_code,400)
        self.assertEqual(self.client.get('/api/traffic?client_id=abc').status_code,400)
        self.assertEqual(self.client.get('/api/traffic?client_id=999').status_code,404)
        ident=self.post('clients',{'profile_id':self.profile['id'],'count':1}).json['ids'][0]
        with patch.object(traffic,'report',return_value={'clients':[{'id':ident}],'points':[]}) as report:
            r=self.client.get('/api/traffic?client_id='+str(ident))
            self.assertEqual(r.status_code,200)
            report.assert_called_once_with('day',client_id=ident)
