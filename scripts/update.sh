#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || exit 1
APP_DIR=/opt/amnezia-control
WORK=$(mktemp -d /tmp/ac-update.XXXXXX)
trap 'rm -rf -- "$WORK"' EXIT
SOURCE=''
if [[ ${1:-} == --source ]]; then SOURCE=$(realpath "${2:?Source folder required}"); fi
if [[ -z $SOURCE ]]; then
  git clone --depth 1 --branch main https://github.com/dagmagnat/amnezia-control.git "$WORK/source"
  SOURCE=$WORK/source
fi
[[ -f $SOURCE/backend/manage.py && -f $SOURCE/dist/app.js ]] || { echo 'Not a complete 0.2 release';exit 1; }
apt-get update
apt-get install -y rsync python3-venv iptables wireguard-tools
BACKUP_DIR=/root/amnezia-control-backups/$(date +%Y%m%d-%H%M%S)
install -d -m 700 "$BACKUP_DIR/source"
rsync -a --exclude=.git --exclude=.venv --exclude=work --exclude=outputs "$APP_DIR/" "$BACKUP_DIR/source/"
# Back up DB, original interfaces, panel service and Nginx settings before replacing code.
paths=()
for path in /var/lib/amnezia-control /etc/amnezia-control /etc/wireguard /etc/amnezia /etc/nginx/sites-available/amnezia-control /etc/systemd/system/amnezia-control.service; do
  [[ ! -e $path ]] || paths+=("$path")
done
systemctl stop amnezia-control
umask 077
tar -czf "$BACKUP_DIR/state.tar.gz" "${paths[@]}"
rollback(){
  echo "Update failed. Restoring previous application. Backup: $BACKUP_DIR"
  rsync -a "$BACKUP_DIR/source/" "$APP_DIR/"
  # Restore data while the service is stopped. VPN interfaces were not restarted.
  tar -xzf "$BACKUP_DIR/state.tar.gz" -C /
  systemctl daemon-reload
  systemctl start amnezia-control || true
}
trap 'rollback; rm -rf -- "$WORK"' ERR
rsync -a --exclude=.git --exclude=.venv --exclude=work --exclude=outputs "$SOURCE/" "$APP_DIR/"
find "$APP_DIR/scripts" -name '*.sh' -exec sed -i 's/\r$//' {} +
chmod +x "$APP_DIR"/scripts/*.sh
bash "$APP_DIR/scripts/install-engines.sh"
install -d -m 700 /etc/amnezia-control /etc/wireguard /etc/amnezia/amneziawg
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
export AMNEZIA_CONTROL_ROOT=$APP_DIR AMNEZIA_CONTROL_DATA=/var/lib/amnezia-control
"$APP_DIR/.venv/bin/python" "$APP_DIR/backend/manage.py" migrate
"$APP_DIR/.venv/bin/python" "$APP_DIR/backend/manage.py" web-limits
install -m 644 "$APP_DIR/systemd/amnezia-control.service" /etc/systemd/system/amnezia-control.service
install -m 644 "$APP_DIR/systemd/ac-awg@.service" /etc/systemd/system/ac-awg@.service
systemctl daemon-reload
systemctl reset-failed amnezia-control
systemctl start amnezia-control
bash "$APP_DIR/scripts/wait-panel.sh"
systemctl is-active --quiet amnezia-control
trap - ERR
printf 'Updated successfully. Backup / Копия: %s\n' "$BACKUP_DIR"
echo 'Existing VPN keys and Nginx IP:port settings preserved. Refresh browser with Ctrl+F5.'
