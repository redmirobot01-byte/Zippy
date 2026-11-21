"""Play Market (Google Play Store) link ýasaýjy.

Bir programmanyň ady (ýa-da paket ady) boýunça Google Play Market-de açylýan
sowda linkini ýasaýar. Esas amany:

    https://play.google.com/store/apps/details?id=<paket-ady>

Her programmanyň Play Market-däki sowda linki onuň Android paket ady bilen
anyklanýar (``id=`` parametri), şonuň üçin belli programmalar üçin paket adyny
bir ýerde saklap, islendik programmanyň linkiniň düzülmegi üçin module
birleşdirýäris.
"""

from __future__ import annotations

import re

PLAY_STORE_BASE = "https://play.google.com/store/apps/details"

# Belli programmalar (VPN we ýörite sazlanan Happ VPN ugry):
# ``name`` — adaty görkezilýän ady, ``package`` — Play Market-däki paket ady,
# ``aliases`` — gözlegde ulanylýan goşmaça sözler (tükeniksiz sözler hem).
APPS: tuple[dict, ...] = (
    {
        "name": "Happ VPN",
        "package": "com.happproxy",
        "aliases": ("happ", "hap vpn", "happ vpn"),
        "note": "Zippy VPN abunalary bilen işleýän Happ VPN klienti",
    },
    {
        "name": "v2rayNG",
        "package": "com.v2ray.ng",
        "aliases": ("v2ray", "v2ray ng", "v2rayng"),
        "note": "VLESS / VMess / Trojan goldaýan meşhur Android klient",
    },
    {
        "name": "Hiddify Next",
        "package": "com.hiddify.next",
        "aliases": ("hiddify", "hiddify next"),
        "note": "VLESS, Hysteria2, Trojan we Shadowsocks goldaýan klient",
    },
    {
        "name": "NekoBox",
        "package": "io.nekobox",
        "aliases": ("nekobox", "neko box", "neko"),
        "note": "sing-box we Xray ýadroly köp protokol klienti",
    },
    {
        "name": "Clash for Android",
        "package": "com.github.kr328.clash",
        "aliases": ("clash", "clash for android", "cfa"),
        "note": "Clashýň ilkinji resmi Android görnüşi",
    },
    {
        "name": "ClashMetaForAndroid",
        "package": "com.meta.clash",
        "aliases": ("clash meta", "meta clash", "cmfa"),
        "note": "Müşderi meseleleri üçin Clash Meta görnüşi",
    },
    {
        "name": "Shadowsocks",
        "package": "com.shadowsocks",
        "aliases": ("shadowsocks", "ss", "socks"),
        "note": "Shadowsocks-yň resmi Android klienti",
    },
    {
        "name": "WireGuard",
        "package": "com.wireguard.android",
        "aliases": ("wireguard", "wg"),
        "note": "WireGuard VPN-iň resmi Android klienti",
    },
    {
        "name": "1.1.1.1 (Cloudflare)",
        "package": "com.cloudflare.1111",
        "aliases": ("cloudflare", "1111", "one one one"),
        "note": "Cloudflare-iň çalt DNS we VPN ulanylyşy",
    },
)

_PACKAGE_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$")


def build_play_link(package: str) -> str:
    """Islendik Android paket ady üçin Play Market sowda linkini ýasaýar.

    Paket ady bolmasa ýa-da nädogry bolsa ``ValueError`` atýar.
    """
    package = (package or "").strip()
    if not package or not _PACKAGE_RE.match(package):
        raise ValueError(
            f"Nädogry paket ady: {package!r}. "
            "Paket ady sahypa görnüşinde bolmaly, mysal üçin: com.happproxy"
        )
    return f"{PLAY_STORE_BASE}?id={package}"


def is_package_id(text: str) -> bool:
    """Berlen söz paket ady (``com.example.app``) görnüşindemi ýa-da ýokmy."""
    return bool(_PACKAGE_RE.match((text or "").strip()))


def find_apps(query: str) -> list[dict]:
    """Ady (ýa-da alias) boýunça registry-de programmalary gözleýär.

    Çeýe gözleg: kiçi harplary we bellikleri göz öňünde tutýar. Üstünlik
    tapylanda iň gowy kablastyň önünden başlap tertiplenen sanawy berýär.
    """
    query = (query or "").strip().lower()
    if not query:
        return []

    scored: list[tuple[int, dict]] = []
    for app in APPS:
        haystack_parts = [app["name"].lower(), app["package"].lower(), *app["aliases"]]
        haystack = " ".join(haystack_parts)

        if query in haystack:
            score = 0
        elif any(
            part and part.startswith(query) for part in haystack_parts
        ):
            score = 1
        else:
            continue

        scored.append((score, app))

    scored.sort(key=lambda item: item[0])
    return [app for _, app in scored]


def resolve(query: str) -> tuple[dict | None, str | None]:
    """Bir söz boýunça link ýasamagy çözýär.

    Sargyt paket ady görnüşinde bolsa, registry-ni gözden geçirmezden link
    ýasamaýar. Düzgünli tapylan programma üçin ``(app, link)``, tapylyp
    bilinmese ``(None, None)`` gaýtarýar.
    """
    query = (query or "").strip()
    if not query:
        return None, None

    if is_package_id(query):
        try:
            return None, build_play_link(query)
        except ValueError:
            return None, None

    apps = find_apps(query)
    if not apps:
        return None, None
    app = apps[0]
    return app, build_play_link(app["package"])


def format_result(app: dict, link: str) -> str:
    """Terminal görnüşi üçin netijäni düzýär."""
    note = f" — {app['note']}" if app.get("note") else ""
    if app:
        return f"{app['name']} ({app['package']}){note}\n{link}"
    return link
