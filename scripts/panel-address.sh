#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || exit 1
printf '1) Русский (Russian)\n2) English (Английский)\n'; read -r -p '[1]: ' LANG_CHOICE
read -r -p 'Domain / Домен (Enter = IP): ' PANEL_DOMAIN
read -r -p 'Public IP / Публичный IP: ' PANEL_IP
read -r -p 'Port / Порт [8080]: ' PANEL_PORT; PANEL_PORT=${PANEL_PORT:-8080}
export PANEL_DOMAIN PANEL_PORT PANEL_IP
/opt/amnezia-control/.venv/bin/python -c 'import json,os;print(json.dumps(dict(domain=os.environ["PANEL_DOMAIN"],port=os.environ["PANEL_PORT"],ip=os.environ["PANEL_IP"])))' | /opt/amnezia-control/.venv/bin/python /opt/amnezia-control/backend/manage.py panel
printf 'http://%s:%s\n' "${PANEL_DOMAIN:-$PANEL_IP}" "$PANEL_PORT"
echo 'Open the TCP port at your provider / Откройте TCP-порт в панели провайдера.'
