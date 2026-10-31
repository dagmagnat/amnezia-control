#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || exit 1
read -r -p '1) Панель / Panel only  2) Панель и созданные VPN / Panel + managed VPN [1]: ' MODE
if [[ ${MODE:-1} == 2 ]]; then
  echo 'This deletes managed server/client keys. Existing external VPN services are preserved.'
fi
read -r -p 'Введите REMOVE / Type REMOVE: ' CONFIRM
[[ $CONFIRM == REMOVE ]] || exit 0
bash /opt/amnezia-control/scripts/backup.sh
systemctl disable --now amnezia-control
if [[ ${MODE:-1} == 2 ]]; then
  /opt/amnezia-control/.venv/bin/python - <<'PY'
import sqlite3,subprocess
from pathlib import Path
con=sqlite3.connect('/var/lib/amnezia-control/control.db');con.row_factory=sqlite3.Row
for p in con.execute('SELECT * FROM profiles'):
    # Never automatically remove adopted legacy interfaces.
    if not p['interface'].startswith(('acwg','acawg')): continue
    service=('ac-awg' if p['protocol']=='amneziawg' else 'wg-quick')+'@'+p['interface']
    subprocess.run(['systemctl','disable','--now',service],check=True)
    root=Path('/etc/amnezia/amneziawg' if p['protocol']=='amneziawg' else '/etc/wireguard')
    (root/(p['interface']+'.conf')).unlink(missing_ok=True)
PY
  rm -f /etc/sysctl.d/99-amnezia-control.conf
fi
rm -f /etc/nginx/sites-enabled/amnezia-control /etc/nginx/sites-available/amnezia-control /etc/systemd/system/amnezia-control.service
systemctl daemon-reload
nginx -t && systemctl reload nginx
if [[ ${MODE:-1} == 2 ]]; then
  rm -f /etc/systemd/system/ac-awg@.service
  rm -rf /var/lib/amnezia-control /etc/amnezia-control /opt/amnezia-control
  systemctl daemon-reload
else
  echo 'VPN runtime kept in /opt/amnezia-control so managed AWG services can start after reboot.'
fi
echo 'Removed. Backups are in /root. Shared packages and adopted VPNs preserved.'
