"""Amnezia Control HTTP application. All records are local to this VPS."""
import base64
import io
import ipaddress
import json
import os
import re
import secrets
import shutil
import threading
import time
from collections import defaultdict
from functools import wraps
from pathlib import Path
from flask import Flask, abort, jsonify, request, send_from_directory, session
from werkzeug.exceptions import HTTPException
from core import (Problem, GENERATIONS, PARAMS, command, keys, key, number, host,
                  endpoint, parameters, parse_config, binary, config_path, atomic_text, service)
import state
from provision import create_profile, ensure_profile, cleanup_profile, CLIENT_VERSIONS
from password_hash import hash_password
import hashlib
import hmac

ROOT=Path(os.environ.get('AMNEZIA_CONTROL_ROOT',Path(__file__).resolve().parents[1]))
DIST=ROOT/'dist'
app=Flask(__name__,static_folder=None)
app.secret_key=os.environ.get('AMNEZIA_CONTROL_SECRET') or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=9*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',PERMANENT_SESSION_LIFETIME=28800)
ATTEMPTS=defaultdict(list)

@app.before_request
def origin_check():
    if request.path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS'):
        if not hmac.compare_digest(str(session.get('csrf','')),str(request.headers.get('X-CSRF-Token',''))) or not session.get('csrf'):
            raise Problem('Session expired. Reload the page.',403)

@app.after_request
def no_cache(response):
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    return response

@app.errorhandler(Problem)
def problem(exc): return jsonify(error=str(exc)),exc.status

@app.errorhandler(HTTPException)
def http_error(exc): return jsonify(error=exc.description),exc.code

@app.errorhandler(Exception)
def unexpected(exc):
    app.logger.error('Request failed (%s)',type(exc).__name__)
    return jsonify(error='Internal error. Check service journal.'),500

