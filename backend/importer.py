"""Bounded, non-executing VPN migration with a stateless, reviewed import plan.

Archive contents are read into memory, never extracted or executed. Import keeps
the original server and client identities; no key generation occurs here.
"""
import hashlib
import io
import ipaddress
import json
import re
import sqlite3
import stat
import tarfile
import time
import zipfile
from pathlib import PurePosixPath

import core
import state
from provision import cleanup_profile

MAX_UPLOAD = 8 * 1024 * 1024
MAX_EXPANDED = 24 * 1024 * 1024
MAX_FILES = 4096
HOOKS = {'PreUp', 'PostUp', 'PreDown', 'PostDown'}
LOCAL_PARAMS = {'Jc', 'Jmin', 'Jmax', 'I1', 'I2', 'I3', 'I4', 'I5'}


def read_uploads(uploads):
    files = {}; total = expanded = count = 0

    def add(name, size, reader):
        nonlocal expanded, count
        name = name.replace('\\', '/')
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or ':' in name or '\x00' in name:
            raise core.Problem('Unsafe archive path')
        count += 1; expanded += size
        if count > MAX_FILES or expanded > MAX_EXPANDED:
            raise core.Problem('Archive exceeds import limits')
        if not name.lower().endswith('.conf'): return
        if size > 2 * 1024 * 1024: raise core.Problem('Configuration exceeds 2 MiB')
        name = str(path)
        if name in files: raise core.Problem('Duplicate configuration filename')
        try: files[name] = reader().decode('utf-8-sig')
        except (UnicodeError, RuntimeError, OSError): raise core.Problem('Cannot read configuration as UTF-8')

    try:
        for upload in uploads:
            raw = upload.read(MAX_UPLOAD + 1); total += len(raw)
            if total > MAX_UPLOAD: raise core.Problem('Upload exceeds 8 MiB')
            name = upload.filename or 'import.conf'
            if name.lower().endswith('.conf'):
                add(PurePosixPath(name.replace('\\', '/')).name, len(raw), lambda: raw)
            elif name.lower().endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    for item in archive.infolist():
                        mode = item.external_attr >> 16
                        if stat.S_ISLNK(mode) or item.flag_bits & 1: raise core.Problem('Links and encrypted archives are not supported')
                        if item.is_dir():
                            count+=1
                            if count>MAX_FILES: raise core.Problem('Archive exceeds import limits')
                            continue
                        add(item.filename, item.file_size, lambda: archive.read(item))
            elif name.lower().endswith(('.tar.gz', '.tgz', '.tar')):
                with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as archive:
                    for item in archive:
                        if item.isdir():
                            count+=1
                            if count>MAX_FILES: raise core.Problem('Archive exceeds import limits')
                            continue
                        if not item.isfile(): raise core.Problem('Archive links and special files are not supported')
                        add(item.name, item.size, lambda: archive.extractfile(item).read())
            else: raise core.Problem('Use .conf, .zip or .tar.gz')
    except (tarfile.TarError, zipfile.BadZipFile, EOFError, OSError):
        raise core.Problem('Invalid or damaged archive')
    if not files: raise core.Problem('No VPN .conf found. A panel database alone does not contain the VPN server configuration.')
    return files


def generation(params):
    if any(k in params for k in ('RandomTrailers', 'DisableCookies')): return '3.1'
    if 'HeaderProtectionKey' in params: return '3.0'
    if any(k in params for k in ('S3', 'S4')): return '2.0'
    if any(k in params for k in ('I1', 'I2', 'I3', 'I4', 'I5')): return '1.5'
    return '1.0' if params else 'wg'


def exact_params(fields):
    params = {k: fields[k] for k in core.PARAMS if k in fields}
    if params: core.parameters(generation(params), params)  # Validate only: never fill missing fields on import.
    return params


