"""Xray-core configuration builders for live node verification and Happ Fragment mode."""

from __future__ import annotations

from typing import Any

from .models import ProxyNode


def _build_stream_settings(node: ProxyNode, with_fragment: bool = False) -> dict[str, Any]:
    net = node.transport
    if net == "h2":
        net = "http"

    stream: dict[str, Any] = {"network": net}

    if node.security == "reality":
        stream["security"] = "reality"
        stream["realitySettings"] = {
            "show": False,
            "fingerprint": node.fp or "chrome",
            "serverName": node.sni,
            "publicKey": node.pbk,
            "shortId": node.sid or "",
            "spiderX": node.spx or "/",
        }
    elif node.security == "tls":
        tls_cfg: dict[str, Any] = {
            "serverName": node.sni,
            "allowInsecure": False,
            "fingerprint": node.fp or "chrome",
        }
        if node.alpn:
            tls_cfg["alpn"] = [a.strip() for a in node.alpn.split(",") if a.strip()]
        stream["security"] = "tls"
        stream["tlsSettings"] = tls_cfg
    else:
        stream["security"] = "none"

    if net == "ws":
        ws_cfg: dict[str, Any] = {"path": node.path or "/"}
        if node.host_header:
            ws_cfg["headers"] = {"Host": node.host_header}
        stream["wsSettings"] = ws_cfg
    elif net == "grpc":
        stream["grpcSettings"] = {
            "serviceName": node.service_name or "",
            "multiMode": node.mode == "multi",
        }
    elif net == "xhttp":
        xhttp_cfg: dict[str, Any] = {
            "path": node.path or "/",
            "mode": node.mode or "auto",
        }
        if node.host_header:
            xhttp_cfg["host"] = node.host_header
        stream["xhttpSettings"] = xhttp_cfg
    elif net == "httpupgrade":
        hu_cfg: dict[str, Any] = {"path": node.path or "/"}
        if node.host_header:
            hu_cfg["host"] = node.host_header
        stream["httpupgradeSettings"] = hu_cfg
    elif net == "http":
        http_cfg: dict[str, Any] = {"path": node.path or "/"}
        if node.host_header:
            http_cfg["host"] = [node.host_header]
        stream["httpSettings"] = http_cfg

    if with_fragment:
        stream["sockopt"] = {
            "dialerProxy": "fragment",
            "tcpKeepAliveIdle": 100,
            "tcpNoDelay": True,
        }

    return stream


def node_to_xray_outbound(
    node: ProxyNode,
    tag: str = "proxy",
    with_fragment: bool = False,
) -> dict[str, Any] | None:
    """Convert a ProxyNode into an Xray-core outbound dict (None if not Xray-native)."""
    if node.protocol == "h2" or node.transport == "h2":
        # Xray v25+ removed standalone HTTP/2 transport; skip in Xray JSON
        return None

    if node.protocol == "vless":
        user: dict[str, Any] = {
            "id": node.credential,
            "encryption": "none",
        }
        if node.flow and node.transport == "tcp":
            user["flow"] = node.flow
        return {
            "tag": tag,
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": node.host,
                    "port": node.port,
                    "users": [user],
                }]
            },
            "streamSettings": _build_stream_settings(node, with_fragment=with_fragment),
        }

    if node.protocol == "trojan":
        return {
            "tag": tag,
            "protocol": "trojan",
            "settings": {
                "servers": [{
                    "address": node.host,
                    "port": node.port,
                    "password": node.credential,
                }]
            },
            "streamSettings": _build_stream_settings(node, with_fragment=with_fragment),
        }

    if node.protocol == "vmess":
        return {
            "tag": tag,
            "protocol": "vmess",
            "settings": {
                "vnext": [{
                    "address": node.host,
                    "port": node.port,
                    "users": [{
                        "id": node.credential,
                        "alterId": 0,
                        "security": node.method or "auto",
                    }],
                }]
            },
            "streamSettings": _build_stream_settings(node, with_fragment=with_fragment),
        }

    if node.protocol == "ss":
        return {
            "tag": tag,
            "protocol": "shadowsocks",
            "settings": {
                "servers": [{
                    "address": node.host,
                    "port": node.port,
                    "method": node.method,
                    "password": node.credential,
                }]
            },
            "streamSettings": {"network": "tcp", "security": "none"},
        }

    return None


