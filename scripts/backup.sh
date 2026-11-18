#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || exit 1
OUT=${1:-/root/amnezia-control-$(date +%Y%m%d-%H%M%S).tar.gz}
WORK=$(mktemp -d /tmp/ac-backup.XXXXXX)
trap 'rm -rf -- "$WORK"' EXIT
umask 077
/opt/amnezia-control/.venv/bin/python - "$WORK/control.db" <<'PY'
import sqlite3,sys
from pathlib import Path
for name in ('control.db','traffic.db'):
    source_path=Path('/var/lib/amnezia-control')/name
    if not source_path.exists(): continue
    source=sqlite3.connect(source_path);target=sqlite3.connect(Path(sys.argv[1]).parent/name)
    source.backup(target);target.close();source.close()
PY
paths=()
for path in /etc/amnezia-control /etc/wireguard /etc/amnezia /etc/nginx/sites-available/amnezia-control /etc/systemd/system/amnezia-control.service; do [[ ! -e $path ]] || paths+=("$path"); done
tar -czf "$OUT" -C "$WORK" . -C / "${paths[@]}"
echo "Backup / Копия: $OUT"
