"""Comprehensive unit and integration test suite for Zippy VPN."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest

from zippy.exporter import export_all_subscriptions
from zippy.models import country_flag, detect_country, mask_host
from zippy.parser import (
    decode_subscription_text,
    deduplicate_and_rank,
    parse_uri,
    serialize_uri,
    validate_host,
    validate_sni,
)
from zippy.xray_config import (
    build_happ_fragment_subscription,
    build_xray_batch_test_config,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PBK = base64.urlsafe_b64encode(b"\x11" * 32).decode("ascii").rstrip("=")
SAMPLE_SS2022_16 = base64.b64encode(b"\x22" * 16).decode("ascii")
SAMPLE_SS2022_32 = base64.b64encode(b"\x33" * 32).decode("ascii")


class TestSecurityAndValidation(unittest.TestCase):
    def test_rejects_private_and_reserved_hosts(self) -> None:
        blocked = [
            "127.0.0.1",
            "0.0.0.0",
            "10.0.0.5",
            "172.16.5.4",
            "192.168.1.1",
            "169.254.169.254",
            "100.64.10.20",
            "::1",
            "fe80::1",
            "fc00::1",
            "localhost",
            "server.local",
            "bad.onion",
            "fake.rkn",
            "1.1.1.1",
            "8.8.8.8",
        ]
        for host in blocked:
            self.assertIsNone(validate_host(host), f"Expected {host} to be rejected")

    def test_accepts_valid_public_hosts(self) -> None:
        self.assertEqual(validate_host("185.220.101.42"), "185.220.101.42")
        self.assertEqual(validate_host("DE1.Example-Vpn.NET."), "de1.example-vpn.net")
        self.assertEqual(validate_host("[2606:4700:4700::1002]"), "2606:4700:4700::1002")

    def test_sni_validation(self) -> None:
        self.assertEqual(validate_sni("www.cloudflare.com"), "www.cloudflare.com")
        self.assertIsNone(validate_sni("185.220.101.42"))
        self.assertIsNone(validate_sni("fuck.rkn"))
        self.assertIsNone(validate_sni("box.internal"))

    def test_rejects_insecure_and_plaintext_configs(self) -> None:
        # allowInsecure=1 must be rejected
        insecure_vless = (
            "vless://711c018e-2692-4aa8-93f3-544d83fcd16c@185.220.101.42:443"
            "?security=tls&sni=cdn.example.net&allowInsecure=1&type=ws&path=/ws#DE"
        )
        self.assertIsNone(parse_uri(insecure_vless))

        # Plain unencrypted vless must be rejected
        plain_vless = (
            "vless://711c018e-2692-4aa8-93f3-544d83fcd16c@185.220.101.42:80"
            "?security=none&type=ws&path=/ws#DE"
        )
        self.assertIsNone(parse_uri(plain_vless))

        # Nil UUID must be rejected
        nil_vless = (
            f"vless://00000000-0000-0000-0000-000000000000@185.220.101.42:443"
            f"?security=reality&sni=www.apple.com&pbk={SAMPLE_PBK}&type=tcp#DE"
        )
        self.assertIsNone(parse_uri(nil_vless))

        # Double-encoded path (%252Fws) is normalized to /ws; triple-encoded (%25252Fws) rejected
        double_enc = (
            "vless://711c018e-2692-4aa8-93f3-544d83fcd16c@185.220.101.42:443"
            "?security=tls&sni=cdn.example.net&type=ws&path=%252Fws#DE"
        )
        repaired = parse_uri(double_enc)
        self.assertIsNotNone(repaired)
        assert repaired is not None
        self.assertEqual(repaired.path, "/ws")

        triple_enc = (
            "vless://711c018e-2692-4aa8-93f3-544d83fcd16c@185.220.101.42:443"
            "?security=tls&sni=cdn.example.net&type=ws&path=%25252Fws#DE"
        )
        self.assertIsNone(parse_uri(triple_enc))

        # Unpinned insecure Hysteria2 must be rejected
        insecure_hy2 = "hysteria2://secretpass@185.220.101.42:443?insecure=1&sni=de.example.net#DE"
        self.assertIsNone(parse_uri(insecure_hy2))

        # Weak Shadowsocks cipher must be rejected
        weak_ss_user = base64.b64encode(b"rc4-md5:password123").decode()
        self.assertIsNone(parse_uri(f"ss://{weak_ss_user}@185.220.101.42:8388#DE"))


class TestProtocolParsingRoundTrip(unittest.TestCase):
    def test_vless_reality_roundtrip(self) -> None:
        uri = (
            f"vless://711c018e-2692-4aa8-93f3-544d83fcd16c@185.220.101.42:443"
            f"?security=reality&type=raw&sni=www.microsoft.com&fp=chrome"
            f"&pbk={SAMPLE_PBK}&sid=a1b2c3d4&flow=xtls-rprx-vision#%F0%9F%87%A9%F0%9F%87%AA%20Test"
        )
        node = parse_uri(uri)
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.protocol, "vless")
        self.assertEqual(node.transport, "tcp")  # raw normalized to tcp for Happ compatibility
        self.assertTrue(node.is_reality)
        self.assertEqual(node.country, "DE")
        re_uri = serialize_uri(node, node.format_label(1))
        reparsed = parse_uri(re_uri)
        self.assertIsNotNone(reparsed)
        assert reparsed is not None
        self.assertEqual(node.dedup_key(), reparsed.dedup_key())

    def test_trojan_grpc_roundtrip(self) -> None:
        uri = (
            "trojan://StrongPass_2026@95.216.10.20:443"
            "?security=tls&type=grpc&serviceName=grpc-svc&sni=fi1.example.org&fp=firefox#FI"
        )
        node = parse_uri(uri)
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.country, "FI")
        self.assertEqual(node.transport, "grpc")
        reparsed = parse_uri(serialize_uri(node, node.format_label(2)))
        self.assertIsNotNone(reparsed)

    def test_vmess_tls_roundtrip(self) -> None:
        vmess_json = {
            "v": "2",
            "ps": "🇳🇱 Amsterdam",
            "add": "104.21.44.55",
            "port": "2053",
            "id": "711c018e-2692-4aa8-93f3-544d83fcd16c",
            "aid": "0",
            "scy": "auto",
            "net": "ws",
            "host": "ws.example.org",
            "path": "/v2ray",
            "tls": "tls",
            "sni": "ws.example.org",
        }
        uri = "vmess://" + base64.b64encode(json.dumps(vmess_json).encode()).decode()
        node = parse_uri(uri)
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.country, "NL")
        reparsed = parse_uri(serialize_uri(node, node.format_label(3)))
        self.assertIsNotNone(reparsed)

    def test_ss_and_ss2022_roundtrip(self) -> None:
        u1 = base64.urlsafe_b64encode(
            f"2022-blake3-aes-128-gcm:{SAMPLE_SS2022_16}".encode()
        ).decode().rstrip("=")
        n1 = parse_uri(f"ss://{u1}@45.90.10.20:443#SE")
        self.assertIsNotNone(n1)
        assert n1 is not None
        self.assertEqual(n1.badge, "SS-2022")
        self.assertIsNotNone(parse_uri(serialize_uri(n1, n1.format_label(1))))

        # Wrong key size (16B key for 256-gcm expecting 32B) must be rejected
        bad = base64.urlsafe_b64encode(
            f"2022-blake3-aes-256-gcm:{SAMPLE_SS2022_16}".encode()
        ).decode()
        self.assertIsNone(parse_uri(f"ss://{bad}@45.90.10.20:443#SE"))

        good32 = base64.urlsafe_b64encode(
            f"2022-blake3-chacha20-poly1305:{SAMPLE_SS2022_32}".encode()
        ).decode()
        self.assertIsNotNone(parse_uri(f"ss://{good32}@45.90.10.20:443#SE"))

    def test_hysteria2_roundtrip(self) -> None:
        uri = (
            "hy2://myAuthToken99@91.107.150.10:443"
            "?insecure=0&sni=de2.example.org&obfs=salamander&obfs-password=obfsKey123#DE"
        )
        node = parse_uri(uri)
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.protocol, "hy2")
        self.assertEqual(node.obfs, "salamander")
        out = serialize_uri(node, node.format_label(1))
        self.assertTrue(out.startswith("hysteria2://"))
        self.assertIsNotNone(parse_uri(out))

    def test_base64_subscription_decode(self) -> None:
        line = (
            f"vless://711c018e-2692-4aa8-93f3-544d83fcd16c@185.220.101.42:443"
            f"?security=reality&type=tcp&sni=yahoo.com&pbk={SAMPLE_PBK}#DE"
        )
        raw = f"#profile-title: Zippy\n{line}\n"
        encoded = base64.b64encode(raw.encode()).decode().rstrip("=")
        decoded = decode_subscription_text(encoded)
        self.assertEqual(decoded, [line])


class TestDeduplicationXrayAndExport(unittest.TestCase):
    def test_cluster_cap_and_custom_exemption(self) -> None:
        nodes = []
        for i in range(5):
            uri = (
                f"vless://711c018e-2692-4aa8-93f3-544d83fcd16c@185.220.101.{10 + i}:443"
                f"?security=reality&type=tcp&sni=www.apple.com&pbk={SAMPLE_PBK}#DE"
            )
            n = parse_uri(uri, source="Upstream", weight=90)
            assert n is not None
            nodes.append(n)

        ranked = deduplicate_and_rank(nodes, preferred_countries=["DE"], max_per_host=2)
        self.assertEqual(len(ranked), 2)

        # Custom user nodes bypass cluster cap
        custom_uri = (
            f"vless://711c018e-2692-4aa8-93f3-544d83fcd16c@185.220.101.99:443"
            f"?security=reality&type=tcp&sni=www.apple.com&pbk={SAMPLE_PBK}#DE"
        )
        cn = parse_uri(custom_uri, source="Custom", weight=150)
        assert cn is not None
        ranked2 = deduplicate_and_rank(nodes + [cn], preferred_countries=["DE"], max_per_host=2)
        self.assertEqual(len(ranked2), 3)
        self.assertEqual(ranked2[0].source, "Custom")

    def test_xray_batch_and_happ_fragment_export(self) -> None:
        uri = (
            f"vless://711c018e-2692-4aa8-93f3-544d83fcd16c@185.220.101.42:443"
            f"?security=reality&type=tcp&sni=www.cloudflare.com&pbk={SAMPLE_PBK}"
            f"&sid=01ab&flow=xtls-rprx-vision#DE"
        )
        node = parse_uri(uri)
        assert node is not None

        batch_cfg, port_map = build_xray_batch_test_config([node], base_port=25000)
        self.assertEqual(len(port_map), 1)
        self.assertEqual(batch_cfg["inbounds"][0]["port"], 25000)
        self.assertEqual(batch_cfg["inbounds"][0]["listen"], "127.0.0.1")

        frags = build_happ_fragment_subscription([node], limit=5)
        self.assertEqual(len(frags), 1)
        frag_cfg = frags[0]
        self.assertEqual(
            frag_cfg["outbounds"][0]["streamSettings"]["sockopt"]["dialerProxy"],
            "fragment",
        )
        self.assertEqual(
            frag_cfg["outbounds"][1]["settings"]["fragment"]["packets"],
            "tlshello",
        )

        with tempfile.TemporaryDirectory() as tmp:
            sub_p = Path(tmp) / "sub"
            docs_p = Path(tmp) / "docs_sub"
            stats = export_all_subscriptions(
                nodes=[node],
                sub_dir=sub_p,
                docs_sub_dir=docs_p,
                profile_cfg={"title": "Zippy VPN", "repo": "redmirobot01-byte/Zippy", "branch": "main"},
                limits_cfg={},
            )
            self.assertEqual(stats["counts"]["happ_main"], 1)
            happ_txt = (sub_p / "happ.txt").read_text(encoding="utf-8")
            self.assertIn("#profile-title: Zippy VPN", happ_txt)
            self.assertIn("#profile-update-interval:", happ_txt)
            self.assertIn("#subscription-userinfo:", happ_txt)
            self.assertTrue((docs_p / "happ.txt").is_file())

    def test_helpers(self) -> None:
        self.assertEqual(country_flag("DE"), "🇩🇪")
        self.assertEqual(detect_country("", "fi2.node.example.com"), "FI")
        self.assertEqual(mask_host("185.220.101.42"), "185.220.•••.42")

    def test_generated_live_subscriptions_are_valid(self) -> None:
        happ_file = ROOT / "sub" / "happ.txt"
        all_file = ROOT / "sub" / "all.txt"
        frag_file = ROOT / "sub" / "happ-fragment.json"
        b64_file = ROOT / "sub" / "happ-base64.txt"
        stats_file = ROOT / "sub" / "stats.json"

        for f in (happ_file, all_file, frag_file, b64_file, stats_file):
            self.assertTrue(f.is_file(), f"Missing generated file: {f}")

        happ_text = happ_file.read_text(encoding="utf-8")
        self.assertTrue(happ_text.startswith("#profile-title: Zippy VPN\n"))
        happ_uris = decode_subscription_text(happ_text)
        self.assertGreaterEqual(len(happ_uris), 20)

        # Every single generated URI must re-parse cleanly with zero errors
        for uri in happ_uris:
            self.assertIsNotNone(parse_uri(uri), f"Generated URI failed re-parse: {uri[:80]}")

        # Base64 Happ subscription must decode identically to happ.txt
        b64_decoded = base64.b64decode(b64_file.read_text(encoding="utf-8").strip()).decode("utf-8")
        self.assertEqual(b64_decoded, happ_text)

        # Fragment JSON must be valid JSON list of complete Xray configs
        frags = json.loads(frag_file.read_text(encoding="utf-8"))
        self.assertIsInstance(frags, list)
        self.assertGreaterEqual(len(frags), 5)
        for item in frags:
            self.assertIn("remarks", item)
            self.assertIn("inbounds", item)
            self.assertIn("outbounds", item)


if __name__ == "__main__":
    unittest.main()
