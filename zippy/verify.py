"""Hakyky işleýän konfiglary saýlaýjy.

Bu modul GitHub-dan alnan linkleri *diňe port açykmy* däl, eýsem
**uçdan-uça el gysyş** bilen barlaýar:

* `ss://` (aes-256-gcm / aes-128-gcm / chacha20-ietf-poly1305) →
  öz Shadowsocks klientimiz bilen hakyky şifrlenen birikme açyp,
  nyşana HTTP sorag iberýär we `HTTP/` jogabyny alýar.  [`level=full`]
* `vless://` (security=none, type=tcp) → öz VLESS klientimiz bilen
  şol bir zady edýär.                                      [`level=full`]
* TLS / Reality / WS / VMess / Trojan → TLS el gysyşy ýa-da TCP barlagy.
                                                          [`level=port`]

⚠️  Sandbox-yň daşarky maglumat akymy çäkli bolany üçin bu guraly **öz
    kompýuteriňde** işlet: `python -m zippy verify`. Şonda hakyky netije alarsyň.
"""
from __future__ import annotations

import asyncio
import logging
import ssl
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from . import shadowsocks, subs, vless
from .common import close_writer
from .crypto import METHODS

log = logging.getLogger("zippy.verify")


@dataclass
class Result:
    link: str
    proto: str
    host: str
    port: int
    level: str = ""          # full | port | ""
    latency: float = 0.0
    detail: str = ""

    def __bool__(self) -> bool:
        return bool(self.level)


def _http_request(target_host: str) -> bytes:
    return (f"GET / HTTP/1.1\r\nHost: {target_host}\r\n"
            f"User-Agent: ZippyVerify/1.0\r\nConnection: close\r\n\r\n").encode()


async def _full_ss(info: dict, target_host: str, target_port: int, timeout: float) -> str:
    method = info.get("method", "")
    if method not in METHODS:
        raise RuntimeError(f"goldanylmaýan şifr: {method}")
    pw = info.get("password", "")
    ss = await asyncio.wait_for(
        shadowsocks.connect(info["host"], info["port"], target_host, target_port,
                            pw, method), timeout)
    try:
        await ss.write_plain(_http_request(target_host))
        data = await asyncio.wait_for(ss.read_chunk(), timeout)
        if not data or b"HTTP/" not in data[:200]:
            raise RuntimeError("HTTP jogaby gelmedi")
        return "full"
    finally:
        await close_writer(ss.writer)


async def _full_vless(info: dict, target_host: str, target_port: int, timeout: float) -> str:
    reader, writer = await asyncio.wait_for(
        vless.connect(info["host"], info["port"], target_host, target_port,
                      info.get("uuid", "")), timeout)
    try:
        writer.write(_http_request(target_host))
        await writer.drain()
        data = await asyncio.wait_for(reader.read(2048), timeout)
        if b"HTTP/" not in data[:200]:
            raise RuntimeError("HTTP jogaby gelmedi")
        return "full"
    finally:
        await close_writer(writer)


async def _port_check(info: dict, timeout: float) -> str:
    """TLS el gysyşy (mümkin bolsa) ýa-da ýönekeý TCP birikmesi."""
    host, port = info["host"], info["port"]
    if not host or not port:
        raise RuntimeError("host/port ýok")
    security = info.get("security") or "none"
    if security in ("tls", "reality") or info.get("params", {}).get("security") == "tls":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ctx, server_hostname=host), timeout)
        await close_writer(writer)
    else:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        await close_writer(writer)
    return "port"


async def verify_link(link: str, target_host: str = "example.com",
                      target_port: int = 80, timeout: float = 6.0) -> Result:
    info = subs.parse_link(link)
    r = Result(link=link, proto=info["proto"], host=info.get("host", ""),
               port=info.get("port", 0))
    t0 = time.monotonic()
    try:
        if r.proto == "ss" and info.get("method") in METHODS:
            r.level = await _full_ss(info, target_host, target_port, timeout)
            r.detail = f"{info['method']} · şifrlenen el gysyş + HTTP jogaby"
        elif r.proto == "vless" and (info.get("security") in ("none", "")) \
                and (info.get("type") in ("tcp", "", "none")):
            r.level = await _full_vless(info, target_host, target_port, timeout)
            r.detail = "VLESS el gysyş + HTTP jogaby"
        else:
            r.level = await _port_check(info, timeout)
            r.detail = "port / TLS el gysyşy açyk (doly protokol barlagy ýok)"
    except Exception as exc:
        r.detail = f"{type(exc).__name__}: {str(exc)[:90]}"
        r.level = ""
    r.latency = round(time.monotonic() - t0, 2)
    return r


