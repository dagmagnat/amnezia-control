"""Create or reuse a local VPN connection from a protocol choice."""
import ipaddress
import json
import shutil
import core
import state

CLIENT_VERSIONS = list(core.GENERATIONS)


def create_profile(con, data):
    protocol=data.get('protocol'); version=data.get('version')
    if protocol not in ('wireguard','amneziawg'): raise core.Problem('Unknown protocol')
    if protocol=='wireguard': version='wg'
    elif version not in core.GENERATIONS: raise core.Problem('Unknown AmneziaWG generation')
    b='awg' if protocol=='amneziawg' else 'wg'
    if not shutil.which(b): raise core.Problem(b+' is not installed',503)
    params=core.parameters(version,data.get('params')) if b=='awg' else {}
    destination=core.endpoint(data.get('endpoint',''))
    n=con.execute('SELECT COALESCE(MAX(id),0)+1 n FROM profiles').fetchone()['n']
    if n>254: raise core.Problem('Profile limit reached')
    if data.get('subnet'):
        try: network=ipaddress.ip_network(data['subnet'])
        except ValueError: raise core.Problem('Invalid subnet')
    else:
        occupied=[ipaddress.ip_interface(r['address']).network for r in con.execute('SELECT address FROM profiles')]
        network=next((ipaddress.ip_network(f'10.77.{i}.0/24') for i in range(1,255) if not any(ipaddress.ip_network(f'10.77.{i}.0/24').overlaps(net) for net in occupied)),None)
        if network is None: raise core.Problem('No free private subnet')
    if network.version!=4 or network.prefixlen!=24 or not network.is_private: raise core.Problem('Use a private IPv4 /24 subnet')
    for row in con.execute('SELECT address FROM profiles'):
        if network.overlaps(ipaddress.ip_interface(row['address']).network): raise core.Problem('Subnet overlaps another connection')
    iface=f'ac{b}{n}'; port=core.number(data.get('port'),1024,65535)
    if con.execute('SELECT 1 FROM profiles WHERE port=?',(port,)).fetchone(): raise core.Problem('UDP port already used')
    if core.config_path({'interface':iface,'protocol':protocol}).exists(): raise core.Problem('Interface config already exists')
    private,public=core.keys(b)
    name=str(data.get('name') or ('AmneziaWG '+version if b=='awg' else 'WireGuard')).strip()[:60]
    cur=con.execute('INSERT INTO profiles(name,protocol,version,interface,address,port,endpoint,private_key,public_key,params) VALUES(?,?,?,?,?,?,?,?,?,?)',
        (name,protocol,version,iface,str(next(network.hosts()))+'/24',port,destination,private,public,json.dumps(params)))
    profile=dict(con.execute('SELECT * FROM profiles WHERE id=?',(cur.lastrowid,)).fetchone())
    try: state.sync(con,profile)
    except core.Problem:
        cleanup_profile(profile)
        raise
    state.audit(con,'VPN profile created: '+name)
    return profile


def cleanup_profile(profile):
    for action in ('stop','disable'):
        try: core.command('systemctl',action,core.service(profile))
        except core.Problem: pass
    core.config_path(profile).unlink(missing_ok=True)


def usable(profile):
    if profile['protocol']=='wireguard': return True
    params=json.loads(profile['params'])
    if not all(k in params for k in core.BASE): return False
    if profile['version'] in ('2.0','3.0','3.1') and not all(k in params for k in ('S3','S4')): return False
    if profile['version'] in ('3.0','3.1') and not params.get('HeaderProtectionKey'): return False
    if profile['version']=='3.1' and params.get('RandomTrailers')!='on': return False
    return True


def ensure_profile(con, protocol, version):
    if protocol not in ('wireguard','amneziawg'): raise core.Problem('Choose WireGuard or AmneziaWG')
    version='wg' if protocol=='wireguard' else version
    if protocol=='amneziawg' and version not in CLIENT_VERSIONS: raise core.Problem('Choose a supported AmneziaWG generation')
    for row in con.execute('SELECT * FROM profiles WHERE protocol=? AND version=? ORDER BY id',(protocol,version)):
        if usable(dict(row)): return dict(row),False
    hostname=state.value(con,'vpn_host')
    if not hostname:
        existing=con.execute("SELECT endpoint FROM profiles WHERE endpoint != '' ORDER BY id LIMIT 1").fetchone()
        if existing:
            hostname=existing['endpoint'].rsplit(':',1)[0].strip('[]')
        else:
            hostname=state.value(con,'panel_ip')
    if not hostname: raise core.Problem('Set the VPN server IP/domain in Settings first')
    hostname=core.host(hostname)
    port=51820 if protocol=='wireguard' else {'3.1':51821,'2.0':51822,'1.5':51823,'1.0':51824,'3.0':51825}[version]
    busy=set()
    for line in core.command('ss','-H','-lun').splitlines():
        fields=line.split()
        if len(fields)>3 and fields[3].rsplit(':',1)[-1].isdigit(): busy.add(int(fields[3].rsplit(':',1)[-1]))
    while port in busy or con.execute('SELECT 1 FROM profiles WHERE port=?',(port,)).fetchone(): port+=1
    if port>65535: raise core.Problem('No free UDP port')
    destination=(f'[{hostname}]' if ':' in hostname else hostname)+':'+str(port)
    return create_profile(con,{'protocol':protocol,'version':version,'port':port,'endpoint':destination}),True
