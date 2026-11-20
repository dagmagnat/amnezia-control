"""Optional official WARP client isolated from host routing in a network namespace.

Only forwarded IPv4 packets arriving on explicitly managed VPN interfaces are
routed here. Host OUTPUT, SSH replies, DNS and VPN endpoints keep their routes.
"""
import ipaddress
import json
import os
import re
import secrets
import shutil
import shlex
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import state
from core import Problem, atomic_text

ROOT=Path(__file__).resolve().parents[1]
DATA=state.DATA/'warp'
NS='ac-warp'; HOST='acw-host'; PEER='acw-ns'
HOST_IP='169.254.172.1'; PEER_IP='169.254.172.2'; TABLE='51888'
PREF='10888'; TAG='ac-warp'; CHAIN='AC_WARP'
DEFAULT={'enabled':False,'scope':'selected','profile_ids':[],'protocol':'MASQUE','dns':[]}
TASK_LOCK=threading.Lock()


def run(*args,timeout=20,check=True):
    try: p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired): raise Problem('WARP command unavailable or timed out',503)
    if check and p.returncode: raise Problem('WARP operation failed. Check journalctl -u ac-warp-task -u ac-warp-client.',503)
    return p


def read(name,default):
    try: return json.loads((DATA/name).read_text(encoding='utf-8'))
    except FileNotFoundError: return default


def save(name,data):
    DATA.mkdir(mode=0o700,parents=True,exist_ok=True)
    atomic_text(DATA/name,json.dumps(data,ensure_ascii=True))


def config(): return DEFAULT|read('config.json',{})


@contextmanager
def lock(blocking=True):
    import fcntl
    DATA.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (DATA/'runtime.lock').open('a') as f:
        os.chmod(f.name,0o600)
        try: fcntl.flock(f,fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError: raise Problem('A WARP operation is already running',409)
        try: yield
        finally: fcntl.flock(f,fcntl.LOCK_UN)


def profiles(cfg, inventory=None):
    if inventory is None:
        with state.connection() as con:
            inventory=list(con.execute('SELECT id,name,interface,address FROM profiles ORDER BY id'))
    rows=[dict(row) for row in inventory]
    if cfg['scope']=='selected': rows=[r for r in rows if r['id'] in cfg['profile_ids']]
    for row in rows:
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,15}',row['interface']): raise Problem('Invalid VPN interface')
        if ipaddress.ip_interface(row['address']).version!=4: raise Problem('WARP currently supports IPv4 VPN profiles only')
    return rows


def validate(data, inventory=None):
    if not isinstance(data,dict) or set(data)-set(DEFAULT): raise Problem('Invalid WARP settings')
    cfg=DEFAULT|data
    if type(cfg['enabled']) is not bool: raise Problem('enabled must be boolean')
    if cfg['scope'] not in ('all','selected'): raise Problem('Choose all or selected VPN profiles')
    if cfg['protocol'] not in ('MASQUE','WireGuard'): raise Problem('Choose MASQUE or WireGuard')
    ids=cfg['profile_ids']
    if not isinstance(ids,list) or len(ids)>254 or any(type(i) is not int or i<1 for i in ids) or len(set(ids))!=len(ids): raise Problem('Invalid VPN profile selection')
    if inventory is None:
        with state.connection() as con:
            inventory=list(con.execute('SELECT id,name,interface,address FROM profiles ORDER BY id'))
    known={row['id'] for row in inventory}
    if set(ids)-known: raise Problem('VPN profile list changed. Refresh it.',409)
    if cfg['enabled'] and cfg['scope']=='selected' and not ids: raise Problem('Select at least one VPN profile')
    if not isinstance(cfg['dns'],list) or len(cfg['dns'])>2: raise Problem('Choose up to two namespace DNS servers')
    for address in cfg['dns']:
        try: parsed=ipaddress.ip_address(address)
        except (ValueError,TypeError): raise Problem('Invalid DNS address')
        if parsed.version!=4 or parsed.is_loopback or parsed.is_unspecified or parsed.is_multicast: raise Problem('Use reachable IPv4 DNS servers')
    profiles(cfg, inventory)
    return cfg


