"""Bounded, observational telemetry. Never writes VPN state or calls configuration tools."""
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

INTERVAL = 10
RETENTION = 35 * 86400
_baselines = {}
_sessions = {}
_last = 0


def path():
    import state
    return Path(state.DATA) / 'traffic.db'


def connect():
    con = sqlite3.connect(path(), timeout=0.3)
    con.row_factory = sqlite3.Row
    return con


def initialize():
    global _sessions, _baselines, _last
    with closing(connect()) as con, con:
        con.execute('PRAGMA journal_mode=WAL')
        con.executescript('''CREATE TABLE IF NOT EXISTS buckets(
            ts INTEGER PRIMARY KEY, upload INTEGER NOT NULL, download INTEGER NOT NULL,
            seconds REAL NOT NULL, samples INTEGER NOT NULL, online_sum INTEGER NOT NULL,
            online_max INTEGER NOT NULL, peak_upload REAL NOT NULL, peak_download REAL NOT NULL,
            peak_total REAL NOT NULL, partial INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS live(id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS client_buckets(
                client_id INTEGER NOT NULL, ts INTEGER NOT NULL, upload INTEGER NOT NULL,
                download INTEGER NOT NULL, seconds REAL NOT NULL, samples INTEGER NOT NULL,
                online_sum INTEGER NOT NULL, online_max INTEGER NOT NULL,
                peak_upload REAL NOT NULL, peak_download REAL NOT NULL,peak_total REAL NOT NULL,
                partial INTEGER NOT NULL,PRIMARY KEY(client_id,ts)) WITHOUT ROWID;
            CREATE INDEX IF NOT EXISTS client_buckets_time ON client_buckets(ts);
            CREATE TABLE IF NOT EXISTS client_time(client_id INTEGER PRIMARY KEY,
                total_seconds REAL NOT NULL DEFAULT 0,sessions INTEGER NOT NULL DEFAULT 0);''')
        con.execute("INSERT OR IGNORE INTO meta VALUES('started',?)", (int(time.time()),))
        con.execute("INSERT OR IGNORE INTO meta VALUES('client_history_started',?)", (int(time.time()),))
        _baselines = {}; _last = 0
        _sessions = {r['id']:json.loads(r['payload']) | {'online':False} for r in con.execute('SELECT * FROM live')}
    if os.name != 'nt': os.chmod(path(), 0o600)


