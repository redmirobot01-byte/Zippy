#!/usr/bin/env bash
# Has güýçli wariant: hakyky Xray-core + VLESS/REALITY + VMess + Shadowsocks.
# DPI / peteklemä garşy iň çydamly wariant. Ubuntu/Debian, root gerek.
#   sudo -E bash deploy/install-xray.sh
#
# Üýtgeýjiler: XRAY_VERSION, ZIPPY_HOST, REALITY_DEST, REALITY_SNI,
#              SS_PORT, VMESS_PORT
set -euo pipefail

XRAY_VERSION="${XRAY_VERSION:-v26.11.9}"
REALITY_DEST="${REALITY_DEST:-www.microsoft.com:443}"
REALITY_SNI="${REALITY_SNI:-www.microsoft.com}"
SS_PORT="${SS_PORT:-8388}"
VMESS_PORT="${VMESS_PORT:-8080}"
CONF_DIR=/usr/local/etc/xray
OUT_DIR=/etc/zippy-xray

if [[ "$(id -u)" -ne 0 ]]; then
  echo "❌ root gerek.  sudo -E bash deploy/install-xray.sh" >&2
  exit 1
fi

echo "==> [1/6]paketler + Xray-core ${XRAY_VERSION} (github.com/XTLS/Xray-install)..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl unzip ca-certificates openssl
curl -fsSL https://raw.githubusercontent.com/XTLS/Xray-install/main/install-release.sh \
    -o /tmp/xray-install.sh
bash /tmp/xray-install.sh install --version "$XRAY_VERSION"
XRAY=/usr/local/bin/xray
[[ -x "$XRAY" ]] || { echo "❌ xray gurnalmandy" >&2; exit 1; }

echo "==> [2/6]açarlar we UUID..."
KEYS="$($XRAY x25519)"
PRIVATE="$(printf '%s\n' "$KEYS" | sed -n 's/^PrivateKey: //p')"
PUBLIC="$(printf '%s\n' "$KEYS" | sed -n 's/^Password (PublicKey): //p')"
if [[ -z "$PRIVATE" || -z "$PUBLIC" ]]; then
  echo "❌ x25519 açary alynmandy: $KEYS" >&2
  exit 1
fi
UUID="$($XRAY uuid)"
SID="$(openssl rand -hex 6)"                      # 12 hex = 6 baýt shortId
WS_PATH="/$(openssl rand -hex 8)"
SS_PASS="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | cut -c1-24)"

HOST="${ZIPPY_HOST:-}"
[[ -z "$HOST" ]] && HOST="$(curl -fsS --max-time 10 https://api.ipify.org 2>/dev/null || true)"
[[ -z "$HOST" ]] && HOST="$(hostname -I 2>/dev/null | awk '{print $1}')"
[[ -z "$HOST" ]] && { echo "❌ ZIPPY_HOST beriň" >&2; exit 1; }
echo "    host = $HOST   reality dest = $REALITY_DEST ($REALITY_SNI)"

echo "==> [3/6]Xray konfigurasiýasy + linkler..."
mkdir -p "$CONF_DIR" "$OUT_DIR"
python3 - "$HOST" "$UUID" "$PRIVATE" "$PUBLIC" "$SID" "$WS_PATH" \
        "$SS_PASS" "$SS_PORT" "$VMESS_PORT" "$REALITY_DEST" "$REALITY_SNI" <<'PY'
import base64, json, sys, urllib.parse

(host, uid, priv, pub, sid, ws_path, ss_pass, ss_port, vmess_port,
 dest, sni) = sys.argv[1:]
ss_port, vmess_port = int(ss_port), int(vmess_port)

