#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || exit 1
OUT=${1:-/root/amnezia-control-$(date +%Y%m%d-%H%M%S).tar.gz}
WORK=$(mktemp -d /tmp/ac-backup.XXXXXX)
trap 'rm -rf -- "$WORK"' EXIT
umask 077
/opt/amnezia-control/.venv/bin/python - "$WORK/control.db" <<'PY'
import sqlite3,sys
source=sqlite3.connect('/var/lib/amnezia-control/control.db');target=sqlite3.connect(sys.argv[1]);source.backup(target);target.close();source.close()
PY
paths=()
for path in /etc/amnezia-control /etc/wireguard /etc/amnezia /etc/nginx/sites-available/amnezia-control /etc/systemd/system/amnezia-control.service; do [[ ! -e $path ]] || paths+=("$path"); done
tar -czf "$OUT" -C "$WORK" control.db -C / "${paths[@]}"
echo "Backup / Копия: $OUT"