def wireguard_compatible(params):
    # Legacy AntiZapret sends junk/CPS packets but keeps standard WireGuard
    # handshake sizes and message identifiers. Modern AWG obfuscation is not WG.
    return (not (set(params) - (set(core.BASE) | LOCAL_PARAMS))
            and all(params.get('S'+str(i),'0') == '0' for i in (1,2))
            and all(params.get('H'+str(i),str(i)) == str(i) for i in range(1,5)))


def parse_server(text):
    interface = {}; peers = []; target = None; pending = {}; ignored = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line: continue
        if line.startswith(('#', ';')):
            match = re.fullmatch(r'#\s*(Client|PrivateKey)\s*=\s*(.*)', line)
            if match: pending[match[1]] = match[2].strip()
            continue
        if line == '[Interface]':
            if target is not None: raise core.Problem('Duplicate or misplaced Interface')
            target = interface; continue
        if line == '[Peer]':
            if target is None: raise core.Problem('Peer before Interface')
            target = {'_name': pending.get('Client', ''), '_private': pending.get('PrivateKey', '')}
            pending = {}; peers.append(target); continue
        if target is None or '=' not in line: raise core.Problem('Invalid server configuration')
        name, value = (s.strip() for s in line.split('=', 1))
        value = value.split(' #', 1)[0].strip()
        if target is interface and name in HOOKS | {'SaveConfig', 'Table', 'FwMark', 'DNS'}:
            ignored.add(name); continue
        allowed = ({'PrivateKey', 'Address', 'ListenPort', 'MTU'} | set(core.PARAMS)) if target is interface else {'PublicKey', 'PresharedKey', 'AllowedIPs', 'PersistentKeepalive', 'Endpoint'}
        if name not in allowed or name in target: raise core.Problem('Unsupported or duplicate server field: ' + name)
        if len(value) > 4096: raise core.Problem('Server field too long')
        target[name] = value
    core.key(interface.get('PrivateKey'))
    core.number(interface.get('ListenPort'), 1024, 65535)
    try:
        address = ipaddress.ip_interface(interface.get('Address', ''))
        if address.version != 4 or not address.network.is_private or not 16 <= address.network.prefixlen <= 30: raise ValueError()
    except ValueError: raise core.Problem('Server migration requires one private IPv4 subnet, /16 to /30')
    core.number(interface.get('MTU', '1380'), 576, 9000)
    exact_params(interface)
    seen_keys = set(); seen_ips = set()
    for peer in peers:
        public = core.key(peer.get('PublicKey')); core.key(peer.get('PresharedKey'), True)
        if peer['_private']: core.key(peer['_private'])
        try:
            network = ipaddress.ip_network(peer.get('AllowedIPs', ''))
            if network.version != 4 or network.prefixlen != 32 or network.network_address not in address.network or network.network_address in (address.ip, address.network.network_address, address.network.broadcast_address): raise ValueError()
        except ValueError: raise core.Problem('Only individual IPv4 /32 clients in the server subnet can be migrated')
        if public in seen_keys or str(network) in seen_ips: raise core.Problem('Duplicate server peer key or address')
        seen_keys.add(public); seen_ips.add(str(network))
    return interface, peers, sorted(ignored)


def fingerprint(con):
    # Counters may change while the operator reviews a plan. Identity changes may not.
    records = [list(r) for r in con.execute('SELECT id,public_key,address,port,params FROM profiles ORDER BY id')]
    records += [list(r) for r in con.execute('SELECT id,profile_id,public_key,address,private_key,preshared_key,config FROM clients ORDER BY id')]
    return hashlib.sha256(json.dumps(records).encode()).hexdigest()


