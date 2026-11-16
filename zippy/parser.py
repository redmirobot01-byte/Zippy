"""Strict URI parser, security validator, deduplicator, scorer, and serializer."""

from __future__ import annotations

import base64
import ipaddress
import json
import re
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

from .models import ProxyNode, detect_country

SUPPORTED_SCHEMES = ("vless://", "trojan://", "vmess://", "ss://", "hysteria2://", "hy2://")

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_NIL_UUID = "00000000-0000-0000-0000-000000000000"
_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TLD_RE = re.compile(r"^[a-z]{2,24}$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]*$")
_PBK_RE = re.compile(r"^[A-Za-z0-9_-]{42,44}$")

_BLOCKED_TLDS = frozenset({
    "local", "localhost", "invalid", "test", "example", "internal",
    "lan", "home", "corp", "onion", "arpa", "rkn", "intranet",
})
_BLOCKED_HOSTS = frozenset({
    "localhost", "example.com", "www.example.com", "google.com", "www.google.com",
    "telegram.org", "t.me", "github.com", "raw.githubusercontent.com",
    "1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4", "9.9.9.9", "149.112.112.112",
    "208.67.222.222", "208.67.220.220",
})
_BLOCKED_SNI_SUBSTRINGS = ("fuck", "porn", "xxx", "127.0.0.1", "localhost")
_BLOCKED_PORTS = frozenset({0, 7, 9, 19, 21, 22, 23, 25, 53, 110, 135, 139, 143, 445, 3389})
_PREFERRED_PORTS = frozenset({443, 8443, 2053, 2083, 2087, 2096})
_CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")

_SPAM_REMARK_RE = re.compile(
    r"(?:expired|traffic\s*[:=]|remaining\s*[:=]|0\s*(?:gb|mb)\s*left|update\s+sub)",
    re.IGNORECASE,
)

_VALID_FPS = frozenset({
    "chrome", "firefox", "safari", "ios", "android", "edge", "360", "qq", "random", "randomized",
})
_SS_CLASSICAL_AEAD = frozenset({
    "aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305", "xchacha20-ietf-poly1305",
})
_SS_2022_KEY_BYTES: dict[str, int] = {
    "2022-blake3-aes-128-gcm": 16,
    "2022-blake3-aes-256-gcm": 32,
    "2022-blake3-chacha20-poly1305": 32,
}


def safe_b64decode(data: str) -> bytes | None:
    """Decode standard or URL-safe Base64 with tolerant padding."""
    cleaned = "".join(data.strip().split())
    if not cleaned:
        return None
    normalized = cleaned.replace("-", "+").replace("_", "/")
    rem = len(normalized) % 4
    if rem == 1:
        return None
    if rem:
        normalized += "=" * (4 - rem)
    try:
        return base64.b64decode(normalized, validate=True)
    except Exception:
        return None


def decode_subscription_text(raw_text: str) -> list[str]:
    """Extract raw proxy URI lines from plain or Base64-encoded subscription content."""
    if not raw_text:
        return []
    text = raw_text.lstrip("\ufeff").strip()
    if not text:
        return []

    has_direct_scheme = any(scheme in text for scheme in SUPPORTED_SCHEMES)
    if not has_direct_scheme:
        decoded = safe_b64decode(text)
        if decoded:
            text = decoded.decode("utf-8", errors="ignore")

    uris: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if "&amp;" in line:
            line = line.replace("&amp;", "&")
        lower = line.lower()
        if lower.startswith(SUPPORTED_SCHEMES):
            if len(line) <= 4096:
                uris.append(line)
    return uris


