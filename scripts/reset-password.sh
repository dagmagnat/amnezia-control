#!/usr/bin/env bash
set -Eeuo pipefail
sudo /opt/amnezia-control/.venv/bin/python /opt/amnezia-control/backend/manage.py password
