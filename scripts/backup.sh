#!/usr/bin/env bash
set -Eeuo pipefail
OUT="${1:-/root/amnezia-control-backup-$(date +%Y%m%d-%H%M%S).tar.gz}"
umask 077
paths=()
for path in /var/lib/amnezia-control /etc/amnezia-control /etc/wireguard /etc/amnezia; do
  [[ ! -d "$path" ]] || paths+=("$path")
done
[[ ${#paths[@]} -gt 0 ]] || { echo 'No installation data found'; exit 1; }
tar -czf "$OUT" "${paths[@]}"
echo "Backup: $OUT"
