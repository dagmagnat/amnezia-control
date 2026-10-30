#!/usr/bin/env bash
set -Eeuo pipefail
CONF=${1:?Usage: import-conf.sh /path/to/client.conf}
[[ -f "$CONF" ]] || { echo "File not found"; exit 1; }
mkdir -p /var/lib/amnezia-control/imports
cp "$CONF" "/var/lib/amnezia-control/imports/$(basename "$CONF")"
echo "Imported file to /var/lib/amnezia-control/imports. Finish import in the panel."