def is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def validate_host(host: str) -> str | None:
    """Return canonical public host/IP, or None if private, reserved, or malformed."""
    if not host:
        return None
    cleaned = host.strip().strip("[]").rstrip(".").lower()
    if not cleaned or len(cleaned) > 253 or cleaned in _BLOCKED_HOSTS:
        return None
    if any(ch.isspace() or ord(ch) < 33 for ch in cleaned):
        return None

    # Check IPv4 / IPv6
    try:
        addr = ipaddress.ip_address(cleaned)
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        ):
            return None
        if isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT_NET:
            return None
        canonical = addr.compressed
        if canonical in _BLOCKED_HOSTS:
            return None
        return canonical
    except ValueError:
        pass

    # Check domain name
    try:
        ascii_host = cleaned.encode("idna").decode("ascii")
    except Exception:
        return None
    if len(ascii_host) > 253 or "." not in ascii_host:
        return None
    labels = ascii_host.split(".")
    if len(labels) < 2:
        return None
    tld = labels[-1]
    if not _TLD_RE.match(tld) or tld in _BLOCKED_TLDS:
        return None
    for label in labels:
        if not _LABEL_RE.match(label):
            return None
    return ascii_host


def validate_sni(sni: str) -> str | None:
    """Validate TLS/Reality Server Name Indication (must be a legitimate FQDN)."""
    if not sni:
        return None
    cleaned = sni.strip().rstrip(".").lower()
    if "," in cleaned:
        cleaned = cleaned.split(",", 1)[0].strip()
    if not cleaned or len(cleaned) > 253 or is_ip_address(cleaned):
        return None
    if any(bad in cleaned for bad in _BLOCKED_SNI_SUBSTRINGS):
        return None
    try:
        ascii_sni = cleaned.encode("idna").decode("ascii")
    except Exception:
        return None
    labels = ascii_sni.split(".")
    if len(labels) < 2:
        return None
    tld = labels[-1]
    if not _TLD_RE.match(tld) or tld in _BLOCKED_TLDS:
        return None
    for label in labels:
        if not _LABEL_RE.match(label):
            return None
    return ascii_sni


def validate_port(port_val: int | str | None) -> int | None:
    if port_val is None:
        return None
    try:
        port = int(str(port_val).strip())
    except ValueError:
        return None
    if port < 1 or port > 65535 or port in _BLOCKED_PORTS:
        return None
    return port


def validate_reality_pbk(pbk: str) -> str | None:
    cleaned = (pbk or "").strip()
    if not _PBK_RE.match(cleaned):
        return None
    raw = safe_b64decode(cleaned)
    if raw is None or len(raw) != 32:
        return None
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _first_param(params: dict[str, list[str]], *names: str) -> str:
    for name in names:
        vals = params.get(name)
        if vals and vals[0]:
            return vals[0].strip()
    return ""


def _is_truthy(val: str) -> bool:
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _clean_path(path: str) -> str | None:
    if not path:
        return "/"
    cleaned = path.strip()
    # Reject double-encoded paths like %252F which fail on Xray servers
    if "%252f" in cleaned.lower():
        return None
    if cleaned.lower().startswith("%2f"):
        cleaned = unquote(cleaned)
    if any(ord(c) < 32 or c in "\r\n" for c in cleaned):
        return None
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    if len(cleaned) > 512:
        return None
    return cleaned


def _normalize_fp(fp: str) -> str:
    low = (fp or "").strip().lower()
    return low if low in _VALID_FPS else "chrome"


def _normalize_transport(net: str) -> str | None:
    low = (net or "tcp").strip().lower()
    mapping = {
        "": "tcp",
        "tcp": "tcp",
        "raw": "tcp",
        "ws": "ws",
        "websocket": "ws",
        "grpc": "grpc",
        "gun": "grpc",
        "xhttp": "xhttp",
        "splithttp": "xhttp",
        "httpupgrade": "httpupgrade",
        "h2": "h2",
        "http": "h2",
    }
    return mapping.get(low)


def _normalize_alpn(alpn: str) -> str:
    if not alpn:
        return ""
    allowed = {"h3", "h2", "http/1.1"}
    tokens = [t.strip() for t in unquote(alpn).split(",") if t.strip() in allowed]
    return ",".join(dict.fromkeys(tokens))


