"""Data-only snapshots for moving a panel to a freshly installed server."""

import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
from contextlib import closing, nullcontext

import core
import state
import warp


FORMAT = 'amnezia-control-portable-v1'
MAX_BYTES = 8 * 1024 * 1024
FIELDS = {
    'profiles': ('id', 'name', 'protocol', 'version', 'interface', 'address',
                 'port', 'endpoint', 'private_key', 'public_key', 'params', 'mtu'),
    'clients': ('id', 'name', 'description', 'protocol', 'version', 'address',
                'public_key', 'private_key', 'preshared_key', 'endpoint',
                'traffic_limit', 'expires_at', 'enabled', 'created_at', 'config',
                'profile_id', 'quota_bytes', 'used_bytes', 'download_variant_id'),
    'client_variants': ('id', 'client_id', 'profile_id', 'address', 'public_key',
                        'private_key', 'preshared_key'),
}
INTEGERS = {'id', 'port', 'mtu', 'enabled', 'created_at', 'profile_id', 'client_id',
            'quota_bytes', 'used_bytes', 'download_variant_id'}
SETTINGS = ('language', 'vpn_host', 'next_client_number')
STARTERS = {('WireGuard', 'wireguard', 'wg', 'acwg1', 51820),
            ('AmneziaWG 3.1', 'amneziawg', '3.1', 'acawg2', 51821)}


def export():
    with state.LOCK, state.connection() as con:
        con.execute('BEGIN')
        tables = {table: [dict(row) for row in con.execute(
            f'SELECT {",".join(fields)} FROM {table} ORDER BY id')]
            for table, fields in FIELDS.items()}
        settings = {name: state.value(con, name) for name in SETTINGS}
        settings['language'] = settings['language'] or 'ru'
        warp_config = warp.config()
        if warp.read('restore-pending.json', {}).get('enable') is True:
            warp_config['enabled'] = True
    profile_ids = {row['id'] for row in tables['profiles']}
    warp_config['profile_ids'] = [ident for ident in warp_config['profile_ids'] if ident in profile_ids]
    data = json.dumps({'format': FORMAT, 'settings': settings, 'warp': warp_config,
                       **tables}, ensure_ascii=False, separators=(',', ':')).encode()
    if len(data) > MAX_BYTES:
        raise core.Problem('This backup exceeds the 8 MiB web limit.', 413)
    return data


def read(file):
    if not file:
        raise core.Problem('Select a portable backup file.')
    raw = file.stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise core.Problem('This backup exceeds the 8 MiB web limit.', 413)
    try:
        data = json.loads(raw)
        validate(data)
    except (ValueError, TypeError, KeyError, RecursionError, core.Problem):
        raise core.Problem('Invalid or unsupported Amnezia Control backup.') from None
    return data, hashlib.sha256(raw).hexdigest()


def require(condition):
    if not condition:
        raise ValueError('Invalid backup data')