def cli(*args,check=True):
    return run('ip','netns','exec',NS,str(DATA/'bin/warp-cli'),'--accept-tos',*args,timeout=35,check=check)


def status():
    cfg=config();job=read('task.json',{});runtime=read('status.json',{})
    if os.name=='posix' and job.get('state') in ('queued','running') and time.time()-job.get('started_at',time.time())>15:
        try:
            active=run('systemctl','is-active','ac-warp-task',timeout=3,check=False).stdout.strip()
            if active not in ('active','activating','deactivating'):
                job=job|{'state':'failed','error':'WARP task was interrupted. Retry the operation.'}
                save('task.json',job)
        except Problem: pass
    return {'config':cfg,'installed':(DATA/'bin/warp-svc').is_file(),'registered':bool(read('registration.json',{}).get('registered')),
            'restore_pending': read('restore-pending.json', {}).get('enable') is True,
            'version':read('package.json',{}).get('version',''),'runtime':runtime,'task':job,
            'terms_url':'https://www.cloudflare.com/application/terms/','docs_url':'https://developers.cloudflare.com/warp-client/get-started/linux/'}


def queue(action,payload=None):
    if action not in ('install','register','save','check'): raise Problem('Unknown WARP action')
    if os.name!='posix': raise Problem('WARP integration requires Linux',503)
    with TASK_LOCK,lock(blocking=False):
        active=run('systemctl','is-active','ac-warp-task',check=False).stdout.strip()
        if active in ('active','activating','deactivating'): raise Problem('A WARP operation is already running',409)
        if action=='save': payload=validate(payload)
        if action in ('register','save') and not (DATA/'bin/warp-cli').is_file(): raise Problem('Install WARP first',409)
        if action=='register' and (not isinstance(payload,dict) or payload.get('accept_terms') is not True): raise Problem('Accept Cloudflare terms before registering')
        job={'id':secrets.token_hex(8),'action':action,'state':'queued','started_at':int(time.time()),'error':''}
        save('request.json',{'action':action,'payload':payload});save('task.json',job)
        try:
            run('systemctl','reset-failed','ac-warp-task',check=False)
            run('systemd-run','--unit=ac-warp-task','--collect','--no-block','--property=UMask=0077','--property=PrivateTmp=yes',
                str(ROOT/'.venv/bin/python'),str(ROOT/'backend/warp.py'),'task')
        except Exception:
            save('task.json',job|{'state':'failed','error':'Unable to start WARP task'});raise
    return {'ok':True,'task_id':job['id']}


def ipt(*args,namespace=False,check=True):
    prefix=('ip','netns','exec',NS) if namespace else ()
    return run(*prefix,'iptables','-w','5',*args,check=check)


def rule(args,namespace=False):
    # Append only our labelled rules; never flush a shared chain.
    pos=next(i for i,v in enumerate(args) if v in ('-A','-I'))
    test=list(args);test[pos]='-C'
    if ipt(*test,namespace=namespace,check=False).returncode: ipt(*args,namespace=namespace)


def nsip(*args,check=True): return run('ip','-n',NS,*args,check=check)


def dns_servers(cfg):
    if cfg['dns']: return cfg['dns']
    for path in (Path('/run/systemd/resolve/resolv.conf'),Path('/etc/resolv.conf')):
        if not path.exists(): continue
        result=[]
        for line in path.read_text().splitlines():
            if not line.startswith('nameserver '): continue
            try: address=ipaddress.ip_address(line.split()[1])
            except (ValueError,IndexError): continue
            if address.version==4 and not address.is_loopback and not address.is_unspecified: result.append(str(address))
        if result: return result[:2]
    raise Problem('No reachable upstream DNS found. Set namespace DNS servers in WARP settings.',409)


