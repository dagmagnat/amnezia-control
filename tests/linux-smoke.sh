#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 && ${AC_RUN_VPN_SMOKE:-0} == 1 ]] || { echo 'Run only on a disposable test VPS: sudo AC_RUN_VPN_SMOKE=1 bash tests/linux-smoke.sh';exit 1; }
# Real engine/config smoke test. No changes to production interfaces, DB or routes.
PY=/opt/amnezia-control/.venv/bin/python
"$PY" - <<'PY'
import sys,tempfile,subprocess
sys.path.insert(0,'/opt/amnezia-control/backend')
from pathlib import Path
from core import command,parameters,keys
interfaces=[]
try:
    for n,v in enumerate(['wg','1.0','1.5','2.0','3.0','3.1']):
        iface='actest'+str(n)
        if subprocess.run(['ip','link','show',iface],capture_output=True).returncode==0:
            raise RuntimeError('Test interface already exists; nothing will be replaced: '+iface)
        b='wg' if v=='wg' else 'awg'
        private,public=keys(b)
        if b=='wg':command('ip','link','add',iface,'type','wireguard')
        else:command('amneziawg-go',iface)
        interfaces.append(iface)
        params={} if b=='wg' else parameters(v)
        with tempfile.NamedTemporaryFile(mode='w',suffix='.conf') as f:
            f.write('[Interface]\nPrivateKey = '+private+'\nListenPort = 0\n'+'\n'.join(k+' = '+value for k,value in params.items())+'\n');f.flush()
            command(b,'setconf',iface,f.name)
        assert command(b,'show',iface,'public-key')==public
        print('PASS',v)
finally:
    for iface in interfaces: subprocess.run(['ip','link','delete',iface],capture_output=True)
PY
