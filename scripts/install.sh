#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/opt/amnezia-control}"
DATA_DIR="${DATA_DIR:-/var/lib/amnezia-control}"
REPO_URL="${REPO_URL:-https://github.com/dagmagnat/amnezia-control.git}"
SOURCE_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE_DIR="$(realpath "$2")"; shift 2;;
    --repo) REPO_URL="$2"; shift 2;;
    *) echo "Unknown argument: $1"; exit 2;;
  esac
done
if [[ $EUID -ne 0 ]]; then echo "Run as root: sudo ./scripts/install.sh"; exit 1; fi
LANG_CODE="${LANG_CODE:-}"; [[ -n "$LANG_CODE" ]] || { read -r -p "Language / Язык (ru/en) [ru]: " LANG_CODE; LANG_CODE=${LANG_CODE:-ru}; }
read -r -p "Panel admin login [admin]: " ADMIN_USER; ADMIN_USER=${ADMIN_USER:-admin}
read -r -s -p "Panel admin password: " ADMIN_PASS; echo
[[ ${#ADMIN_PASS} -ge 10 ]] || { echo "Password must contain at least 10 characters"; exit 1; }
read -r -p "Public domain (empty = IP only): " PANEL_DOMAIN
read -r -p "VPN engine (wireguard/amneziawg) [wireguard]: " VPN_ENGINE; VPN_ENGINE=${VPN_ENGINE:-wireguard}
read -r -p "VPN public endpoint (IP or domain:port) [auto]: " VPN_ENDPOINT
VPN_ENDPOINT=${VPN_ENDPOINT:-$(hostname -I | awk '{print $1}'):51820}
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip nginx sqlite3 curl ca-certificates unzip qrencode wireguard wireguard-tools git openssl
if [[ "$VPN_ENGINE" == "amneziawg" ]] && command -v add-apt-repository >/dev/null 2>&1; then add-apt-repository -y ppa:amnezia/ppa || true; apt-get update || true; apt-get install -y amneziawg amneziawg-tools || true; fi
if [[ ! -d "$APP_DIR/.git" ]]; then
  rm -rf "$APP_DIR"; mkdir -p "$(dirname "$APP_DIR")"
  if [[ -n "$SOURCE_DIR" ]]; then cp -a "$SOURCE_DIR/." "$APP_DIR/"; else git clone "$REPO_URL" "$APP_DIR"; fi
fi
python3 -m venv "$APP_DIR/.venv"; "$APP_DIR/.venv/bin/pip" install --upgrade pip; "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
mkdir -p "$DATA_DIR" /etc/amnezia-control
HASH=$("$APP_DIR/.venv/bin/python" -c 'import sys;sys.path.insert(0,"backend");from app import hash_password;print(hash_password(sys.argv[1]))' "$ADMIN_PASS")
VPN_BIN=wg; [[ "$VPN_ENGINE" == "amneziawg" ]] && command -v awg >/dev/null 2>&1 && VPN_BIN=awg
VPN_PRIVATE=$(umask 077; "$VPN_BIN" genkey)
VPN_PUBLIC=$(printf '%s\n' "$VPN_PRIVATE" | "$VPN_BIN" pubkey)
mkdir -p /etc/wireguard
VPN_INTERFACE=wg0; [[ "$VPN_ENGINE" == "amneziawg" ]] && VPN_INTERFACE=awg0
WAN_IFACE=$(ip route get 1.1.1.1 | awk '{print $5; exit}')
cat > "/etc/wireguard/$VPN_INTERFACE.conf" <<WGCONF
[Interface]
Address = 10.8.0.1/24
ListenPort = 51820
PrivateKey = $VPN_PRIVATE
SaveConfig = true
PostUp = iptables -A FORWARD -i $VPN_INTERFACE -j ACCEPT; iptables -A FORWARD -o $VPN_INTERFACE -j ACCEPT; iptables -t nat -A POSTROUTING -o $WAN_IFACE -j MASQUERADE
PostDown = iptables -D FORWARD -i $VPN_INTERFACE -j ACCEPT; iptables -D FORWARD -o $VPN_INTERFACE -j ACCEPT; iptables -t nat -D POSTROUTING -o $WAN_IFACE -j MASQUERADE
WGCONF
chmod 600 "/etc/wireguard/$VPN_INTERFACE.conf"
sysctl -w net.ipv4.ip_forward=1 >/dev/null
grep -q '^net.ipv4.ip_forward=1' /etc/sysctl.d/99-amnezia-control.conf 2>/dev/null || echo 'net.ipv4.ip_forward=1' > /etc/sysctl.d/99-amnezia-control.conf
QUICK_SERVICE=wg-quick; [[ "$VPN_ENGINE" == "amneziawg" ]] && command -v awg-quick >/dev/null 2>&1 && QUICK_SERVICE=awg-quick
systemctl enable --now "$QUICK_SERVICE@$VPN_INTERFACE" || true
cat > /etc/amnezia-control/panel.env <<EOF
AMNEZIA_CONTROL_ROOT=$APP_DIR
AMNEZIA_CONTROL_DATA=$DATA_DIR
AMNEZIA_CONTROL_SECRET=$(openssl rand -hex 32)
EOF
"$APP_DIR/.venv/bin/python" - "$DATA_DIR/control.db" "$ADMIN_USER" "$HASH" <<'PY'
import sqlite3,sys
con=sqlite3.connect(sys.argv[1]); con.executescript('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT DEFAULT "",protocol TEXT NOT NULL,version TEXT NOT NULL,address TEXT NOT NULL UNIQUE,public_key TEXT NOT NULL,private_key TEXT NOT NULL,preshared_key TEXT DEFAULT "",endpoint TEXT DEFAULT "",traffic_limit TEXT DEFAULT "",expires_at TEXT DEFAULT "",enabled INTEGER NOT NULL DEFAULT 1,created_at INTEGER NOT NULL,config TEXT NOT NULL);')
con.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('admin_user',sys.argv[2])); con.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('admin_password',sys.argv[3])); con.commit()
PY
"$APP_DIR/.venv/bin/python" - "$DATA_DIR/control.db" "$VPN_ENGINE" "$VPN_INTERFACE" "$VPN_PUBLIC" "$VPN_ENDPOINT" <<'PY'
import sqlite3,sys
con=sqlite3.connect(sys.argv[1]);
for key,value in [('vpn_engine',sys.argv[2]),('vpn_interface',sys.argv[3]),('server_public_key',sys.argv[4]),('endpoint',sys.argv[5])]: con.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,value))
con.commit()
PY
cp "$APP_DIR/systemd/amnezia-control.service" /etc/systemd/system/amnezia-control.service
sed -i '/\[Service\]/a EnvironmentFile=/etc/amnezia-control/panel.env' /etc/systemd/system/amnezia-control.service
systemctl daemon-reload; systemctl enable --now amnezia-control
cat >/etc/nginx/sites-available/amnezia-control <<NGINX
server { listen 80; server_name ${PANEL_DOMAIN:-_}; location / { proxy_pass http://127.0.0.1:8090; proxy_set_header Host \$host; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; } }
NGINX
ln -sfn /etc/nginx/sites-available/amnezia-control /etc/nginx/sites-enabled/amnezia-control
nginx -t && systemctl reload nginx
if [[ -n "$PANEL_DOMAIN" ]] && command -v certbot >/dev/null 2>&1; then echo "For HTTPS run: certbot --nginx -d $PANEL_DOMAIN"; fi
echo "Amnezia Control installed. URL: ${PANEL_DOMAIN:-http://$(hostname -I | awk '{print $1}')}  user: $ADMIN_USER"
