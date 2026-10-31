#!/usr/bin/env bash
set -Eeuo pipefail
systemctl --no-pager --full status amnezia-control || true
systemctl --no-pager --full status awg-quick@awg0 || true
systemctl --no-pager --full status wg-quick@wg0 || true
printf '\nVPN binaries:\n'; command -v wg || true; command -v awg || true
printf '\nInterfaces:\n'; wg show 2>/dev/null || true; awg show 2>/dev/null || true
printf '\nPorts:\n'; ss -ltnup | grep -E ':(80|443|8080|51820|8090)\b' || true
