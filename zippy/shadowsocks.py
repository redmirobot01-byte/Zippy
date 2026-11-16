"""Shadowsocks AEAD TCP server + client connector."""
from __future__ import annotations

import asyncio
import logging

from .address import encode_ss_address, read_ss_address
from .common import (ProtocolError, close_writer, is_bad_error, open_remote,
                     read_exact)
from .crypto import method_info
from .stream import SSStream

log = logging.getLogger("zippy.ss")


async def handle_client(reader, writer, cfg: dict) -> None:
    method = cfg.get("method", "aes-256-gcm")
    password = cfg["password"]
    allow_private = bool(cfg.get("allow_private", False))
    remote_writer = None
    try:
        async with asyncio.timeout(30):
            ss = await SSStream.accept(reader, writer, method, password)
            host, port = await read_ss_address(ss)
        remote_reader, remote_writer = await open_remote(host, port, allow_private)
        log.info("ss -> %s:%s", host, port)

        leftover = ss.take_remaining()
        if leftover:
            remote_writer.write(leftover)
            await remote_writer.drain()

        async def up() -> None:
            try:
                while True:
                    chunk = await ss.read_chunk()
                    if chunk is None:
                        break
                    if chunk:
                        remote_writer.write(chunk)
                        await remote_writer.drain()
                if remote_writer.can_write_eof():
                    remote_writer.write_eof()
            except (ConnectionError, OSError, ProtocolError):
                remote_writer.close()

        async def down() -> None:
            try:
                while True:
                    data = await remote_reader.read(65536)
                    if not data:
                        break
                    await ss.write_plain(data)
            except (ConnectionError, OSError, ProtocolError):
                pass
            finally:
                writer.close()

        await asyncio.gather(up(), down())
    except Exception as exc:
        if not is_bad_error(exc):
            log.exception("shadowsocks handler error")
        elif isinstance(exc, ProtocolError):
            log.debug("rejected shadowsocks client: %s", exc)
    finally:
        if remote_writer is not None:
            await close_writer(remote_writer)
        await close_writer(writer)


async def connect(host: str, port: int, target_host: str, target_port: int,
                  password: str, method: str = "aes-256-gcm", ssl=None) -> SSStream:
    """Open a Shadowsocks connection and return a plaintext-like stream."""
    method_info(method)  # validate
    reader, writer = await asyncio.open_connection(host, port, ssl=ssl)
    ss = await SSStream.connect(reader, writer, method, password)
    await ss.write_plain(encode_ss_address(target_host, target_port))
    return ss
