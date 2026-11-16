"""Shared helpers: exact reads, safe outbound connects and bidirectional relay."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket

log = logging.getLogger("zippy")


class ProtocolError(Exception):
    """Malformed or unauthorised client traffic."""


async def read_exact(reader: asyncio.StreamReader, n: int) -> bytes:
    """Read exactly n bytes. Raises EOFError on a clean EOF."""
    if n < 0:
        raise ProtocolError("negative length")
    if n == 0:
        return b""
    try:
        return await reader.readexactly(n)
    except asyncio.IncompleteReadError as exc:
        raise EOFError(f"peer closed after {len(exc.partial)}/{n} bytes") from exc


async def open_remote(host: str, port: int, allow_private: bool) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to the requested target, optionally blocking SSRF to private nets."""
    if not host or not (1 <= port <= 65535):
        raise ProtocolError(f"invalid target {host!r}:{port}")
    if not allow_private:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ProtocolError(f"DNS lookup failed for {host!r}") from exc
        for info in infos:
            try:
                ip = ipaddress.ip_address(info[4][0])
            except ValueError:
                continue
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise ProtocolError(f"refusing private target {host!r} ({ip})")
    return await asyncio.open_connection(host, port)


async def raw_relay(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    remote_reader: asyncio.StreamReader,
    remote_writer: asyncio.StreamWriter,
) -> None:
    """Plain bidirectional copy with proper half-close."""

    async def up() -> None:
        try:
            while True:
                data = await client_reader.read(65536)
                if not data:
                    break
                remote_writer.write(data)
                await remote_writer.drain()
            if remote_writer.can_write_eof():
                remote_writer.write_eof()
        except (ConnectionError, OSError):
            pass

    async def down() -> None:
        try:
            while True:
                data = await remote_reader.read(65536)
                if not data:
                    break
                client_writer.write(data)
                await client_writer.drain()
            try:
                if client_writer.can_write_eof():
                    client_writer.write_eof()
            except (NotImplementedError, OSError, ConnectionError):
                pass
        except (ConnectionError, OSError):
            pass
        finally:
            # Unblocks up() when the target closed first (TLS transports often
            # cannot signal EOF via write_eof).
            client_writer.close()

    await asyncio.gather(up(), down())


async def close_writer(writer: asyncio.StreamWriter) -> None:
    try:
        writer.close()
        await writer.wait_closed()
    except (ConnectionError, OSError, asyncio.CancelledError):
        pass


def is_bad_error(exc: BaseException) -> bool:
    return isinstance(exc, (EOFError, ProtocolError, asyncio.IncompleteReadError,
                            ConnectionError, OSError, ValueError, asyncio.TimeoutError))
