#!/usr/bin/env python3
import base64, hashlib, hmac, json, os, secrets, sqlite3, subprocess, time
from pathlib import Path
from functools import wraps
from flask import Flask, jsonify, request, session, send_from_directory, abort

ROOT = Path(os.environ.get('AMNEZIA_CONTROL_ROOT', '/opt/amnezia-control'))
DATA = Path(os.environ.get('AMNEZIA_CONTROL_DATA', '/var/lib/amnezia-control'))
DB = Path(os.environ.get('AMNEZIA_CONTROL_DB', DATA / 'control.db'))
VPN_DIR = Path(os.environ.get('AMNEZIA_CONTROL_VPN_DIR', '/etc/wireguard'))
DIST = ROOT / 'dist'
DATA.mkdir(parents=True, exist_ok=True)
app = Flask(__name__, static_folder=str(DIST), static_url_path='')
app.secret_key = os.environ.get('AMNEZIA_CONTROL_SECRET', secrets.token_hex(32))
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

SCHEMA = '''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT DEFAULT '', protocol TEXT NOT NULL, version TEXT NOT NULL, address TEXT NOT NULL UNIQUE, public_key TEXT NOT NULL, private_key TEXT NOT NULL, preshared_key TEXT DEFAULT '', endpoint TEXT DEFAULT '', traffic_limit TEXT DEFAULT '', expires_at TEXT DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, config TEXT NOT NULL);'''

def db():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row; con.executescript(SCHEMA); return con

def setting(key, default=''):
    row = db().execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone(); return row['value'] if row else default

def hash_password(value):
    salt = secrets.token_bytes(16); digest = hashlib.scrypt(value.encode(), salt=salt, n=16384, r=8, p=1); return base64.b64encode(salt + digest).decode()

def verify_password(value, encoded):
    raw = base64.b64decode(encoded); return hmac.compare_digest(hashlib.scrypt(value.encode(), salt=raw[:16], n=16384, r=8, p=1), raw[16:])

def run(*args, input=None):
    try: return subprocess.run(args, input=input, text=True, capture_output=True, check=True, timeout=15).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired): return ''

def keypair(binary):
    private = run(binary, 'genkey') or base64.b64encode(secrets.token_bytes(32)).decode(); public = run(binary, 'pubkey', input=private + '\n') or base64.b64encode(secrets.token_bytes(32)).decode(); return private, public

def vpn_engine():
    preferred = setting('vpn_engine', 'wireguard')
    if preferred == 'amneziawg' and run('which', 'awg'): return 'awg'
    return 'wg' if run('which', 'wg') else preferred

def apply_peer(row):
    engine = vpn_engine(); interface = setting('vpn_interface', 'wg0')
    if not run('which', engine): return False
    try:
        subprocess.run([engine, 'set', interface, 'peer', row['public_key'], 'preshared-key', '/dev/stdin', 'allowed-ips', row['address']], input=row['preshared_key'], text=True, capture_output=True, check=True, timeout=10)
        return True
    except (subprocess.SubprocessError, OSError): return False

def login_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not session.get('user'): return jsonify(error='auth_required'), 401
        return fn(*args, **kwargs)
    return inner

def next_address(con):
    used = {r['address'] for r in con.execute('SELECT address FROM clients')}
    for n in range(2, 254):
        address = f'10.8.0.{n}/32'
        if address not in used: return address
    raise ValueError('client_limit_reached')

def render_config(row):
    iface = 'awg0' if row['protocol'] == 'amneziawg' else 'wg0'
    return f'''[Interface]\nPrivateKey = {row['private_key']}\nAddress = {row['address']}\nDNS = 1.1.1.1\n\n[Peer]\nPublicKey = {setting('server_public_key', '<SERVER_PUBLIC_KEY>')}\nPresharedKey = {row['preshared_key']}\nEndpoint = {row['endpoint'] or setting('endpoint', 'SERVER_IP:51820')}\nAllowedIPs = 0.0.0.0/0\nPersistentKeepalive = 25\n# AmneziaWG version: {row['version']}\n# Interface: {iface}\n'''

