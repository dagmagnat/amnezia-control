#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || exit 1
APP_DIR=/opt/amnezia-control
for unit in ac-awg-reply-refresh.service ac-awg-reply-refresh.timer; do
  install -m 644 "$APP_DIR/systemd/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl start ac-awg-reply-refresh.service
systemctl enable --now ac-awg-reply-refresh.timer
# Upgrade from the verified, earlier fixed-IP repair without removing its
# active table. The new service has already installed the current policy.
legacy=/etc/systemd/system/ac-awg3-reply-source.service
if [[ -f "$legacy" ]] && grep -Fq '/etc/amnezia-control/awg3-reply-source.nft' "$legacy"; then
  systemctl disable ac-awg3-reply-source.service
fi
