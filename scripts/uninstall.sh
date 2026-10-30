#!/usr/bin/env bash
set -Eeuo pipefail
read -r -p "Type REMOVE to delete Amnezia Control and its panel service: " ANSWER
[[ "$ANSWER" == "REMOVE" ]] || { echo "Cancelled"; exit 0; }
systemctl disable --now amnezia-control || true
rm -f /etc/systemd/system/amnezia-control.service /etc/nginx/sites-enabled/amnezia-control /etc/nginx/sites-available/amnezia-control
systemctl daemon-reload; systemctl reload nginx || true
rm -rf /opt/amnezia-control /var/lib/amnezia-control /etc/amnezia-control
echo "Panel removed. WireGuard interfaces and /etc/wireguard were preserved. Remove them separately only if you are sure."