def _format_uri_host(host: str) -> str:
    return f"[{host}]" if ":" in host else host


def _split_authority(netloc: str) -> tuple[str, str, int] | None:
    """Split userinfo@host:port safely including IPv6 and special password characters."""
    if "@" not in netloc:
        return None
    userinfo, hostport = netloc.rsplit("@", 1)
    if not userinfo or not hostport:
        return None

    if hostport.startswith("["):
        end = hostport.find("]")
        if end == -1:
            return None
        raw_host = hostport[1:end]
        rest = hostport[end + 1:]
        if not rest.startswith(":"):
            return None
        raw_port = rest[1:]
    else:
        if ":" not in hostport:
            return None
        raw_host, raw_port = hostport.rsplit(":", 1)

    host = validate_host(raw_host)
    port = validate_port(raw_port)
    if not host or not port:
        return None
    return userinfo, host, port


def parse_vless(uri: str, source: str = "", weight: int = 80) -> ProxyNode | None:
    try:
        parts = urlsplit(uri)
    except Exception:
        return None
    auth = _split_authority(parts.netloc)
    if not auth:
        return None
    raw_uuid, host, port = auth
    uuid = unquote(raw_uuid).strip().lower()
    if not _UUID_RE.match(uuid) or uuid == _NIL_UUID:
        return None

    remark = unquote(parts.fragment or "").strip()
    if remark and _SPAM_REMARK_RE.search(remark):
        return None

    params = parse_qs(parts.query, keep_blank_values=False)
    if _is_truthy(_first_param(params, "allowInsecure", "insecure")):
        return None

    encryption = _first_param(params, "encryption").lower()
    if encryption and encryption != "none":
        # Skip non-standard post-quantum/custom experimental encryption strings if malformed
        return None

    transport = _normalize_transport(_first_param(params, "type", "net"))
    if not transport:
        return None

    # Ignore obsolete TCP HTTP header obfuscation (only allow none)
    header_type = _first_param(params, "headerType").lower()
    if transport == "tcp" and header_type and header_type != "none":
        return None

    security = _first_param(params, "security").lower()
    if security not in {"reality", "tls"}:
        return None

    raw_sni = _first_param(params, "sni", "serverName", "peer")
    raw_host_hdr = _first_param(params, "host")
    host_header = validate_sni(raw_host_hdr) or ""

    pbk = ""
    sid = ""
    spx = ""
    if security == "reality":
        valid_pbk = validate_reality_pbk(_first_param(params, "pbk", "publicKey"))
        valid_sni = validate_sni(raw_sni)
        if not valid_pbk or not valid_sni:
            return None
        pbk = valid_pbk
        sni = valid_sni
        raw_sid = _first_param(params, "sid", "shortId").lower()
        if len(raw_sid) > 16 or len(raw_sid) % 2 != 0 or not _HEX_RE.match(raw_sid):
            return None
        sid = raw_sid
        raw_spx = _first_param(params, "spx", "spiderX")
        if raw_spx:
            cleaned_spx = _clean_path(raw_spx)
            spx = cleaned_spx if cleaned_spx else ""
    else:
        fallback_sni = raw_sni or raw_host_hdr or ("" if is_ip_address(host) else host)
        valid_sni = validate_sni(fallback_sni)
        if not valid_sni:
            return None
        sni = valid_sni

    flow = _first_param(params, "flow").lower()
    if flow:
        if flow != "xtls-rprx-vision" or transport != "tcp":
            return None

    path = ""
    service_name = ""
    mode = ""
    if transport in {"ws", "httpupgrade", "xhttp", "h2"}:
        cleaned_path = _clean_path(_first_param(params, "path"))
        if cleaned_path is None:
            return None
        path = cleaned_path
        if not host_header and security == "tls":
            host_header = sni
        if transport == "xhttp":
            raw_mode = _first_param(params, "mode").lower()
            mode = raw_mode if raw_mode in {"auto", "packet-up", "stream-up", "stream-one"} else "auto"
    elif transport == "grpc":
        svc = _first_param(params, "serviceName", "path").lstrip("/")
        if len(svc) > 128 or any(ord(c) < 32 or c.isspace() for c in svc):
            return None
        service_name = svc
        raw_mode = _first_param(params, "mode").lower()
        mode = "multi" if raw_mode == "multi" else "gun"

    return ProxyNode(
        protocol="vless",
        host=host,
        port=port,
        credential=uuid,
        transport=transport,
        security=security,
        sni=sni,
        host_header=host_header,
        path=path,
        service_name=service_name,
        alpn=_normalize_alpn(_first_param(params, "alpn")),
        fp=_normalize_fp(_first_param(params, "fp", "fingerprint")),
        flow=flow,
        pbk=pbk,
        sid=sid,
        spx=spx,
        mode=mode,
        country=detect_country(remark, host),
        source=source,
        source_weight=weight,
    )


