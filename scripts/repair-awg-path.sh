#!/usr/bin/env bash
# Repair the legacy installer path without generating or replacing keys.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root'; exit 1; }
command -v awg >/dev/null
command -v awg-quick >/dev/null
SOURCE=/etc/wireguard/awg0.conf
TARGET=/etc/amnezia/amneziawg/awg0.conf
if [[ ! -f "$TARGET" ]]; then
  [[ -f "$SOURCE" ]] || { echo 'No awg0.conf found. Nothing changed.'; exit 1; }
  install -d -m 700 /etc/amnezia/amneziawg
  install -m 600 "$SOURCE" "$TARGET"
  echo 'Copied legacy configuration. Original preserved in /etc/wireguard/awg0.conf.'
else
  echo 'Existing target configuration preserved.'
fi
if systemctl is-active --quiet awg-quick@awg0; then
  echo 'Service already active. No restart performed.'
else
  systemctl reset-failed awg-quick@awg0
  if ! systemctl start awg-quick@awg0; then
    echo 'VPN still failed. Check: journalctl -u awg-quick@awg0 -n 60 --no-pager'
    exit 1
  fi
fi
systemctl is-active --quiet awg-quick@awg0
awg show awg0 public-key >/dev/null
echo 'AmneziaWG interface is active. Verify a client handshake and Internet access separately.'