def build_plan(con, files, options):
    mode = options.get('mode', 'clients'); errors = []; warnings = []; entries = []; sources = []
    for name, text in files.items():
        if re.search(r'^\s*ListenPort\s*=', text, re.M): sources.append(name)
    selected = options.get('server_file') or (sources[0] if len(sources) == 1 else '')
    profile = None; new = False; known_peers = None
    if mode == 'server':
        if not selected or selected not in sources:
            return {'mode': mode, 'sources': sources, 'errors': ['Select one original server configuration'], 'warnings': [], 'clients': [], 'can_apply': False}, None, []
        fields, known_peers, ignored = parse_server(files[selected]); params = exact_params(fields)
        protocol = 'amneziawg' if params else 'wireguard'; version = generation(params)
        public = core.key(core.command('awg' if params else 'wg', 'pubkey', input=fields['PrivateKey']+'\n'))
        destination = core.endpoint(options.get('endpoint', ''))
        port = int(fields['ListenPort'])
        if int(destination.rsplit(':', 1)[1]) != port:
            warnings.append('Endpoint port differs from ListenPort. An external UDP relay must forward it to the original server port.')
        profile = dict(name=PurePosixPath(selected).stem[:60], protocol=protocol, version=version,
                       address=fields['Address'], port=port, endpoint=destination, private_key=fields['PrivateKey'],
                       public_key=public, params=json.dumps(params), mtu=int(fields.get('MTU', 1380)))
        matches = [dict(p) for p in con.execute('SELECT * FROM profiles') if p['public_key'] == public and p['address'] == profile['address'] and p['protocol'] == protocol]
        if matches:
            profile = matches[0]
            if profile['port'] != port or json.loads(profile['params']) != params: errors.append('Existing server identity has different port or parameters')
        else:
            new = True
            n = con.execute('SELECT COALESCE(MAX(id),0)+1 FROM profiles').fetchone()[0]
            profile['interface'] = ('acawg' if params else 'acwg') + str(n)
            if core.config_path(profile).exists(): errors.append('Target interface file already exists')
            network = ipaddress.ip_interface(profile['address']).network
            for p in con.execute('SELECT * FROM profiles'):
                if p['port'] == port: errors.append('Original UDP port is already used by another profile')
                if network.overlaps(ipaddress.ip_interface(p['address']).network): errors.append('Original subnet overlaps an existing profile')
            busy = core.command('ss', '-H', '-lun')
            if any(len(parts := line.split()) > 3 and parts[3].rsplit(':', 1)[-1] == str(port) for line in busy.splitlines()): errors.append('Original UDP port is already listening on this VPS')
        if ignored: warnings.append('Server hooks and network-specific fields will not be executed: ' + ', '.join(ignored))
        if any('/antizapret' in '/'+name.lower() for name in [selected]):
            warnings.append('AntiZapret selective routing and its internal DNS are not restored. Client .conf files are needed to check routes and DNS before switching devices.')
        if not params: warnings.append('This server file is standard WireGuard. AmneziaWG obfuscation will not be invented; provide original AmneziaWG client files to check compatibility.')
    elif mode == 'clients':
        row = con.execute('SELECT * FROM profiles WHERE id=?', (options.get('profile_id'),)).fetchone()
        if not row: raise core.Problem('Choose the destination VPN profile')
        profile = dict(row)
    else: raise core.Problem('Unknown import mode')

    supplied = {}; server_params = json.loads(profile['params'])
    for name, text in files.items():
        if name in sources: continue
        try:
            interface, peer = core.parse_config(text)
            if peer['PublicKey'] != profile['public_key']:
                if mode == 'clients': errors.append(name + ': different server public key')
                continue
            params = exact_params(interface)
            if profile['protocol'] == 'wireguard' and params:
                if not wireguard_compatible(params): raise core.Problem('AmneziaWG client requires its original AmneziaWG server parameters; no silent conversion to WireGuard')
                warnings.append('Legacy AmneziaWG client with S1/S2=0 and H1-H4=1/2/3/4: its original junk/CPS fields are preserved with the standard WireGuard server.')
            else:
                for k in set(core.PARAMS) - LOCAL_PARAMS:
                    if params.get(k) != server_params.get(k): raise core.Problem('Shared AmneziaWG parameter mismatch: ' + k)
            address = ipaddress.ip_interface(interface['Address'])
            network = ipaddress.ip_interface(profile['address'])
            if mode=='server' and address.ip not in network.network: continue
            if address.version != 4 or address.ip not in network.network or address.ip in (network.ip, network.network.network_address, network.network.broadcast_address): raise core.Problem('Client address does not belong to the server subnet')
            public = core.key(core.command(core.binary(profile), 'pubkey', input=interface['PrivateKey']+'\n'))
            item = dict(name=PurePosixPath(name).stem[:30], address=str(address.ip)+'/32', public_key=public,
                        private_key=interface['PrivateKey'], preshared_key=peer.get('PresharedKey', ''), endpoint=core.endpoint(peer.get('Endpoint', '')), config=text,
                        description='Imported client .conf',client_protocol='amneziawg' if params else profile['protocol'],client_version=generation(params) if params else profile['version'])
            if peer['Endpoint'].rsplit(':',1)[1] != str(profile['port']):
                warnings.append('An imported client uses a different external UDP port. Preserve its existing relay/NAT mapping before switching devices.')
            if 'DNS' in interface:
                try:
                    if any(ipaddress.ip_address(x.strip()).is_private for x in interface['DNS'].split(',')):
                        warnings.append('An imported client uses private DNS. Its DNS service must also be migrated; it is not provided by this import.')
                except ValueError: pass
            if public in supplied:
                if supplied[public]['config'] != text: raise core.Problem('Conflicting client files for the same public key')
                continue
            supplied[public] = item
        except core.Problem as exc: errors.append(name + ': ' + str(exc))
    if known_peers is not None:
        for index, peer in enumerate(known_peers, 1):
            public = peer['PublicKey']; item = supplied.pop(public, None)
            if item:
                if item['address'] != str(ipaddress.ip_network(peer['AllowedIPs'])) or item['preshared_key'] != peer.get('PresharedKey', ''):
                    errors.append('Client file conflicts with original server peer #' + str(index))
            else:
                private = peer['_private']
                if private and core.key(core.command(core.binary(profile), 'pubkey', input=private+'\n')) != public:
                    errors.append('Client private/public key mismatch in original server peer #' + str(index))
                item = dict(name=(peer['_name'] or 'Imported '+str(index))[:30], description='Imported server peer',
                            public_key=public, private_key=private, preshared_key=peer.get('PresharedKey', ''),
                            address=str(ipaddress.ip_network(peer['AllowedIPs'])), endpoint='', config='')
            entries.append(item)
        if supplied: errors.append('Some supplied client files are absent from the original server peer list')
    else: entries = list(supplied.values())
    if not entries: errors.append('No matching clients found')
    seen = set()
    for item in entries:
        if item['address'] in seen: errors.append('Duplicate client address in upload')
        seen.add(item['address']); item['action'] = 'create'
        rows = [dict(r) for r in con.execute('SELECT * FROM clients WHERE (public_key=? AND profile_id=?) OR address=?', (item['public_key'],profile.get('id'),item['address']))]
        if rows:
            row = rows[0]
            if len(rows) != 1 or row['public_key'] != item['public_key'] or row['address'] != item['address'] or row['profile_id'] != profile.get('id'):
                errors.append('Client identity/address conflicts with an existing client: ' + item['name']); continue
            item['id'] = row['id']; item['action'] = 'skip'
            if row['preshared_key'] != item['preshared_key'] or (row['private_key'] and item['private_key'] and row['private_key'] != item['private_key']):
                errors.append('Existing client key differs: ' + item['name'])
            elif (item['private_key'] and not row['private_key']) or (item['config'] and not row['config']): item['action'] = 'complete'
    missing = sum(not c['private_key'] for c in entries)
    reconstructed = sum(bool(c['private_key']) and not c['config'] for c in entries)
    if missing: warnings.append(f'{missing} clients have no private key: existing device files keep working, but QR/download is unavailable until those .conf files are supplied.')
    if reconstructed: warnings.append(f'{reconstructed} clients have keys but no original .conf. Downloaded files will use default DNS/routes; original device files are not changed.')
    public_plan = dict(mode=mode, sources=sources, server_file=selected if mode=='server' else '',
                       profile={k: profile[k] for k in ('name','protocol','version','address','port','endpoint','public_key')},
                       new_profile=new, clients=[{k: c[k] for k in ('name','address','action')} | {'downloadable':bool(c['private_key']), 'original_config':bool(c['config'])} for c in entries],
                       errors=sorted(set(errors)), warnings=list(dict.fromkeys(warnings)), can_apply=not errors,
                       counts={action:sum(c['action']==action for c in entries) for action in ('create','complete','skip')})
    return public_plan, profile, entries


