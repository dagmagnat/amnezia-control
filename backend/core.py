"""Validated data and official WireGuard/AmneziaWG command integration."""
import base64
import configparser
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

GENERATIONS = ['1.0', '1.5', '2.0', '3.0', '3.1']
BASE = {'Jc': '4', 'Jmin': '40', 'Jmax': '120', 'S1': '64', 'S2': '64',
        'H1': '1000001', 'H2': '2000001', 'H3': '3000001', 'H4': '4000001'}
EXTRA = ['I1', 'I2', 'I3', 'I4', 'I5', 'S3', 'S4', 'HeaderProtectionKey',
         'ContentPaddingAddition', 'RekeyAfterTime', 'RekeyTimeout', 'RejectAfterTime',
         'KeepaliveTimeout', 'MaxHandshakeAttempts', 'RandomTrailers', 'DisableCookies']
PARAMS = list(BASE) + EXTRA

class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

def command(*args, input=None):
    try:
        p = subprocess.run(list(map(str, args)), input=input, text=True, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Problem('VPN command unavailable: ' + str(args[0]), 503) from e
    if p.returncode:
        # Output can contain keys or configs. Never return it to HTTP clients.
        raise Problem('Command failed: ' + ' '.join(map(str, args[:2])) + '. Check service journal.', 503)
    return p.stdout.strip()

def key(value, optional=False):
    if optional and not value:
        return ''
    try:
        if len(base64.b64decode(value, validate=True)) != 32:
            raise ValueError()
    except (ValueError, TypeError):
        raise Problem('Invalid 32-byte key')
    return value

def keys(binary):
    private = key(command(binary, 'genkey'))
    return private, key(command(binary, 'pubkey', input=private + '\n'))

def host(value):
    value = str(value).strip()
    try:
        return str(ipaddress.ip_address(value.strip('[]')))
    except ValueError:
        pass
    try:
        value = value.encode('idna').decode('ascii').lower()
    except UnicodeError:
        raise Problem('Invalid IP or domain')
    if len(value) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', p) for p in value.rstrip('.').split('.')):
        raise Problem('Invalid IP or domain')
    return value.rstrip('.')

def endpoint(value):
    value = str(value).strip()
    if value.startswith('['):
        match = re.fullmatch(r'\[([^]]+)\]:(\d+)', value)
        if not match:
            raise Problem('Use [IPv6]:port')
        hostname, port = match.groups()
    else:
        try:
            hostname, port = value.rsplit(':', 1)
        except ValueError:
            raise Problem('Use IP:port or domain:port')
    hostname = host(hostname)
    port = number(port, 1, 65535)
    return f'[{hostname}]:{port}' if ':' in hostname else f'{hostname}:{port}'

def number(value, low, high):
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise Problem('Invalid number')
    if result < low or result > high:
        raise Problem(f'Number must be between {low} and {high}')
    return result

def parameters(version, supplied=None):
    result = dict(BASE)
    if version in ('2.0', '3.0', '3.1'):
        result.update(S3='16', S4='16')
    if version in ('3.0', '3.1'):
        result.update(S1='16', S2='16', H1='1', H2='2', H3='3', H4='4',
                      HeaderProtectionKey=base64.b64encode(secrets.token_bytes(32)).decode(),
                      ContentPaddingAddition='0-32')
    if version == '3.1':
        result.update(RandomTrailers='on')
    if supplied is not None:
        if not isinstance(supplied, dict) or set(supplied) - set(PARAMS):
            raise Problem('Unknown AmneziaWG parameter')
        result.update({k: str(v) for k, v in supplied.items() if str(v) != ''})
    allowed = set(BASE)
    if version != '1.0': allowed.update('I' + str(i) for i in range(1, 6))
    if version in ('2.0', '3.0', '3.1'): allowed.update(['S3', 'S4'])
    if version in ('3.0', '3.1'): allowed.update(EXTRA)
    if set(result) - allowed:
        raise Problem('Parameter is incompatible with selected generation')
    for name, value in result.items():
        if '\n' in value or '\r' in value or len(value) > 4096:
            raise Problem('Invalid parameter value')
        if name.startswith('I'):
            if not re.fullmatch(r'(?:<(?:b 0x[0-9a-fA-F]+|r [0-9]+|rc [0-9]+|rd [0-9]+|t|c)>)+', value):
                raise Problem('Invalid CPS signature')
        elif name == 'HeaderProtectionKey': key(value)
        elif name in ('RandomTrailers', 'DisableCookies'):
            if value not in ('on', 'off'): raise Problem('Use on/off')
        else:
            values = value.split('-')
            ranged = name.startswith('H') and version in ('2.0','3.0','3.1') or name in ('ContentPaddingAddition','RekeyAfterTime','RekeyTimeout','RejectAfterTime','KeepaliveTimeout','MaxHandshakeAttempts')
            if len(values)>1 and not ranged: raise Problem(name+' requires a single integer')
            if len(values) > 2: raise Problem('Invalid range')
            nums = [number(x, 0, 4294967295 if name.startswith('H') else 65535) for x in values]
            if len(nums) == 2 and nums[0] > nums[1]: raise Problem('Range minimum exceeds maximum')
    if int(result['Jmin']) > int(result['Jmax']): raise Problem('Jmin exceeds Jmax')
    if int(result['S1'])+148 == int(result['S2'])+92: raise Problem('Handshake packet lengths must differ')
    if 'HeaderProtectionKey' in result and any(int(result.get('S'+str(i), 0)) < 12 for i in range(1, 5)):
        raise Problem('Header protection requires S1–S4 >= 12')
    ranges = [(int(result['H'+str(i)].split('-')[0]), int(result['H'+str(i)].split('-')[-1])) for i in range(1,5)]
    for i, a in enumerate(ranges):
        if any(max(a[0], b[0]) <= min(a[1], b[1]) for b in ranges[i+1:]): raise Problem('H1–H4 ranges overlap')
    return result

def parse_config(text):
    if len(text) > 65536: raise Problem('Config too large')
    parser = configparser.ConfigParser(interpolation=None, strict=True, inline_comment_prefixes=('#',))
    parser.optionxform = str
    try: parser.read_string(text.lstrip('\ufeff'))
    except configparser.Error: raise Problem('Invalid configuration')
    if set(parser.sections()) != {'Interface', 'Peer'}: raise Problem('Expected one Interface and one Peer')
    interface, peer = dict(parser['Interface']), dict(parser['Peer'])
    if any('\n' in v or '\r' in v for v in list(interface.values())+list(peer.values())):
        raise Problem('Multiline config values are not allowed')
    if set(interface) - ({'PrivateKey','Address','DNS','MTU'} | set(PARAMS)) or set(peer) - {'PublicKey','PresharedKey','Endpoint','AllowedIPs','PersistentKeepalive'}:
        raise Problem('Config contains unsupported fields or executable hooks')
    key(interface.get('PrivateKey')); key(peer.get('PublicKey')); key(peer.get('PresharedKey'), True)
    try:
        ipaddress.ip_interface(interface.get('Address',''))
        for route in peer.get('AllowedIPs','0.0.0.0/0').split(','): ipaddress.ip_network(route.strip(),strict=False)
    except ValueError: raise Problem('Invalid IP address or route')
    if 'Endpoint' in peer: endpoint(peer['Endpoint'])
    if 'PersistentKeepalive' in peer: number(peer['PersistentKeepalive'],0,65535)
    if 'MTU' in interface: number(interface['MTU'],576,9000)
    if 'DNS' in interface:
        for entry in interface['DNS'].split(','): host(entry.strip())
    return interface, peer

def config_path(profile):
    root = Path(os.environ.get('AC_CONFIG_ROOT', '/etc'))
    return root / ('amnezia/amneziawg' if profile['protocol'] == 'amneziawg' else 'wireguard') / (profile['interface'] + '.conf')

def binary(profile):
    return 'awg' if profile['protocol'] == 'amneziawg' else 'wg'

def service(profile):
    if profile['protocol']=='amneziawg' and profile['interface'].startswith('acawg'):
        return 'ac-awg@'+profile['interface']
    return ('awg-quick' if profile['protocol']=='amneziawg' else 'wg-quick')+'@'+profile['interface']

def atomic_text(path, text):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f: f.write(text)
    os.chmod(temporary, 0o600); os.replace(temporary, path)

def interface_text(profile, peers, quick=True):
    lines = ['[Interface]', 'PrivateKey = '+profile['private_key'], 'ListenPort = '+str(profile['port'])]
    if quick:
        lines += ['Address = '+profile['address'], 'MTU = 1380', 'SaveConfig = false']
        for rule in firewall_rules(profile):
            args = ' '.join(rule)
            table = '-t nat ' if rule[0]=='POSTROUTING' else ''
            lines += ['PostUp = iptables '+table+'-C '+args+' 2>/dev/null || iptables '+table+'-I '+args,
                      'PostDown = iptables '+table+'-D '+args+' 2>/dev/null || true']
    lines += [k+' = '+v for k,v in json.loads(profile['params']).items()]
    for c in peers:
        if c['enabled'] and not c.get('blocked_reason'):
            lines += ['', '[Peer]', 'PublicKey = '+c['public_key'], 'AllowedIPs = '+c['address']]
            if c['preshared_key']: lines.append('PresharedKey = '+c['preshared_key'])
    return '\n'.join(lines)+'\n'

def firewall_rules(profile):
    iface = profile['interface']; subnet = str(ipaddress.ip_interface(profile['address']).network)
    # Dedicated, labelled rules. Never flush or replace existing firewall tables.
    return [ ['INPUT','-p','udp','--dport',str(profile['port']),'-m','comment','--comment','ac-'+iface,'-j','ACCEPT'],
             ['FORWARD','-i',iface,'-m','comment','--comment','ac-'+iface,'-j','ACCEPT'],
             ['FORWARD','-o',iface,'-m','conntrack','--ctstate','RELATED,ESTABLISHED','-m','comment','--comment','ac-'+iface,'-j','ACCEPT'],
             ['POSTROUTING','-s',subnet,'-m','comment','--comment','ac-'+iface,'-j','MASQUERADE'] ]

class Engine:
    def apply(self, profile, peers):
        b = binary(profile); iface = profile['interface']; path = config_path(profile)
        command('systemctl', 'enable', service(profile))
        previous = path.read_text(encoding='utf-8') if path.exists() else None
        managed = {c['public_key'] for c in peers}
        unmanaged = []
        # Keep peers created outside this panel, including during migration.
        try:
            live = command(b, 'showconf', iface)
        except Problem:
            live = previous or ''
        for chunk in live.split('[Peer]')[1:]:
            match = re.search(r'^PublicKey\s*=\s*(\S+)', chunk, re.M)
            if match and match[1] not in managed:
                unmanaged.append('[Peer]'+chunk)
        suffix = '\n'+'\n'.join(unmanaged) if unmanaged else ''
        atomic_text(path, interface_text(profile, peers)+suffix)
        try:
            command(b, 'show', iface, 'public-key')
        except Problem:
            try: command('systemctl', 'start', service(profile))
            except Problem:
                if previous is not None: atomic_text(path, previous)
                raise
        runtime = path.with_suffix('.runtime')
        try:
            atomic_text(runtime, interface_text(profile, peers, quick=False)+suffix)
            command(b, 'syncconf', iface, str(runtime))
        except Problem:
            if previous is not None: atomic_text(path, previous)
            # syncconf may apply partially; restore original runtime if possible.
            if previous:
                try:
                    text = command('awg-quick' if b == 'awg' else 'wg-quick', 'strip', str(path))
                    atomic_text(runtime, text+'\n'); command(b, 'syncconf', iface, str(runtime))
                except Problem: pass
            raise
        finally:
            runtime.unlink(missing_ok=True)

    def stats(self, profile):
        try:
            b = binary(profile); iface = profile['interface']
            transfers = command(b, 'show', iface, 'transfer')
            handshakes = command(b, 'show', iface, 'latest-handshakes')
            result = {}
            for line in transfers.splitlines():
                k, rx, tx = line.split(); result[k] = {'rx':int(rx),'tx':int(tx),'handshake':0}
            for line in handshakes.splitlines():
                k, timestamp = line.split(); result.setdefault(k, {'rx':0,'tx':0})['handshake'] = int(timestamp)
            return result, ''
        except (Problem, ValueError): return {}, 'Interface unavailable'
