"""Managed AWG userspace interface lifecycle; no config hooks are executed."""
import configparser
import ipaddress
import os
import re
import subprocess
import sys
from pathlib import Path
from core import Problem, atomic_text, command, firewall_rules

def read_network_settings(text):
    # wg-quick files legitimately repeat PostUp/PostDown. They are never executed
    # here: read only the scalar network fields needed by this managed service.
    lines=['[Interface]']
    for line in text.split('[Peer]')[0].splitlines():
        if '=' in line and line.split('=',1)[0].strip() in ('Address','ListenPort','MTU'):
            lines.append(line)
    parser=configparser.ConfigParser(interpolation=None)
    parser.optionxform=str
    parser.read_string('\n'.join(lines))
    return dict(parser['Interface'])


def main():
    action,iface=sys.argv[1:]
    if action not in ('up','down') or not re.fullmatch(r'acawg[0-9]+',iface): raise Problem('Invalid managed interface')
    path=Path('/etc/amnezia/amneziawg')/(iface+'.conf')
    fields=read_network_settings(path.read_text());address=str(ipaddress.ip_interface(fields['Address']))
    p={'interface':iface,'address':address,'port':int(fields['ListenPort'])}
    rules=firewall_rules(p)
    if action=='down':
        for rule in reversed(rules):
            prefix=['iptables']+(['-t','nat'] if rule[0]=='POSTROUTING' else [])
            subprocess.run(prefix+['-D']+rule,capture_output=True)
        subprocess.run(['ip','link','delete',iface],capture_output=True)
        return
    if subprocess.run(['ip','link','show',iface],capture_output=True).returncode==0:
        raise Problem('Interface already exists; inspect it before starting')
    runtime=path.with_suffix('.runtime')
    try:
        command('amneziawg-go',iface)
        # Use the official stripper to remove Address/MTU/hook fields, never evaluate hooks.
        atomic_text(runtime,command('awg-quick','strip',str(path))+'\n')
        command('awg','setconf',iface,str(runtime))
        command('ip','address','add',address,'dev',iface)
        command('ip','link','set','dev',iface,'mtu',str(int(fields.get('MTU','1380'))),'up')
        added=[]
        for rule in rules:
            prefix=['iptables']+(['-t','nat'] if rule[0]=='POSTROUTING' else [])
            if subprocess.run(prefix+['-C']+rule,capture_output=True).returncode:
                command(*prefix,'-I',*rule);added.append((prefix,rule))
    except Exception:
        for prefix,rule in reversed(locals().get('added',[])): subprocess.run(prefix+['-D']+rule,capture_output=True)
        subprocess.run(['ip','link','delete',iface],capture_output=True)
        raise
    finally: runtime.unlink(missing_ok=True)

if __name__=='__main__':
    try: main()
    except (Problem,OSError,ValueError) as e:print(str(e),file=sys.stderr);sys.exit(1)
