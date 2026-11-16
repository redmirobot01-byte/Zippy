"""Address encoders/decoders for Shadowsocks (SOCKS5 style) and VLESS.

Shadowsocks:  ATYP | address | PORT(be)
              1=IPv4, 3=domain(1-byte len), 4=IPv6

VLESS (Xray): PORT(be) | ATYP | address
              1=IPv4, 2=domain(1-byte len), 3=IPv6
Source: XTLS/Xray-core common/protocol/address.go + payload.go
"""
from __future__ import annotations

import ipaddress

from .common import ProtocolError, read_exact


def encode_ss_address(host: str, port: int) -> bytes:
    port_b = port.to_bytes(2, "big")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            raw = host.encode("idna")
        except UnicodeError as exc:
            raise ProtocolError(f"bad hostname {host!r}") from exc
        if not raw or len(raw) > 255:
            raise ProtocolError("bad hostname length")
        return b"\x03" + bytes([len(raw)]) + raw + port_b
    return (b"\x01" if ip.version == 4 else b"\x04") + ip.packed + port_b


async def read_ss_address(src) -> tuple[str, int]:
    """src must expose async read_plain(n) -> bytes (see stream.SSStream)."""
    atyp = (await src.read_plain(1))[0]
    if atyp == 1:
        host = str(ipaddress.IPv4Address(await src.read_plain(4)))
    elif atyp == 4:
        host = str(ipaddress.IPv6Address(await src.read_plain(16)))
    elif atyp == 3:
        n = (await src.read_plain(1))[0]
        if n == 0:
            raise ProtocolError("empty domain")
        host = (await src.read_plain(n)).decode("idna")
    else:
        raise ProtocolError(f"unknown shadowsocks ATYP {atyp}")
    port = int.from_bytes(await src.read_plain(2), "big")
    return host, port


def encode_vless_address(host: str, port: int) -> bytes:
    port_b = port.to_bytes(2, "big")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            raw = host.encode("idna")
        except UnicodeError as exc:
            raise ProtocolError(f"bad hostname {host!r}") from exc
        if not raw or len(raw) > 255:
            raise ProtocolError("bad hostname length")
        return port_b + b"\x02" + bytes([len(raw)]) + raw
    return port_b + (b"\x01" if ip.version == 4 else b"\x03") + ip.packed


async def read_vless_address(reader) -> tuple[str, int]:
    port = int.from_bytes(await read_exact(reader, 2), "big")
    atyp = (await read_exact(reader, 1))[0]
    if atyp == 1:
        host = str(ipaddress.IPv4Address(await read_exact(reader, 4)))
    elif atyp == 3:
        host = str(ipaddress.IPv6Address(await read_exact(reader, 16)))
    elif atyp == 2:
        n = (await read_exact(reader, 1))[0]
        if n == 0:
            raise ProtocolError("empty domain")
        host = (await read_exact(reader, n)).decode("idna")
    else:
        raise ProtocolError(f"unknown VLESS address type {atyp}")
    return host, port