def auth(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        with state.connection() as con:
            valid=session.get('user') and session.get('revision','0')==state.value(con,'auth_revision','0')
        if not valid: raise Problem('Please sign in',401)
        return fn(*args,**kwargs)
    return wrapped

def body(): return request.get_json(silent=True) or {}

def password_ok(password, encoded):
    try:
        raw=base64.b64decode(encoded,validate=True)
        return hmac.compare_digest(hashlib.scrypt(password.encode(),salt=raw[:16],n=16384,r=8,p=1),raw[16:])
    except (ValueError,TypeError): return False

def profile_by_id(con, ident):
    row=con.execute('SELECT * FROM profiles WHERE id=?',(ident,)).fetchone()
    if not row: raise Problem('VPN profile not found',404)
    return dict(row)

def client_by_id(con, ident):
    row=con.execute('SELECT * FROM clients WHERE id=?',(ident,)).fetchone()
    if not row: raise Problem('Client not found',404)
    return dict(row)

def public_client(row):
    result={k:v for k,v in dict(row).items() if k not in ('private_key','preshared_key','config')}
    result['downloadable']=bool(row['private_key'])
    now=time.time()
    if not row['enabled']: status='disabled'
    elif row['blocked_reason']=='expired' or row['expires_at'] and int(row['expires_at'])<=now: status='expired'
    elif row['blocked_reason']=='quota' or row['quota_bytes'] and row['used_bytes']>=row['quota_bytes']: status='quota'
    elif row['handshake'] and 0<=now-row['handshake']<180: status='online'
    else: status='offline'
    result['status']=status
    result['online']=status=='online'
    return result

def expiry(value):
    if value in (None,'',0): return ''
    return str(number(value,1,4102444800))

@app.get('/api/me')
def me():
    session.setdefault('csrf',secrets.token_hex(32))
    with state.connection() as con:
        authenticated=bool(session.get('user') and session.get('revision','0')==state.value(con,'auth_revision','0'))
        return jsonify(authenticated=authenticated,user=session.get('user') if authenticated else None,csrf=session['csrf'],language=state.value(con,'language','ru'))

@app.post('/api/login')
def login():
    data=body(); ip=request.remote_addr; now=time.time(); ATTEMPTS[ip]=[t for t in ATTEMPTS[ip] if now-t<300]
    if len(ATTEMPTS[ip])>=10: raise Problem('Too many attempts. Wait 5 minutes.',429)
    with state.connection() as con:
        if data.get('username')!=state.value(con,'admin_user') or not password_ok(str(data.get('password','')),state.value(con,'admin_password')):
            ATTEMPTS[ip].append(now); raise Problem('Invalid login or password',401)
        session.clear(); session.update(user=data['username'],csrf=secrets.token_hex(32),revision=state.value(con,'auth_revision','0')); session.permanent=True
        ATTEMPTS.pop(ip,None)
    return jsonify(ok=True,csrf=session['csrf'])

@app.post('/api/logout')
def logout(): session.clear(); return jsonify(ok=True)

@app.get('/api/summary')
@auth
def summary():
    with state.connection() as con:
        clients=[public_client(r) for r in con.execute('SELECT * FROM clients ORDER BY id')]
        profiles=[]
        for row in con.execute('SELECT * FROM profiles ORDER BY id'):
            p=dict(row); _,error=state.ENGINE.stats(p)
            profiles.append({k:v for k,v in p.items() if k!='private_key'} | {'active':not bool(error)})
        events=[dict(r) for r in con.execute('SELECT * FROM events ORDER BY id DESC LIMIT 25')]
        panel={'domain':state.value(con,'panel_domain'),'ip':state.value(con,'panel_ip'),'port':int(state.value(con,'panel_port','8080')),'language':state.value(con,'language','ru'),'vpn_host':state.value(con,'vpn_host')}
    return jsonify(clients=clients,profiles=profiles,events=events,panel=panel,
                   capabilities={'wireguard':bool(shutil.which('wg')),'amneziawg':bool(shutil.which('awg')),'generations':GENERATIONS,'client_versions':CLIENT_VERSIONS},
                   version='0.4.1')

@app.get('/api/clients')
@auth
def clients():
    with state.connection() as con: return jsonify(clients=[public_client(r) for r in con.execute('SELECT * FROM clients ORDER BY id')])

@app.post('/api/profiles')
@auth
def add_profile():
    with state.LOCK,state.connection() as con:
        profile=create_profile(con,body())
    return jsonify(ok=True,id=profile['id']),201

@app.patch('/api/profiles/<int:ident>')
@auth
def edit_profile(ident):
    data=body()
    with state.LOCK,state.connection() as con:
        p=profile_by_id(con,ident)
        if 'endpoint' in data: p['endpoint']=endpoint(data['endpoint'])
        if 'name' in data: p['name']=str(data['name']).strip()[:60]
        # Existing obfuscation changes invalidate client files: explicit opt-in required.
        if 'params' in data:
            if not data.get('confirm_regenerate'): raise Problem('Confirm reissue of all client files',409)
            p['params']=json.dumps(parameters(p['version'],data['params']))
        con.execute('UPDATE profiles SET name=?,endpoint=?,params=? WHERE id=?',(p['name'],p['endpoint'],p['params'],ident))
        if 'params' in data: state.sync(con,p)
        state.audit(con,'VPN profile updated: '+p['name'])
    return jsonify(ok=True)

@app.post('/api/clients')
@auth
def add_clients():
    data=body(); count=number(data.get('count',1),1,25)
    name=str(data.get('name','')).strip()
    if len(name)>30: raise Problem('Name limit: 30 characters')
    quota=number(data.get('quota_bytes',0),0,10**16); expires=expiry(data.get('expires_at'))
    with state.LOCK,state.connection() as con:
        if data.get('protocol'):
            p,created_profile=ensure_profile(con,data['protocol'],data.get('version','3.1'))
        else:
            p=profile_by_id(con,data.get('profile_id'));created_profile=False
        try:
            first=int(state.value(con,'next_client_number','1'))
            network=ipaddress.ip_interface(p['address']).network
            taken={str(ipaddress.ip_interface(r['address']).ip) for r in con.execute('SELECT address FROM clients')}
            taken.add(str(ipaddress.ip_interface(p['address']).ip))
            free=[str(ip)+'/32' for ip in network.hosts() if str(ip) not in taken]
            if len(free)<count: raise Problem('Subnet is full')
            ids=[]
            for i in range(count):
                cname=(name if count==1 else (name[:26]+f' {i+1:02d}')) if name else f'User {first+i:02d}'
                private,public=keys(binary(p)); psk=key(command(binary(p),'genpsk'))
                cur=con.execute('INSERT INTO clients(name,description,protocol,version,address,public_key,private_key,preshared_key,endpoint,traffic_limit,expires_at,enabled,created_at,config,profile_id,quota_bytes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (cname,str(data.get('description',''))[:500],p['protocol'],p['version'],free[i],public,private,psk,'','',expires,1,int(time.time()),'',p['id'],quota))
                ids.append(cur.lastrowid); state.audit(con,'Client created: '+cname)
            state.put(con,'next_client_number',first+count)
            state.sync(con,p)
        except Exception:
            if created_profile: cleanup_profile(p)
            raise
    return jsonify(ok=True,ids=ids,profile_id=p['id'],endpoint=p['endpoint'],protocol=p['protocol'],version=p['version'],udp_port=p['port']),201

@app.patch('/api/clients/<int:ident>')
@auth
def edit_client(ident):
    data=body()
    with state.LOCK,state.connection() as con:
        c=client_by_id(con,ident); p=profile_by_id(con,c['profile_id'])
        for name in ('name','description','endpoint'):
            if name in data: c[name]=str(data[name]).strip()
        if not c['name'] or len(c['name'])>30: raise Problem('Name: 1–30 characters')
        if len(c['description'])>500: raise Problem('Description too long')
        if c['endpoint']: c['endpoint']=endpoint(c['endpoint'])
        if 'enabled' in data:
            if type(data['enabled']) is not bool: raise Problem('enabled must be boolean')
            c['enabled']=int(data['enabled'])
        if 'quota_bytes' in data: c['quota_bytes']=number(data['quota_bytes'],0,10**16)
        if 'expires_at' in data: c['expires_at']=expiry(data['expires_at'])
        if data.get('reset_usage'): c['used_bytes']=0
        c['blocked_reason']='quota' if c['quota_bytes'] and c['used_bytes']>=c['quota_bytes'] else ('expired' if c['expires_at'] and int(c['expires_at'])<time.time() else '')
        names=['name','description','endpoint','enabled','quota_bytes','expires_at','used_bytes','blocked_reason']
        con.execute('UPDATE clients SET '+','.join(k+'=?' for k in names)+' WHERE id=?',tuple(c[k] for k in names)+(ident,))
        state.sync(con,p); state.audit(con,'Client updated: '+c['name'])
    return jsonify(ok=True)

@app.delete('/api/clients/<int:ident>')
@auth
def delete_client(ident):
    from client_actions import delete_clients
    return jsonify(**delete_clients([ident]))

@app.post('/api/clients/bulk-delete')
@auth
def bulk_delete_clients():
    from client_actions import delete_clients
    data=body()
    return jsonify(**delete_clients(data.get('ids') if isinstance(data,dict) else None))

@app.get('/api/clients/<int:ident>/config')
@auth
def config(ident):
    with state.connection() as con:
        c=client_by_id(con,ident); text=state.client_config(c,profile_by_id(con,c['profile_id']))
    return app.response_class(text,mimetype='text/plain',headers={'Content-Disposition':f'attachment; filename="client-{ident}.conf"'})

@app.get('/api/clients/<int:ident>/qr')
@auth
def qr(ident):
    import qrcode
    with state.connection() as con:
        c=client_by_id(con,ident); text=state.client_config(c,profile_by_id(con,c['profile_id']))
    out=io.BytesIO(); qrcode.make(text).save(out,format='PNG')
    return app.response_class(out.getvalue(),mimetype='image/png')

@app.post('/api/import')
@auth
def import_client():
    # Existing client .conf can be adopted only with its original server identity.
    upload=request.files.get('file')
    if not upload: raise Problem('Choose a client .conf file')
    interface,peer=parse_config(upload.read(65537).decode('utf-8-sig'))
    with state.LOCK,state.connection() as con:
        p=profile_by_id(con,request.form.get('profile_id'))
        if peer['PublicKey']!=p['public_key']: raise Problem('Different server key. Import the original SERVER configuration first; replacing the client key would break migration.',409)
        for k in PARAMS:
            if interface.get(k)!=json.loads(p['params']).get(k): raise Problem('Obfuscation parameters do not match the server: '+k,409)
        address=ipaddress.ip_interface(interface.get('Address',''))
        if address.version!=4 or address.ip not in ipaddress.ip_interface(p['address']).network: raise Problem('Client address does not belong to this profile')
        private=interface['PrivateKey']; public=key(command(binary(p),'pubkey',input=private+'\n'))
        name=str(request.form.get('name') or upload.filename.rsplit('.',1)[0])[:30]
        if con.execute('SELECT 1 FROM clients WHERE public_key=? OR address=?',(public,str(address.ip)+'/32')).fetchone(): raise Problem('Client already exists',409)
        destination=endpoint(peer['Endpoint'])
        stored='[Interface]\n'+'\n'.join(k+' = '+v for k,v in interface.items())+'\n\n[Peer]\n'+'\n'.join(k+' = '+v for k,v in peer.items())+'\n'
        cur=con.execute('INSERT INTO clients(name,description,protocol,version,address,public_key,private_key,preshared_key,endpoint,created_at,profile_id,config) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (name,'Imported .conf',p['protocol'],p['version'],str(address.ip)+'/32',public,private,peer.get('PresharedKey',''),destination,int(time.time()),p['id'],stored))
        state.sync(con,p); state.audit(con,'Client imported: '+name)
    return jsonify(ok=True,id=cur.lastrowid),201

def migration_plan(con):
    import importer
    files=importer.read_uploads(request.files.getlist('files'))
    options={k:request.form.get(k,'') for k in ('mode','profile_id','server_file','endpoint')}
    plan,profile,entries=importer.build_plan(con,files,options)
    if options['mode']=='server':
        options['server_file']=plan.get('server_file',options['server_file']); options['profile_id']=''
    else: options['server_file']=''; options['endpoint']=''
    digest=hashlib.sha256(json.dumps([files,options,plan,importer.fingerprint(con)],sort_keys=True).encode()).hexdigest()
    token=hmac.new(str(app.secret_key).encode(),digest.encode(),hashlib.sha256).hexdigest()
    return plan,profile,entries,token

@app.post('/api/import/preview')
@auth
def import_preview():
    with state.LOCK,state.connection() as con:
        plan,_,_,token=migration_plan(con)
    return jsonify(**plan,token=token)

@app.post('/api/import/apply')
@auth
def import_apply():
    import importer
    with state.LOCK,state.connection() as con:
        plan,profile,entries,token=migration_plan(con)
        if not hmac.compare_digest(token,str(request.form.get('token',''))):
            raise Problem('Files or VPN state changed. Run preview again before importing.',409)
        result=importer.apply_plan(con,plan,profile,entries)
    return jsonify(**result),201

@app.patch('/api/settings')
@auth
def settings():
    data=body()
    with state.connection() as con:
        if 'vpn_host' in data: state.put(con,'vpn_host',host(data['vpn_host']))
        if 'language' in data:
            if data['language'] not in ('ru','en'): raise Problem('Unknown language')
            state.put(con,'language',data['language'])
        if data.get('password'):
            if not password_ok(str(data.get('current_password','')),state.value(con,'admin_password')): raise Problem('Invalid current password',403)
            if len(data['password'])<10: raise Problem('Password: at least 10 characters')
            state.put(con,'admin_password',hash_password(data['password'])); revision=secrets.token_hex(16)
            state.put(con,'auth_revision',revision); session['revision']=revision
        state.audit(con,'Panel settings updated')
    return jsonify(ok=True)

@app.get('/api/backup')
@auth
def backup():
    import sqlite3
    memory=sqlite3.connect(':memory:')
    with state.connection() as con: con.backup(memory)
    data='\n'.join(memory.iterdump()); memory.close()
    # Includes all server/client private keys. Authenticated, no-store download only.
    return app.response_class(data,mimetype='application/sql',headers={'Content-Disposition':'attachment; filename="amnezia-control.sql"'})

@app.patch('/api/panel-access')
@auth
def access_settings():
    from manage import panel_address
    cfg=body();domain=host(cfg['domain']) if cfg.get('domain') else ''
    try: ip=str(ipaddress.ip_address(cfg.get('ip','')))
    except ValueError: raise Problem('Invalid public IP')
    port=number(cfg.get('port'),1024,65535)
    existing=Path('/etc/nginx/sites-available/amnezia-control')
    if existing.exists() and 'ssl_certificate' in existing.read_text():
        raise Problem('HTTPS is configured. Use panel-address.sh on the VPS to preserve your certificate setup.',409)
    panel_address(domain,port,ip)
    address=domain or ('['+ip+']' if ':' in ip else ip)
    return jsonify(ok=True,url=f'http://{address}:{port}')

@app.route('/',defaults={'path':''})
@app.route('/<path:path>')
def spa(path):
    if path.startswith('api/'): abort(404)
    return send_from_directory(DIST,path or 'index.html')

def monitor():
    while True:
        try: state.refresh()
        except Exception as e: app.logger.error('Reconciliation failed (%s)',type(e).__name__)
        time.sleep(10)

def start():
    state.initialize()
    threading.Thread(target=monitor,daemon=True).start()
    from waitress import serve
    serve(app,host='127.0.0.1',port=int(os.environ.get('PORT','8090')),threads=4)

if __name__=='__main__': start()
