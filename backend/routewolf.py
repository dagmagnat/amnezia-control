"""Manage the optional RouteWolf transport for a native WireGuard interface."""
import base64
import gzip
import hashlib
import hmac
import ipaddress
import json
import os
import platform
import re
import socket
import tempfile
import urllib.request
from pathlib import Path

import core

VERSION = 'routewolf'
NAME = 'WireGuard для RouteWolf'
ASSETS = Path(__file__).with_name('routewolf-assets.txt')
BINARY = Path('/usr/local/libexec/amnezia-control/routewolf-wg-transport')
CONFIG_DIR = Path('/etc/amnezia-control/routewolf')
MAX_DOWNLOAD = 3 * 1024 * 1024


def is_wrapped(profile):
    fields = dict(profile)
    return fields.get('protocol') == 'wireguard' and fields.get('version') == VERSION


def external_port(profile):
    return int(profile['endpoint'].rsplit(':', 1)[1])


def key_for_peer(psk):
    raw = base64.b64decode(core.key(psk), validate=True)
    return hmac.digest(raw, b'amnezia-control/routewolf/transport-key/v2', 'sha256').hex()


def service(profile):
    return 'ac-routewolf@' + profile['interface'] + '.service'


def bind_host(endpoint):
    hostname = endpoint.rsplit(':', 1)[0].strip('[]')
    try:
        resolved = {item[4][0] for item in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM)}
    except socket.gaierror as exc:
        raise core.Problem('The RouteWolf endpoint must resolve to a local IPv4 address') from exc
    local = {item['local'] for device in json.loads(core.command('ip', '-j', '-4', 'addr', 'show'))
             for item in device.get('addr_info', [])}
    matches = sorted(resolved & local)
    if len(matches) != 1 or ipaddress.ip_address(matches[0]).is_loopback:
        raise core.Problem('Use a RouteWolf endpoint with one IPv4 address assigned to this server')
    return matches[0]


def check_endpoint_change(profile, destination):
    if int(destination.rsplit(':', 1)[1]) != external_port(profile):
        raise core.Problem('Create a new RouteWolf profile to change its public UDP port', 409)
    path = CONFIG_DIR / (profile['interface'] + '.json')
    previously_bound = json.loads(path.read_text())['Listen'].rsplit(':', 1)[0] if path.is_file() else bind_host(profile['endpoint'])
    if bind_host(destination) != previously_bound:
        raise core.Problem('The new RouteWolf endpoint must resolve to the current listener IP', 409)


def native_arch():
    return {'x86_64': 'amd64', 'aarch64': 'arm64', 'armv7l': 'armv7'}.get(platform.machine())


def install_binary():
    if BINARY.is_file():
        return
    arch = native_arch()
    if not arch:
        raise core.Problem('RouteWolf transport is unavailable for this CPU', 503)
    prefix, *rows = ASSETS.read_text().splitlines()
    filename = 'routewolf-wg-transport-' + arch + '.gz'
    checks = {name: digest for digest, name in (line.split() for line in rows if line.strip())}
    if not re.fullmatch('[0-9a-f]{40}', prefix) or filename not in checks:
        raise core.Problem('Invalid embedded RouteWolf binary manifest', 503)
    url = 'https://raw.githubusercontent.com/dagmagnat/RouteWolf/' + prefix + '/' + filename
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            packed = response.read(MAX_DOWNLOAD + 1)
        if len(packed) > MAX_DOWNLOAD or not hmac.compare_digest(hashlib.sha256(packed).hexdigest(), checks[filename]):
            raise ValueError('RouteWolf archive checksum mismatch')
        data = gzip.decompress(packed)
        if not data.startswith(b'\x7fELF') or len(data) > 8 * 1024 * 1024:
            raise ValueError('Invalid RouteWolf executable')
        BINARY.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=BINARY.parent, delete=False) as file:
            pending = Path(file.name)
            try:
                file.write(data)
                file.close()
                pending.chmod(0o755)
                pending.replace(BINARY)
            finally:
                pending.unlink(missing_ok=True)
    except (OSError, ValueError) as exc:
        raise core.Problem('Could not install the RouteWolf transport binary', 503) from exc


def sync(profile, peers):
    install_binary()
    address = bind_host(profile['endpoint'])
    path = CONFIG_DIR / (profile['interface'] + '.json')
    previous = path.read_text() if path.is_file() else None
    config = {'Mode': 'server', 'Listen': f'{address}:{external_port(profile)}',
              'WireGuard': f"127.0.0.1:{profile['port']}",
              'Keys': sorted({key_for_peer(peer['preshared_key']) for peer in peers
                              if peer['enabled'] and not peer.get('blocked_reason') and peer['preshared_key']})}
    identity = ('Mode', 'Listen', 'WireGuard')
    restart = previous is not None and any(json.loads(previous).get(k) != config[k] for k in identity)
    updated = json.dumps(config, separators=(',', ':')) + '\n'
    if previous != updated:
        core.atomic_text(path, updated)
    unit = service(profile)
    try:
        # The server reads key changes in place, so another router does not lose its session.
        core.command('systemctl', 'enable', unit)
        core.command('systemctl', 'restart' if restart else 'start', unit)
        core.command('systemctl', 'is-active', unit)
    except core.Problem:
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            core.atomic_text(path, previous)
            if restart:
                try:
                    core.command('systemctl', 'restart', unit)
                except core.Problem:
                    pass
        raise


def cleanup(profile):
    for action in ('stop', 'disable'):
        try:
            core.command('systemctl', action, service(profile))
        except core.Problem:
            pass
    (CONFIG_DIR / (profile['interface'] + '.json')).unlink(missing_ok=True)