def validate(data):
    require(isinstance(data, dict) and set(data) == {*FIELDS, 'format', 'settings', 'warp'})
    require(data['format'] == FORMAT)
    require(isinstance(data['profiles'], list) and len(data['profiles']) <= 254)
    for table, fields in FIELDS.items():
        rows = data[table]
        require(isinstance(rows, list))
        ids = set()
        for row in rows:
            require(isinstance(row, dict) and set(row) == set(fields))
            for field, value in row.items():
                if field in INTEGERS:
                    require(type(value) is int and 0 <= value <= 2**63 - 2)
                else:
                    require(isinstance(value, str) and '\x00' not in value)
            require(row['id'] > 0 and row['id'] not in ids)
            ids.add(row['id'])

    settings = data['settings']
    require(isinstance(settings, dict) and set(settings) == set(SETTINGS))
    require(all(isinstance(value, str) for value in settings.values()))
    require(settings['language'] in ('ru', 'en'))
    if settings['vpn_host']:
        require(core.host(settings['vpn_host']) == settings['vpn_host'])
    require(1 <= int(settings['next_client_number']) <= 2**63 - 2)

    profiles = {row['id']: row for row in data['profiles']}
    networks = {}
    interfaces, ports = set(), set()
    for ident, profile in profiles.items():
        protocol, version = profile['protocol'], profile['version']
        require(protocol in ('wireguard', 'amneziawg'))
        require(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,14}', profile['interface']))
        if profile['interface'].startswith('acawg'):
            require(protocol == 'amneziawg' and re.fullmatch(r'acawg[0-9]+', profile['interface']))
        require(profile['interface'] not in interfaces and profile['port'] not in ports)
        interfaces.add(profile['interface'])
        ports.add(profile['port'])
        require(1 <= profile['port'] <= 65535 and 576 <= profile['mtu'] <= 9000)
        address = ipaddress.ip_interface(profile['address'])
        require(address.version == 4 and str(address) == profile['address'])
        require(not any(address.network.overlaps(net.network) for net in networks.values()))
        networks[ident] = address
        if profile['endpoint']:
            require(core.endpoint(profile['endpoint']) == profile['endpoint'])
        core.key(profile['private_key'])
        core.key(profile['public_key'])
        params = json.loads(profile['params'])
        require(isinstance(params, dict) and all(isinstance(value, str) for value in params.values()))
        if protocol == 'wireguard':
            require(version in ('wg', 'legacy') and not params)
        elif version == 'legacy':
            require(not params)
        else:
            require(version in core.GENERATIONS)
            core.parameters(version, params)

    clients = {row['id']: row for row in data['clients']}
    variants = {row['id']: row for row in data['client_variants']}
    peer_addresses, peer_keys, memberships = set(), set(), set()
    for peer in (*clients.values(), *variants.values()):
        ident = peer['profile_id']
        require(ident in profiles)
        address = ipaddress.ip_interface(peer['address'])
        require(address.version == 4 and address.network.prefixlen == 32 and str(address) == peer['address'])
        require(address.ip in networks[ident].network and address.ip != networks[ident].ip)
        require(address.ip not in peer_addresses and (ident, peer['public_key']) not in peer_keys)
        peer_addresses.add(address.ip)
        peer_keys.add((ident, peer['public_key']))
        core.key(peer['public_key'])
        core.key(peer['private_key'], optional='client_id' not in peer)
        core.key(peer['preshared_key'], optional=True)
        if 'client_id' in peer:
            owner = clients.get(peer['client_id'])
            membership = (peer['client_id'], ident)
            require(owner and owner['profile_id'] != ident and membership not in memberships)
            memberships.add(membership)
        else:
            # A legacy AmneziaWG export can use a WireGuard-compatible interface.
            require(peer['protocol'] in ('wireguard', 'amneziawg'))
            require(peer['enabled'] in (0, 1))
            require(not peer['expires_at'] or 1 <= int(peer['expires_at']) <= 4102444800)
            if peer['endpoint']:
                require(core.endpoint(peer['endpoint']) == peer['endpoint'])
            if peer['config']:
                core.parse_config(peer['config'])
            preferred = peer['download_variant_id']
            require(not preferred or preferred in variants and variants[preferred]['client_id'] == peer['id'])
    require(isinstance(data['warp'], dict) and set(data['warp']) == set(warp.DEFAULT))
    warp.validate(data['warp'] | {'enabled': False}, list(profiles.values()))
    require(type(data['warp']['enabled']) is bool)


def preview(data, digest):
    with state.connection() as con:
        fresh = eligible(con)
    return {'digest': digest, 'profiles': len(data['profiles']), 'clients': len(data['clients']),
            'variants': len(data['client_variants']), 'vpn_host': data['settings']['vpn_host'],
            'ports': sorted(p['port'] for p in data['profiles']), 'warp_was_enabled': data['warp']['enabled'],
            'can_restore': fresh}


def eligible(con):
    if any(con.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone()
           for table in ('clients', 'client_variants')):
        return False
    rows = con.execute('SELECT name,protocol,version,interface,port FROM profiles')
    return (all(tuple(row) in STARTERS for row in rows) and not warp.config()['enabled']
            and not warp.read('routes.json', {}).get('profiles'))


def insert_rows(con, data):
    for table, fields in FIELDS.items():
        columns, placeholders = ','.join(fields), ','.join('?' for _ in fields)
        con.executemany(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})',
                        (tuple(row[field] for field in fields) for row in data[table]))
    con.execute("""UPDATE clients SET blocked_reason = CASE
        WHEN quota_bytes > 0 AND used_bytes >= quota_bytes THEN 'quota'
        WHEN expires_at != '' AND CAST(expires_at AS INTEGER) <= ? THEN 'expired'
        ELSE '' END""", (int(time.time()),))
    for name in SETTINGS:
        state.put(con, name, data['settings'][name])