def claim_resources():
    if read('ownership.json',{}).get('version')==1: return
    rules=json.loads(run('ip','-j','rule','show').stdout)
    if any(r.get('priority')==int(PREF) or str(r.get('table'))==TABLE for r in rules):
        raise Problem('Reserved WARP policy table or priority is already in use',409)
    routes=run('ip','-j','route','show','table',TABLE,check=False)
    if routes.returncode==0 and json.loads(routes.stdout):
        raise Problem('Reserved WARP routing table is already in use',409)
    namespaces=run('ip','netns','list').stdout
    if NS in [line.split()[0] for line in namespaces.splitlines() if line.strip()] or run('ip','link','show',HOST,check=False).returncode==0:
        raise Problem('Reserved WARP network already exists outside this installation',409)
    assigned=json.loads(run('ip','-j','address','show').stdout)
    reserved=ipaddress.ip_network(HOST_IP+'/30',strict=False)
    for iface in assigned:
        for address in iface.get('addr_info',[]):
            if address.get('family')=='inet' and ipaddress.ip_address(address['local']) in reserved:
                raise Problem('Reserved WARP subnet is already assigned',409)
    save('ownership.json',{'version':1})


def write_dns(cfg):
    folder=Path('/etc/netns')/NS;folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    atomic_text(folder/'resolv.conf',''.join('nameserver '+v+'\n' for v in dns_servers(cfg)))


def network():
    cfg=config();claim_resources()
    existing=run('ip','netns','list').stdout
    if NS not in [line.split()[0] for line in existing.splitlines() if line.strip()]:
        if run('ip','link','show',HOST,check=False).returncode==0: raise Problem('Reserved WARP interface already exists',409)
        run('ip','netns','add',NS)
    if run('ip','link','show',HOST,check=False).returncode!=0:
        run('ip','link','add',HOST,'type','veth','peer','name',PEER)
        run('ip','link','set',PEER,'netns',NS)
    run('ip','address','replace',HOST_IP+'/30','dev',HOST);run('ip','link','set',HOST,'up')
    nsip('address','replace',PEER_IP+'/30','dev',PEER);nsip('link','set',PEER,'up');nsip('link','set','lo','up')
    nsip('route','replace','default','via',HOST_IP,'dev',PEER,'metric','32760')
    run('ip','netns','exec',NS,'sysctl','-q','-w','net.ipv4.ip_forward=1','net.ipv4.conf.all.rp_filter=0',f'net.ipv4.conf.{PEER}.rp_filter=0')
    run('sysctl','-q','-w',f'net.ipv4.conf.{HOST}.rp_filter=2')
    # Native client is untrusted with host routes; all route/DNS changes stay here.
    write_dns(cfg)
    rule(['-t','nat','-I','POSTROUTING','-s',PEER_IP+'/32','!','-o',HOST,'-m','comment','--comment',TAG+'-transport','-j','MASQUERADE'])
    rule(['-I','FORWARD','-i',HOST,'-s',PEER_IP+'/32','-m','comment','--comment',TAG+'-transport','-j','ACCEPT'])
    rule(['-I','FORWARD','-o',HOST,'-d',PEER_IP+'/32','-m','conntrack','--ctstate','RELATED,ESTABLISHED','-m','comment','--comment',TAG+'-transport','-j','ACCEPT'])
    # No fallback through the namespace WAN when WARP disconnects.
    ipt('-N',CHAIN,namespace=True,check=False)
    if ipt('-C','FORWARD','-i',PEER,'-j',CHAIN,namespace=True,check=False).returncode: ipt('-I','FORWARD','1','-i',PEER,'-j',CHAIN,namespace=True)
    rule(['-A',CHAIN,'!','-o','CloudflareWARP','-j','REJECT'],namespace=True)
    rule(['-A',CHAIN,'-j','ACCEPT'],namespace=True)
    rule(['-t','nat','-A','POSTROUTING','-o','CloudflareWARP','-m','comment','--comment',TAG,'-j','MASQUERADE'],namespace=True)
    rule(['-A','FORWARD','-o',PEER,'-m','conntrack','--ctstate','RELATED,ESTABLISHED','-j','ACCEPT'],namespace=True)


