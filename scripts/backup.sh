#!/usr/bin/env bash
set -Eeuo pipefail
OUT="${1:-/root/amnezia-control-backup-$(date +%Y%m%d-%H%M%S).tar.gz}"
tar -czf "$OUT" /var/lib/amnezia-control /etc/amnezia-control /etc/wireguard 2>/dev/null || tar -czf "$OUT" /var/lib/amnezia-control /etc/amnezia-control
echo "Backup: $OUT"