cfg = {
  "log": {"loglevel": "warning"},
  "inbounds": [
    {
      "tag": "vless-reality", "listen": "0.0.0.0", "port": 443,
      "protocol": "vless",
      "settings": {
        "clients": [{"id": uid, "flow": "xtls-rprx-vision"}],
        "decryption": "none",
      },
      "streamSettings": {
        "network": "tcp", "security": "reality",
        "realitySettings": {
          "show": False, "dest": dest, "xver": 0,
          "serverNames": [sni], "privateKey": priv,
          "shortIds": [sid], "maxTimeDiff": 0,
        },
      },
      "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
    },
    {
      "tag": "vmess-ws", "listen": "0.0.0.0", "port": vmess_port,
      "protocol": "vmess",
      "settings": {"clients": [{"id": uid, "alterId": 0}]},
      "streamSettings": {
        "network": "ws",
        "wsSettings": {"path": ws_path, "headers": {"Host": host}},
      },
    },
    {
      "tag": "shadowsocks", "listen": "0.0.0.0", "port": ss_port,
      "protocol": "shadowsocks",
      "settings": {"method": "aes-256-gcm", "password": ss_pass,
                   "network": "tcp,udp"},
    },
  ],
  "outbounds": [
    {"protocol": "freedom", "tag": "direct"},
    {"protocol": "blackhole", "tag": "blocked"},
  ],
  "routing": {
    "domainStrategy": "IPIfNonMatch",
    "rules": [{"type": "field", "ip": ["geoip:private"], "outboundTag": "blocked"}],
  },
}
with open("/usr/local/etc/xray/config.json", "w") as f:
    json.dump(cfg, f, indent=2)

q = urllib.parse.urlencode({
    "encryption": "none", "security": "reality", "type": "tcp",
    "flow": "xtls-rprx-vision", "sni": sni, "fp": "chrome",
    "pbk": pub, "sid": sid,
})
vless = f"vless://{uid}@{host}:443?{q}#Zippy-Reality"

vmess_obj = {
    "v": "2", "ps": "Zippy-VMess", "add": host, "port": str(vmess_port),
    "id": uid, "aid": "0", "net": "ws", "type": "none", "host": host,
    "path": ws_path, "tls": "", "scy": "auto",
}
vmess = "vmess://" + base64.b64encode(
    json.dumps(vmess_obj, separators=(",", ":")).encode()).decode()

ss_user = base64.urlsafe_b64encode(f"aes-256-gcm:{ss_pass}".encode()).decode().rstrip("=")
ss = f"ss://{ss_user}@{host}:{ss_port}#Zippy-SS"

links = [vless, vmess, ss]
with open("/etc/zippy-xray/links.txt", "w") as f:
    f.write("\n".join(links) + "\n")
with open("/etc/zippy-xray/subscription.txt", "w") as f:
    f.write(base64.b64encode(("\n".join(links) + "\n").encode()).decode() + "\n")
with open("/etc/zippy-xray/credentials.json", "w") as f:
    json.dump({"host": host, "uuid": uid, "reality_private_key": priv,
               "reality_public_key": pub, "short_id": sid,
               "ws_path": ws_path, "ss_password": ss_pass}, f, indent=2)
PY
chmod 600 "$OUT_DIR/credentials.json"

echo "==> [4/6]konfigurasiýa barlanýar..."
$XRAY run -test -config "$CONF_DIR/config.json" || {
  echo "❌ Xray konfigy ýalňyş — $CONF_DIR/config.json barlaň" >&2
  exit 1
}

echo "==> [5/6]hyzmat + firewall..."
systemctl enable --now xray
systemctl restart xray
if command -v ufw >/dev/null 2>&1; then
  ufw allow 443/tcp >/dev/null || true
  ufw allow "${VMESS_PORT}/tcp" >/dev/null || true
  ufw allow "${SS_PORT}/tcp" >/dev/null || true
  ufw allow "${SS_PORT}/udp" >/dev/null || true
fi

echo "==> [6/6]taýýar"
echo
echo "================== TAÝÝAR =================="
echo "  Bulut firewall-ynda 443/tcp, ${VMESS_PORT}/tcp, ${SS_PORT}/tcp+udp açyň."
echo "  REALITY dest: ${REALITY_DEST}  (VPS-den elýeterli bolmaly; üýtgetmek üçin REALITY_DEST=...)"
echo
echo "  Linkler:"
sed 's/^/    /' "$OUT_DIR/links.txt"
echo
echo "  Abuna (v2rayNG/Hiddify): $OUT_DIR/subscription.txt"
echo "  Gizlin açarlar:          $OUT_DIR/credentials.json"
echo "==========================================="
