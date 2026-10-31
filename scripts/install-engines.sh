#!/usr/bin/env bash
set -Eeuo pipefail
# Build only official upstreams. Resolve once and record full source revisions.
[[ $EUID -eq 0 ]] || exit 1
if [[ -f /etc/amnezia-control/engine-sources.txt ]] && command -v wg >/dev/null && command -v awg >/dev/null && command -v awg-quick >/dev/null && command -v amneziawg-go >/dev/null; then
  echo 'WireGuard / AmneziaWG binaries found'
  exit 0
fi
apt-get install -y build-essential git curl ca-certificates python3 wireguard-tools
STAGE=$(mktemp -d /tmp/ac-engines.XXXXXX)
trap 'rm -rf -- "$STAGE"' EXIT
install -d -m 755 /opt/amnezia-control-toolchain /etc/amnezia/amneziawg /etc/wireguard
curl -fsSL 'https://go.dev/dl/?mode=json' -o "$STAGE/go.json"
case $(uname -m) in x86_64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; *) echo 'Supported CPU: x86_64 / arm64'; exit 1;; esac
python3 - "$STAGE/go.json" "$ARCH" > "$STAGE/go-release" <<'PY'
import json,sys
versions=json.load(open(sys.argv[1]))
for release in versions:
    if not release['stable']: continue
    for f in release['files']:
        if f['os']=='linux' and f['arch']==sys.argv[2] and f['kind']=='archive':
            print(f['filename']);print(f['sha256']);sys.exit(0)
raise SystemExit('No official Go release found')
PY
mapfile -t RELEASE < "$STAGE/go-release"
curl -fsSL "https://go.dev/dl/${RELEASE[0]}" -o "$STAGE/go.tar.gz"
printf '%s  %s\n' "${RELEASE[1]}" "$STAGE/go.tar.gz" | sha256sum -c -
tar -xzf "$STAGE/go.tar.gz" -C /opt/amnezia-control-toolchain
export PATH=/opt/amnezia-control-toolchain/go/bin:$PATH
export GOTOOLCHAIN=auto
# Variables allow explicitly selecting an audited upstream tag/commit.
git clone https://github.com/amnezia-vpn/amneziawg-go.git "$STAGE/go-source"
git -C "$STAGE/go-source" checkout "${AWG_GO_REF:-master}"
(cd "$STAGE/go-source"; go build -trimpath -o "$STAGE/amneziawg-go" .)
install -m 755 "$STAGE/amneziawg-go" /usr/local/bin/amneziawg-go
git clone https://github.com/amnezia-vpn/amneziawg-tools.git "$STAGE/tools"
git -C "$STAGE/tools" checkout "${AWG_TOOLS_REF:-master}"
make -C "$STAGE/tools/src" -j"$(nproc)"
make -C "$STAGE/tools/src" install WITH_WGQUICK=yes WITH_SYSTEMDUNITS=yes
command -v awg
command -v awg-quick
command -v amneziawg-go
install -d -m 700 /etc/amnezia-control
{ printf 'amneziawg-go '; git -C "$STAGE/go-source" rev-parse HEAD; printf 'amneziawg-tools '; git -C "$STAGE/tools" rev-parse HEAD; } > /etc/amnezia-control/engine-sources.txt
systemctl daemon-reload
