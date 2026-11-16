"""Local SOCKS5 proxy that tunnels through a Zippy server.

Lets desktop apps (browser, git, curl) use the server without a TUN device;
on Android/iOS use v2rayNG / Hiddify / Shadowrocket with the share links.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import ssl

from . import shadowsocks, vless
from .common import close_writer, read_exact

log = logging.getLogger("zippy.socks")


class VlessTunnel:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer

    async def read(self):
        return await self.reader.read(65536)

    async def write(self, data: bytes):
        self.writer.write(data)
        await self.writer.drain()

    async def close(self):
        await close_writer(self.writer)


class SSTunnel:
    def __init__(self, ss):
        self.ss = ss

    async def read(self):
        return await self.ss.read_chunk()

    async def write(self, data: bytes):
        await self.ss.write_plain(data)

    async def close(self):
        await close_writer(self.ss.writer)


async def _connect(cfg: dict, target_host: str, target_port: int, protocol: str):
    host, allow_private = cfg["host"], True  # local client may target localhost
    ss, v = cfg.get("shadowsocks", {}), cfg.get("vless", {})
    if protocol == "shadowsocks" and ss.get("enabled", True):
        return SSTunnel(await shadowsocks.connect(
            host, int(ss["port"]), target_host, target_port,
            ss["password"], ss.get("method", "aes-256-gcm")))
    if protocol == "vless" and v.get("enabled", True):
        ctx = None
        if v.get("tls"):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        reader, writer = await vless.connect(
            host, int(v["port"]), target_host, target_port,
            v["uuid"], ssl=ctx)
        return VlessTunnel(reader, writer)
    raise RuntimeError(f"protocol {protocol!r} is not enabled in config")


async def handle_socks(reader, writer, cfg: dict, protocol: str) -> None:
    tunnel = None
    try:
        ver, nmethods = await read_exact(reader, 2)
        methods = await read_exact(reader, nmethods)
        if ver != 5:
            return
        writer.write(b"\x05\x00" if 0 in methods else b"\x05\xff")
        await writer.drain()

        ver, cmd, _rsv, atyp = await read_exact(reader, 4)
        if ver != 5 or cmd != 1:
            writer.write(b"\x05\x07\x00\x01" + b"\x00" * 6)
            await writer.drain()
            return
        if atyp == 1:
            target_host = str(ipaddress.IPv4Address(await read_exact(reader, 4)))
        elif atyp == 3:
            n = (await read_exact(reader, 1))[0]
            target_host = (await read_exact(reader, n)).decode("idna")
        elif atyp == 4:
            target_host = str(ipaddress.IPv6Address(await read_exact(reader, 16)))
        else:
            raise ValueError(f"unsupported SOCKS ATYP {atyp}")
        target_port = int.from_bytes(await read_exact(reader, 2), "big")

        try:
            tunnel = await _connect(cfg, target_host, target_port, protocol)
        except Exception as exc:
            log.warning("cannot reach %s:%s via %s: %s", target_host, target_port, protocol, exc)
            writer.write(b"\x05\x05\x00\x01" + b"\x00" * 6)
            await writer.drain()
            return

        writer.write(b"\x05\x00\x00\x01" + b"\x00" * 6)
        await writer.drain()
        log.info("socks5 -> %s:%s via %s", target_host, target_port, protocol)

        async def up():
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                await tunnel.write(data)

        async def down():
            try:
                while True:
                    data = await tunnel.read()
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
                try:
                    if writer.can_write_eof():
                        writer.write_eof()
                except (NotImplementedError, OSError, ConnectionError):
                    pass
            finally:
                # Propagate EOF to the local client and unblock up().
                writer.close()

        await asyncio.gather(up(), down())
    except (EOFError, ConnectionError, OSError, ValueError, asyncio.IncompleteReadError):
        pass
    finally:
        if tunnel is not None:
            await tunnel.close()
        await close_writer(writer)


async def run_socks_server(cfg: dict, protocol: str = "vless",
                           listen: str = "127.0.0.1", port: int = 10808):
    server = await asyncio.start_server(
        lambda r, w: handle_socks(r, w, cfg, protocol), listen, port, reuse_address=True)
    return server
