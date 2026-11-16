"""The Zippy VPN server: Shadowsocks AEAD + VLESS (optional TLS) in one process."""
from __future__ import annotations

import asyncio
import logging
import ssl
from pathlib import Path

from . import shadowsocks, vless
from .config import resolve

log = logging.getLogger("zippy")


def _tls_context(cfg: dict, v: dict) -> ssl.SSLContext:
    cert = Path(resolve(cfg, v["cert"]))
    key = Path(resolve(cfg, v["key"]))
    if not cert.exists() or not key.exists():
        raise FileNotFoundError(
            f"TLS cert/key missing ({cert}, {key}). Run: python -m zippy cert --config ...")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert), str(key))
    ctx.set_alpn_protocols(["h2", "http/1.1"])
    return ctx


class ZippyServer:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.servers: dict[str, asyncio.AbstractServer] = {}
        self.ports: dict[str, int] = {}

    async def start(self) -> dict[str, int]:
        listen = self.cfg.get("listen", "0.0.0.0")
        allow_private = bool(self.cfg.get("allow_private", False))

        ss = self.cfg.get("shadowsocks", {})
        if ss.get("enabled", True):
            ss_cfg = {**ss, "allow_private": allow_private}
            srv = await asyncio.start_server(
                lambda r, w: shadowsocks.handle_client(r, w, ss_cfg),
                listen, int(ss["port"]), reuse_address=True,
            )
            self.servers["shadowsocks"] = srv
            self.ports["shadowsocks"] = srv.sockets[0].getsockname()[1]
            log.info("Shadowsocks (%s) listening on %s:%s",
                     ss.get("method", "aes-256-gcm"), listen, self.ports["shadowsocks"])

        v = self.cfg.get("vless", {})
        if v.get("enabled", True):
            v_cfg = {**v, "allow_private": allow_private}
            tls_ctx = _tls_context(self.cfg, v) if v.get("tls") else None
            srv = await asyncio.start_server(
                lambda r, w: vless.handle_client(r, w, v_cfg),
                listen, int(v["port"]), reuse_address=True, ssl=tls_ctx,
            )
            self.servers["vless"] = srv
            self.ports["vless"] = srv.sockets[0].getsockname()[1]
            log.info("VLESS%s listening on %s:%s",
                     "+TLS" if tls_ctx else "", listen, self.ports["vless"])

        if not self.servers:
            raise RuntimeError("no inbound enabled in config")
        return dict(self.ports)

    async def serve(self) -> None:
        await asyncio.gather(*(s.serve_forever() for s in self.servers.values()))

    async def close(self) -> None:
        for srv in self.servers.values():
            srv.close()
        await asyncio.gather(*(s.wait_closed() for s in self.servers.values()))
        self.servers.clear()


async def run(cfg: dict) -> None:
    server = ZippyServer(cfg)
    await server.start()
    try:
        await server.serve()
    except asyncio.CancelledError:
        pass
    finally:
        await server.close()
