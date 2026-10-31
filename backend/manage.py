"""Root-only management entry point used by shell scripts."""
import argparse
import ipaddress
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
from pathlib import Path
from core import Problem, command, keys, key, parameters, endpoint, host, number, atomic_text
import state
from password_hash import hash_password


def panel_address(domain, port, ip):
    port=number(port,1024,65535)
    if port==8090: raise Problem('8090 is reserved for the internal backend')
    names=' '.join(dict.fromkeys([host(ip)] + ([host(domain)] if domain else []) + ['_']))
    path=Path('/etc/nginx/sites-available/amnezia-control')
    text=f'''server {{
    listen {port};
    server_name {names};
    client_max_body_size 9m;
    location / {{
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
    }}
}}
'''
    previous=path.read_text() if path.exists() else None
    if previous: atomic_text(path.with_suffix('.before-change'),previous)
    atomic_text(path,text)
    link=Path('/etc/nginx/sites-enabled/amnezia-control')
    if not link.exists(): link.symlink_to(path)
    try: command('nginx','-t'); command('systemctl','reload','nginx')
    except Problem:
        if previous: atomic_text(path,previous)
        else: link.unlink(missing_ok=True); path.unlink(missing_ok=True)
        raise
    with state.connection() as con:
        state.put(con,'panel_port',port);state.put(con,'panel_domain',domain);state.put(con,'panel_ip',ip)


def provision(public_host):
    with state.LOCK,state.connection() as con:
        for protocol,version in [('wireguard','wg'),('amneziawg','3.1')]:
            if con.execute('SELECT 1 FROM profiles WHERE protocol=?',(protocol,)).fetchone(): continue
            n=con.execute('SELECT COALESCE(MAX(id),0)+1 FROM profiles').fetchone()[0]
            port=51820 if protocol=='wireguard' else 51821
            while con.execute('SELECT 1 FROM profiles WHERE port=?',(port,)).fetchone(): port+=1
            network=f'10.77.{n}.1/24'; iface=('acwg' if protocol=='wireguard' else 'acawg')+str(n)
            b='wg' if protocol=='wireguard' else 'awg';private,public=keys(b)
            params=parameters(version) if b=='awg' else {}
            destination=endpoint((f'[{public_host}]' if ':' in public_host else public_host)+':'+str(port))
            cur=con.execute('INSERT INTO profiles(name,protocol,version,interface,address,port,endpoint,private_key,public_key,params) VALUES(?,?,?,?,?,?,?,?,?,?)',
                ('WireGuard' if b=='wg' else 'AmneziaWG 3.1',protocol,version,iface,network,port,destination,private,public,json.dumps(params)))
            profile=dict(con.execute('SELECT * FROM profiles WHERE id=?',(cur.lastrowid,)).fetchone())
            state.sync(con,profile)
            state.audit(con,'Default profile provisioned: '+protocol)


def web_limits():
    path=Path('/etc/nginx/sites-available/amnezia-control')
    if not path.exists(): return
    previous=path.read_text()
    if re.search(r'\bclient_max_body_size\s+[^;]+;',previous):
        text=re.sub(r'\bclient_max_body_size\s+[^;]+;', 'client_max_body_size 9m;', previous)
    else:
        text=re.sub(r'\bserver\s*\{', 'server {\n    client_max_body_size 9m;', previous)
    if text==previous: return
    atomic_text(path,text)
    try: command('nginx','-t'); command('systemctl','reload','nginx')
    except Problem:
        atomic_text(path,previous)
        raise


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['init','migrate','reconcile','provision','panel','restore','password','web-limits']); args=parser.parse_args()
    state.initialize()
    if args.action=='init':
        cfg=json.load(sys.stdin)
        with state.connection() as con:
            if state.value(con,'admin_user'): raise Problem('Administrator already exists. Use update.')
            if len(cfg['password'])<10: raise Problem('Password must be at least 10 characters')
            state.put(con,'admin_user',cfg['username']);state.put(con,'admin_password',hash_password(cfg['password']))
            state.put(con,'language',cfg.get('language','ru'))
            state.audit(con,'Panel installed')
    elif args.action=='reconcile':
        with state.connection() as con:
            for p in con.execute('SELECT * FROM profiles').fetchall(): state.sync(con,dict(p))
    elif args.action=='provision': provision(host(json.load(sys.stdin)['host']))
    elif args.action=='panel': panel_address(**json.load(sys.stdin))
    elif args.action=='web-limits': web_limits()
    elif args.action=='password':
        import getpass
        password=getpass.getpass('New password / Новый пароль: ')
        if len(password)<10 or getpass.getpass('Repeat / Повторите: ')!=password: raise Problem('Password mismatch or too short')
        with state.connection() as con:
            state.put(con,'admin_password',hash_password(password)); state.put(con,'auth_revision',secrets.token_hex(16))
    elif args.action=='restore':
        # Root only, stopped services, trusted backup. SQL backups contain private keys.
        source=Path(input('SQL backup / SQL копия: ').strip()).resolve()
        if input('Type RESTORE / Введите RESTORE: ')!='RESTORE': return
        command('systemctl','stop','amnezia-control')
        temporary=state.DB.with_suffix('.restoring')
        try:
            con=sqlite3.connect(temporary); con.executescript(source.read_text(encoding='utf-8-sig'))
            assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; con.close()
            shutil.copy2(state.DB,state.DB.with_suffix('.before-restore'))
            os.replace(temporary,state.DB)
            state.initialize()
        finally: command('systemctl','start','amnezia-control')
    print('OK')

if __name__=='__main__':
    try: main()
    except Problem as exc: print(str(exc),file=sys.stderr);sys.exit(1)
