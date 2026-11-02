"""Additional protocol generations, sharing one client's access and traffic budget."""
import ipaddress
import os
import secrets
import sqlite3
import time

import core
import state
from provision import ensure_profile, cleanup_profile


def selected(con, data):
    ids=data.get('ids')
    if not isinstance(ids,list) or not ids or len(ids)>1000 or any(type(i) is not int or i<1 for i in ids) or len(set(ids))!=len(ids):
        raise core.Problem('Select 1–1000 unique client IDs')
    rows=[dict(r) for r in con.execute('SELECT * FROM clients WHERE id IN ('+','.join('?' for _ in ids)+') ORDER BY id',ids)]
    if len(rows)!=len(ids): raise core.Problem('Client list changed. Refresh it before applying.',409)
    return rows


def existing(con, row, version):
    candidates=state.client_profiles(con,row['id'])
    return next((p for p in candidates if p['protocol']=='amneziawg' and p['version']==version
                 and (p['id']!=row['profile_id'] or row['private_key'] or con.execute(
                     'SELECT 1 FROM client_variants WHERE client_id=? AND profile_id=?',(row['id'],p['id'])).fetchone())),None)


def options(con, row):
    result=[{'id':0,'protocol':row['protocol'],'version':row['version'],'address':row['address'],'downloadable':bool(row['private_key'])}]
    result += [dict(v) | {'downloadable':True} for v in con.execute('''SELECT v.id,v.address,p.protocol,p.version FROM client_variants v
               JOIN profiles p ON p.id=v.profile_id WHERE v.client_id=? ORDER BY v.id''',(row['id'],))]
    return result


def configuration(con, row, variant_id=0):
    if variant_id:
        variant=con.execute('SELECT * FROM client_variants WHERE id=? AND client_id=?',(variant_id,row['id'])).fetchone()
        if not variant: raise core.Problem('Client version not found',404)
        row=dict(row) | {k:variant[k] for k in ('address','profile_id','private_key','public_key','preshared_key')} | {'endpoint':'','config':''}
    profile=con.execute('SELECT * FROM profiles WHERE id=?',(row['profile_id'],)).fetchone()
    if not profile: raise core.Problem('Client VPN profile is missing',409)
    return state.client_config(row,dict(profile))


def add(data):
    version=data.get('version')
    if version not in core.GENERATIONS: raise core.Problem('Choose a supported AmneziaWG generation')
    with state.LOCK,state.connection() as con:
        rows=selected(con,data)
        pending=[row for row in rows if not existing(con,row,version)]
        if not pending: return {'ok':True,'created':0,'skipped':len(rows)}
        folder=state.DATA/'version-backups';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
        backup=folder/(time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4)+'.db')
        fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
        target=sqlite3.connect(backup)
        try:
            with state.connection() as source: source.backup(target)
        finally: target.close()
        originals={};created_profiles={}; additions={}
        try:
            for row in pending:
                p,created=ensure_profile(con,'amneziawg',version)
                if created: created_profiles[p['id']]=p
                if p['id'] not in originals: originals[p['id']]=(p,state.all_peers(con,p['id']))
                network=ipaddress.ip_interface(p['address']).network;taken=state.taken_addresses(con)
                address=next((str(ip)+'/32' for ip in network.hosts() if str(ip) not in taken),None)
                if not address: raise core.Problem('Subnet is full')
                private,public=core.keys('awg');psk=core.key(core.command('awg','genpsk'))
                con.execute('INSERT INTO client_variants(client_id,profile_id,address,private_key,public_key,preshared_key) VALUES(?,?,?,?,?,?)',
                            (row['id'],p['id'],address,private,public,psk))
                additions.setdefault(p['id'],[]).append(dict(row,address=address,public_key=public,preshared_key=psk,enabled=0))
            for p,_ in originals.values(): state.sync(con,p)
            state.audit(con,'Additional AmneziaWG '+version+': '+str(len(pending))+' clients; original connections preserved')
            con.commit()
        except Exception:
            con.rollback();failed=False
            for pid,(p,peers) in originals.items():
                if pid in created_profiles:
                    cleanup_profile(p);continue
                try: state.ENGINE.apply(p,peers+additions.get(pid,[]))
                except Exception: failed=True
            if failed: raise core.Problem('Adding versions failed; VPN rollback needs attention. Database snapshot saved.',503)
            raise
    return {'ok':True,'created':len(pending),'skipped':len(rows)-len(pending),'backup':backup.name}
