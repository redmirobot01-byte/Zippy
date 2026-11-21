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

import json
import os
import re
import urllib.error
import urllib.request

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
    # --- AI programmalary ---
    {
        "name": "ChatGPT",
        "package": "com.openai.chatgpt",
        "aliases": ("chatgpt", "openai", "gpt"),
        "note": "OpenAI-yň söhbetdeşlik AI programmasy",
    },
    {
        "name": "Gemini",
        "package": "com.google.ai.gemini",
        "aliases": ("gemini", "google gemini", "ai gemini"),
        "note": "Google-yň ýokary AI söhbetdeşligi",
    },
    {
        "name": "Microsoft Copilot",
        "package": "com.microsoft.copilot",
        "aliases": ("copilot", "ms copilot", "microsoft copilot"),
        "note": "Microsoft-yň AI kömekçisi",
    },
    {
        "name": "Perplexity",
        "package": "com.perplexity.ai",
        "aliases": ("perplexity",),
        "note": "Sorag-jogap AI we gözleg",
    },
    {
        "name": "Claude",
        "package": "com.anthropic.claude",
        "aliases": ("claude", "anthropic"),
        "note": "Anthropic-iň Claude AI söhbetdeşligi",
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


def resolve(query: str, use_ai: bool = False) -> tuple[dict | None, str | None]:
    """Bir söz boýunça link ýasamagy çözýär.

    ``use_ai=True`` bolsa, ilkinji AI akylly gözlegden geçirýär: programmanyň
    adyny AI-a berip, Play Market-däki paket adyny tapdyryp link ýasamaýar.
    AI jobaýyşy bolmasa ýa-da tapyp bilmese, ýerli registre geçýär.

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

    if use_ai:
        package = ai_lookup(query)
        if package:
            return None, build_play_link(package)

    apps = find_apps(query)
    if not apps:
        return None, None
    app = apps[0]
    return app, build_play_link(app["package"])


# ---------------------------------------------------------------------------
# AI akylly gözleg (OpenAI-niň Chat Completions API-si, ýa-da şonuň bilen
# işleýän islendik ulag: OpenRouter, Groq, Ollama, LocalAI ...)
#
# API açaryny adatça dal gizläp saklanýar: şu üýtgetmeleri ulanyň:
#   ZIPPY_AI_API_KEY   (ýa-da OPENAI_API_KEY)
#   ZIPPY_AI_BASE_URL  (default: https://api.openai.com/v1)
#   ZIPPY_AI_MODEL     (default: gpt-4o-mini)
# ---------------------------------------------------------------------------

_AI_SYSTEM_PROMPT = (
    "Sen Android programmalarynyň Google Play Market-däki paket adyny "
    "tapýan kömekçisің. Adaty nädogry sözler, baglanyşyklar ýa-da şerhler "
    "ýazma. Jogabyň diňe paýlaşyk görünüşi bolmaly, mysal üçin "
    "com.example.app. Nädogry bolsa, jogap bermekden ýeňrel."
)


def ai_settings() -> dict | None:
    """AI ulanmak üçin sazlamalar. Açary bolmasa ``None`` gaýtarýar."""
    api_key = os.environ.get("ZIPPY_AI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return {
        "api_key": api_key,
        "base_url": os.environ.get("ZIPPY_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        "model": os.environ.get("ZIPPY_AI_MODEL", "gpt-4o-mini"),
    }


def parse_ai_package(text: str) -> str | None:
    """AI jogabyndaky paket adyny aýyryp alýar (ýalňyş sözler gerisinde)."""
    match = re.search(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", (text or "").strip())
    return match.group(0) if match else None


def ai_lookup(app_name: str, timeout: float = 20.0) -> str | None:
    """Programmanyň adyny AI-a berip Play Market paket adyny tapýar.

    Açar sazlanmadyk, API hata berende ýa-da AI paket görnüşinde
    jogap bermedikde ``None`` gaýtarýar.
    """
    config = ai_settings()
    if not config:
        return None

    body = {
        "model": config["model"],
        "temperature": 0,
        "max_tokens": 20,
        "messages": [
            {"role": "system", "content": _AI_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Google Play Market programmasynyň ady: {app_name}",
            },
        ],
    }
    request = urllib.request.Request(
        url=f"{config['base_url']}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        package = parse_ai_package(data["choices"][0]["message"]["content"])
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError):
        return None

    if package and is_package_id(package):
        return package
    return None


def format_result(app: dict, link: str) -> str:
    """Terminal görnüşi üçin netijäni düzýär."""
    note = f" — {app['note']}" if app.get("note") else ""
    if app:
        return f"{app['name']} ({app['package']}){note}\n{link}"
    return link
