"""Revoke selected local VPN clients with a snapshot and multi-interface rollback."""
import os
import secrets
import sqlite3
import time

import state
from core import Problem


def update_clients(data):
    """Change selected parents atomically, synchronizing each affected interface once."""
    import versions
    if not isinstance(data,dict): raise Problem('Invalid bulk action')
    action=data.get('action')
    fields={'enable':set(),'disable':set(),'extend':{'days'},'set_expiry':{'expires_at'},
            'clear_expiry':set(),'set_quota':{'quota_bytes'},'reset_usage':set()}
    if not isinstance(action,str) or action not in fields: raise Problem('Choose a supported bulk action')
    if set(data)!={'ids','action'}|fields[action]: raise Problem('Invalid bulk action fields')
    now=int(time.time());value=None
    if action in ('extend','set_expiry','set_quota'):
        field=next(iter(fields[action]));value=data[field]
        limits={'extend':(1,3650),'set_expiry':(now+1,4102444800),'set_quota':(0,10**16)}
        low,high=limits[action]
        if type(value) is not int or not low<=value<=high: raise Problem('Invalid '+field)
    with state.LOCK,state.connection() as con:
        rows=versions.selected(con,data);plans=[];pids=set();unchanged=0
        for original in rows:
            c=dict(original)
            if action in ('enable','disable'): c['enabled']=int(action=='enable')
            elif action=='extend':
                # Extending unlimited access must never turn it into expiring access.
                if not c['expires_at']: unchanged+=1;continue
                c['expires_at']=str(max(now,int(c['expires_at']))+value*86400)
                if int(c['expires_at'])>4102444800: raise Problem('Extended expiry is too far in the future')
            elif action=='set_expiry': c['expires_at']=str(value)
            elif action=='clear_expiry': c['expires_at']=''
            elif action=='set_quota': c['quota_bytes']=value
            elif action=='reset_usage': c['used_bytes']=0
            c['blocked_reason']='quota' if c['quota_bytes'] and c['used_bytes']>=c['quota_bytes'] else ('expired' if c['expires_at'] and int(c['expires_at'])<=now else '')
            names=('enabled','expires_at','quota_bytes','used_bytes','blocked_reason')
            if all(c[k]==original[k] for k in names): unchanged+=1;continue
            if bool(original['enabled'] and not original['blocked_reason'])!=bool(c['enabled'] and not c['blocked_reason']):
                pids.update(p['id'] for p in state.client_profiles(con,c['id']))
            plans.append(c)
        originals=[]
        for pid in sorted(pids):
            profile=con.execute('SELECT * FROM profiles WHERE id=?',(pid,)).fetchone()
            if not profile: raise Problem('Client VPN profile is missing',409)
            originals.append((dict(profile),state.all_peers(con,pid)))
        backup=None
        if plans:
            folder=state.DATA/'client-action-backups';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
            backup=folder/(time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4)+'.db')
            fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            target=sqlite3.connect(backup)
            try:
                with state.connection() as source: source.backup(target)
            finally: target.close()
        try:
            for c in plans:
                con.execute('UPDATE clients SET enabled=?,expires_at=?,quota_bytes=?,used_bytes=?,blocked_reason=? WHERE id=?',
                            (c['enabled'],c['expires_at'],c['quota_bytes'],c['used_bytes'],c['blocked_reason'],c['id']))
            for profile,_ in originals: state.sync(con,profile)
            if plans: state.audit(con,'Bulk action '+action+': '+str(len(plans))+' clients; backup: '+backup.name)
            con.commit()
        except Exception:
            con.rollback();failed=False
            for profile,peers in originals:
                try: state.ENGINE.apply(profile,peers)
                except Exception: failed=True
            if failed: raise Problem('Bulk update failed; VPN rollback needs attention. The database snapshot is saved.',503)
            raise
        current=[con.execute('SELECT enabled,blocked_reason FROM clients WHERE id=?',(r['id'],)).fetchone() for r in rows]
    return {'ok':True,'action':action,'selected':len(rows),'updated':len(plans),'unchanged':unchanged,
            'restricted':sum(not c['enabled'] or bool(c['blocked_reason']) for c in current),
            'backup':backup.name if backup else None}


def delete_clients(ids):
    if not isinstance(ids,list) or not ids or len(ids)>1000 or any(type(i) is not int or i<1 for i in ids):
        raise Problem('Select 1–1000 client IDs')
    if len(set(ids))!=len(ids): raise Problem('Duplicate client IDs')
    marks=','.join('?' for _ in ids)
    with state.LOCK,state.connection() as con:
        rows=con.execute('SELECT * FROM clients WHERE id IN ('+marks+')',ids).fetchall()
        if len(rows)!=len(ids): raise Problem('Client list changed. Refresh it before deleting.',409)
        if any(row['profile_id'] is None for row in rows): raise Problem('Client VPN profile is missing',409)
        originals=[];pids={row['profile_id'] for row in rows}
        pids.update(r['profile_id'] for r in con.execute('SELECT profile_id FROM client_variants WHERE client_id IN ('+marks+')',ids))
        if None in pids: raise Problem('Client VPN profile is missing',409)
        for pid in sorted(pids):
            profile=con.execute('SELECT * FROM profiles WHERE id=?',(pid,)).fetchone()
            if not profile: raise Problem('Client VPN profile is missing',409)
            originals.append((dict(profile),state.all_peers(con,pid)))
        folder=state.DATA/'client-delete-backups';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
        backup=folder/(time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4)+'.db')
        fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        target=sqlite3.connect(backup)
        try:
            with state.connection() as source: source.backup(target)
        finally: target.close()
        try:
            # Keep revoked peers in the registry during sync so Engine will not
            # mistake them for unmanaged peers that must be preserved.
            con.execute('UPDATE clients SET enabled=0 WHERE id IN ('+marks+')',ids)
            for profile,_ in originals: state.sync(con,profile)
            con.execute('DELETE FROM client_variants WHERE client_id IN ('+marks+')',ids)
            con.execute('DELETE FROM clients WHERE id IN ('+marks+')',ids)
            state.audit(con,'Clients deleted: '+str(len(ids))+'; backup: '+backup.name)
            con.commit()
        except Exception:
            con.rollback();failed=False
            for profile,peers in originals:
                try: state.ENGINE.apply(profile,peers)
                except Exception: failed=True
            if failed: raise Problem('Deletion failed; VPN rollback needs attention. The original database snapshot is saved.',503)
            raise
    return {'ok':True,'deleted':len(ids),'backup':backup.name}