def block_ipv6(iface,enabled=True):
    args=['FORWARD','-i',iface,'-m','comment','--comment',TAG+'-ipv6','-j','REJECT']
    exists=run('ip6tables','-w','5','-C',*args,check=False).returncode==0
    if enabled and not exists: run('ip6tables','-w','5','-I',*args)
    elif not enabled and exists: run('ip6tables','-w','5','-D',*args)


def guard_profile(profile):
    cfg=config()
    if not cfg['enabled'] or (cfg['scope']=='selected' and profile['id'] not in cfg['profile_ids']): return
    claim_resources()
    iface=profile['interface']
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,15}',iface): raise Problem('Invalid VPN interface')
    block_ipv6(iface)
    run('ip','route','replace','unreachable','default','metric','32760','table',TABLE)
    rules=json.loads(run('ip','-j','rule','show').stdout)
    if not any(r.get('priority')==int(PREF) and r.get('iif')==iface and str(r.get('table'))==TABLE for r in rules):
        run('ip','rule','add','priority',PREF,'iif',iface,'lookup',TABLE)


def guard(cfg):
    if not cfg['enabled']: return
    claim_resources()
    run('ip','route','replace','unreachable','default','metric','32760','table',TABLE)
    rules=json.loads(run('ip','-j','rule','show').stdout)
    for row in profiles(cfg):
        block_ipv6(row['interface'])
        if not any(r.get('priority')==int(PREF) and r.get('iif')==row['interface'] and str(r.get('table'))==TABLE for r in rules):
            run('ip','rule','add','priority',PREF,'iif',row['interface'],'lookup',TABLE)


def routing(cfg):
    """Reconcile policy before allowing selected clients onto a new route."""
    desired=profiles(cfg) if cfg['enabled'] else []
    old=read('routes.json',{'profiles':[]})['profiles']
    if desired:
        run('ip','route','replace','unreachable','default','metric','32760','table',TABLE)
        run('ip','route','replace','default','via',PEER_IP,'dev',HOST,'metric','10','table',TABLE)
        # Existing VPN MASQUERADE rules must not hide source subnets from namespace.
        if ipt('-t','nat','-C','POSTROUTING','-o',HOST,'-m','comment','--comment',TAG+'-source','-j','ACCEPT',check=False).returncode:
            ipt('-t','nat','-I','POSTROUTING','1','-o',HOST,'-m','comment','--comment',TAG+'-source','-j','ACCEPT')
    current=run('ip','-j','rule','show').stdout
    rules=json.loads(current)
    for row in desired:
        block_ipv6(row['interface'])
        subnet=str(ipaddress.ip_interface(row['address']).network)
        # The official daemon places its policy rule before other user rules.
        # A scoped unicast return route in this private namespace's local table
        # remains ahead of that rule without touching daemon-owned priorities.
        nsip('route','replace',subnet,'via',HOST_IP,'dev',PEER,'table','local')
        # Force only forwarded packets from this interface, never local OUTPUT.
        if not any(r.get('priority')==int(PREF) and r.get('iif')==row['interface'] and str(r.get('table'))==TABLE for r in rules):
            run('ip','rule','add','priority',PREF,'iif',row['interface'],'lookup',TABLE)
        for direction in ('-i','-o'):
            match=[direction,row['interface'], '-o' if direction=='-i' else '-i',HOST]
            if ipt('-C','FORWARD',*match,'-m','comment','--comment',TAG,'-j','ACCEPT',check=False).returncode:
                ipt('-I','FORWARD','1',*match,'-m','comment','--comment',TAG,'-j','ACCEPT')
    wanted={r['interface'] for r in desired}
    old += [{'interface':r['iif']} for r in rules if r.get('priority')==int(PREF) and str(r.get('table'))==TABLE and r.get('iif') and r['iif'] not in {p['interface'] for p in old}]
    for row in old:
        if row['interface'] in wanted: continue
        block_ipv6(row['interface'],False)
        for _ in range(max(1,sum(r.get('priority')==int(PREF) and r.get('iif')==row['interface'] and str(r.get('table'))==TABLE for r in rules))):
            run('ip','rule','del','priority',PREF,'iif',row['interface'],'lookup',TABLE,check=False)
        if row.get('address'):
            subnet=str(ipaddress.ip_interface(row['address']).network)
            nsip('route','del',subnet,'via',HOST_IP,'dev',PEER,'table','local',check=False)
        for direction in ('-i','-o'):
            match=[direction,row['interface'],'-o' if direction=='-i' else '-i',HOST]
            ipt('-D','FORWARD',*match,'-m','comment','--comment',TAG,'-j','ACCEPT',check=False)
    if not desired:
        ipt('-t','nat','-D','POSTROUTING','-o',HOST,'-m','comment','--comment',TAG+'-source','-j','ACCEPT',check=False)
    save('routes.json',{'profiles':desired})


