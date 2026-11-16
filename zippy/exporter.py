"""Subscription file builder and stats exporter optimized for Happ VPN (Android/iOS)."""

from __future__ import annotations

import base64
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any

from .models import ProxyNode, country_flag, country_name_tk, mask_host
from .parser import serialize_uri
from .xray_config import build_happ_fragment_subscription


def build_happ_headers(
    title: str,
    update_interval_hours: int,
    web_page_url: str,
    announce: str = "",
    updated_str: str = "",
    count: int = 0,
) -> list[str]:
    """Generate Happ-compatible inline metadata comment lines."""
    # ASCII-safe check for profile-title; use base64: prefix when non-ASCII chars exist
    try:
        title.encode("ascii")
        title_val = title
    except UnicodeEncodeError:
        title_val = "base64:" + base64.b64encode(title.encode("utf-8")).decode("ascii")

    lines = [
        f"#profile-title: {title_val}",
        f"#profile-update-interval: {max(1, int(update_interval_hours))}",
        "#subscription-userinfo: upload=0; download=0; total=0; expire=0",
        f"#profile-web-page-url: {web_page_url}",
    ]
    if announce:
        ann_b64 = base64.b64encode(announce.encode("utf-8")).decode("ascii")
        lines.append(f"#announce: base64:{ann_b64}")
    if updated_str:
        lines.append(f"# Zippy VPN | Updated: {updated_str} | Nodes: {count}")
    return lines


def select_balanced_happ_nodes(nodes: list[ProxyNode], limit: int = 100) -> list[ProxyNode]:
    """Pick top nodes while ensuring multi-protocol resilience for restricted networks."""
    if len(nodes) <= limit:
        return list(nodes)

    # Target minimum diversity quotas so if one transport is throttled others still work
    quotas: list[tuple[str, int]] = [
        ("reality", int(limit * 0.40)),
        ("vless_tls", int(limit * 0.20)),
        ("trojan", int(limit * 0.14)),
        ("hy2", int(limit * 0.10)),
        ("ss", int(limit * 0.10)),
        ("vmess", int(limit * 0.06)),
    ]

    buckets: dict[str, list[ProxyNode]] = {name: [] for name, _ in quotas}
    for n in nodes:
        if n.is_reality:
            buckets["reality"].append(n)
        elif n.protocol == "vless":
            buckets["vless_tls"].append(n)
        elif n.protocol == "trojan":
            buckets["trojan"].append(n)
        elif n.protocol == "hy2":
            buckets["hy2"].append(n)
        elif n.protocol == "ss":
            buckets["ss"].append(n)
        elif n.protocol == "vmess":
            buckets["vmess"].append(n)

    selected: list[ProxyNode] = []
    seen: set[str] = set()

    for bucket_name, quota in quotas:
        for n in buckets[bucket_name][:quota]:
            key = n.dedup_key()
            if key not in seen and len(selected) < limit:
                seen.add(key)
                selected.append(n)

    # Fill any remaining slots with highest-scoring nodes overall
    for n in nodes:
        if len(selected) >= limit:
            break
        key = n.dedup_key()
        if key not in seen:
            seen.add(key)
            selected.append(n)

    selected.sort(key=lambda item: item.score, reverse=True)
    return selected[:limit]


def _render_sub_file(
    nodes: list[ProxyNode],
    title: str,
    interval: int,
    web_url: str,
    announce: str,
    updated_str: str,
) -> tuple[str, list[str]]:
    uris = [serialize_uri(node, node.format_label(i + 1)) for i, node in enumerate(nodes)]
    headers = build_happ_headers(
        title=title,
        update_interval_hours=interval,
        web_page_url=web_url,
        announce=announce,
        updated_str=updated_str,
        count=len(uris),
    )
    content = "\n".join(headers + uris) + "\n"
    return content, uris