def parse_trojan(uri: str, source: str = "", weight: int = 80) -> ProxyNode | None:
    try:
        parts = urlsplit(uri)
    except Exception:
        return None
    auth = _split_authority(parts.netloc)
    if not auth:
        return None
    raw_pw, host, port = auth
    password = unquote(raw_pw).strip()
    if not password or len(password) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in password):
        return None

    remark = unquote(parts.fragment or "").strip()
    if remark and _SPAM_REMARK_RE.search(remark):
        return None

    params = parse_qs(parts.query, keep_blank_values=False)
    if _is_truthy(_first_param(params, "allowInsecure", "insecure")):
        return None

    # Reject non-standard certificate pinning parameters that old Xray clients skip
    transport = _normalize_transport(_first_param(params, "type", "net"))
    if not transport or transport == "xhttp":
        return None

    security = (_first_param(params, "security") or "tls").lower()
    if security not in {"tls", "reality"}:
        return None

    raw_sni = _first_param(params, "sni", "peer", "serverName")
    raw_host_hdr = _first_param(params, "host")
    host_header = validate_sni(raw_host_hdr) or ""

    pbk = ""
    sid = ""
    if security == "reality":
        valid_pbk = validate_reality_pbk(_first_param(params, "pbk", "publicKey"))
        valid_sni = validate_sni(raw_sni)
        if not valid_pbk or not valid_sni:
            return None
        pbk = valid_pbk
        sni = valid_sni
        raw_sid = _first_param(params, "sid", "shortId").lower()
        if len(raw_sid) > 16 or len(raw_sid) % 2 != 0 or not _HEX_RE.match(raw_sid):
            return None
        sid = raw_sid
    else:
        fallback_sni = raw_sni or raw_host_hdr or ("" if is_ip_address(host) else host)
        valid_sni = validate_sni(fallback_sni)
        if not valid_sni:
            return None
        sni = valid_sni

    path = ""
    service_name = ""
    mode = ""
    if transport in {"ws", "httpupgrade", "h2"}:
        cleaned_path = _clean_path(_first_param(params, "path"))
        if cleaned_path is None:
            return None
        path = cleaned_path
        if not host_header and security == "tls":
            host_header = sni
    elif transport == "grpc":
        svc = _first_param(params, "serviceName", "path").lstrip("/")
        if len(svc) > 128 or any(ord(c) < 32 or c.isspace() for c in svc):
            return None
        service_name = svc
        mode = "multi" if _first_param(params, "mode").lower() == "multi" else "gun"

    return ProxyNode(
        protocol="trojan",
        host=host,
        port=port,
        credential=password,
        transport=transport,
        security=security,
        sni=sni,
        host_header=host_header,
        path=path,
        service_name=service_name,
        alpn=_normalize_alpn(_first_param(params, "alpn")),
        fp=_normalize_fp(_first_param(params, "fp", "fingerprint")),
        pbk=pbk,
        sid=sid,
        mode=mode,
        country=detect_country(remark, host),
        source=source,
        source_weight=weight,
    )


