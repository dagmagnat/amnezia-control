"""Revoke selected local VPN clients with a snapshot and multi-interface rollback."""
import os
import secrets
import sqlite3
import time

import state
from core import Problem


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