def record(observations, now=None, partial=False):
    """Receive successful quota-poller readings; RX at server means client upload.

    Missing/failed readings invalidate that peer's next interval. Initial counters
    and intervals over 45s are baselines, never synthetic traffic/speed spikes.
    """
    global _baselines, _sessions, _last
    now = float(time.time() if now is None else now)
    elapsed = now - _last if _last else 0
    valid = 0 < elapsed <= 45
    next_baselines = {}
    totals = {}
    for peer, client_id, sample, allowed in observations:
        previous = _baselines.get(peer)
        up = down = 0
        if valid and previous is not None:
            # A reset loses the unobserved tail, but the new counter is real traffic.
            up = sample['rx'] - previous[0] if sample['rx'] >= previous[0] else sample['rx']
            down = sample['tx'] - previous[1] if sample['tx'] >= previous[1] else sample['tx']
        next_baselines[peer] = (sample['rx'], sample['tx'])
        row = totals.setdefault(client_id, {'upload': 0, 'download': 0, 'online': False})
        row['upload'] += max(0, up); row['download'] += max(0, down)
        hs = sample.get('handshake', 0)
        row['online'] |= bool(allowed and hs and 0 <= now-hs < 180)
    live = []; time_increments=[]
    for ident, row in totals.items():
        old = _sessions.get(ident, {})
        continuous = valid and old.get('online', False) and row['online']
        session_seconds = old.get('session_seconds', 0) + elapsed if continuous else 0
        session_up = old.get('session_upload', 0) + row['upload'] if continuous else 0
        session_down = old.get('session_download', 0) + row['download'] if continuous else 0
        upload_bps = row['upload']/elapsed if valid else 0
        download_bps = row['download']/elapsed if valid else 0
        result = dict(row, id=ident, updated_at=now, upload_bps=upload_bps,
                      download_bps=download_bps, session_seconds=session_seconds,
                      session_upload=session_up, session_download=session_down,
                      average_upload_bps=session_up/session_seconds if session_seconds else 0,
                      average_download_bps=session_down/session_seconds if session_seconds else 0,
                      peak_upload_bps=max(old.get('peak_upload_bps', 0), upload_bps),
                      peak_download_bps=max(old.get('peak_download_bps', 0), download_bps))
        live.append(result)
        time_increments.append((ident,elapsed if continuous else 0,int(row['online'] and not continuous)))
    up = sum(r['upload'] for r in live); down = sum(r['download'] for r in live)
    online = sum(r['online'] for r in live)
    # Commit telemetry before advancing in-memory baselines. Its errors cannot
    # roll back or block the main control.db transaction.
    with closing(connect()) as con, con:
        con.executemany('''INSERT INTO client_time VALUES(?,?,?) ON CONFLICT(client_id)
            DO UPDATE SET total_seconds=total_seconds+excluded.total_seconds,
            sessions=sessions+excluded.sessions''',time_increments)
        con.executemany('INSERT OR REPLACE INTO live VALUES (?,?)',
                        [(r['id'], json.dumps(r)) for r in live])
        ids = {r['id'] for r in live}
        for row in con.execute('SELECT id FROM live').fetchall():
            if row['id'] not in ids: con.execute('DELETE FROM live WHERE id=?', (row['id'],))
        if valid:
            con.executemany('''INSERT INTO client_buckets VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(client_id,ts) DO UPDATE SET upload=upload+excluded.upload,
                download=download+excluded.download,seconds=seconds+excluded.seconds,
                samples=samples+1,online_sum=online_sum+excluded.online_sum,
                online_max=MAX(online_max,excluded.online_max),
                peak_upload=MAX(peak_upload,excluded.peak_upload),
                peak_download=MAX(peak_download,excluded.peak_download),
                peak_total=MAX(peak_total,excluded.peak_total),partial=MAX(partial,excluded.partial)''',
                [(r['id'],int(now)//300*300,r['upload'],r['download'],elapsed,1,int(r['online']),
                  int(r['online']),r['upload_bps'],r['download_bps'],
                  r['upload_bps']+r['download_bps'],int(partial)) for r in live])
            con.execute('''INSERT INTO buckets VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(ts) DO UPDATE SET upload=upload+excluded.upload,
                download=download+excluded.download,seconds=seconds+excluded.seconds,
                samples=samples+1,online_sum=online_sum+excluded.online_sum,
                online_max=MAX(online_max,excluded.online_max),
                peak_upload=MAX(peak_upload,excluded.peak_upload),
                peak_download=MAX(peak_download,excluded.peak_download),
                peak_total=MAX(peak_total,excluded.peak_total),partial=MAX(partial,excluded.partial)''',
                (int(now)//300*300, up, down, elapsed, 1, online, online,
                 up/elapsed, down/elapsed, (up+down)/elapsed, int(partial)))
        con.execute('DELETE FROM buckets WHERE ts < ?', (int(now)-RETENTION,))
        con.execute('DELETE FROM client_buckets WHERE ts < ?', (int(now)-RETENTION,))
        con.execute("INSERT OR REPLACE INTO meta VALUES('updated',?)", (int(now),))
    for ident in _sessions.keys()-totals.keys(): _sessions[ident]['online']=False
    _baselines = next_baselines; _sessions.update({r['id']:r for r in live}); _last = now


def report(period='day', now=None, client_id=None):
    now = int(time.time() if now is None else now)
    duration, step = {'day':(86400,300), 'week':(604800,3600), 'month':(30*86400,21600)}[period]
    since = (now-duration)//step*step
    if not path().exists():
        return {'points':[], 'clients':[], 'updated_at':0, 'started_at':0, 'period':period, 'step':step}
    with closing(connect()) as con:
        meta = dict(con.execute('SELECT key,value FROM meta'))
        table='client_buckets' if client_id is not None else 'buckets'
        where=' AND client_id=?' if client_id is not None else ''
        args=(step,step,since)+((client_id,) if client_id is not None else ())
        rows = con.execute('''SELECT CAST(ts / ? AS INTEGER)*? ts,SUM(upload) upload,
            SUM(download) download,SUM(seconds) seconds,SUM(samples) samples,
            SUM(online_sum)*1.0/SUM(samples) online_average,MAX(online_max) online_max,
            MAX(peak_upload) peak_upload,MAX(peak_download) peak_download,
            MAX(peak_total) peak_total,MAX(partial) partial FROM '''+table+'''
            WHERE ts>=?'''+where+' GROUP BY 1 ORDER BY 1',args).fetchall()
        time_rows={r['client_id']:dict(r) for r in con.execute('SELECT * FROM client_time')}
        clients = [json.loads(r[0]) for r in con.execute('SELECT payload FROM live')]
        if client_id is not None: clients=[c for c in clients if c['id']==client_id]
        for c in clients:
            timing=time_rows.get(c['id'],{})
            c['total_online_seconds']=timing.get('total_seconds',0)
            c['session_count']=timing.get('sessions',0)
            c['average_session_seconds']=c['total_online_seconds']/c['session_count'] if c['session_count'] else 0
    # No backfilling outages with zero. Missing bins remain explicit gaps.
    return {'points':[dict(r) for r in rows], 'clients':clients, 'period':period,
            'step':step, 'started_at':meta.get('client_history_started' if client_id is not None else 'started',0),
            'time_started_at':meta.get('client_history_started',0), 'client_id':client_id, 'updated_at':meta.get('updated',0),
            'stale':now-meta.get('updated',0)>45, 'since':since}
