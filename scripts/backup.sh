#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || exit 1
OUT=${1:-/root/amnezia-control-$(date +%Y%m%d-%H%M%S).tar.gz}
LAYOUT=${2:-archive}
[[ $LAYOUT == archive || $LAYOUT == --root-layout ]] || exit 2
WORK=$(mktemp -d /tmp/ac-backup.XXXXXX)
trap 'rm -rf -- "$WORK"' EXIT
umask 077
DB_DIR=$WORK
if [[ $LAYOUT == --root-layout ]]; then
  DB_DIR=$WORK/var/lib/amnezia-control
  mkdir -p "$DB_DIR"
fi
/opt/amnezia-control/.venv/bin/python - "$DB_DIR" <<'PY'
import sqlite3,sys
from contextlib import closing
from pathlib import Path
for name in ('control.db','traffic.db'):
    source_path=Path('/var/lib/amnezia-control')/name
    if name != 'control.db' and not source_path.exists(): continue
    with (closing(sqlite3.connect(f'file:{source_path}?mode=ro', uri=True)) as source,
          closing(sqlite3.connect(Path(sys.argv[1])/name)) as target):
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise SystemExit(f'Cannot back up {name}')
PY
# Copy stable files before running tar. Runtime logs, sockets, binaries and
# the Cloudflare device registration are regenerated on the destination.
for path in /etc/amnezia-control /etc/wireguard /etc/amnezia/amneziawg \
            /etc/nginx/sites-available/amnezia-control /etc/systemd/system/amnezia-control.service \
            /var/lib/amnezia-control/warp/config.json /var/lib/amnezia-control/warp/restore-pending.json; do
  [[ ! -e $path ]] || cp -a --parents "$path" "$WORK/"
done
tar -czf "$OUT" -C "$WORK" .
tar -tzf "$OUT" >/dev/null
echo "Backup / Копия: $OUT"