def export_all_subscriptions(
    nodes: list[ProxyNode],
    sub_dir: Path,
    docs_sub_dir: Path | None,
    profile_cfg: dict[str, Any],
    limits_cfg: dict[str, Any],
    check_mode: str = "source",
    sources_ok: int = 0,
    sources_total: int = 0,
    raw_candidates: int = 0,
) -> dict[str, Any]:
    """Write all Happ subscription formats, mirror to docs/sub, and return summary stats."""
    sub_dir.mkdir(parents=True, exist_ok=True)

    repo = str(profile_cfg.get("repo") or "redmirobot01-byte/Zippy").strip()
    branch = str(profile_cfg.get("branch") or "main").strip()
    owner, repo_name = (repo.split("/", 1) + ["Zippy"])[:2]
    web_url = f"https://{owner}.github.io/{repo_name}/"

    base_title = str(profile_cfg.get("title") or "Zippy VPN")
    interval = int(profile_cfg.get("update_interval_hours") or 3)
    announce = str(
        profile_cfg.get("announce")
        or "⚡ Zippy VPN — GitHub arkaly awto-täzelenýär"
    )

    now = datetime.now(timezone.utc)
    updated_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    updated_human = now.strftime("%Y-%m-%d %H:%M UTC")

    lim_main = int(limits_cfg.get("happ_main") or 100)
    lim_fast = int(limits_cfg.get("happ_fast") or 30)
    lim_reality = int(limits_cfg.get("reality") or 80)
    lim_fragment = int(limits_cfg.get("fragment") or 25)
    lim_proto = int(limits_cfg.get("per_protocol") or 80)
    lim_all = int(limits_cfg.get("all") or 250)

    happ_main_nodes = select_balanced_happ_nodes(nodes, limit=lim_main)
    happ_fast_nodes = nodes[:lim_fast]
    reality_nodes = [n for n in nodes if n.is_reality][:lim_reality]
    vless_nodes = [n for n in nodes if n.protocol == "vless"][:lim_proto]
    trojan_nodes = [n for n in nodes if n.protocol == "trojan"][:lim_proto]
    ss_nodes = [n for n in nodes if n.protocol == "ss"][:lim_proto]
    vmess_nodes = [n for n in nodes if n.protocol == "vmess"][:lim_proto]
    hy2_nodes = [n for n in nodes if n.protocol == "hy2"][:lim_proto]
    all_nodes = nodes[:lim_all]

    # 1. Primary Happ subscription (plain + base64)
    happ_txt, happ_uris = _render_sub_file(
        happ_main_nodes, base_title, interval, web_url, announce, updated_human
    )
    (sub_dir / "happ.txt").write_text(happ_txt, encoding="utf-8")
    happ_b64 = base64.b64encode(happ_txt.encode("utf-8")).decode("ascii")
    (sub_dir / "happ-base64.txt").write_text(happ_b64 + "\n", encoding="utf-8")

    # 2. Fast Top-30 subscription
    fast_txt, _ = _render_sub_file(
        happ_fast_nodes,
        f"{base_title} · Calt TOP-{len(happ_fast_nodes)}",
        interval,
        web_url,
        announce,
        updated_human,
    )
    (sub_dir / "happ-fast.txt").write_text(fast_txt, encoding="utf-8")

    # 3. Reality anti-DPI subscription
    reality_txt, _ = _render_sub_file(
        reality_nodes,
        f"{base_title} · Reality",
        interval,
        web_url,
        announce,
        updated_human,
    )
    (sub_dir / "reality.txt").write_text(reality_txt, encoding="utf-8")

    # 4. Per-protocol subscriptions
    proto_sets = [
        ("vless.txt", vless_nodes, "VLESS"),
        ("trojan.txt", trojan_nodes, "Trojan"),
        ("ss.txt", ss_nodes, "Shadowsocks"),
        ("vmess.txt", vmess_nodes, "VMess"),
        ("hy2.txt", hy2_nodes, "Hysteria2"),
    ]
    for filename, pnodes, label in proto_sets:
        ptxt, _ = _render_sub_file(
            pnodes, f"{base_title} · {label}", interval, web_url, announce, updated_human
        )
        (sub_dir / filename).write_text(ptxt, encoding="utf-8")

    # 5. Anti-DPI TLS Fragment JSON subscription for Happ (Xray-core)
    fragment_configs = build_happ_fragment_subscription(nodes, limit=lim_fragment)
    (sub_dir / "happ-fragment.json").write_text(
        json.dumps(fragment_configs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # 6. Universal all & base64 subscriptions (works in Happ, Hiddify, v2rayNG, NekoBox)
    all_txt, all_uris = _render_sub_file(
        all_nodes, f"{base_title} · All", interval, web_url, announce, updated_human
    )
    (sub_dir / "all.txt").write_text(all_txt, encoding="utf-8")
    pure_b64 = base64.b64encode("\n".join(all_uris).encode("utf-8")).decode("ascii")
    (sub_dir / "base64.txt").write_text(pure_b64 + "\n", encoding="utf-8")

    # 7. Dashboard stats & interactive server list
    country_counter = Counter(n.country for n in all_nodes if n.country != "UN")
    countries_summary = [
        {
            "code": cc,
            "flag": country_flag(cc),
            "name_tk": country_name_tk(cc),
            "count": cnt,
        }
        for cc, cnt in country_counter.most_common(16)
    ]

    featured_nodes: list[dict[str, Any]] = []
    for idx, (node, uri) in enumerate(zip(happ_main_nodes[:60], happ_uris[:60]), start=1):
        featured_nodes.append({
            "id": idx,
            "label": node.format_label(idx),
            "protocol": "reality" if node.is_reality else node.protocol,
            "raw_protocol": node.protocol,
            "badge": node.badge,
            "transport": node.transport.upper(),
            "security": node.security.upper(),
            "country": node.country,
            "flag": country_flag(node.country),
            "country_tk": country_name_tk(node.country),
            "host_masked": mask_host(node.host),
            "port": node.port,
            "sni": node.sni or "—",
            "latency_ms": node.latency_ms,
            "check_method": node.check_method,
            "uri": uri,
        })

    measured = [n.latency_ms for n in all_nodes if n.latency_ms is not None and n.latency_ms > 0]
    stats: dict[str, Any] = {
        "name": base_title,
        "repo": repo,
        "branch": branch,
        "web_url": web_url,
        "updated_at": updated_iso,
        "updated_human": updated_human,
        "update_interval_hours": interval,
        "check_mode": check_mode,
        "sources_ok": sources_ok,
        "sources_total": sources_total,
        "raw_candidates": raw_candidates,
        "fastest_ms": min(measured) if measured else None,
        "median_ms": sorted(measured)[len(measured) // 2] if measured else None,
        "counts": {
            "total": len(all_nodes),
            "happ_main": len(happ_main_nodes),
            "happ_fast": len(happ_fast_nodes),
            "reality": len(reality_nodes),
            "fragment": len(fragment_configs),
            "vless": len(vless_nodes),
            "trojan": len(trojan_nodes),
            "ss": len(ss_nodes),
            "vmess": len(vmess_nodes),
            "hy2": len(hy2_nodes),
        },
        "countries": countries_summary,
        "featured_nodes": featured_nodes,
    }
    (sub_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Mirror subscriptions into docs/sub/ for GitHub Pages and live preview
    if docs_sub_dir is not None:
        docs_sub_dir.mkdir(parents=True, exist_ok=True)
        for src_file in sub_dir.iterdir():
            if src_file.is_file():
                shutil.copy2(src_file, docs_sub_dir / src_file.name)

    return stats
