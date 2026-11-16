"""Data models, country metadata, and formatting helpers for Zippy VPN."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import ipaddress
import re

VALID_COUNTRY_CODES: frozenset[str] = frozenset({
    "AD", "AE", "AF", "AL", "AM", "AR", "AT", "AU", "AZ", "BA", "BD", "BE",
    "BG", "BH", "BR", "BY", "CA", "CH", "CL", "CN", "CO", "CY", "CZ", "DE",
    "DK", "EE", "EG", "ES", "EU", "FI", "FR", "GB", "GE", "GR", "HK", "HR",
    "HU", "ID", "IE", "IL", "IN", "IQ", "IR", "IS", "IT", "JP", "KE", "KG",
    "KR", "KW", "KZ", "LT", "LU", "LV", "MD", "ME", "MK", "MN", "MX", "MY",
    "NG", "NL", "NO", "NZ", "OM", "PA", "PE", "PH", "PK", "PL", "PT", "QA",
    "RO", "RS", "RU", "SA", "SE", "SG", "SI", "SK", "TH", "TJ", "TM", "TR",
    "TW", "UA", "US", "UZ", "VN", "ZA",
})

COUNTRY_NAMES_TK: dict[str, str] = {
    "DE": "Germaniýa",
    "NL": "Niderlandlar",
    "FI": "Finlýandiýa",
    "SE": "Şwesiýa",
    "AT": "Awstriýa",
    "CH": "Şweýsariýa",
    "PL": "Polşa",
    "FR": "Fransiýa",
    "GB": "Beýik Britaniýa",
    "TR": "Türkiýe",
    "EE": "Estoniýa",
    "LV": "Latwiýa",
    "LT": "Litwa",
    "CZ": "Çehiýa",
    "RO": "Rumyniýa",
    "BG": "Bolgariýa",
    "NO": "Norwegiýa",
    "DK": "Daniýa",
    "IE": "Irlandiýa",
    "IT": "Italiýa",
    "ES": "Ispaniýa",
    "PT": "Portugaliýa",
    "BE": "Belgiýa",
    "LU": "Lýuksemburg",
    "HU": "Wengriýa",
    "SK": "Slowakiýa",
    "IS": "Islandiýa",
    "MD": "Moldowa",
    "UA": "Ukraina",
    "RU": "Russiýa",
    "KZ": "Gazagystan",
    "AE": "BAE",
    "US": "ABŞ",
    "CA": "Kanada",
    "SG": "Singapur",
    "JP": "Ýaponiýa",
    "KR": "Günorta Koreýa",
    "HK": "Gonkong",
    "TW": "Taýwan",
    "IN": "Hindistan",
    "AU": "Awstraliýa",
    "BR": "Braziliýa",
    "IL": "Ysraýyl",
    "CY": "Kipr",
    "GE": "Gruziýa",
    "AM": "Ermenistan",
    "AZ": "Azerbaýjan",
    "EU": "Ýewropa",
    "UN": "Halkara",
}

HOSTNAME_COUNTRY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:^|[.-])(?:de\d*|fra\d*|ffm\d*|ber\d*|nue\d*|falkenstein|hetzner)(?:[.-]|$)"), "DE"),
    (re.compile(r"(?:^|[.-])(?:nl\d*|ams\d*|amsterdam)(?:[.-]|$)"), "NL"),
    (re.compile(r"(?:^|[.-])(?:fi\d*|hel\d*|helsinki)(?:[.-]|$)"), "FI"),
    (re.compile(r"(?:^|[.-])(?:se\d*|sto\d*|stockholm)(?:[.-]|$)"), "SE"),
    (re.compile(r"(?:^|[.-])(?:fr\d*|par\d*|cdg\d*|rbx\d*|gra\d*|sbg\d*)(?:[.-]|$)"), "FR"),
    (re.compile(r"(?:^|[.-])(?:uk\d*|gb\d*|lon\d*|lhr\d*|london)(?:[.-]|$)"), "GB"),
    (re.compile(r"(?:^|[.-])(?:tr\d*|ist\d*|istanbul)(?:[.-]|$)"), "TR"),
    (re.compile(r"(?:^|[.-])(?:pl\d*|waw\d*|warsaw)(?:[.-]|$)"), "PL"),
    (re.compile(r"(?:^|[.-])(?:at\d*|vie\d*|vienna)(?:[.-]|$)"), "AT"),
    (re.compile(r"(?:^|[.-])(?:ch\d*|zrh\d*|zurich)(?:[.-]|$)"), "CH"),
    (re.compile(r"(?:^|[.-])(?:ee\d*|tll\d*|tallinn)(?:[.-]|$)"), "EE"),
    (re.compile(r"(?:^|[.-])(?:lv\d*|rix\d*|riga)(?:[.-]|$)"), "LV"),
    (re.compile(r"(?:^|[.-])(?:lt\d*|vno\d*|vilnius)(?:[.-]|$)"), "LT"),
    (re.compile(r"(?:^|[.-])(?:sg\d*|sgp\d*|sin\d*|singapore)(?:[.-]|$)"), "SG"),
    (re.compile(r"(?:^|[.-])(?:jp\d*|tyo\d*|nrt\d*|tokyo)(?:[.-]|$)"), "JP"),
    (re.compile(r"(?:^|[.-])(?:us\d*|nyc\d*|lax\d*|sjc\d*|iad\d*|ord\d*|ash\d*)(?:[.-]|$)"), "US"),
    (re.compile(r"(?:^|[.-])(?:ca\d*|yyz\d*|bhs\d*|toronto)(?:[.-]|$)"), "CA"),
    (re.compile(r"(?:^|[.-])(?:kz\d*|ala\d*|almaty)(?:[.-]|$)"), "KZ"),
    (re.compile(r"(?:^|[.-])(?:ae\d*|dxb\d*|dubai)(?:[.-]|$)"), "AE"),
    (re.compile(r"(?:^|[.-])(?:hk\d*|hkg\d*)(?:[.-]|$)"), "HK"),
    (re.compile(r"(?:^|[.-])(?:kr\d*|icn\d*|seoul)(?:[.-]|$)"), "KR"),
)

_REGIONAL_BASE = 0x1F1E6
_FLAG_RE = re.compile(r"([\U0001F1E6-\U0001F1FF])([\U0001F1E6-\U0001F1FF])")
_CODE_TOKEN_RE = re.compile(r"(?:^|[\s|\[\(\-_/·•])([A-Z]{2})(?:$|[\s|\]\)\-_/·•:])")


def country_flag(code: str) -> str:
    """Return Unicode flag emoji for a 2-letter ISO country code."""
    cc = (code or "UN").upper()
    if cc == "UK":
        cc = "GB"
    if len(cc) != 2 or cc not in VALID_COUNTRY_CODES:
        return "🌐"
    return chr(_REGIONAL_BASE + ord(cc[0]) - ord("A")) + chr(
        _REGIONAL_BASE + ord(cc[1]) - ord("A")
    )


def country_name_tk(code: str) -> str:
    """Return Turkmen display name for a country code."""
    cc = (code or "UN").upper()
    if cc == "UK":
        cc = "GB"
    return COUNTRY_NAMES_TK.get(cc, cc if cc in VALID_COUNTRY_CODES else "Halkara")


def detect_country(remark: str, host: str = "") -> str:
    """Infer ISO 3166-1 alpha-2 country code from remark flag/text or hostname."""
    if remark:
        for match in _FLAG_RE.finditer(remark):
            c1 = chr(ord(match.group(1)) - _REGIONAL_BASE + ord("A"))
            c2 = chr(ord(match.group(2)) - _REGIONAL_BASE + ord("A"))
            cc = "GB" if (c1 + c2) == "UK" else (c1 + c2)
            if cc in VALID_COUNTRY_CODES:
                return cc
        for match in _CODE_TOKEN_RE.finditer(remark):
            cc = match.group(1)
            if cc == "UK":
                cc = "GB"
            # Avoid mistaking protocol/network tags for country codes
            if cc in {"WS", "SS", "BL", "WL", "IP", "CF", "TG", "TV", "OK", "GO", "AI", "HD"}:
                continue
            if cc in VALID_COUNTRY_CODES:
                return cc

    lower_host = (host or "").lower()
    if lower_host:
        for pattern, cc in HOSTNAME_COUNTRY_PATTERNS:
            if pattern.search(lower_host):
                return cc
    return "UN"


def mask_host(host: str) -> str:
    """Mask part of a server IP/hostname for compact UI display."""
    try:
        addr = ipaddress.ip_address(host)
        if addr.version == 4:
            parts = host.split(".")
            return f"{parts[0]}.{parts[1]}.•••.{parts[3]}"
        parts = addr.exploded.split(":")
        return f"{parts[0]}:{parts[1]}:•••:{parts[-1]}"
    except ValueError:
        parts = host.split(".")
        if len(parts) >= 3:
            return f"{parts[0]}.•••.{parts[-1]}"
        if len(parts) == 2 and len(parts[0]) > 3:
            return f"{parts[0][:3]}•••.{parts[1]}"
        return host


@dataclass
class ProxyNode:
    """Normalized, validated VPN server configuration compatible with Happ."""

    protocol: str  # vless | trojan | vmess | ss | hy2
    host: str
    port: int
    credential: str
    method: str = ""
    transport: str = "tcp"
    security: str = "tls"  # reality | tls | aead
    sni: str = ""
    host_header: str = ""
    path: str = ""
    service_name: str = ""
    alpn: str = ""
    fp: str = ""
    flow: str = ""
    pbk: str = ""
    sid: str = ""
    spx: str = ""
    mode: str = ""
    obfs: str = ""
    obfs_password: str = ""
    pin_sha256: str = ""
    country: str = "UN"
    source: str = ""
    source_weight: int = 80
    latency_ms: int | None = None
    check_method: str = "source"  # xray | tls | tcp | source
    score: float = 0.0

    @property
    def is_reality(self) -> bool:
        return self.security == "reality" and bool(self.pbk)

    @property
    def badge(self) -> str:
        """Short uppercase protocol badge shown in Happ and Web Panel."""
        if self.protocol == "vless" and self.is_reality:
            return "REALITY"
        if self.protocol == "vless":
            return f"VLESS-{self.transport.upper()}" if self.transport != "tcp" else "VLESS"
        if self.protocol == "trojan":
            return "TROJAN-R" if self.is_reality else "TROJAN"
        if self.protocol == "hy2":
            return "HYSTERIA2"
        if self.protocol == "ss":
            return "SS-2022" if self.method.startswith("2022-") else "SS"
        if self.protocol == "vmess":
            return "VMESS"
        return self.protocol.upper()

    def dedup_key(self) -> str:
        """Stable SHA-256 key identifying unique logical proxy endpoints."""
        raw = "|".join([
            self.protocol,
            self.host.lower(),
            str(self.port),
            self.credential,
            self.transport,
            self.security,
            self.pbk,
            (self.path or self.service_name)[:64],
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    def host_bucket_key(self) -> str:
        """Key used to prevent a single IP/domain from flooding subscriptions."""
        return f"{self.protocol}:{self.host.lower()}"

    def credential_bucket_key(self) -> str:
        """Key used to prevent one backend cluster with many alias domains from flooding."""
        return f"{self.protocol}:{self.credential}:{self.pbk}"

    def format_label(self, index: int, prefix: str = "") -> str:
        """Format clean, spam-free server title for Happ VPN."""
        flag = country_flag(self.country)
        cc = self.country if self.country in VALID_COUNTRY_CODES else "GL"
        parts = [f"{prefix}{flag} {cc}".strip(), self.badge]
        if self.latency_ms is not None and self.latency_ms > 0:
            parts.append(f"{self.latency_ms}ms")
        parts.append(f"Zippy #{index:02d}")
        return " · ".join(parts)

    def supports_fragment(self) -> bool:
        """Return True if this node supports Xray TLS ClientHello fragmentation."""
        if self.protocol not in {"vless", "trojan", "vmess"}:
            return False
        if self.security not in {"reality", "tls"}:
            return False
        if self.transport not in {"tcp", "ws", "grpc", "httpupgrade", "xhttp"}:
            return False
        return bool(self.sni or self.host_header)
