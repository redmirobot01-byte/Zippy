"""Share-link / subscription generation (v2rayNG, Hiddify, NekoBox, Shadowrocket)."""
from __future__ import annotations

import base64
import json
from urllib.parse import quote, urlencode

from . import vless


def _host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def ss_sip002(method: str, password: str, host: str, port: int,
              name: str = "Zippy") -> str:
    """SIP002: ss://BASE64URL(method:password)@host:port#tag"""
    userinfo = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode().rstrip("=")
    return f"ss://{userinfo}@{_host(host)}:{port}#{quote(name)}"


def ss_legacy(method: str, password: str, host: str, port: int,
              name: str = "Zippy") -> str:
    """Legacy whole-string base64, for older clients."""
    raw = f"{method}:{password}@{host}:{port}".encode()
    return "ss://" + base64.urlsafe_b64encode(raw).decode().rstrip("=") + f"#{quote(name)}"


def vless_link(cfg: dict) -> str:
    v = cfg["vless"]
    return vless.share_link(
        v["uuid"], cfg["host"], int(v["port"]),
        security="tls" if v.get("tls") else "none",
        sni=v.get("sni"),
        name="Zippy VLESS",
    )


def all_links(cfg: dict) -> list[dict]:
    out: list[dict] = []
    ss = cfg.get("shadowsocks", {})
    if ss.get("enabled", True):
        out.append({
            "protocol": "shadowsocks",
            "name": "Zippy Shadowsocks (aes-256-gcm)",
            "url": ss_sip002(ss.get("method", "aes-256-gcm"), ss["password"],
                             cfg["host"], int(ss["port"])),
            "fallback": ss_legacy(ss.get("method", "aes-256-gcm"), ss["password"],
                                  cfg["host"], int(ss["port"])),
        })
    v = cfg.get("vless", {})
    if v.get("enabled", True):
        out.append({
            "protocol": "vless",
            "name": "Zippy VLESS" + (" (TLS)" if v.get("tls") else " (plain)"),
            "url": vless_link(cfg),
        })
    return out


def subscription_text(cfg: dict) -> str:
    """Base64 subscription (one link per line) importable by most clients."""
    plain = "\n".join(x["url"] for x in all_links(cfg)) + "\n"
    return base64.b64encode(plain.encode()).decode()


def xray_client_json(cfg: dict) -> str:
    """Minimal Xray / v2rayN client config for desktop use."""
    outbounds = []
    ss = cfg.get("shadowsocks", {})
    if ss.get("enabled", True):
        outbounds.append({
            "tag": "zippy-ss",
            "protocol": "shadowsocks",
            "settings": {"servers": [{
                "address": cfg["host"],
                "port": int(ss["port"]),
                "method": ss.get("method", "aes-256-gcm"),
                "password": ss["password"],
                "ota": False,
            }]},
        })
    v = cfg.get("vless", {})
    if v.get("enabled", True):
        stream = {"network": "tcp"}
        if v.get("tls"):
            stream["security"] = "tls"
            stream["tlsSettings"] = {
                "serverName": v.get("sni") or cfg["host"],
                "allowInsecure": True,
                "fingerprint": "chrome",
            }
        outbounds.append({
            "tag": "zippy-vless",
            "protocol": "vless",
            "settings": {"vnext": [{
                "address": cfg["host"],
                "port": int(v["port"]),
                "users": [{"id": v["uuid"], "encryption": "none",
                           "flow": ""}],
            }]},
            "streamSettings": stream,
        })
    return json.dumps({
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "tag": "socks-in",
            "listen": "127.0.0.1",
            "port": 10808,
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True},
        }],
        "outbounds": outbounds,
        "routing": {"rules": [], "domainStrategy": "AsIs"},
    }, indent=2)