def snapshot(con, starters):
    backup = Path(tempfile.mkdtemp(prefix='before-restore-', dir=state.DATA))
    path = backup / 'control.db'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    with closing(sqlite3.connect(path)) as target:
        con.backup(target)
    for profile in starters:
        original = core.config_path(profile)
        if original.is_file():
            core.atomic_text(backup / original.name, original.read_text(encoding='utf-8'))
    for name in ('config.json', 'restore-pending.json'):
        config = warp.DATA / name
        if config.is_file():
            core.atomic_text(backup / ('warp-' + name), config.read_text(encoding='utf-8'))
    return backup


def stop_profile(profile):
    service = core.service(profile)
    core.command('systemctl', 'stop', service)
    core.command('systemctl', 'disable', service)
    core.config_path(profile).unlink(missing_ok=True)


def restore(data, digest, confirmed):
    if not hmac.compare_digest(digest, confirmed):
        raise core.Problem('Backup changed. Preview it again.', 409)
    warp_lock = warp.lock(blocking=False) if os.name == 'posix' else nullcontext()
    with warp_lock, state.LOCK, state.connection() as con:
        if not eligible(con):
            raise core.Problem('Restore requires a fresh panel with no clients and WARP disabled.', 409)
        starters = [dict(row) for row in con.execute('SELECT * FROM profiles')]
        starter_paths = {core.config_path(profile) for profile in starters}
        starter_names = {profile['interface'] for profile in starters}
        starter_ports = {profile['port'] for profile in starters}
        links = {row['ifname'] for row in json.loads(core.command('ip', '-j', 'link', 'show') or '[]')}
        sockets = core.command('ss', '-H', '-lun').splitlines()
        busy_ports = {int(fields[3].rsplit(':', 1)[-1]) for line in sockets
                      if len(fields := line.split()) > 3 and fields[3].rsplit(':', 1)[-1].isdigit()}
        for profile in starters:
            if profile['interface'] in links and core.command(core.binary(profile), 'show', profile['interface'], 'peers'):
                raise core.Problem('A starter VPN has active peers outside the panel.', 409)
        for profile in data['profiles']:
            path = core.config_path(profile)
            if (path.exists() and path not in starter_paths or
                profile['interface'] in links - starter_names or profile['port'] in busy_ports - starter_ports):
                raise core.Problem('A backup interface or UDP port is already in use on this server.', 409)
            if core.command(core.binary(profile), 'pubkey', input=profile['private_key'] + '\n') != profile['public_key']:
                raise core.Problem('Backup server keys do not match.', 400)

        backup = snapshot(con, starters)
        stopped, applied = [], []
        try:
            con.execute('BEGIN IMMEDIATE')
            con.execute('DELETE FROM profiles')
            insert_rows(con, data)
            for profile in starters:
                stopped.append(profile)
                stop_profile(profile)
            for profile in data['profiles']:
                applied.append(profile)
                state.sync(con, profile)
            warp.save('config.json', data['warp'] | {'enabled': False})
            warp.save('restore-pending.json', {'enable': data['warp']['enabled']})
            state.audit(con, f"Portable backup restored: {len(data['clients'])} clients")
            con.commit()
        except Exception as exc:
            con.rollback()
            rollback_failed = False
            for profile in reversed(applied):
                try:
                    stop_profile(profile)
                except Exception:
                    rollback_failed = True
            for profile in stopped:
                try:
                    previous = backup / core.config_path(profile).name
                    if previous.is_file():
                        core.atomic_text(core.config_path(profile), previous.read_text(encoding='utf-8'))
                    state.sync(con, profile)
                except Exception:
                    rollback_failed = True
            for name in ('config.json', 'restore-pending.json'):
                try:
                    previous = backup / ('warp-' + name)
                    if previous.is_file():
                        core.atomic_text(warp.DATA / name, previous.read_text(encoding='utf-8'))
                    else:
                        (warp.DATA / name).unlink(missing_ok=True)
                except OSError:
                    rollback_failed = True
            reason = ('Rollback needs attention.' if rollback_failed else 'Changes rolled back.')
            raise core.Problem(f'Restore failed. {reason} Recovery copy: {backup.name}', 503) from exc
    return {'ok': True, 'clients': len(data['clients']), 'profiles': len(data['profiles']),
            'recovery': backup.name, 'language': data['settings']['language']}
