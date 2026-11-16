"""Two-stage live server verifier: asyncio TCP/TLS + Xray-core real proxy testing."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import time

from .models import VALID_COUNTRY_CODES, ProxyNode
from .parser import validate_host
from .xray_config import build_xray_batch_test_config


def _create_tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


async def _resolve_safe_ip(host: str, port: int, timeout: float = 3.5) -> str | None:
    """Resolve host and ensure all returned IPs are safe public addresses (no DNS rebinding)."""
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, port, type=socket.SOCK_STREAM),
            timeout=timeout,
        )
    except Exception:
        return None
    if not infos:
        return None
    chosen: str | None = None
    for info in infos:
        ip_str = info[4][0]
        if validate_host(ip_str) is None:
            return None
        if chosen is None:
            chosen = ip_str
    return chosen


async def _probe_single_tcp_tls(
    node: ProxyNode,
    sem: asyncio.Semaphore,
    tls_ctx: ssl.SSLContext,
    timeout: float,
) -> ProxyNode | None:
    async with sem:
        resolved_ip = await _resolve_safe_ip(node.host, node.port, timeout=min(timeout, 3.5))
        if not resolved_ip:
            return None

        # Hysteria2 runs over UDP/QUIC; keep validated public-DNS HY2 nodes with optional 443 check
        if node.protocol == "hy2":
            start = time.monotonic()
            writer = None
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        resolved_ip,
                        node.port,
                        ssl=tls_ctx if node.sni and not node.pin_sha256 else None,
                        server_hostname=node.sni if (node.sni and not node.pin_sha256) else None,
                    ),
                    timeout=timeout,
                )
                rtt = max(1, int((time.monotonic() - start) * 1000))
                node.latency_ms = rtt
                node.check_method = "tls"
            except Exception:
                # Pure UDP Hysteria2 servers don't listen on TCP; mark DNS-verified
                node.check_method = "source"
            finally:
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
            return node

        use_tls = node.security == "tls" and bool(node.sni)
        writer = None
        start = time.monotonic()
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    resolved_ip,
                    node.port,
                    ssl=tls_ctx if use_tls else None,
                    server_hostname=node.sni if use_tls else None,
                ),
                timeout=timeout,
            )
            elapsed_ms = max(1, int((time.monotonic() - start) * 1000))
            if elapsed_ms > int(timeout * 1000):
                return None
            node.latency_ms = elapsed_ms
            node.check_method = "tls" if use_tls else "tcp"
            return node
        except Exception:
            return None
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass


async def check_nodes_tcp_tls(
    nodes: list[ProxyNode],
    concurrency: int = 40,
    timeout: float = 4.5,
) -> list[ProxyNode]:
    """Filter nodes via concurrent DNS safety + TCP/TLS handshake latency probes."""
    if not nodes:
        return []
    sem = asyncio.Semaphore(max(1, concurrency))
    tls_ctx = _create_tls_context()
    tasks = [_probe_single_tcp_tls(n, sem, tls_ctx, timeout) for n in nodes]
    results = await asyncio.gather(*tasks)
    return [n for n in results if n is not None]


async def _socks5_http_get(
    socks_port: int,
    target_host: str,
    target_port: int,
    path: str,
    timeout: float,
) -> tuple[int, str, int] | None:
    """Perform an HTTP/1.1 GET through a local no-auth SOCKS5 proxy; returns (status, body, ms)."""
    writer = None
    host_bytes = target_host.encode("ascii")
    start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", socks_port),
            timeout=min(timeout, 3.0),
        )
        # SOCKS5 greeting: ver=5, nmethods=1, method=0 (no auth)
        writer.write(b"\x05\x01\x00")
        await writer.drain()
        greet = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
        if greet != b"\x05\x00":
            return None

        # SOCKS5 CONNECT domain request: ver=5, cmd=1, rsv=0, atyp=3 (domain)
        req = (
            b"\x05\x01\x00\x03"
            + bytes([len(host_bytes)])
            + host_bytes
            + struct.pack("!H", target_port)
        )
        writer.write(req)
        await writer.drain()

        # Measure real proxy handshake + HTTP round-trip from CONNECT send
        proxy_start = time.monotonic()
        head = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
        if head[0] != 5 or head[1] != 0:
            return None
        atyp = head[3]
        if atyp == 1:
            await asyncio.wait_for(reader.readexactly(4 + 2), timeout=timeout)
        elif atyp == 3:
            dlen = (await asyncio.wait_for(reader.readexactly(1), timeout=timeout))[0]
            await asyncio.wait_for(reader.readexactly(dlen + 2), timeout=timeout)
        elif atyp == 4:
            await asyncio.wait_for(reader.readexactly(16 + 2), timeout=timeout)
        else:
            return None

        http_req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {target_host}\r\n"
            f"User-Agent: Mozilla/5.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii")
        writer.write(http_req)
        await writer.drain()

        raw_resp = await asyncio.wait_for(reader.read(2048), timeout=timeout)
        elapsed_ms = max(1, int((time.monotonic() - proxy_start) * 1000))
        if not raw_resp:
            return None
        text = raw_resp.decode("utf-8", errors="ignore")
        first_line = text.split("\r\n", 1)[0]
        parts = first_line.split(" ", 2)
        if len(parts) < 2 or not parts[0].startswith("HTTP/"):
            return None
        status = int(parts[1])
        body = text.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in text else ""
        _ = start
        return status, body, elapsed_ms
    except Exception:
        return None
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def _wait_local_port(port: int, timeout: float = 4.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port),
                timeout=0.3,
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            await asyncio.sleep(0.1)
    return False


async def _probe_xray_slot(
    port: int,
    node: ProxyNode,
    sem: asyncio.Semaphore,
    timeout: float,
) -> ProxyNode | None:
    async with sem:
        res = await _socks5_http_get(
            socks_port=port,
            target_host="www.gstatic.com",
            target_port=80,
            path="/generate_204",
            timeout=timeout,
        )
        if res is None or res[0] != 204:
            # Fallback check via Cloudflare generate_204
            res = await _socks5_http_get(
                socks_port=port,
                target_host="cp.cloudflare.com",
                target_port=80,
                path="/generate_204",
                timeout=timeout,
            )
            if res is None or res[0] != 204:
                return None

        node.latency_ms = res[2]
        node.check_method = "xray"

        # Detect true exit country code if unknown
        if node.country == "UN":
            trace = await _socks5_http_get(
                socks_port=port,
                target_host="cp.cloudflare.com",
                target_port=80,
                path="/cdn-cgi/trace",
                timeout=min(timeout, 4.0),
            )
            if trace and trace[0] == 200:
                for line in trace[1].splitlines():
                    if line.startswith("loc="):
                        loc = line[4:].strip().upper()
                        if loc in VALID_COUNTRY_CODES:
                            node.country = loc
                        break
        return node


async def _run_xray_batch(
    xray_bin: str,
    batch: list[ProxyNode],
    base_port: int,
    concurrency: int,
    timeout: float,
) -> list[ProxyNode]:
    cfg, port_map = build_xray_batch_test_config(batch, base_port=base_port)
    if not port_map:
        return []

    with tempfile.TemporaryDirectory(prefix="zippy-xray-") as tmpdir:
        cfg_path = Path(tmpdir) / "config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        proc = subprocess.Popen(
            [xray_bin, "run", "-c", str(cfg_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            ready = await _wait_local_port(port_map[0][1], timeout=4.0)
            if not ready or proc.poll() is not None:
                return []
            sem = asyncio.Semaphore(max(1, concurrency))
            tasks = [
                _probe_xray_slot(port=port, node=node, sem=sem, timeout=timeout)
                for _, port, node in port_map
            ]
            results = await asyncio.gather(*tasks)
            return [n for n in results if n is not None]
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)


async def check_nodes_xray(
    nodes: list[ProxyNode],
    xray_bin: str | None = None,
    concurrency: int = 35,
    tcp_timeout: float = 4.0,
    proxy_timeout: float = 6.5,
    batch_size: int = 50,
) -> list[ProxyNode]:
    """Two-stage verifier: fast TCP/TLS pre-filter followed by real Xray 204 proxy checks."""
    if not nodes:
        return []

    # Stage 1: DNS rebinding check + TCP/TLS reachability
    alive = await check_nodes_tcp_tls(nodes, concurrency=concurrency, timeout=tcp_timeout)
    if not alive:
        return []

    resolved_xray = xray_bin or shutil.which("xray")
    if not resolved_xray:
        return alive

    xray_candidates = [
        n for n in alive
        if n.protocol in {"vless", "trojan", "vmess", "ss"} and n.transport != "h2"
    ]
    non_xray_alive = [n for n in alive if n.protocol == "hy2"]

    verified: list[ProxyNode] = []
    for offset in range(0, len(xray_candidates), batch_size):
        chunk = xray_candidates[offset: offset + batch_size]
        passed = await _run_xray_batch(
            xray_bin=resolved_xray,
            batch=chunk,
            base_port=24000,
            concurrency=min(concurrency, len(chunk)),
            timeout=proxy_timeout,
        )
        verified.extend(passed)

    # Combine Xray-verified nodes with DNS/TLS-validated Hysteria2 (QUIC/UDP) nodes
    hy2_tls = [n for n in non_xray_alive if n.check_method == "tls"]
    hy2_udp = [n for n in non_xray_alive if n.check_method != "tls"][:25]
    verified.extend(hy2_tls)
    verified.extend(hy2_udp)
    return verified