def build_xray_batch_test_config(
    nodes: list[ProxyNode],
    base_port: int = 24000,
) -> tuple[dict[str, Any], list[tuple[int, int, ProxyNode]]]:
    """Build a single Xray config exposing each candidate node on its own loopback SOCKS5 port."""
    inbounds: list[dict[str, Any]] = []
    outbounds: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    port_map: list[tuple[int, int, ProxyNode]] = []

    slot = 0
    for idx, node in enumerate(nodes):
        out_tag = f"out-{idx}"
        outbound = node_to_xray_outbound(node, tag=out_tag, with_fragment=False)
        if outbound is None:
            continue
        port = base_port + slot
        slot += 1
        in_tag = f"in-{idx}"
        inbounds.append({
            "tag": in_tag,
            "listen": "127.0.0.1",
            "port": port,
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": False},
        })
        outbounds.append(outbound)
        rules.append({
            "type": "field",
            "inboundTag": [in_tag],
            "outboundTag": out_tag,
        })
        port_map.append((idx, port, node))

    outbounds.append({"tag": "block", "protocol": "blackhole"})
    config: dict[str, Any] = {
        "log": {"loglevel": "none"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": {
            "domainStrategy": "AsIs",
            "rules": rules,
        },
    }
    return config, port_map


def build_happ_fragment_config(node: ProxyNode, remarks: str) -> dict[str, Any] | None:
    """Build a complete Happ-compatible Xray JSON config with TLS Hello fragmentation."""
    if not node.supports_fragment():
        return None
    proxy_outbound = node_to_xray_outbound(node, tag="proxy", with_fragment=True)
    if proxy_outbound is None:
        return None

    return {
        "remarks": remarks,
        "log": {"loglevel": "warning"},
        "dns": {
            "servers": [
                "https://1.1.1.1/dns-query",
                "https://8.8.8.8/dns-query",
                "1.1.1.1",
            ],
            "queryStrategy": "UseIPv4",
        },
        "inbounds": [
            {
                "tag": "socks",
                "port": 10808,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                    "routeOnly": True,
                },
                "settings": {"auth": "noauth", "udp": True},
            },
            {
                "tag": "http",
                "port": 10809,
                "listen": "127.0.0.1",
                "protocol": "http",
                "settings": {"allowTransparent": False},
            },
        ],
        "outbounds": [
            proxy_outbound,
            {
                "tag": "fragment",
                "protocol": "freedom",
                "settings": {
                    "domainStrategy": "UseIP",
                    "fragment": {
                        "packets": "tlshello",
                        "length": "100-200",
                        "interval": "10-20",
                    },
                },
                "streamSettings": {
                    "sockopt": {
                        "tcpNoDelay": True,
                        "tcpKeepAliveIdle": 100,
                    }
                },
            },
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {
                    "type": "field",
                    "ip": [
                        "10.0.0.0/8",
                        "172.16.0.0/12",
                        "192.168.0.0/16",
                        "127.0.0.0/8",
                        "169.254.0.0/16",
                        "fc00::/7",
                        "fe80::/10",
                        "::1/128",
                    ],
                    "outboundTag": "direct",
                },
                {
                    "type": "field",
                    "network": "tcp,udp",
                    "outboundTag": "proxy",
                },
            ],
        },
    }


def build_happ_fragment_subscription(
    nodes: list[ProxyNode],
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Build an Xray JSON array subscription of top Fragment-capable nodes for Happ."""
    configs: list[dict[str, Any]] = []
    for node in nodes:
        if len(configs) >= limit:
            break
        label = node.format_label(len(configs) + 1, prefix="🛡️ ")
        cfg = build_happ_fragment_config(node, remarks=label)
        if cfg is not None:
            configs.append(cfg)
    return configs