def parse_vmess(uri: str, source: str = "", weight: int = 80) -> ProxyNode | None:
    payload_b64 = uri[len("vmess://"):].strip()
    if "#" in payload_b64:
        payload_b64 = payload_b64.split("#", 1)[0]
    decoded = safe_b64decode(payload_b64)
    if not decoded or len(decoded) > 8192:
        return None
    try:
        obj = json.loads(decoded.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None

    uuid = str(obj.get("id") or "").strip().lower()
    if not _UUID_RE.match(uuid) or uuid == _NIL_UUID:
        return None

    try:
        aid = int(str(obj.get("aid") or "0").strip())
    except ValueError:
        return None
    if aid != 0:
        return None

    host = validate_host(str(obj.get("add") or ""))
    port = validate_port(obj.get("port"))
    if not host or not port:
        return None

    remark = str(obj.get("ps") or obj.get("name") or "").strip()
    if remark and _SPAM_REMARK_RE.search(remark):
        return None

    # Require authenticated TLS on VMess for security and DPI resistance
    tls = str(obj.get("tls") or "").strip().lower()
    if tls != "tls":
        return None
    if _is_truthy(str(obj.get("allowInsecure") or "")) or _is_truthy(str(obj.get("insecure") or "")):
        return None

    transport = _normalize_transport(str(obj.get("net") or "tcp"))
    if not transport or transport == "xhttp":
        return None

    hdr_type = str(obj.get("type") or "none").strip().lower()
    if transport == "tcp" and hdr_type and hdr_type != "none":
        return None

    raw_host_hdr = str(obj.get("host") or "").strip()
    raw_sni = str(obj.get("sni") or "").strip()
    host_header = validate_sni(raw_host_hdr) or ""
    sni = validate_sni(raw_sni or raw_host_hdr or ("" if is_ip_address(host) else host))
    if not sni:
        return None

    scy = str(obj.get("scy") or "auto").strip().lower()
    if scy not in {"auto", "aes-128-gcm", "chacha20-poly1305", "zero"}:
        scy = "auto"

    path = ""
    service_name = ""
    mode = ""
    raw_path = str(obj.get("path") or "").strip()
    if transport in {"ws", "httpupgrade", "h2"}:
        cleaned_path = _clean_path(raw_path)
        if cleaned_path is None:
            return None
        path = cleaned_path
        if not host_header:
            host_header = sni
    elif transport == "grpc":
        svc = raw_path.lstrip("/")
        if len(svc) > 128 or any(ord(c) < 32 or c.isspace() for c in svc):
            return None
        service_name = svc
        mode = "gun"

    return ProxyNode(
        protocol="vmess",
        host=host,
        port=port,
        credential=uuid,
        method=scy,
        transport=transport,
        security="tls",
        sni=sni,
        host_header=host_header,
        path=path,
        service_name=service_name,
        alpn=_normalize_alpn(str(obj.get("alpn") or "")),
        fp=_normalize_fp(str(obj.get("fp") or "")),
        mode=mode,
        country=detect_country(remark, host),
        source=source,
        source_weight=weight,
    )


def _validate_ss_method_and_password(method: str, password: str) -> tuple[str, str] | None:
    m = method.strip().lower()
    pw = password.strip()
    if not pw or len(pw) > 256 or any(ord(c) < 32 or c in "\r\n" for c in pw):
        return None
    if m in _SS_CLASSICAL_AEAD:
        if len(pw) < 6:
            return None
        return m, pw
    if m in _SS_2022_KEY_BYTES:
        expected = _SS_2022_KEY_BYTES[m]
        parts = pw.split(":")
        if len(parts) > 3:
            return None
        for key_part in parts:
            raw = safe_b64decode(key_part)
            if raw is None or len(raw) != expected:
                return None
        return m, pw
    return None


def parse_ss(uri: str, source: str = "", weight: int = 80) -> ProxyNode | None:
    body = uri[len("ss://"):].strip()
    remark = ""
    if "#" in body:
        body, raw_remark = body.split("#", 1)
        remark = unquote(raw_remark).strip()
        if remark and _SPAM_REMARK_RE.search(remark):
            return None

    query = ""
    if "?" in body:
        body, query = body.split("?", 1)
        params = parse_qs(query, keep_blank_values=False)
        # Skip SIP003 external plugins (not bundled in Happ Android)
        if params.get("plugin"):
            return None

    body = body.rstrip("/")
    if "@" not in body:
        decoded = safe_b64decode(body)
        if not decoded:
            return None
        try:
            body = decoded.decode("utf-8")
        except Exception:
            return None

    auth = _split_authority(body)
    if not auth:
        return None
    userinfo, host, port = auth
    userinfo_unq = unquote(userinfo)

    if ":" in userinfo_unq and userinfo_unq.split(":", 1)[0].lower() in (
        _SS_CLASSICAL_AEAD | set(_SS_2022_KEY_BYTES)
    ):
        raw_method, raw_pw = userinfo_unq.split(":", 1)
    else:
        decoded_user = safe_b64decode(userinfo_unq)
        if not decoded_user:
            return None
        try:
            decoded_str = decoded_user.decode("utf-8")
        except Exception:
            return None
        if ":" not in decoded_str:
            return None
        raw_method, raw_pw = decoded_str.split(":", 1)

    validated = _validate_ss_method_and_password(raw_method, raw_pw)
    if not validated:
        return None
    method, password = validated

    return ProxyNode(
        protocol="ss",
        host=host,
        port=port,
        credential=password,
        method=method,
        transport="tcp",
        security="aead",
        country=detect_country(remark, host),
        source=source,
        source_weight=weight,
    )


def parse_hy2(uri: str, source: str = "", weight: int = 80) -> ProxyNode | None:
    normalized = "hysteria2://" + uri.split("://", 1)[1]
    try:
        parts = urlsplit(normalized)
    except Exception:
        return None
    auth = _split_authority(parts.netloc)
    if not auth:
        return None
    raw_pw, host, port = auth
    password = unquote(raw_pw).strip()
    if not password or len(password) > 256 or any(ord(c) < 33 or c.isspace() for c in password):
        return None

    remark = unquote(parts.fragment or "").strip()
    if remark and _SPAM_REMARK_RE.search(remark):
        return None

    params = parse_qs(parts.query, keep_blank_values=False)
    # Skip multi-port hopping specs that may not parse uniformly across clients
    if _first_param(params, "mport"):
        return None

    raw_pin = _first_param(params, "pinSHA256").replace(":", "").lower()
    pin_sha256 = raw_pin if (len(raw_pin) == 64 and _HEX_RE.match(raw_pin)) else ""

    insecure = _is_truthy(_first_param(params, "insecure", "allowInsecure"))
    if insecure and not pin_sha256:
        return None

    raw_sni = _first_param(params, "sni", "peer") or ("" if is_ip_address(host) else host)
    sni = validate_sni(raw_sni) or ""
    if not sni and not pin_sha256:
        return None

    obfs = _first_param(params, "obfs").lower()
    obfs_pw = _first_param(params, "obfs-password")
    if obfs:
        if obfs != "salamander" or not obfs_pw or len(obfs_pw) > 128:
            return None
    else:
        obfs_pw = ""

    alpn = _normalize_alpn(_first_param(params, "alpn")) or "h3"

    return ProxyNode(
        protocol="hy2",
        host=host,
        port=port,
        credential=password,
        transport="quic",
        security="tls",
        sni=sni,
        alpn=alpn,
        obfs=obfs,
        obfs_password=obfs_pw,
        pin_sha256=pin_sha256,
        country=detect_country(remark, host),
        source=source,
        source_weight=weight,
    )


def parse_uri(uri: str, source: str = "", weight: int = 80) -> ProxyNode | None:
    """Parse and validate a single proxy URI; returns None if unsafe or malformed."""
    line = (uri or "").strip()
    low = line.lower()
    if low.startswith("vless://"):
        return parse_vless(line, source=source, weight=weight)
    if low.startswith("trojan://"):
        return parse_trojan(line, source=source, weight=weight)
    if low.startswith("vmess://"):
        return parse_vmess(line, source=source, weight=weight)
    if low.startswith("ss://"):
        return parse_ss(line, source=source, weight=weight)
    if low.startswith(("hysteria2://", "hy2://")):
        return parse_hy2(line, source=source, weight=weight)
    return None


def serialize_uri(node: ProxyNode, label: str) -> str:
    """Serialize a validated ProxyNode into a clean Happ-compatible URI."""
    encoded_label = quote(label, safe="")
    host_str = _format_uri_host(node.host)

    if node.protocol == "vless":
        q: dict[str, str] = {
            "encryption": "none",
            "security": node.security,
            "type": node.transport,
        }
        if node.sni:
            q["sni"] = node.sni
        if node.fp:
            q["fp"] = node.fp
        if node.security == "reality":
            q["pbk"] = node.pbk
            if node.sid:
                q["sid"] = node.sid
            if node.spx:
                q["spx"] = node.spx
        if node.flow and node.transport == "tcp":
            q["flow"] = node.flow
        if node.transport in {"ws", "httpupgrade", "xhttp", "h2"}:
            q["path"] = node.path or "/"
            if node.host_header:
                q["host"] = node.host_header
            if node.transport == "xhttp" and node.mode:
                q["mode"] = node.mode
        elif node.transport == "grpc":
            if node.service_name:
                q["serviceName"] = node.service_name
            q["mode"] = node.mode or "gun"
        if node.alpn and node.security == "tls":
            q["alpn"] = node.alpn
        return f"vless://{node.credential}@{host_str}:{node.port}?{urlencode(q)}#{encoded_label}"

    if node.protocol == "trojan":
        q = {
            "security": node.security,
            "type": node.transport,
        }
        if node.sni:
            q["sni"] = node.sni
        if node.fp:
            q["fp"] = node.fp
        if node.security == "reality":
            q["pbk"] = node.pbk
            if node.sid:
                q["sid"] = node.sid
        if node.transport in {"ws", "httpupgrade", "h2"}:
            q["path"] = node.path or "/"
            if node.host_header:
                q["host"] = node.host_header
        elif node.transport == "grpc":
            if node.service_name:
                q["serviceName"] = node.service_name
            q["mode"] = node.mode or "gun"
        if node.alpn and node.security == "tls":
            q["alpn"] = node.alpn
        pw_enc = quote(node.credential, safe="")
        return f"trojan://{pw_enc}@{host_str}:{node.port}?{urlencode(q)}#{encoded_label}"

    if node.protocol == "vmess":
        vmess_obj: dict[str, str | int] = {
            "v": "2",
            "ps": label,
            "add": node.host,
            "port": node.port,
            "id": node.credential,
            "aid": 0,
            "scy": node.method or "auto",
            "net": node.transport,
            "type": "none",
            "host": node.host_header or node.sni,
            "path": node.service_name if node.transport == "grpc" else (node.path or "/"),
            "tls": "tls",
            "sni": node.sni,
            "fp": node.fp or "chrome",
        }
        if node.alpn:
            vmess_obj["alpn"] = node.alpn
        raw_json = json.dumps(vmess_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return "vmess://" + base64.b64encode(raw_json).decode("ascii")

    if node.protocol == "ss":
        userinfo_raw = f"{node.method}:{node.credential}".encode("utf-8")
        userinfo_b64 = base64.urlsafe_b64encode(userinfo_raw).decode("ascii").rstrip("=")
        return f"ss://{userinfo_b64}@{host_str}:{node.port}#{encoded_label}"

    if node.protocol == "hy2":
        q = {"insecure": "0"}
        if node.sni:
            q["sni"] = node.sni
        if node.alpn:
            q["alpn"] = node.alpn
        if node.obfs == "salamander" and node.obfs_password:
            q["obfs"] = "salamander"
            q["obfs-password"] = node.obfs_password
        if node.pin_sha256:
            q["pinSHA256"] = node.pin_sha256
        pw_enc = quote(node.credential, safe="")
        return f"hysteria2://{pw_enc}@{host_str}:{node.port}?{urlencode(q)}#{encoded_label}"

    raise ValueError(f"Unsupported protocol: {node.protocol}")


def compute_score(node: ProxyNode, preferred_countries: list[str] | None = None) -> float:
    """Score a node by verification status, latency, anti-DPI strength, and location."""
    score = float(node.source_weight)

    # Anti-DPI protocol bonus (tuned for Happ Android on restricted networks)
    if node.protocol == "vless" and node.is_reality:
        score += 42.0
        if node.flow == "xtls-rprx-vision":
            score += 6.0
        if node.transport == "xhttp":
            score += 5.0
    elif node.protocol == "vless" and node.security == "tls":
        score += 30.0
        if node.transport in {"ws", "grpc", "xhttp", "httpupgrade"}:
            score += 5.0
    elif node.protocol == "hy2":
        score += 32.0
        if node.obfs == "salamander":
            score += 4.0
    elif node.protocol == "trojan":
        score += 34.0 if node.is_reality else 26.0
    elif node.protocol == "ss":
        score += 24.0 if node.method.startswith("2022-") else 18.0
    elif node.protocol == "vmess":
        score += 20.0

    # Standard HTTPS port bonus (rarely blocked by carrier firewalls)
    if node.port == 443:
        score += 10.0
    elif node.port in _PREFERRED_PORTS:
        score += 6.0

    # Country routing proximity bonus (Europe/Turkey lowest RTT for Central Asia & EU)
    if preferred_countries and node.country in preferred_countries:
        idx = preferred_countries.index(node.country)
        score += max(2.0, 14.0 - idx * 0.5)

    # Live verification bonus & real latency reward
    if node.check_method == "xray" and node.latency_ms is not None:
        score += 200.0 + max(0.0, 120.0 - node.latency_ms / 12.0)
    elif node.check_method == "tls" and node.latency_ms is not None:
        score += 110.0 + max(0.0, 80.0 - node.latency_ms / 10.0)
    elif node.check_method == "tcp" and node.latency_ms is not None:
        score += 70.0 + max(0.0, 60.0 - node.latency_ms / 10.0)

    node.score = round(score, 2)
    return node.score


def deduplicate_and_rank(
    nodes: list[ProxyNode],
    preferred_countries: list[str] | None = None,
    max_per_host: int = 2,
) -> list[ProxyNode]:
    """Deduplicate identical endpoints, score, sort best-first, and cap clones per host."""
    best_by_key: dict[str, ProxyNode] = {}
    for node in nodes:
        compute_score(node, preferred_countries)
        key = node.dedup_key()
        existing = best_by_key.get(key)
        if existing is None or node.score > existing.score:
            if existing is not None and node.country == "UN" and existing.country != "UN":
                node.country = existing.country
            best_by_key[key] = node

    ranked = sorted(best_by_key.values(), key=lambda n: n.score, reverse=True)
    if max_per_host <= 0:
        return ranked

    host_counts: dict[str, int] = {}
    cred_counts: dict[str, int] = {}
    max_per_cred = max(2, max_per_host)
    diverse: list[ProxyNode] = []
    for node in ranked:
        if node.source == "Custom":
            diverse.append(node)
            continue
        h_bucket = node.host_bucket_key()
        c_bucket = node.credential_bucket_key()
        h_cnt = host_counts.get(h_bucket, 0)
        c_cnt = cred_counts.get(c_bucket, 0)
        if h_cnt >= max_per_host or c_cnt >= max_per_cred:
            continue
        host_counts[h_bucket] = h_cnt + 1
        cred_counts[c_bucket] = c_cnt + 1
        diverse.append(node)
    return diverse
