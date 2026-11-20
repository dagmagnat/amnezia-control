"""Keep replies to managed AmneziaWG 3.1 IPv4 ports on the receiving address."""

import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys

import state


TABLE = 'ac_awg3_reply_source'
RUNTIME = Path('/run/amnezia-control-reply-source')


def command(*args, input=None):
    proc = subprocess.run(args, input=input, text=True, capture_output=True, timeout=8)
    if proc.returncode:
        raise RuntimeError(f'{args[0]} failed: {proc.stderr.strip()}')
    return proc.stdout


def inventory(routes, links):
    wan = set()
    for route in routes:
        if route.get('dev'):
            wan.add(route['dev'])
        wan.update(hop['dev'] for hop in route.get('nexthops', []) if hop.get('dev'))
    found = {}
    for link in links:
        name = link['ifname']
        if name not in wan:
            continue
        addresses = {ipaddress.IPv4Address(entry['local']) for entry in link.get('addr_info', [])
                     if entry.get('family') == 'inet' and entry.get('scope') == 'global'}
        if addresses:
            found[name] = sorted(addresses)
    return found


def make_rules(wans, ports):
    addresses = sorted({address for local in wans.values() for address in local})
    if len(addresses) < 2 or not ports:
        return ''
    port_list = '{ ' + ', '.join(map(str, sorted(set(ports)))) + ' }'
    interfaces = {address: '{ ' + ', '.join(json.dumps(name) for name, local in sorted(wans.items())
                                             if address in local) + ' }' for address in addresses}
    names = {addr: f'destination_{i}' for i, addr in enumerate(addresses)}
    local_pool = '{ ' + ', '.join(map(str, addresses)) + ' }'
    lines = [f'table ip {TABLE} {{']
    for name in names.values():
        lines += [f'    set {name} {{', '        type inet_service . ipv4_addr . inet_service',
                  '        flags dynamic,timeout', '        timeout 90s', '        size 4096', '    }']
    lines += ['    chain remember {', '        type filter hook prerouting priority -150; policy accept;']
    for addr, name in names.items():
        lines.append(f'        iifname {interfaces[addr]} udp dport {port_list} ip daddr {addr} '
                     f'update @{name} {{ udp dport . ip saddr . udp sport }}')
    lines += ['    }', '    chain reply {', '        type route hook output priority -300; policy accept;']
    peer = 'udp sport . ip daddr . udp dport'
    for addr, name in names.items():
        # If the same source port recently contacted two local addresses, the
        # wrong destination cannot safely be inferred. Leave its reply alone.
        unambiguous = ''.join(f' {peer} != @{other}' for other in names.values() if other != name)
        lines.append(f'        oifname {interfaces[addr]} udp sport {port_list} ip saddr {local_pool} '
                     f'ip saddr != {addr} {peer} @{name}{unambiguous} counter ip saddr set {addr}')
    return '\n'.join(lines + ['    }', '}', ''])


def refresh(remove=False):
    import fcntl

    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    stamp = RUNTIME / 'rules.sha256'
    with (RUNTIME / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tables = command('nft', 'list', 'tables').splitlines()
        existing = f'table ip {TABLE}' in {line.strip() for line in tables}
        rules = ''
        if not remove:
            routes = json.loads(command('ip', '-j', '-4', 'route', 'show', 'table', 'main', 'default'))
            links = json.loads(command('ip', '-j', '-4', 'address', 'show'))
            with state.connection() as con:
                ports = [r['port'] for r in con.execute(
                    "SELECT port,interface FROM profiles WHERE protocol='amneziawg' AND version='3.1'")
                         if re.fullmatch(r'acawg[0-9]+', r['interface']) and 1 <= r['port'] <= 65535]
            rules = make_rules(inventory(routes, links), ports)
        if not rules:
            if existing:
                command('nft', 'delete', 'table', 'ip', TABLE)
            stamp.unlink(missing_ok=True)
            return
        digest = hashlib.sha256(rules.encode()).hexdigest()
        if existing and stamp.is_file() and stamp.read_text() == digest:
            return
        # nft commits this file atomically. A failed refresh leaves the previous
        # table in place, including the temporary repair on upgraded servers.
        previous = f'delete table ip {TABLE}\n' if existing else ''
        command('nft', '--file', '-', input=previous + rules)
        stamp.write_text(digest)


if __name__ == '__main__':
    try:
        refresh(remove=sys.argv[1:] == ['--remove'])
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
