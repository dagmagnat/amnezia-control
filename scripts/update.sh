#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR=/opt/amnezia-control
cd "$APP_DIR"
git pull --ff-only || true
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
systemctl restart amnezia-control
nginx -t && systemctl reload nginx
systemctl --no-pager --full status amnezia-control
