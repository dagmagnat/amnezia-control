#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || exit 1
APP_DIR=/opt/amnezia-control
WARP_DIR=/var/lib/amnezia-control/warp
source /etc/os-release
case "${ID}:${VERSION_CODENAME:-}" in
  ubuntu:jammy|ubuntu:noble|ubuntu:resolute|debian:bookworm|debian:trixie) ;;
  *) echo 'WARP: supported Ubuntu 22.04/24.04/26.04 or Debian 12/13 required';exit 1;;
esac
case $(dpkg --print-architecture) in amd64|arm64) ;; *) echo 'WARP: amd64 or arm64 required';exit 1;; esac
# Never adopt or reconfigure a separately installed WARP client.
if command -v warp-cli >/dev/null || systemctl is-active --quiet warp-svc; then
  echo 'Existing external WARP installation detected. It must be handled separately.';exit 1
fi
if [[ -d /var/lib/cloudflare-warp && ! -f $WARP_DIR/package.json ]]; then
  echo 'Existing Cloudflare account state found. Installation stopped to preserve it.';exit 1
fi
install -d -m 700 "$WARP_DIR" "$WARP_DIR/bin"
WORK=$(mktemp -d /tmp/ac-warp-package.XXXXXX)
trap 'rm -rf -- "$WORK"' EXIT
# APT drops privileges to _apt; use a writable private temporary area even
# when a host has a nonstandard /tmp mode. Never weaken signature checks.
chmod 755 "$WORK"
install -d -m 1777 "$WORK/apt-tmp"
export TMPDIR="$WORK/apt-tmp"
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
apt-get -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 -o Acquire::Retries=1 update
PACKAGES=$(apt-cache pkgnames)
headless_dep() {
  local candidate
  for candidate in "$@"; do
    if grep -Fx "$candidate" <<<"$PACKAGES" >/dev/null; then printf '%s' "$candidate";return;fi
  done
  echo 'Missing supported TPM library package' >&2;return 1
}
TPM_LOADER=$(headless_dep libtss2-tctildr0t64 libtss2-tctildr0)
TPM_ESYS=$(headless_dep libtss2-esys-3.0.2-0t64 libtss2-esys-3.0.2-0)
apt-get -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 -o Acquire::Retries=1 install -y --no-install-recommends curl ca-certificates gnupg iproute2 iptables nftables libdbus-1-3 libpcap0.8 libcap2-bin libnss3 "$TPM_LOADER" "$TPM_ESYS"
curl --proto '=https' --tlsv1.2 -fsSL --retry 2 https://pkg.cloudflareclient.com/pubkey.gpg -o "$WORK/cloudflare.gpg"
gpg --batch --yes --dearmor --output "$WORK/keyring.gpg" "$WORK/cloudflare.gpg"
install -m 644 "$WORK/keyring.gpg" /usr/share/keyrings/ac-cloudflare-warp.gpg
printf 'deb [signed-by=/usr/share/keyrings/ac-cloudflare-warp.gpg] https://pkg.cloudflareclient.com/ %s main\n' "$VERSION_CODENAME" >/etc/apt/sources.list.d/ac-cloudflare-warp.list
apt-get -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 -o Acquire::Retries=1 -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/ac-cloudflare-warp.list -o Dir::Etc::sourceparts=- update
# APT verifies signed repository metadata and the package digest. Extract just
# the official headless binaries; do not install or auto-start the host daemon.
chmod 755 "$WORK"
install -d -m 1777 "$WORK/download"
cd "$WORK/download"
apt-get -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 -o Acquire::Retries=1 -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/ac-cloudflare-warp.list -o Dir::Etc::sourceparts=- download cloudflare-warp
DEB=$(find "$WORK/download" -maxdepth 1 -name 'cloudflare-warp_*.deb' -print -quit)
[[ -n $DEB ]]
dpkg-deb -x "$DEB" "$WORK/extracted"
for NAME in warp-cli warp-svc; do
  BIN=$(find "$WORK/extracted" -type f -name "$NAME" -print -quit)
  [[ -n $BIN ]]
  if ldd "$BIN" | grep 'not found' >/dev/null; then echo "Missing headless dependencies for $NAME";exit 1;fi
  install -m 755 "$BIN" "$WARP_DIR/bin/$NAME.new"
done
systemctl stop ac-warp-client || true
mv "$WARP_DIR/bin/warp-cli.new" "$WARP_DIR/bin/warp-cli"
mv "$WARP_DIR/bin/warp-svc.new" "$WARP_DIR/bin/warp-svc"
VERSION=$(dpkg-deb -f "$DEB" Version)
VERSION="$VERSION" "$APP_DIR/.venv/bin/python" - <<'PY'
import json,os
from pathlib import Path
path=Path('/var/lib/amnezia-control/warp/package.json')
path.write_text(json.dumps({'version':os.environ['VERSION'],'source':'https://pkg.cloudflareclient.com/'}))
path.chmod(0o600)
PY
install -d -m 700 /var/lib/cloudflare-warp
bash "$APP_DIR/scripts/setup-warp-units.sh"
echo 'Official WARP binaries installed; registration and routing are still disabled.'
