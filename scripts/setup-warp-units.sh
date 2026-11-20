#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || exit 1
APP_DIR=/opt/amnezia-control
for unit in ac-warp-guard.service ac-warp-network.service ac-warp-client.service ac-warp-watch.service ac-warp-watch.timer; do
  install -m 644 "$APP_DIR/systemd/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable ac-warp-guard.service
# Deliberately do not install, register, enable or start WARP during panel updates.
