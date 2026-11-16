"""Configuration handling for Zippy VPN."""
from __future__ import annotations

import json
import os
import secrets
import uuid
from pathlib import Path

DEFAULT_CONFIG_PATH = "zippy.json"


def default_config(host: str = "127.0.0.1", *, ss_port: int = 8388,
                   vless_port: int = 8443, tls: bool = False,
                   allow_private: bool = False) -> dict:
    return {
        "host": host,                    # public IP / domain used inside share links
        "listen": "0.0.0.0",
        "allow_private": allow_private,  # allow connecting to LAN/loopback targets
        "shadowsocks": {
            "enabled": True,
            "port": ss_port,
            "method": "aes-256-gcm",
            "password": secrets.token_urlsafe(24),
        },
        "vless": {
            "enabled": True,
            "port": vless_port,
            "uuid": str(uuid.uuid4()),
            "tls": tls,
            "cert": "certs/server.crt",
            "key": "certs/server.key",
        },
    }


def load(path: str | os.PathLike = DEFAULT_CONFIG_PATH) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p} (run: python -m zippy init --host IP)")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg.setdefault("listen", "0.0.0.0")
    cfg.setdefault("allow_private", False)
    cfg.setdefault("shadowsocks", {})
    cfg.setdefault("vless", {})
    cfg["_path"] = str(p.resolve())
    return cfg


def save(cfg: dict, path: str | os.PathLike = DEFAULT_CONFIG_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    p.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def resolve(cfg: dict, value: str) -> str:
    """Resolve relative cert/key paths against the config file location."""
    p = Path(value)
    if p.is_absolute():
        return str(p)
    base = Path(cfg.get("_path", DEFAULT_CONFIG_PATH)).resolve().parent
    return str(base / p)
