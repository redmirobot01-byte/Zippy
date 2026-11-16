"""Fetch free public VLESS / VMess / Shadowsocks configs published on GitHub.

⚠️  Public proxies are run by strangers: they can see your DNS requests, log
    metadata and MitM plain HTTP. Never use them for banking, passwords or
    2FA. For anything private, use your own server (`zippy init` + deploy/).

Sources below are real, actively updated GitHub repos (verified 2026-11-16).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

log = logging.getLogger("zippy.subs")

SUPPORTED = ("vless", "vmess", "ss", "trojan", "ssr", "hysteria2", "hy2", "tuic")


@dataclass(frozen=True)
class Source:
    name: str
    repo: str
    branch: str
    path: str
    kind: str = "plain"       # plain | base64

    @property
    def raw_url(self) -> str:
        return f"https://raw.githubusercontent.com/{self.repo}/{self.branch}/{self.path}"

    @property
    def api_url(self) -> str:
        return f"https://api.github.com/repos/{self.repo}/contents/{self.path}?ref={self.branch}"

    @property
    def tree_url(self) -> str:
        return f"https://api.github.com/repos/{self.repo}/git/trees/{self.branch}?recursive=1"


SOURCES: tuple[Source, ...] = (
    Source("Free-v2ray-Configs · barlanan (hemme protokol)", "0xRadikal/Free-v2ray-Configs", "main", "verified/configs_base64.txt", "base64"),
    Source("Free-v2ray-Configs · Shadowsocks", "0xRadikal/Free-v2ray-Configs", "main", "protocols/shadowsocks.txt"),
    Source("Free-v2ray-Configs · VLESS", "0xRadikal/Free-v2ray-Configs", "main", "protocols/vless.txt"),
    Source("Free-v2ray-Configs · VMess", "0xRadikal/Free-v2ray-Configs", "main", "protocols/vmess.txt"),
    Source("vpn-configs-for-russia · VLESS Reality", "igareck/vpn-configs-for-russia", "main", "Vless-Reality-White-Lists-Rus-Mobile.txt"),
    Source("PSG · täze konfiglar", "itsyebekhe/PSG", "main", "config.txt", "base64"),
    Source("V2RayAggregator · sub_merge", "mahdibland/V2RayAggregator", "master", "sub/sub_merge.txt", "base64"),
    Source(".proxy · VLESS", "mheidari98/.proxy", "main", "vless"),
)


def _get(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "ZippyVPN/1.0 (github config fetcher)",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _b64_decode(text: str) -> str:
    cleaned = re.sub(r"\s+", "", text)
    cleaned += "=" * (-len(cleaned) % 4)
    return base64.urlsafe_b64decode(cleaned.encode()).decode("utf-8", "replace")


def fetch_source(source: Source) -> str:
    """Raw URL first (fast), then GitHub API fallbacks (works behind proxies)."""
    errors: list[str] = []
    try:
        return _get(source.raw_url).decode("utf-8", "replace")
    except Exception as exc:
        errors.append(f"raw: {exc}")

    try:
        data = json.loads(_get(source.api_url))
        # For files > 1 MB GitHub returns content="" with encoding="none":
        # that must fall through to the git-blob fallback below.
        if data.get("content") and data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", "replace")
        errors.append(f"api/contents: {data.get('message', 'empty/too large')}")
    except Exception as exc:
        errors.append(f"api/contents: {exc}")

    try:  # git blob works for files > 1 MB where /contents refuses
        tree = json.loads(_get(source.tree_url))
        sha = next(x["sha"] for x in tree["tree"] if x["path"] == source.path)
        blob = json.loads(_get(f"https://api.github.com/repos/{source.repo}/git/blobs/{sha}"))
        return base64.b64decode(blob["content"]).decode("utf-8", "replace")
    except Exception as exc:
        errors.append(f"api/blob: {exc}")
    raise RuntimeError(f"cannot fetch {source.name}: " + " | ".join(errors))


def _extract_links(text: str) -> list[str]:
    found: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "//", ";")):
            continue
        for token in line.split():
            for scheme in SUPPORTED:
                if token.lower().startswith(scheme + "://"):
                    found.setdefault(token, scheme)
                    break
    return list(found)


def decode_subscription(text: str, kind: str = "plain") -> list[str]:
    """Return deduplicated share links from a plain or base64 subscription."""
    found = _extract_links(text)
    if not found:  # base64 subscription (v2rayNG / Clash style)
        try:
            found = _extract_links(_b64_decode(text))
        except Exception:
            pass
    return found


def parse_link(link: str) -> dict:
    scheme, _, rest = link.partition("://")
    scheme = scheme.lower()
    info: dict = {"proto": scheme, "raw": link, "host": "", "port": 0}
    try:
        if scheme in ("vless", "trojan", "hysteria2", "hy2", "tuic"):
            u = urllib.parse.urlparse(link)
            info["host"] = u.hostname or ""
            info["port"] = u.port or (443 if scheme in ("trojan", "vless") else 443)
            info["security"] = (dict(urllib.parse.parse_qsl(u.query)).get("security") or "none")
        elif scheme == "ss":
            body = link.split("#", 1)[0][5:]
            if "@" in body:
                userinfo, hostpart = body.rsplit("@", 1)
                try:
                    info["method"] = _b64_decode(userinfo).split(":", 1)[0]
                except Exception:
                    info["method"] = "?"
                h, _, p = hostpart.rpartition(":")
                info["host"], info["port"] = h.strip("[]"), int(p)
            else:
                decoded = _b64_decode(body)
                info["method"] = decoded.split(":", 1)[0]
                h, _, p = decoded.rsplit("@", 1)[1].rpartition(":")
                info["host"], info["port"] = h.strip("[]"), int(p)
        elif scheme == "vmess":
            cfg = json.loads(_b64_decode(link.split("#", 1)[0][8:]))
            info["host"] = str(cfg.get("add", ""))
            info["port"] = int(cfg.get("port", 0))
        elif scheme == "ssr":
            decoded = _b64_decode(link.split("#", 1)[0][6:])
            parts = decoded.split(":")
            info["host"], info["port"] = parts[0], int(parts[1])
    except Exception as exc:
        info["error"] = str(exc)
    return info


async def tcp_check(host: str, port: int, timeout: float = 2.5) -> bool:
    writer = None
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        return True
    except Exception:
        return False
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def check_links(links: list[str], concurrency: int = 40) -> dict[str, bool]:
    sem = asyncio.Semaphore(concurrency)

    async def one(link: str):
        info = parse_link(link)
        async with sem:
            ok = await tcp_check(info["host"], info["port"]) if info.get("host") and info.get("port") else False
        return link, ok

    results = await asyncio.gather(*(one(x) for x in links))
    return dict(results)


async def collect(sources: tuple[Source, ...] = SOURCES) -> tuple[list[str], list[str]]:
    """Fetch all sources concurrently; return (links, errors)."""
    texts = await asyncio.gather(
        *(asyncio.to_thread(fetch_source, s) for s in sources),
        return_exceptions=True,
    )
    links: list[str] = []
    errors: list[str] = []
    for src, text in zip(sources, texts):
        if isinstance(text, Exception):
            errors.append(f"{src.name}: {text}")
            continue
        try:
            got = decode_subscription(text, src.kind)
            links.extend(got)
            log.info("%-55s -> %d links", src.name, len(got))
        except Exception as exc:
            errors.append(f"{src.name}: decode: {exc}")
    # dedupe, keep order
    seen: set[str] = set()
    out = [x for x in links if not (x in seen or seen.add(x))]
    return out, errors


def filter_proto(links: list[str], wanted: set[str] | None) -> list[str]:
    if not wanted:
        return links
    return [x for x in links if x.split("://", 1)[0].lower() in wanted]


def subscription_base64(links: list[str]) -> str:
    return base64.b64encode(("\n".join(links) + "\n").encode()).decode()
