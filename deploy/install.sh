#!/usr/bin/env bash
# Zippy VPN — VPS üçin bir buýrukly gurnaýjy (Ubuntu / Debian).
#   sudo -E bash deploy/install.sh
# ýa-da GitHub-dan göni:
#   curl -fsSL https://raw.githubusercontent.com/redmirobot01-byte/Zippy/arena/2a68f12a-zippy/deploy/install.sh | sudo -E bash
#
# Üýtgedip bolýan üýtgeýjiler: ZIPPY_HOST, ZIPPY_BRANCH, SS_PORT, VLESS_PORT
set -euo pipefail

REPO="${ZIPPY_REPO:-redmirobot01-byte/Zippy}"
BRANCH="${ZIPPY_BRANCH:-arena/2a68f12a-zippy}"
INSTALL_DIR="${ZIPPY_DIR:-/opt/zippy}"
CONF_DIR="${ZIPPY_CONF_DIR:-/etc/zippy}"
SS_PORT="${SS_PORT:-8388}"
VLESS_PORT="${VLESS_PORT:-8443}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "❌ root gerek.  sudo -E bash deploy/install.sh" >&2
  exit 1
fi

echo "==> [1/7]paketler gurnalýar..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  python3 python3-venv python3-pip curl ca-certificates

echo "==> [2/7]çeşme kody ${INSTALL_DIR} içine goýulýar..."
mkdir -p "$INSTALL_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/../zippy/__init__.py" ]]; then
  (cd "$SCRIPT_DIR/.." && tar --exclude=.git --exclude=.venv --exclude=__pycache__ \
      --exclude=.pytest_cache --exclude=tests -cf - .) | (cd "$INSTALL_DIR" && tar xf -)
  echo "    ýerli repodan alyndy"
else
  curl -fsSL "https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}" \
      -o /tmp/zippy-src.tar.gz
  tar xzf /tmp/zippy-src.tar.gz -C "$INSTALL_DIR" --strip-components=1
  echo "    github.com/${REPO}@${BRANCH} tarball-dan alyndy"
fi

echo "==> [3/7]Python gurşawy..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

echo "==> [4/7]köpçülikleýin IP anyklanýar..."
HOST="${ZIPPY_HOST:-}"
if [[ -z "$HOST" ]]; then
  HOST="$(curl -fsS --max-time 10 https://api.ipify.org 2>/dev/null || true)"
fi
if [[ -z "$HOST" ]]; then
  HOST="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
if [[ -z "$HOST" ]]; then
  echo "❌ IP anyklanmady: ZIPPY_HOST=1.2.3.4 bilen gaýtadan işlet" >&2
  exit 1
fi
echo "    host = $HOST"

echo "==> [5/7]açarlar, sertifikat we konfigurasiýa döredilýär..."
mkdir -p "$CONF_DIR"
PY="$INSTALL_DIR/.venv/bin/python"
cd "$INSTALL_DIR"
"$PY" -m zippy init --host "$HOST" --config "$CONF_DIR/zippy.json" \
    --ss-port "$SS_PORT" --vless-port "$VLESS_PORT" --tls
"$PY" -m zippy links --config "$CONF_DIR/zippy.json" --write --out-dir "$CONF_DIR"
chmod 600 "$CONF_DIR/zippy.json"

echo "==> [6/7]systemd hyzmaty..."
cat > /etc/systemd/system/zippy.service <<EOF
[Unit]
Description=Zippy VPN (Shadowsocks AEAD + VLESS)
Documentation=https://github.com/${REPO}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${PY} -m zippy serve --config ${CONF_DIR}/zippy.json
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now zippy.service

echo "==> [7/7]firewall..."
if command -v ufw >/dev/null 2>&1; then
  ufw allow "${SS_PORT}/tcp" >/dev/null || true
  ufw allow "${VLESS_PORT}/tcp" >/dev/null || true
fi

echo
echo "================ TAÝÝAR ================"
systemctl is-active zippy.service >/dev/null && echo "  Hyzmat: işleýär ✅" || echo "  Hyzmat: BARLAŇ (journalctl -u zippy -n 50)"
echo "  Portlar (bulut firewall-ynda hem açyň): ${SS_PORT}/tcp, ${VLESS_PORT}/tcp"
echo
echo "  Paýlaşylýan linkler:"
sed 's/^/    /' "$CONF_DIR/links.txt"
echo
echo "  ähli maglumat: ${CONF_DIR}/links.txt , ${CONF_DIR}/subscription.txt"
echo "  barlag: systemctl status zippy --no-pager"
echo "======================================="
