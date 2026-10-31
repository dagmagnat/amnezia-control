"""SQLite state, backwards-compatible migrations and quota reconciliation."""
import base64
import configparser
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from core import Problem, PARAMS, command, binary, config_path, Engine, atomic_text, parse_config

DATA = Path(os.environ.get('AMNEZIA_CONTROL_DATA', '/var/lib/amnezia-control'))
DB = Path(os.environ.get('AMNEZIA_CONTROL_DB', DATA / 'control.db'))
LOCK = threading.RLock()
ENGINE = Engine()

@contextmanager
def connection():
    con = sqlite3.connect(DB, timeout=30); con.row_factory = sqlite3.Row
    try:
        yield con; con.commit()
    except Exception:
        con.rollback(); raise
    finally: con.close()

def value(con, key, default=''):
    row = con.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    return row['value'] if row else default

def put(con, key, val):
    con.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,str(val)))

def audit(con, message):
    con.execute('INSERT INTO events(created_at,message) VALUES (?,?)',(int(time.time()),message))

def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    with connection() as con:
        con.executescript('''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profiles(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,protocol TEXT NOT NULL,version TEXT NOT NULL,interface TEXT NOT NULL UNIQUE,address TEXT NOT NULL,port INTEGER NOT NULL UNIQUE,endpoint TEXT NOT NULL,private_key TEXT NOT NULL,public_key TEXT NOT NULL,params TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT DEFAULT '',protocol TEXT NOT NULL,version TEXT NOT NULL,address TEXT NOT NULL UNIQUE,public_key TEXT NOT NULL,private_key TEXT NOT NULL,preshared_key TEXT DEFAULT '',endpoint TEXT DEFAULT '',traffic_limit TEXT DEFAULT '',expires_at TEXT DEFAULT '',enabled INTEGER NOT NULL DEFAULT 1,created_at INTEGER NOT NULL,config TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at INTEGER NOT NULL,message TEXT NOT NULL);''')
        if 'mtu' not in {r['name'] for r in con.execute('PRAGMA table_info(profiles)')}:
            con.execute('ALTER TABLE profiles ADD COLUMN mtu INTEGER NOT NULL DEFAULT 1380')
        cols = {r['name'] for r in con.execute('PRAGMA table_info(clients)')}
        extras = {'profile_id':'INTEGER','quota_bytes':'INTEGER NOT NULL DEFAULT 0','used_bytes':'INTEGER NOT NULL DEFAULT 0','last_rx':'INTEGER NOT NULL DEFAULT 0','last_tx':'INTEGER NOT NULL DEFAULT 0','handshake':'INTEGER NOT NULL DEFAULT 0','blocked_reason':"TEXT NOT NULL DEFAULT ''"}
        for key, decl in extras.items():
            if key not in cols: con.execute('ALTER TABLE clients ADD COLUMN '+key+' '+decl)
        # Adopt old interface using its existing private key; never generate a replacement.
        if not value(con,'migration_v2'):
            iface = value(con,'vpn_interface')
            if iface:
                protocol = value(con,'vpn_engine','wireguard')
                dummy = {'protocol':protocol,'interface':iface}
                paths = [config_path(dummy), Path(os.environ.get('AC_CONFIG_ROOT','/etc'))/'wireguard'/(iface+'.conf')]
                source = next((p for p in paths if p.exists()), None)
                if source:
                    text=source.read_text(encoding='utf-8-sig'); section=text.split('[Peer]')[0]
                    parser=configparser.ConfigParser(interpolation=None,inline_comment_prefixes=('#',),strict=False); parser.optionxform=str
                    parser.read_string(section); fields=dict(parser['Interface'])
                    private=fields['PrivateKey']; public=command(binary(dummy),'pubkey',input=private+'\n')
                    params={k:fields[k] for k in PARAMS if k in fields}
                    version='3.1' if 'RandomTrailers' in params else ('3.0' if 'HeaderProtectionKey' in params else ('2.0' if 'S3' in params else ('1.0' if params else 'legacy')))
                    address=fields.get('Address','10.8.0.1/24'); port=int(fields.get('ListenPort','51820'))
                    cur=con.execute('INSERT OR IGNORE INTO profiles(name,protocol,version,interface,address,port,endpoint,private_key,public_key,params) VALUES(?,?,?,?,?,?,?,?,?,?)',('Existing VPN',protocol,version,iface,address,port,value(con,'endpoint'),private,public,json.dumps(params)))
                    profile=con.execute('SELECT * FROM profiles WHERE interface=?',(iface,)).fetchone()
                    con.execute('UPDATE clients SET profile_id=?,protocol=?,version=? WHERE profile_id IS NULL',(profile['id'],protocol,version))
                    # Read existing runtime peers into the registry before applying managed configs.
                    try:
                        dump=command(binary(dummy),'show',iface,'dump')
                        for line in dump.splitlines()[1:]:
                            parts=line.split('\t')
                            if len(parts) < 8 or con.execute('SELECT 1 FROM clients WHERE public_key=?',(parts[0],)).fetchone(): continue
                            if parts[3] == '(none)': continue
                            con.execute('INSERT OR IGNORE INTO clients(name,protocol,version,address,public_key,private_key,preshared_key,created_at,profile_id) VALUES(?,?,?,?,?,?,?,?,?)',('Existing peer',protocol,version,parts[3],parts[0],'','' if parts[1]=='(none)' else parts[1],int(time.time()),profile['id']))
                    except Problem: pass
                    audit(con,'Existing VPN adopted; server keys preserved')
            for row in con.execute('SELECT * FROM clients').fetchall():
                expires=str(row['expires_at'] or '')
                if expires and not expires.isdigit():
                    match=re.search(r'(\d+)',expires)
                    days=int(match[1]) if match else 0
                    if 'год' in expires or 'year' in expires: days*=365
                    expires=str(int(row['created_at'])+days*86400) if days else ''
                    con.execute('UPDATE clients SET expires_at=? WHERE id=?',(expires,row['id']))
                if not row['quota_bytes']:
                    match=re.match(r'\s*(\d+)',str(row['traffic_limit'] or ''))
                    if match: con.execute('UPDATE clients SET quota_bytes=? WHERE id=?',(int(match[1])*1073741824,row['id']))
            put(con,'migration_v2','1')
        if not value(con,'next_client_number'):
            row=con.execute('SELECT COALESCE(MAX(id),0) n FROM clients').fetchone(); put(con,'next_client_number',row['n']+1)
    if os.name != 'nt': os.chmod(DB,0o600); os.chmod(DATA,0o700)

