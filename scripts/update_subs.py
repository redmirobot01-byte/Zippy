#!/usr/bin/env python3
"""Zippy VPN subscription collector, verifier, and Happ exporter CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from zippy.checker import check_nodes_tcp_tls, check_nodes_xray
from zippy.exporter import export_all_subscriptions
from zippy.fetcher import fetch_all_sources
from zippy.models import ProxyNode
from zippy.parser import decode_subscription_text, deduplicate_and_rank, parse_uri


def select_probe_candidates(nodes: list[ProxyNode], max_candidates: int) -> list[ProxyNode]:
    """Select diverse top candidates so every protocol gets probed fairly."""
    if len(nodes) <= max_candidates:
        return list(nodes)

    quotas = {
        "reality": int(max_candidates * 0.36),
        "vless": int(max_candidates * 0.22),
        "trojan": int(max_candidates * 0.14),
        "ss": int(max_candidates * 0.12),
        "hy2": int(max_candidates * 0.08),
        "vmess": int(max_candidates * 0.08),
    }
    groups: dict[str, list[ProxyNode]] = {k: [] for k in quotas}
    for node in nodes:
        key = "reality" if node.is_reality else node.protocol
        if key in groups:
            groups[key].append(node)

    picked: list[ProxyNode] = []
    seen: set[str] = set()
    for key, quota in quotas.items():
        for node in groups[key][:quota]:
            dk = node.dedup_key()
            if dk not in seen and len(picked) < max_candidates:
                seen.add(dk)
                picked.append(node)

    for node in nodes:
        if len(picked) >= max_candidates:
            break
        dk = node.dedup_key()
        if dk not in seen:
            seen.add(dk)
            picked.append(node)

    return picked


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect, verify, and export Zippy VPN subscriptions for Happ."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT_DIR / "config" / "sources.json",
        help="Path to sources.json configuration file.",
    )
    parser.add_argument(
        "--custom",
        type=Path,
        default=ROOT_DIR / "config" / "custom_nodes.txt",
        help="Path to optional user-supplied proxy URIs.",
    )
    parser.add_argument(
        "--sub-dir",
        type=Path,
        default=ROOT_DIR / "sub",
        help="Output directory for subscription files.",
    )
    parser.add_argument(
        "--docs-sub-dir",
        type=Path,
        default=ROOT_DIR / "docs" / "sub",
        help="Mirrored output directory inside GitHub Pages docs/.",
    )
    parser.add_argument(
        "--mode",
        choices=("xray", "tcp", "source"),
        default="xray",
        help="Verification level: xray (full 204 check), tcp (TCP/TLS ping), source (parse+rank).",
    )
    parser.add_argument(
        "--xray-bin",
        type=str,
        default=None,
        help="Optional explicit path to xray binary.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=400,
        help="Maximum unique candidates to live-probe.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=40,
        help="Concurrent connection limit for live probes.",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default="",
        help="Override GitHub owner/repo metadata.",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default="",
        help="Override GitHub branch metadata.",
    )
    parser.add_argument(
        "--prefer-api",
        action="store_true",
        help="Fetch GitHub sources via GitHub API before raw.githubusercontent.com.",
    )
    return parser.parse_args()


def main() -> int:
    t0 = time.monotonic()
    args = parse_args()

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    profile_cfg = dict(cfg.get("profile") or {})
    limits_cfg = dict(cfg.get("limits") or {})
    preferred_countries = list(cfg.get("preferred_countries") or [])
    sources = list(cfg.get("sources") or [])

    if args.repo:
        profile_cfg["repo"] = args.repo
    if args.branch:
        profile_cfg["branch"] = args.branch

    print(f"[Zippy] Fetching {len(sources)} configured sources...", flush=True)
    fetched = fetch_all_sources(sources, prefer_api=args.prefer_api)

    parsed_nodes: list[ProxyNode] = []
    raw_uri_count = 0
    sources_ok = 0
    sources_enabled = len(fetched)

    # 1. User's own custom nodes always get top priority
    if args.custom.is_file():
        custom_text = args.custom.read_text(encoding="utf-8", errors="ignore")
        custom_uris = decode_subscription_text(custom_text)
        custom_valid = 0
        for uri in custom_uris:
            node = parse_uri(uri, source="Custom", weight=150)
            if node is not None:
                parsed_nodes.append(node)
                custom_valid += 1
        if custom_uris:
            raw_uri_count += len(custom_uris)
            print(f"  + Custom nodes: {custom_valid}/{len(custom_uris)} valid")

    # 2. Upstream verified sources
    for src, text, err in fetched:
        name = src.get("name", "unknown")
        if err or not text:
            print(f"  - [WARN] {name}: {err or 'empty'}")
            continue
        sources_ok += 1
        weight = int(src.get("weight") or 80)
        max_items = int(src.get("max_items") or 500)
        uris = decode_subscription_text(text)[:max_items]
        raw_uri_count += len(uris)
        valid_count = 0
        for uri in uris:
            node = parse_uri(uri, source=name, weight=weight)
            if node is not None:
                parsed_nodes.append(node)
                valid_count += 1
        print(f"  + {name}: {valid_count}/{len(uris)} validated")

    max_per_host = int(limits_cfg.get("max_per_host") or 2)
    unique_nodes = deduplicate_and_rank(
        parsed_nodes,
        preferred_countries=preferred_countries,
        max_per_host=max_per_host,
    )
    print(
        f"[Zippy] Raw URIs: {raw_uri_count} | Validated: {len(parsed_nodes)} | "
        f"Unique diverse nodes: {len(unique_nodes)}",
        flush=True,
    )

    min_valid = int(limits_cfg.get("min_valid_to_publish") or 10)
    effective_mode = args.mode
    final_nodes = unique_nodes

    if args.mode in {"xray", "tcp"} and unique_nodes:
        candidates = select_probe_candidates(unique_nodes, args.max_candidates)
        print(
            f"[Zippy] Probing {len(candidates)} candidates (mode={args.mode}, "
            f"concurrency={args.concurrency})...",
            flush=True,
        )
        if args.mode == "xray":
            probed = asyncio.run(
                check_nodes_xray(
                    candidates,
                    xray_bin=args.xray_bin,
                    concurrency=args.concurrency,
                )
            )
            if probed and any(n.check_method == "xray" for n in probed):
                effective_mode = "xray"
            else:
                effective_mode = "tcp"
            if len(probed) < min_valid:
                print(
                    f"[Zippy] Only {len(probed)} passed Xray check; supplementing with TCP/TLS probes...",
                    flush=True,
                )
                tcp_probed = asyncio.run(
                    check_nodes_tcp_tls(candidates, concurrency=args.concurrency)
                )
                probed = probed + tcp_probed
        else:
            probed = asyncio.run(
                check_nodes_tcp_tls(candidates, concurrency=args.concurrency)
            )
            effective_mode = "tcp"

        final_nodes = deduplicate_and_rank(
            probed,
            preferred_countries=preferred_countries,
            max_per_host=max_per_host,
        )
        print(f"[Zippy] Live verified nodes: {len(final_nodes)} (mode={effective_mode})", flush=True)

    existing_main = args.sub_dir / "happ.txt"
    if len(final_nodes) < min_valid:
        msg = (
            f"[Zippy] Too few working nodes ({len(final_nodes)} < {min_valid}); "
            "keeping existing subscriptions untouched."
        )
        print(msg, file=sys.stderr)
        return 0 if existing_main.is_file() else 1

    stats = export_all_subscriptions(
        nodes=final_nodes,
        sub_dir=args.sub_dir,
        docs_sub_dir=args.docs_sub_dir,
        profile_cfg=profile_cfg,
        limits_cfg=limits_cfg,
        check_mode=effective_mode,
        sources_ok=sources_ok,
        sources_total=sources_enabled,
        raw_candidates=raw_uri_count,
    )

    elapsed = time.monotonic() - t0
    c = stats["counts"]
    print(
        f"[Zippy] Done in {elapsed:.1f}s -> happ:{c['happ_main']} | fast:{c['happ_fast']} | "
        f"reality:{c['reality']} | fragment:{c['fragment']} | vless:{c['vless']} | "
        f"trojan:{c['trojan']} | ss:{c['ss']} | hy2:{c['hy2']} | vmess:{c['vmess']} | "
        f"total:{c['total']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
