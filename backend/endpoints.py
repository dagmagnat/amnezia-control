"""Change the advertised VPN host without altering keys, ports or runtime peers."""
import ipaddress
import json
import os
import secrets
import sqlite3
import subprocess
import time

import core
import routewolf
import state


def check(profile):
    """Resolve the configured destination and check its own server listener."""
    destination = core.endpoint(profile['endpoint'])
    name, port = destination.rsplit(':', 1)
    name = name.strip('[]')
    addresses = set()
    try:
        addresses.add(ipaddress.ip_address(name))
    except ValueError:
        try:
            result = subprocess.run(['getent', 'ahosts', name], text=True, capture_output=True, timeout=5)
            for line in result.stdout.splitlines():
                fields = line.split()
                if fields:
                    addresses.add(ipaddress.ip_address(fields[0]))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    try:
        links = json.loads(core.command('ip', '-j', 'address', 'show'))
        local = {ipaddress.ip_address(item['local']) for link in links for item in link.get('addr_info', [])}
        local_matches = [str(value) for value in sorted(addresses & local, key=str)]
    except (core.Problem, ValueError, KeyError):
        local_matches = None
    try:
        bound = core.command(core.binary(profile), 'show', profile['interface'], 'listen-port')
        if routewolf.is_wrapped(profile):
            core.command('systemctl', 'is-active', routewolf.service(profile))
            bound = str(routewolf.external_port(profile))
    except core.Problem:
        bound = ''
    return {'endpoint': destination, 'addresses': sorted(map(str, addresses)), 'local_matches': local_matches,
            'advertised_port': int(port), 'listen_port': int(bound) if bound.isdecimal() else None}


def change_host(con, hostname):
    hostname=core.host(hostname)
    def replace(destination, fallback=None):
        port=destination.rsplit(':',1)[1] if destination else fallback
        return core.endpoint(('['+hostname+']' if ':' in hostname else hostname)+':'+str(port))
    profiles=[]
    for row in con.execute('SELECT * FROM profiles'):
        updated = replace(row['endpoint'], row['port'])
        if updated != row['endpoint']:
            if routewolf.is_wrapped(row):
                routewolf.check_endpoint_change(row, updated)
            profiles.append((updated, row['id']))
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