def cleanup():
    """Remove only resources reserved and labelled by this integration."""
    with lock():
        run('systemctl','disable','--now','ac-warp-watch.timer',check=False)
        cfg=config()|{'enabled':False};save('config.json',cfg);routing(cfg)
        run('systemctl','stop','ac-warp-client','ac-warp-network',timeout=45,check=False)
        if not read('ownership.json',{}).get('version'): return
        for table,chain in [('filter','FORWARD'),('nat','POSTROUTING')]:
            listing=ipt('-t',table,'-S',chain,check=False)
            for line in listing.stdout.splitlines():
                args=shlex.split(line)
                if '--comment' in args and args[args.index('--comment')+1] in (TAG,TAG+'-transport',TAG+'-source'):
                    args[0]='-D';ipt('-t',table,*args,check=False)
        run('ip','route','del','default','via',PEER_IP,'dev',HOST,'metric','10','table',TABLE,check=False)
        run('ip','route','del','unreachable','default','metric','32760','table',TABLE,check=False)
        run('ip','link','del',HOST,check=False)
        run('ip','netns','del',NS,check=False)
        (Path('/etc/netns')/NS/'resolv.conf').unlink(missing_ok=True)
        try: (Path('/etc/netns')/NS).rmdir()
        except OSError: pass
        (DATA/'ownership.json').unlink(missing_ok=True)


def check_connection():
    client=cli('status',check=False)
    if client.returncode or not re.search(r'\bConnected\b',client.stdout): return False
    trace=run('ip','netns','exec',NS,'curl','-4','-fsS','--interface','CloudflareWARP','--connect-timeout','5','--max-time','12','https://www.cloudflare.com/cdn-cgi/trace',timeout=16,check=False)
    return trace.returncode==0 and bool(re.search(r'^warp=(on|plus)$',trace.stdout,re.M))


def reconcile():
    if not config()['enabled']: return
    with lock():
        cfg=config()
        if not cfg['enabled']: return
        guard(cfg)
        run('systemctl','start','ac-warp-network','ac-warp-client',timeout=40)
        routing(cfg)
        if not re.search(r'\bConnected\b',cli('status',check=False).stdout): cli('connect',check=False)
        healthy=check_connection()
        save('status.json',{'connected':healthy,'checked_at':int(time.time()),'profiles':len(profiles(cfg)),
                            'message':'connected' if healthy else 'blocked_no_warp'})


def task():
    with lock(): task_locked()


