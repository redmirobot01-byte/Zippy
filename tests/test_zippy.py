"""Zippy test suite: `pytest -q` (or `python -m zippy selftest`)."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from zippy import config, crypto, links, selftest, subs, verify


def test_end_to_end_all_protocols():
    results = asyncio.run(selftest.run(verbose=False))
    assert len(results) == 9
    assert all(v == "OK" for v in results.values()), results


def test_bytes_to_key():
    assert crypto.bytes_to_key(b"password", 16) == hashlib.md5(b"password").digest()
    assert len(crypto.bytes_to_key(b"password", 32)) == 32
    first = hashlib.md5(b"password").digest()
    second = hashlib.md5(first + b"password").digest()
    assert crypto.bytes_to_key(b"password", 32) == first + second


def test_hkdf_sha1_matches_cryptography():
    """Our HKDF-SHA1 (used for the Shadowsocks subkey) vs. an independent lib."""
    ikm, salt, info, length = b"master-key-material", b"0123456789abcdef", b"ss-subkey", 32
    ours = crypto.hkdf_sha1(ikm, salt, info, length)
    theirs = HKDF(algorithm=hashes.SHA1(), length=length, salt=salt, info=info).derive(ikm)
    assert ours == theirs


def test_aead_stream_roundtrip_all_methods():
    for method, (_family, key_len) in crypto.METHODS.items():
        salt = bytes(range(key_len))
        a = crypto.AeadCipher(method, "parol-123", salt)
        b = crypto.AeadCipher(method, "parol-123", salt)
        for n in (0, 1, 17, 16383):
            plain = bytes((i * 13) & 0xFF for i in range(n))
            assert b.decrypt(a.encrypt(plain)) == plain
        assert a._counter == b._counter


def test_share_links_parse_back():
    cfg = config.default_config("203.0.113.9", ss_port=8388, vless_port=8443)
    items = links.all_links(cfg)
    assert len(items) == 2
    ss = subs.parse_link(items[0]["url"])
    assert ss["proto"] == "ss" and ss["host"] == "203.0.113.9" and ss["port"] == 8388
    assert ss["method"] == "aes-256-gcm"
    vl = subs.parse_link(items[1]["url"])
    assert vl["proto"] == "vless" and vl["host"] == "203.0.113.9" and vl["port"] == 8443
    q = urllib.parse.parse_qs(urllib.parse.urlparse(items[1]["url"]).query)
    assert q["encryption"] == ["none"] and q["security"] == ["none"]

    cfg["vless"]["tls"] = True
    tls_link = links.vless_link(cfg)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(tls_link).query)
    assert q["security"] == ["tls"] and q["allowInsecure"] == ["1"]


def test_subscription_roundtrip():
    cfg = config.default_config("198.51.100.4")
    text = links.subscription_text(cfg)
    decoded = base64.b64decode(text).decode().splitlines()
    assert decoded == [x["url"] for x in links.all_links(cfg)]
    assert subs.decode_subscription(text) == decoded


def test_xray_client_config_valid_json():
    cfg = config.default_config("198.51.100.4", tls=True)
    data = json.loads(links.xray_client_json(cfg))
    assert len(data["outbounds"]) == 2
    assert data["outbounds"][1]["streamSettings"]["security"] == "tls"


def test_public_sources_are_well_formed():
    assert len(subs.SOURCES) >= 5
    for s in subs.SOURCES:
        assert s.repo and s.branch and s.path
        assert s.raw_url.startswith("https://raw.githubusercontent.com/")
        assert "github.com" in s.api_url


def test_vless_link_parser_handles_ipv6():
    cfg = config.default_config("2001:db8::1")
    url = links.vless_link(cfg)
    assert "@[2001:db8::1]:" in url
    assert subs.parse_link(url)["host"] == "2001:db8::1"


def test_verifier_detects_real_working_nodes():
    """Verifier must actually complete a Shadowsocks AND a VLESS handshake."""
    results = asyncio.run(verify.self_test())
    assert len(results) == 2
    assert all(r.level == "full" for r in results), [r.detail for r in results]
    assert {r.proto for r in results} == {"ss", "vless"}


def test_worker_link_and_client_config():
    uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    url = links.worker_vless_link("zippy-test.example.workers.dev", uid, "/ws")
    info = subs.parse_link(url)
    assert info["proto"] == "vless"
    assert info["host"] == "zippy-test.example.workers.dev"
    assert info["port"] == 443
    assert info["security"] == "tls" and info["type"] == "ws"
    assert urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["path"] == ["/ws"]
    client = json.loads(links.worker_client_json(info["host"], uid, "/ws"))
    assert client["outbounds"][0]["streamSettings"]["network"] == "ws"


def test_cloudflare_worker_node_tests():
    """The Worker JS is exercised end-to-end with mocked Cloudflare APIs."""
    if not shutil.which("node"):
        return
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(["node", "tests/worker_test.mjs"], cwd=root,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "5/5" in proc.stdout