def apply_plan(con, plan, profile, entries):
    if not plan['can_apply']: raise core.Problem('Resolve import conflicts before applying', 409)
    # Durable consistent snapshot before any SQL or VPN mutation.
    folder = state.DATA / 'import-backups'; folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    import secrets
    backup = folder / (time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4)+'.db')
    import os
    fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
    target = sqlite3.connect(backup)
    try:
        with state.connection() as source: source.backup(target)
    finally: target.close()
    previous = state.all_peers(con, profile['id']) if not plan['new_profile'] else []
    try:
        if plan['new_profile']:
            columns = ['name','protocol','version','interface','address','port','endpoint','private_key','public_key','params','mtu']
            cur = con.execute('INSERT INTO profiles('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')', tuple(profile[k] for k in columns))
            profile['id'] = cur.lastrowid
        for c in entries:
            if c['action'] == 'skip': continue
            if c['action'] == 'complete':
                con.execute("UPDATE clients SET private_key=CASE WHEN private_key='' THEN ? ELSE private_key END,config=CASE WHEN config='' THEN ? ELSE config END WHERE id=?", (c['private_key'], c['config'], c['id']))
                if c.get('client_protocol'):
                    con.execute('UPDATE clients SET protocol=?,version=? WHERE id=?',(c['client_protocol'],c['client_version'],c['id']))
            else:
                names = ['name','description','address','public_key','private_key','preshared_key','endpoint','config']
                con.execute('INSERT INTO clients('+','.join(names)+',protocol,version,profile_id,created_at) VALUES('+','.join('?' for _ in range(len(names)+4))+')', tuple(c[k] for k in names)+(c.get('client_protocol',profile['protocol']),c.get('client_version',profile['version']),profile['id'],int(time.time())))
        numbers=[int(m[1]) for c in con.execute('SELECT name FROM clients') if (m:=re.fullmatch(r'User\s+(\d+)',c['name'],re.I))]
        state.put(con,'next_client_number',max(int(state.value(con,'next_client_number','1')),max(numbers,default=0)+1))
        if plan['new_profile'] or any(c['action']!='skip' for c in entries): state.sync(con, profile)
        state.audit(con, 'Import completed: '+str(len(entries))+' clients; keys preserved')
        con.commit()  # Commit failure must roll back the VPN as well.
    except Exception:
        con.rollback()
        if plan['new_profile']: cleanup_profile(profile)
        else:
            # Mark attempted additions as managed-but-disabled: Engine otherwise
            # deliberately preserves unknown peers discovered in the live device.
            tombstones=[dict(c,enabled=0,blocked_reason='') for c in entries if c['action']=='create']
            try: state.ENGINE.apply(profile, previous+tombstones)
            except core.Problem: raise core.Problem('Import failed and VPN rollback failed. Use the pre-import backup and check the service journal.',503)
        raise
    return {'ok':True, 'counts':plan['counts'], 'backup':backup.name, 'profile_id':profile['id']}
