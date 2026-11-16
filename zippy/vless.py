"""VLESS (Xray-core compatible) TCP inbound, with optional TLS.

Request header (client -> server):
    ver(1)=0 | uuid(16) | addons_len(1) | addons | cmd(1) | port(2) | atyp(1) | addr
Response header (server -> client):
    ver(1)=0 | addons_len(1) | addons

cmd 0x01 = TCP (supported), 0x02 = UDP, 0x03 = Mux, 0x04 = Rvs.
Source: XTLS/Xray-core proxy/vless/encoding/{encoding,addons}.go,
        common/protocol/{headers,address,payload}.go
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import uuid as uuidlib
from urllib.parse import quote

from .address import encode_vless_address, read_vless_address
from .common import (ProtocolError, close_writer, is_bad_error, open_remote,
                     raw_relay, read_exact)

log = logging.getLogger("zippy.vless")


def _allowed_uuids(cfg: dict) -> list[bytes]:
    values = cfg.get("uuids") or ([cfg["uuid"]] if cfg.get("uuid") else [])
    out = []
    for value in values:
        try:
            out.append(uuidlib.UUID(str(value)).bytes)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(f"invalid UUID in config: {value!r}") from exc
    if not out:
        raise ValueError("VLESS inbound needs at least one uuid")
    return out


async def handle_client(reader, writer, cfg: dict) -> None:
    allowed = _allowed_uuids(cfg)
    allow_private = bool(cfg.get("allow_private", False))
    remote_writer = None
    try:
        async with asyncio.timeout(30):
            version = (await read_exact(reader, 1))[0]
            if version != 0:
                raise ProtocolError(f"unsupported VLESS version {version}")
            peer_uuid = await read_exact(reader, 16)
            if not any(hmac.compare_digest(peer_uuid, u) for u in allowed):
                raise ProtocolError("unknown VLESS UUID")
            addons_len = (await read_exact(reader, 1))[0]
            if addons_len:
                await read_exact(reader, addons_len)
            cmd = (await read_exact(reader, 1))[0]
            if cmd != 1:
                raise ProtocolError(f"unsupported VLESS command {cmd} (only TCP)")
            host, port = await read_vless_address(reader)
        remote_reader, remote_writer = await open_remote(host, port, allow_private)
        log.info("vless -> %s:%s", host, port)

        writer.write(b"\x00\x00")  # version + zero-length addons
        await writer.drain()
        await raw_relay(reader, writer, remote_reader, remote_writer)
    except Exception as exc:
        if not is_bad_error(exc):
            log.exception("vless handler error")
        elif isinstance(exc, ProtocolError):
            log.debug("rejected VLESS client: %s", exc)
    finally:
        if remote_writer is not None:
            await close_writer(remote_writer)
        await close_writer(writer)


async def connect(host: str, port: int, target_host: str, target_port: int,
                  user_uuid: str, ssl=None):
    """Open a VLESS connection; returns (reader, writer) with headers done."""
    uid = uuidlib.UUID(str(user_uuid)).bytes
    header = (
        b"\x00" + uid + b"\x00" + b"\x01"
        + encode_vless_address(target_host, target_port)
    )
    reader, writer = await asyncio.open_connection(host, port, ssl=ssl)
    writer.write(header)
    await writer.drain()
    version = (await read_exact(reader, 1))[0]
    if version != 0:
        await close_writer(writer)
        raise ProtocolError(f"unexpected VLESS response version {version}")
    addons_len = (await read_exact(reader, 1))[0]
    if addons_len:
        await read_exact(reader, addons_len)
    return reader, writer


def share_link(user_uuid: str, host: str, port: int, *, security: str = "none",
               sni: str | None = None, name: str = "Zippy") -> str:
    from urllib.parse import urlencode
    params = {"encryption": "none", "security": security, "type": "tcp"}
    if security == "tls":
        params.update({"sni": sni or host, "fp": "chrome", "allowInsecure": "1"})
    h = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"vless://{user_uuid}@{h}:{port}?{urlencode(params)}#{quote(name)}"
