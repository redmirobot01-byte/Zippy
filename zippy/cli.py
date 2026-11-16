"""Zippy command line interface."""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import sys
from pathlib import Path

from . import __version__, certs, config, links, selftest, server, socks, subs


def _add_config(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", default=config.DEFAULT_CONFIG_PATH,
                   help="config file (default: zippy.json)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m zippy",
        description="Zippy VPN — Shadowsocks AEAD + VLESS (Xray uýgun) server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Mysallar:
  python -m zippy init --host 203.0.113.7 --tls
  python -m zippy serve
  python -m zippy links --write
  python -m zippy local --port 10808
  python -m zippy subs --proto vless,vmess,ss --limit 30 --check
  python -m zippy selftest
""",
    )
    p.add_argument("--version", action="version", version=f"Zippy {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("init", help="täze konfigurasiýa + açarlar döret")
    q.add_argument("--host", required=True, help="köpçülikleýin IP ýa-da domen (linklerde ulanylýar)")
    _add_config(q)
    q.add_argument("--ss-port", type=int, default=8388)
    q.add_argument("--vless-port", type=int, default=8443)
    q.add_argument("--method", default="aes-256-gcm",
                   choices=["aes-256-gcm", "aes-128-gcm", "chacha20-ietf-poly1305"])
    q.add_argument("--tls", action="store_true", help="VLESS-i TLS bilen işlet (öz-gol çekilen sertifikat)")
    q.add_argument("--no-vless", action="store_true")
    q.add_argument("--no-ss", action="store_true")
    q.add_argument("--allow-private", action="store_true",
                   help="LAN/loopback nyşanlara rugsat ber (diňe synag üçin)")
    q.add_argument("--write", action="store_true", help="links.txt + subscription.txt ýaz")

    q = sub.add_parser("cert", help="TLS sertifikaty döret/täzele")
    _add_config(q)

    q = sub.add_parser("serve", help="serveri işe giriz")
    _add_config(q)

    q = sub.add_parser("links", help="paýlaşylýan linkleri çykar")
    _add_config(q)
    q.add_argument("--write", action="store_true")
    q.add_argument("--out-dir", default=".")

    q = sub.add_parser("qr", help="telefona skanirlemek üçin QR (SVG)")
    _add_config(q)
    q.add_argument("--proto", choices=["vless", "shadowsocks"], default="vless")
    q.add_argument("--out", default="zippy-qr.svg")

    q = sub.add_parser("client-config", help="Xray/v2rayN üçin client.json döret")
    _add_config(q)
    q.add_argument("--out", default="client.json")

    q = sub.add_parser("local", help="lokal SOCKS5 proxy (kompýuter üçin)")
    _add_config(q)
    q.add_argument("--port", type=int, default=10808)
    q.add_argument("--listen", default="127.0.0.1")
    q.add_argument("--proto", choices=["vless", "shadowsocks"], default="vless")

    q = sub.add_parser("subs", help="GitHub-daky mugt VLESS/VMess/SS konfiglaryny al")
    q.add_argument("--proto", default="", help="süzgüç: vless,vmess,ss,trojan (boş = hemmesi)")
    q.add_argument("--limit", type=int, default=25)
    q.add_argument("--check", action="store_true", help="diňe TCP baglanyşygy bar bolanlary görkez")
    q.add_argument("--out", default="", help="netijäni base64 abuna (.txt) hökmünde ýaz")
    q.add_argument("--sources", default="", help="çelgi indeksleri, meselem 0,1,4")

    q = sub.add_parser("selftest", help="lokal uçdan-uça synag (hakyky şifrleme)")

    q = sub.add_parser("sources", help="konfig çeşmeleriniň sanawyny görkez")

    return p


def _print_links(cfg: dict) -> None:
    print(f"\n  Serwer: {cfg['host']}\n")
    for item in links.all_links(cfg):
        print(f"  {item['name']}")
        print(f"  {item['url']}")
        if item.get("fallback"):
            print(f"  (köne klientler): {item['fallback']}")
        print()
    ss = cfg.get("shadowsocks", {})
    if ss.get("enabled", True):
        print(f"  Parol (SS): {ss['password']}")
    v = cfg.get("vless", {})
    if v.get("enabled", True):
        print(f"  UUID (VLESS): {v['uuid']}")
    print("  ⚠️  Bu maglumatlary hiç kim bilen paýlaşmaň.\n")


def _write_links(cfg: dict, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    items = links.all_links(cfg)
    (out / "links.txt").write_text(
        "\n".join(x["url"] for x in items) + "\n", encoding="utf-8")
    (out / "subscription.txt").write_text(links.subscription_text(cfg) + "\n",
                                          encoding="utf-8")
    print(f"  Ýazyldy: {out / 'links.txt'}, {out / 'subscription.txt'}")


async def _cmd_subs(args) -> int:
    sources = subs.SOURCES
    if args.sources:
        idx = [int(x) for x in args.sources.split(",") if x.strip()]
        sources = tuple(subs.SOURCES[i] for i in idx if 0 <= i < len(subs.SOURCES))
    print("GitHub-dan konfiglar alynýar...")
    all_links, errors = await subs.collect(sources)
    wanted = {x.strip().lower() for x in args.proto.split(",") if x.strip()} or None
    selected = subs.filter_proto(all_links, wanted)
    print(f"  Jemi {len(all_links)} tapylany, süzgüçden soň {len(selected)}.\n")
    for err in errors:
        print(f"  [duýduryş] {err}", file=sys.stderr)

    if args.check:
        print("TCP barlagy geçirilýär (diňe porty açyk bolanlar galar)...")
        # check a bounded candidate set for speed
        candidates = selected[:max(args.limit * 5, 100)]
        status = await subs.check_links(candidates)
        selected = [x for x in candidates if status.get(x)]
        print(f"  Işleýän (port açyk): {len(selected)}\n")

    chosen = selected[:args.limit]
    for i, link in enumerate(chosen, 1):
        info = subs.parse_link(link)
        print(f"  {i:2}. [{info['proto']:<9}] {info.get('host', '?'):<40}:{info.get('port', '?')}")
        print(f"      {link[:150]}")
    if not chosen:
        print("  Hiç bir konfig tapylmady. Öz serveriňi gur: python -m zippy init --host IP")
    if chosen and args.out:
        Path(args.out).write_text(subs.subscription_base64(chosen) + "\n", encoding="utf-8")
        print(f"\n  Abuna ýazyldy: {args.out} (v2rayNG/Hiddify import edip bilersiň)")
    print("\n  ⚠️  Köpçülikleýin proksiler näbelli adamlar tarapyndan dolandyrylýar: \
parol/bank/2FA üçin ulanmaň. Öz serveriňiz howpsuz.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        if args.cmd == "init":
            cfg = config.default_config(
                args.host, ss_port=args.ss_port, vless_port=args.vless_port,
                tls=args.tls, allow_private=args.allow_private)
            cfg["shadowsocks"]["method"] = args.method
            cfg["shadowsocks"]["enabled"] = not args.no_ss
            cfg["vless"]["enabled"] = not args.no_vless
            config.save(cfg, args.config)
            cfg = config.load(args.config)
            if args.tls:
                v = cfg["vless"]
                certs.generate_self_signed(
                    args.host, config.resolve(cfg, v["cert"]), config.resolve(cfg, v["key"]))
                print(f"  TLS sertifikaty döredildi: {config.resolve(cfg, v['cert'])}")
            print(f"  Konfig ýazyldy: {args.config} (diňe sen okap bilersiň, 0600)")
            _print_links(cfg)
            if args.write:
                _write_links(cfg, ".")
            return 0

        if args.cmd == "cert":
            cfg = config.load(args.config)
            v = cfg["vless"]
            certs.generate_self_signed(
                cfg["host"], config.resolve(cfg, v["cert"]), config.resolve(cfg, v["key"]))
            print(f"  Sertifikat: {config.resolve(cfg, v['cert'])}")
            return 0

        if args.cmd == "serve":
            cfg = config.load(args.config)
            _print_links(cfg)
            print("  Server işleýär... (Ctrl+C bilen duruz)")
            try:
                asyncio.run(server.run(cfg))
            except KeyboardInterrupt:
                pass
            return 0

        if args.cmd == "links":
            cfg = config.load(args.config)
            _print_links(cfg)
            if args.write:
                _write_links(cfg, args.out_dir)
            return 0

        if args.cmd == "qr":
            cfg = config.load(args.config)
            items = links.all_links(cfg)
            item = next((x for x in items if x["protocol"] == args.proto), None)
            if item is None:
                print(f"{args.proto} öçürilen", file=sys.stderr)
                return 1
            try:
                import qrcode
                import qrcode.image.svg
                img = qrcode.make(item["url"], image_factory=qrcode.image.svg.SvgPathImage)
                img.save(args.out)
                print(f"  QR SVG ýazyldy: {args.out}")
            except ImportError:
                print("  QR üçin: pip install qrcode  (ýa-da linki göçürip el bilen giriz)")
                return 1
            return 0

        if args.cmd == "client-config":
            cfg = config.load(args.config)
            Path(args.out).write_text(links.xray_client_json(cfg) + "\n", encoding="utf-8")
            print(f"  Ýazyldy: {args.out}")
            return 0

        if args.cmd == "local":
            cfg = config.load(args.config)
            async def _run():
                srv = await socks.run_socks_server(cfg, args.proto, args.listen, args.port)
                print(f"  SOCKS5 proxy: {args.listen}:{args.port}  ({args.proto} arkaly)")
                print(f"  Mysal: curl --socks5-hostname 127.0.0.1:{args.port} https://example.com")
                try:
                    async with srv:
                        await srv.serve_forever()
                finally:
                    pass
            try:
                asyncio.run(_run())
            except KeyboardInterrupt:
                pass
            return 0

        if args.cmd == "subs":
            return asyncio.run(_cmd_subs(args))

        if args.cmd == "sources":
            print("  GitHub konfig çeşmeleri (2026-11-16 barlandy):\n")
            for i, s in enumerate(subs.SOURCES):
                print(f"  {i}. {s.name}\n     https://github.com/{s.repo}/blob/{s.branch}/{s.path}")
            return 0

        if args.cmd == "selftest":
            print("Zippy uçdan-uça synag başlaýar (loopback, hakyky şifrleme)...\n")
            results = asyncio.run(selftest.run())
            print(f"\n  {len(results)}/{len(results)} synag geçdi. Server işleýär ✅")
            return 0

    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"  Ýalňyşlyk: {exc}", file=sys.stderr)
        return 1
    return 0
