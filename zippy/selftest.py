"""End-to-end self test: real server + real crypto + real TCP relay, on loopback.

Run with:  python -m zippy selftest
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import ssl
import tempfile
import uuid

from . import shadowsocks, socks, vless
from .certs import generate_self_signed
from .config import default_config
from .server import ZippyServer

log = logging.getLogger("zippy.selftest")


def _pattern(n: int) -> bytes:
    return bytes((i * 31 + 7) & 0xFF for i in range(n))


def _request(n: int) -> bytes:
    return (f"GET /{n} HTTP/1.1\r\nHost: zippy.local\r\n"
            f"Connection: close\r\n\r\n").encode()


def _body(data: bytes) -> bytes:
    head, _, body = data.partition(b"\r\n\r\n")
    if not head.startswith(b"HTTP/1.1 200"):
        raise AssertionError(f"bad HTTP response: {head[:80]!r}")
    return body


async def _start_target():
    async def handler(reader, writer):
        try:
            try:
                head = await reader.readuntil(b"\r\n\r\n")
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
                return
            line = head.split(b"\r\n", 1)[0].decode("latin-1")
            try:
                n = int(line.split()[1].strip("/").split("?")[0])
            except (IndexError, ValueError):
                n = 0
            body = _pattern(n)
            writer.write(
                f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n"
                f"Connection: close\r\n\r\n".encode() + body)
            await writer.drain()
        finally:
            writer.close()

    srv = await asyncio.start_server(handler, "127.0.0.1", 0)
    return srv, srv.sockets[0].getsockname()[1]


def _make_cfg(host: str, tls: bool, tmp: str) -> dict:
    cfg = default_config(host, ss_port=0, vless_port=0,
                         tls=tls, allow_private=True)
    if tls:
        cert = os.path.join(tmp, "server.crt")
        key = os.path.join(tmp, "server.key")
        generate_self_signed("localhost", cert, key)
        cfg["vless"]["cert"] = cert
        cfg["vless"]["key"] = key
    cfg["_path"] = os.path.join(tmp, "zippy.json")
    return cfg


async def _ss_roundtrip(cfg: dict, ports: dict, target_port: int,
                        method: str, size: int) -> None:
    ss = await shadowsocks.connect("127.0.0.1", ports["shadowsocks"],
                                   "127.0.0.1", target_port,
                                   cfg["shadowsocks"]["password"], method)
    await ss.write_plain(_request(size))
    chunks = []
    while True:
        part = await ss.read_chunk()
        if part is None:
            break
        chunks.append(part)
    data = b"".join(chunks)
    assert len(data) > 0, "no response from shadowsocks server"
    assert _body(data) == _pattern(size), f"{method}: payload mismatch ({len(_body(data))} bytes)"
    await asyncio.sleep(0)


async def _vless_roundtrip(cfg: dict, ports: dict, target_port: int,
                           size: int, tls: bool) -> None:
    ctx = None
    if tls:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    reader, writer = await vless.connect("127.0.0.1", ports["vless"],
                                         "127.0.0.1", target_port,
                                         cfg["vless"]["uuid"], ssl=ctx)
    writer.write(_request(size))
    await writer.drain()
    data = await reader.read()
    assert _body(data) == _pattern(size), "vless: payload mismatch"
    writer.close()


async def _bad_uuid(ports: dict, target_port: int) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", ports["vless"])
    header = (b"\x00" + uuid.uuid4().bytes + b"\x00\x01"
              + target_port.to_bytes(2, "big") + b"\x01\x7f\x00\x00\x01")
    writer.write(header)
    await writer.drain()
    rest = await asyncio.wait_for(reader.read(), 3)
    assert not rest, "server answered a request with a wrong UUID!"
    writer.close()


async def _tampered_ss(ports: dict) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", ports["shadowsocks"])
    writer.write(os.urandom(32))   # random salt
    writer.write(os.urandom(18))   # garbage length chunk
    writer.write(os.urandom(64))   # garbage data
    await writer.drain()
    data = await asyncio.wait_for(reader.read(), 3)
    # The server may send its own 32-byte salt before rejecting, never app data.
    assert len(data) <= 32 and b"HTTP/1.1" not in data, "tampered ciphertext was accepted"
    writer.close()


async def _socks_roundtrip(cfg: dict, target_port: int, protocol: str, size: int) -> None:
    srv = await socks.run_socks_server(cfg, protocol, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"\x05\x01\x00")
        assert await reader.readexactly(2) == b"\x05\x00"
        writer.write(b"\x05\x01\x00\x01" + socket.inet_aton("127.0.0.1")
                     + target_port.to_bytes(2, "big"))
        reply = await reader.readexactly(10)
        assert reply[:2] == b"\x05\x00", f"socks connect failed: {reply!r}"
        writer.write(_request(size))
        await writer.drain()
        data = await asyncio.wait_for(reader.read(), 10)
        assert _body(data) == _pattern(size), f"socks({protocol}): payload mismatch"
        writer.close()
    finally:
        srv.close()
        await srv.wait_closed()


async def run(verbose: bool = True) -> dict[str, str]:
    results: dict[str, str] = {}
    target, target_port = await _start_target()
    opened: list[ZippyServer] = []
    try:
        with tempfile.TemporaryDirectory(prefix="zippy-selftest-") as tmp:

            async def check(name: str, fn) -> None:
                await asyncio.wait_for(fn(), 20)
                results[name] = "OK"
                if verbose:
                    print(f"  [OK] {name}")

            # One server per Shadowsocks cipher (the method is fixed at startup).
            for method, size, label in (
                ("aes-256-gcm", 1024, "shadowsocks aes-256-gcm (1 KB)"),
                ("aes-128-gcm", 65536, "shadowsocks aes-128-gcm (64 KB, multi-chunk)"),
                ("chacha20-ietf-poly1305", 200000, "shadowsocks chacha20-poly1305 (200 KB)"),
            ):
                ss_cfg = _make_cfg("127.0.0.1", False, tmp)
                ss_cfg["shadowsocks"]["method"] = method
                ss_cfg["vless"]["enabled"] = False
                srv = ZippyServer(ss_cfg)
                opened.append(srv)
                ports = await srv.start()
                await check(label, lambda: _ss_roundtrip(ss_cfg, ports, target_port, method, size))

            cfg = _make_cfg("127.0.0.1", False, tmp)
            server = ZippyServer(cfg)
            opened.append(server)
            ports = await server.start()
            # Real bound ports are needed by the local SOCKS5 client.
            cfg["shadowsocks"]["port"] = ports["shadowsocks"]
            cfg["vless"]["port"] = ports["vless"]

            await check("vless tcp (2 KB)", lambda: _vless_roundtrip(cfg, ports, target_port, 2048, False))
            await check("wrong UUID rejected", lambda: _bad_uuid(ports, target_port))
            await check("tampered AEAD tag rejected", lambda: _tampered_ss(ports))
            await check("local SOCKS5 via VLESS", lambda: _socks_roundtrip(cfg, target_port, "vless", 4096))
            await check("local SOCKS5 via Shadowsocks", lambda: _socks_roundtrip(cfg, target_port, "shadowsocks", 4096))

            tls_cfg = _make_cfg("127.0.0.1", True, tmp)
            tls_server = ZippyServer(tls_cfg)
            opened.append(tls_server)
            tls_ports = await tls_server.start()
            await check("vless over TLS (8 KB)",
                        lambda: _vless_roundtrip(tls_cfg, tls_ports, target_port, 8192, True))
    finally:
        for srv in opened:
            await srv.close()
        target.close()
        await target.wait_closed()
    return results
