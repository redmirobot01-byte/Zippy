#!/usr/bin/env python3
"""Play Market (Google Play) link ýasaýjy — CLI.

Zehinsiz Python ulanylýan CLI: belli programmanyň adyny ýa-da islendik
Android paket adyny berip, onuň Google Play Market-däki sowda linkini
ýasamaýar.

Mysallar:

    python3 scripts/play_market_link.py happ
    python3 scripts/play_market_link.py v2rayng
    python3 scripts/play_market_link.py --id com.v2ray.ng
    python3 scripts/play_market_link.py --list
    python3 scripts/play_market_link.py cloudflare --json
    python3 scripts/play_market_link.py "my app" --ai   # AI akylly gözleg
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from zippy.playmarket import (  # noqa: E402
    APPS,
    ai_settings,
    build_play_link,
    format_result,
    resolve,
)


def _print_list() -> None:
    print(f"{'Ady':<24} {'Paket ady':<28}  Biket")
    print("-" * 72)
    for app in APPS:
        print(f"{app['name']:<24} {app['package']:<28}  {app.get('note', '')}")
    print(f"\n{len(APPS)} programma. Gornüş üçin: --id <paket-ady>")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Play Market-de açylýan programma linklerini ýasaýar.",
        epilog="Mysal: python3 scripts/play_market_link.py happ",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Programmanyň ady (mysal: happ) ýa-da paket ady (com.happproxy)",
    )
    parser.add_argument(
        "--id",
        dest="package",
        help="Islendik programma üçin paket adyndan link ýasaýar",
    )
    parser.add_argument("--list", action="store_true", help="Registered programmalary görkezýär")
    parser.add_argument("--json", action="store_true", help="Netijäni JSON görnüşinde çykarýar")
    parser.add_argument(
        "--open",
        action="store_true",
        help="Brauzerde linki göni açýar",
    )
    parser.add_argument(
        "--ai",
        action="store_true",
        help="AI akylly gözleg (paket adyny AI tapýar). Açar ZIPPY_AI_API_KEY bilen sazlanmaly",
    )
    args = parser.parse_args()

    if args.list:
        _print_list()
        return 0

    if args.package:
        try:
            link = build_play_link(args.package)
        except ValueError as exc:
            print(f"Xata: {exc}", file=sys.stderr)
            return 2
        app = None
        result = {"app": None, "package": args.package, "link": link}
    elif args.query:
        if args.ai and not ai_settings():
            print(
                "AI akylly gözleg üçin açar gerek: ZIPPY_AI_API_KEY (ýa-da OPENAI_API_KEY) "
                "üýtgetmesini ulanyň. İndiden ýerli registre gözlener.",
                file=sys.stderr,
            )
        app, link = resolve(args.query, use_ai=args.ai)
        if link is None:
            print(
                f"Tapylmady: {args.query!r}. Gözleg sahypasynda sanawy --list bilen görkeziň, "
                "ýa-da paket adyny --id bilen beriň.",
                file=sys.stderr,
            )
            return 1
        result = {
            "app": app["name"] if app else None,
            "package": app["package"] if app else args.query.strip(),
            "link": link,
        }
    else:
        parser.print_help()
        return 0

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_result(app or {}, result["link"]))

    if args.open:
        webbrowser.open(result["link"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
