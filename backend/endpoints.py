"""Change the advertised VPN host without altering keys, ports or runtime peers."""
import os
import secrets
import sqlite3
import time

import core
import state


def change_host(con, hostname):
    hostname=core.host(hostname)
    def replace(destination, fallback=None):
        port=destination.rsplit(':',1)[1] if destination else fallback
        return core.endpoint(('['+hostname+']' if ':' in hostname else hostname)+':'+str(port))
    profiles=[(replace(r['endpoint'],r['port']),r['id']) for r in con.execute('SELECT id,endpoint,port FROM profiles')
              if replace(r['endpoint'],r['port'])!=r['endpoint']]
    clients=[(replace(r['endpoint']),r['id']) for r in con.execute("SELECT id,endpoint FROM clients WHERE endpoint!=''")
             if replace(r['endpoint'])!=r['endpoint']]
    if profiles or clients:
        folder=state.DATA/'endpoint-backups';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
        path=folder/(time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4)+'.db')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
        target=sqlite3.connect(path)
        try:
            with state.connection() as source: source.backup(target)
        finally: target.close()
        con.executemany('UPDATE profiles SET endpoint=? WHERE id=?',profiles)
        con.executemany('UPDATE clients SET endpoint=? WHERE id=?',clients)
        state.audit(con,'VPN endpoint host updated: '+hostname)
    state.put(con,'vpn_host',hostname)
    return {'profiles':len(profiles),'client_overrides':len(clients)}