@app.post('/api/login')
def login():
    body = request.get_json(silent=True) or {}; user = setting('admin_user'); encoded = setting('admin_password')
    if not user or not encoded or body.get('username') != user or not verify_password(body.get('password',''), encoded): return jsonify(error='invalid_credentials'), 401
    session['user'] = user; return jsonify(ok=True, user=user)

@app.post('/api/logout')
def logout(): session.clear(); return jsonify(ok=True)

@app.get('/api/me')
def me(): return jsonify(authenticated=bool(session.get('user')), user=session.get('user'))

@app.get('/api/clients')
@login_required
def clients():
    rows = [dict(r) for r in db().execute('SELECT id,name,description,protocol,version,address,public_key,endpoint,traffic_limit,expires_at,enabled,created_at FROM clients ORDER BY id')]; return jsonify(clients=rows)

@app.post('/api/clients')
@login_required
def create_client():
    body = request.get_json(silent=True) or {}; name = str(body.get('name','')).strip()[:30]
    if not name: name = f"User {db().execute('SELECT COUNT(*) c FROM clients').fetchone()['c'] + 1:02d}"
    protocol = body.get('protocol','amneziawg').lower(); version = body.get('version','3.1'); binary = 'awg' if protocol == 'amneziawg' and run('which','awg') else 'wg'
    con = db(); address = next_address(con); private, public = keypair(binary); preshared = run(binary,'genpsk') or base64.b64encode(secrets.token_bytes(32)).decode(); now = int(time.time())
    cur = con.execute('INSERT INTO clients(name,description,protocol,version,address,public_key,private_key,preshared_key,endpoint,traffic_limit,expires_at,created_at,config) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(name,str(body.get('description',''))[:500],protocol,version,address,public,private,preshared,str(body.get('endpoint','')),str(body.get('traffic_limit','')),str(body.get('expires_at','')),now,'')); client_id=cur.lastrowid
    row=con.execute('SELECT * FROM clients WHERE id=?',(client_id,)).fetchone(); config=render_config(row); con.execute('UPDATE clients SET config=? WHERE id=?',(config,client_id)); con.commit(); apply_peer(row); return jsonify(client={**dict(row),'config':config}), 201

@app.get('/api/clients/<int:client_id>/config')
@login_required
def config(client_id):
    row=db().execute('SELECT name,config FROM clients WHERE id=?',(client_id,)).fetchone();
    if not row: abort(404)
    return app.response_class(row['config'], mimetype='text/plain', headers={'Content-Disposition':f'attachment; filename="{row["name"]}.conf"'})

@app.patch('/api/clients/<int:client_id>')
@login_required
def update_client(client_id):
    body=request.get_json(silent=True) or {}; allowed={'name','description','endpoint','traffic_limit','expires_at','enabled'}; changes={k:body[k] for k in allowed if k in body};
    if 'name' in changes: changes['name']=str(changes['name'])[:30]
    if not changes: return jsonify(error='nothing_to_update'),400
    con=db(); sets=', '.join(f'{k}=?' for k in changes); con.execute(f'UPDATE clients SET {sets} WHERE id=?',(*changes.values(),client_id)); con.commit(); return jsonify(ok=True)

@app.delete('/api/clients/<int:client_id>')
@login_required
def delete_client(client_id):
    con=db(); row=con.execute('SELECT * FROM clients WHERE id=?',(client_id,)).fetchone();
    if row: run(vpn_engine(), 'set', setting('vpn_interface','wg0'), 'peer', row['public_key'], 'remove')
    con.execute('DELETE FROM clients WHERE id=?',(client_id,)); con.commit(); return jsonify(ok=True)

@app.get('/api/status')
@login_required
def status():
    return jsonify(wg=bool(run('which','wg')), awg=bool(run('which','awg')), nginx=bool(run('systemctl','is-active','nginx')), service=bool(run('systemctl','is-active','amnezia-control')))

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def static(path):
    target = DIST / path
    if path and target.exists(): return send_from_directory(DIST, path)
    return send_from_directory(DIST, 'index.html')

if __name__ == '__main__': app.run(host='127.0.0.1', port=int(os.environ.get('PORT','8090')))