async def verify_many(links: list[str], *, max_links: int = 250,
                      concurrency: int = 50, target_host: str = "example.com",
                      target_port: int = 80, timeout: float = 6.0,
                      wanted: set[str] | None = None) -> list[Result]:
    candidates = subs.filter_proto(links, wanted)[:max_links]
    sem = asyncio.Semaphore(concurrency)

    async def one(link: str) -> Result:
        async with sem:
            return await verify_link(link, target_host, target_port, timeout)

    results = await asyncio.gather(*(one(x) for x in candidates))
    good = [x for x in results if x]
    good.sort(key=lambda x: (0 if x.level == "full" else 1, x.latency))
    return good


def write_outputs(results: list[Result], out_dir: str, qr_count: int = 3,
                  limit: int = 15) -> list[str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chosen = results[:limit]
    links = [x.link for x in chosen]
    (out / "working-configs.txt").write_text("\n".join(links) + "\n", encoding="utf-8")
    (out / "working-subscription.txt").write_text(
        subs.subscription_base64(links) + "\n", encoding="utf-8")
    stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    lines = [f"# Işleýän konfiglar — barlanan wagty: {stamp}", "",
             "| # | Protokol | Host:port | Barlag | Gijikme |", "|---|---|---|---|---|"]
    for i, x in enumerate(chosen, 1):
        lines.append(f"| {i} | {x.proto} | {x.host}:{x.port} | {x.level} | {x.latency}s |")
    lines += ["", "  * `full` = hakyky şifrlenen/VLESS el gysyş + HTTP jogaby alyndy.",
              "  * `port` = diňe port / TLS el gysyşy açyk.", "",
              "⚠️ Köpçülikleýin düwünler näbelli adamlaryňky — parol/bank/2FA üçin ulanmaň.", ""]
    (out / "working-report.md").write_text("\n".join(lines), encoding="utf-8")

    written: list[str] = []
    try:
        import qrcode
        import qrcode.image.svg
        for i, link in enumerate(links[:qr_count], 1):
            p = out / f"qr-working-{i}.svg"
            qrcode.make(link, image_factory=qrcode.image.svg.SvgPathImage).save(p)
            written.append(str(p))
    except ImportError:
        log.warning("qrcode ýok — QR-lar geçirilmedi (pip install qrcode)")
    return written


async def self_test() -> list[Result]:
    """Lokal serwerler bilen barlaýjynyň özüni barla (daşarky internet gerek däl)."""
    from .config import default_config
    from .links import ss_sip002
    from .server import ZippyServer

    async def target_handler(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        await writer.drain()
        writer.close()

    target = await asyncio.start_server(target_handler, "127.0.0.1", 0)
    target_port = target.sockets[0].getsockname()[1]
    cfg = default_config("127.0.0.1", ss_port=0, vless_port=0, allow_private=True)
    cfg["vless"]["tls"] = False
    srv = ZippyServer(cfg)
    ports = await srv.start()
    try:
        ss_link = ss_sip002("aes-256-gcm", cfg["shadowsocks"]["password"],
                            "127.0.0.1", ports["shadowsocks"])
        vl_link = vless.share_link(cfg["vless"]["uuid"], "127.0.0.1", ports["vless"],
                                   security="none", name="local")
        results = await asyncio.gather(
            verify_link(ss_link, "127.0.0.1", target_port, 5),
            verify_link(vl_link, "127.0.0.1", target_port, 5),
        )
        return list(results)
    finally:
        await srv.close()
        target.close()
        await target.wait_closed()