def task_locked():
    request=read('request.json',{});job=read('task.json',{})
    save('task.json',job|{'state':'running'})
    try:
        action=request['action']
        if action=='install':
            if config()['enabled']: raise Problem('Disable WARP before reinstalling it',409)
            result=run('bash',str(ROOT/'scripts/install-warp.sh'),timeout=900,check=False)
            atomic_text(DATA/'install.log',result.stdout+'\n'+result.stderr)
            if result.returncode: raise Problem('WARP installation failed. Check /var/lib/amnezia-control/warp/install.log',503)
        elif action=='register':
            if config()['enabled']: raise Problem('Disable WARP before registering it',409)
            run('systemctl','start','ac-warp-network','ac-warp-client',timeout=45)
            for _ in range(20):
                if cli('status',check=False).returncode==0: break
                time.sleep(1)
            # Called only after explicit acceptance in the panel; no license keys in logs.
            if not read('registration.json',{}).get('registered'): cli('registration','new')
            cli('mode','tunnel_only');cli('disconnect',check=False)
            save('registration.json',{'registered':True,'accepted_at':int(time.time())})
        elif action=='save':
            cfg=validate(request['payload']);old=config()
            if cfg['enabled'] and not read('registration.json',{}).get('registered'): raise Problem('Register WARP first',409)
            # Keep network alive while switching; block selected traffic during outages.
            if cfg['enabled']:
                claim_resources()
                save('config.json',cfg)
                guard(cfg)
                run('systemctl','start','ac-warp-network','ac-warp-client',timeout=45)
                write_dns(cfg)
                if cfg['dns']!=old['dns']: run('systemctl','restart','ac-warp-client',timeout=45)
                routing(cfg)
                run('systemctl','enable','--now','ac-warp-watch.timer')
                cli('mode','tunnel_only');cli('tunnel','protocol','set',cfg['protocol']);cli('connect')
                healthy=False
                for _ in range(12):
                    if check_connection(): healthy=True;break
                    time.sleep(2)
                save('status.json',{'connected':healthy,'checked_at':int(time.time()),'profiles':len(profiles(cfg)),
                                    'message':'connected' if healthy else 'blocked_no_warp'})
                if not healthy: raise Problem('WARP did not connect. Selected traffic is blocked; disable WARP to restore direct access.',503)
            else:
                # Removal of iif rules explicitly restores the original Internet route.
                run('systemctl','disable','--now','ac-warp-watch.timer',check=False)
                save('config.json',cfg);routing(cfg)
                cli('disconnect',check=False)
                save('status.json',{'connected':False,'checked_at':int(time.time()),'profiles':0,'message':'disabled'})
            (DATA / 'restore-pending.json').unlink(missing_ok=True)
        elif action=='check':
            cfg=config()
            if cfg['enabled']:
                guard(cfg);routing(cfg)
                healthy=check_connection()
                save('status.json',{'connected':healthy,'checked_at':int(time.time()),'profiles':len(profiles(cfg)),'message':'connected' if healthy else 'blocked_no_warp'})
        save('task.json',job|{'state':'done','finished_at':int(time.time()),'error':''})
    except Exception as exc:
        # Error messages are controlled: never return raw registration/command output.
        message=str(exc) if isinstance(exc,Problem) else 'WARP task failed. Check ac-warp-task journal.'
        save('task.json',job|{'state':'failed','finished_at':int(time.time()),'error':message})
        raise


if __name__=='__main__':
    if os.geteuid()!=0: raise SystemExit('Root required')
    try:
        action=sys.argv[1]
        if action=='task': task()
        elif action=='network': network()
        elif action=='reconcile': reconcile()
        elif action=='guard':
            with lock(): guard(config())
        elif action=='cleanup': cleanup()
        elif action=='disable':
            with lock():
                run('systemctl','disable','--now','ac-warp-watch.timer',check=False)
                cfg=config()|{'enabled':False};save('config.json',cfg);routing(cfg)
                if (DATA/'bin/warp-cli').is_file(): cli('disconnect',check=False)
        else: raise Problem('Unknown WARP command')
    except Problem as exc: print(str(exc),file=sys.stderr);raise SystemExit(1)