def all_peers(con, profile_id):
    return [dict(r) for r in con.execute('SELECT * FROM clients WHERE profile_id=?',(profile_id,))]

def sync(con, profile):
    ENGINE.apply(dict(profile), all_peers(con,profile['id']))

def refresh():
    with LOCK, connection() as con:
        now=int(time.time())
        for profile in con.execute('SELECT * FROM profiles').fetchall():
            readings, error=ENGINE.stats(dict(profile)); changed=False
            for row in con.execute('SELECT * FROM clients WHERE profile_id=?',(profile['id'],)).fetchall():
                sample=readings.get(row['public_key']); used=row['used_bytes']; rx=row['last_rx']; tx=row['last_tx']; handshake=row['handshake']
                if sample:
                    used += sample['rx']-rx if sample['rx'] >= rx else sample['rx']
                    used += sample['tx']-tx if sample['tx'] >= tx else sample['tx']
                    rx=sample['rx']; tx=sample['tx']; handshake=sample.get('handshake',0)
                elif not error:
                    rx=tx=0
                reason=''
                try:
                    if row['expires_at'] and int(row['expires_at']) <= now: reason='expired'
                except ValueError: pass
                if row['quota_bytes'] and used >= row['quota_bytes']: reason='quota'
                if reason != row['blocked_reason']: changed=True; audit(con,row['name']+': '+(reason or 'access resumed'))
                con.execute('UPDATE clients SET used_bytes=?,last_rx=?,last_tx=?,handshake=?,blocked_reason=? WHERE id=?',(used,rx,tx,handshake,reason,row['id']))
            if changed:
                sync(con,profile)

def client_config(row, profile):
    if not row['private_key']: raise Problem('Private key not available; use the existing client file',409)
    destination=row['endpoint'] or profile['endpoint']
    original_interface={}; original_peer={}
    if row.get('config'):
        try: original_interface,original_peer=parse_config(row['config'])
        except Problem: pass
    fields={'PrivateKey':row['private_key'],'Address':original_interface.get('Address',row['address'])}
    if original_interface:
        fields.update({k:original_interface[k] for k in ('DNS','MTU') if k in original_interface})
    else: fields.update(DNS='1.1.1.1',MTU=str(profile.get('mtu',1380)))
    params=json.loads(profile['params'])
    if original_interface:
        if profile['protocol']=='wireguard':
            # Only validated WG-compatible legacy AWG files reach this path.
            params.update({k:original_interface[k] for k in PARAMS if k in original_interface})
        for k in ('Jc','Jmin','Jmax','I1','I2','I3','I4','I5'):
            params.pop(k,None)
            if k in original_interface: params[k]=original_interface[k]
    fields.update(params)
    lines=['[Interface]']+[k+' = '+v for k,v in fields.items()]
    lines += ['', '[Peer]','PublicKey = '+profile['public_key']]
    if row['preshared_key']: lines += ['PresharedKey = '+row['preshared_key']]
    lines += ['Endpoint = '+destination,'AllowedIPs = '+original_peer.get('AllowedIPs','0.0.0.0/0')]
    if not original_peer or 'PersistentKeepalive' in original_peer:
        lines += ['PersistentKeepalive = '+original_peer.get('PersistentKeepalive','25')]
    return '\n'.join(lines)+'\n'
