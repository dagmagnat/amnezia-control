#!/usr/bin/env bash
set -Eeuo pipefail
systemctl --no-pager --full status amnezia-control || true
ss -ltnup
wg show || true
awg show || true
curl -fsS http://127.0.0.1:8090/api/me || true
