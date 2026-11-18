#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root / Запустите через sudo'; exit 1; }
APP_DIR=/opt/amnezia-control
DATA_DIR=/var/lib/amnezia-control
SOURCE_DIR=''
while [[ $# -gt 0 ]]; do case "$1" in --source) SOURCE_DIR=$(realpath "$2"); shift 2;; *) echo "Unknown argument $1"; exit 2;; esac; done
printf '1) Русский (Russian)\n2) English (Английский)\n'
read -r -p '[1]: ' CHOICE; LANG_CODE=ru; [[ ${CHOICE:-1} == 2 ]] && LANG_CODE=en
say(){ if [[ $LANG_CODE == ru ]]; then printf '%s\n' "$1"; else printf '%s\n' "$2"; fi; }
ask(){ say "$1" "$2"; read -r REPLY; }
if [[ -f "$DATA_DIR/control.db" ]]; then say 'Проект уже установлен. Используйте update.sh.' 'Already installed. Use update.sh.'; exit 1; fi
. /etc/os-release
case "$ID:$VERSION_ID" in ubuntu:22.04|ubuntu:24.04|ubuntu:26.04|debian:12|debian:13) ;; *) say 'Нужен Ubuntu 22.04/24.04/26.04 или Debian 12/13.' 'Requires Ubuntu 22.04/24.04/26.04 or Debian 12/13.';exit 1;; esac
[[ -c /dev/net/tun ]] || { say 'Нет /dev/net/tun. Включите TUN у провайдера VPS.' 'Missing /dev/net/tun. Enable TUN at your VPS provider.'; exit 1; }
ask 'Логин администратора [admin]:' 'Admin username [admin]:'; ADMIN_USER=${REPLY:-admin}
while true; do
  say 'Пароль (от 10 символов):' 'Password (at least 10 characters):'; read -r -s ADMIN_PASS; printf '\n'
  say 'Повторите пароль:' 'Repeat password:'; read -r -s AGAIN; printf '\n'
  [[ ${#ADMIN_PASS} -ge 10 && $ADMIN_PASS == "$AGAIN" ]] && break
  say 'Пароли не совпадают или слишком короткие.' 'Passwords mismatch or too short.'
done
ask 'Порт панели [8080]:' 'Panel port [8080]:'; PANEL_PORT=${REPLY:-8080}
[[ $PANEL_PORT =~ ^[0-9]{1,5}$ ]] && ((10#$PANEL_PORT>=1024 && 10#$PANEL_PORT<=65535 && 10#$PANEL_PORT!=8090)) || { echo 'Invalid port';exit 1; }
PANEL_PORT=$((10#$PANEL_PORT))
ask '1) Вход по IP  2) Домен + IP [1]:' '1) IP access  2) Domain + IP [1]:'; MODE=${REPLY:-1}; PANEL_DOMAIN=''
if [[ $MODE == 2 ]]; then ask 'Домен панели (пример panel.example.com):' 'Panel domain (panel.example.com):'; PANEL_DOMAIN=$REPLY; fi
ask 'Публичный IP этого VPS (Enter = определить автоматически):' 'Public IP of this VPS (Enter = auto-detect):'; PANEL_IP=$REPLY
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv nginx curl ca-certificates git rsync sqlite3 iptables iproute2 openssl wireguard-tools certbot python3-certbot-nginx
if [[ -z $PANEL_IP ]]; then PANEL_IP=$(curl -4 -fsS --max-time 10 https://api.ipify.org) || { echo 'Enter public IP manually';exit 1; }; fi
if [[ -n $PANEL_DOMAIN ]]; then
  if ! getent ahostsv4 "$PANEL_DOMAIN" | awk '{print $1}' | grep -Fxq "$PANEL_IP"; then
    say 'DNS пока не указывает на VPS. Установка продолжится; вход по IP останется.' 'DNS does not point here yet. Continuing; IP access remains available.'
  fi
fi
WORK=$(mktemp -d /tmp/ac-install.XXXXXX)
trap 'unset ADMIN_PASS AGAIN; rm -rf -- "$WORK"' EXIT
if [[ -z $SOURCE_DIR ]]; then git clone --depth 1 https://github.com/dagmagnat/amnezia-control.git "$WORK/source"; SOURCE_DIR=$WORK/source; fi
[[ -f $SOURCE_DIR/backend/manage.py ]] || { echo 'Wrong source archive'; exit 1; }
# Never remove an existing directory or its runtime state.
install -d -m 755 "$APP_DIR"
rsync -a --exclude=.git --exclude=.venv --exclude=outputs --exclude=work "$SOURCE_DIR/" "$APP_DIR/"
find "$APP_DIR/scripts" -name '*.sh' -exec sed -i 's/\r$//' {} +
chmod +x "$APP_DIR"/scripts/*.sh
bash "$APP_DIR/scripts/install-engines.sh"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
install -d -m 700 "$DATA_DIR" /etc/amnezia-control /etc/wireguard /etc/amnezia/amneziawg
umask 077
cat > /etc/amnezia-control/panel.env <<EOF
AMNEZIA_CONTROL_ROOT=$APP_DIR
AMNEZIA_CONTROL_DATA=$DATA_DIR
AMNEZIA_CONTROL_SECRET=$(openssl rand -hex 32)
EOF
export AMNEZIA_CONTROL_ROOT=$APP_DIR AMNEZIA_CONTROL_DATA=$DATA_DIR
# JSON stdin, no password in process arguments, files or logs.
export ADMIN_USER LANG_CODE
printf '%s' "$ADMIN_PASS" | "$APP_DIR/.venv/bin/python" -c 'import sys,json,os;print(json.dumps(dict(username=os.environ["ADMIN_USER"],password=sys.stdin.read(),language=os.environ["LANG_CODE"])))' | "$APP_DIR/.venv/bin/python" "$APP_DIR/backend/manage.py" init
unset ADMIN_PASS AGAIN
printf 'net.ipv4.ip_forward=1\n' > /etc/sysctl.d/99-amnezia-control.conf
sysctl -p /etc/sysctl.d/99-amnezia-control.conf
modprobe wireguard
install -m 644 "$APP_DIR/systemd/ac-awg@.service" /etc/systemd/system/ac-awg@.service
systemctl daemon-reload
printf '%s' "$PANEL_IP" | "$APP_DIR/.venv/bin/python" -c 'import sys,json;print(json.dumps(dict(host=sys.stdin.read())))' | "$APP_DIR/.venv/bin/python" "$APP_DIR/backend/manage.py" provision
install -m 644 "$APP_DIR/systemd/amnezia-control.service" /etc/systemd/system/amnezia-control.service
systemctl daemon-reload
systemctl enable --now nginx
export PANEL_DOMAIN PANEL_PORT PANEL_IP
"$APP_DIR/.venv/bin/python" -c 'import os,json;print(json.dumps(dict(domain=os.environ["PANEL_DOMAIN"],port=int(os.environ["PANEL_PORT"]),ip=os.environ["PANEL_IP"])))' | "$APP_DIR/.venv/bin/python" "$APP_DIR/backend/manage.py" panel
systemctl enable --now amnezia-control
bash "$APP_DIR/scripts/wait-panel.sh"
systemctl is-active --quiet amnezia-control
if command -v ufw >/dev/null && ufw status | grep -q 'Status: active'; then ufw allow "$PANEL_PORT/tcp"; ufw allow 51820/udp; ufw allow 51821/udp; fi
say 'Установка завершена.' 'Installation complete.'
printf 'IP: http://%s:%s\nLogin: %s\nWireGuard UDP: 51820\nAmneziaWG UDP: 51821\n' "$PANEL_IP" "$PANEL_PORT" "$ADMIN_USER"
[[ -z $PANEL_DOMAIN ]] || printf 'Domain: http://%s:%s\n' "$PANEL_DOMAIN" "$PANEL_PORT"
say 'HTTPS: bash /opt/amnezia-control/scripts/https.sh' 'HTTPS: bash /opt/amnezia-control/scripts/https.sh'
