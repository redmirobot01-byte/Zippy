#!/usr/bin/env python3
"""Zero-dependency HTTP server for previewing the Zippy VPN Web Panel & Happ subscriptions."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"


class ZippyPanelHandler(SimpleHTTPRequestHandler):
    """Static handler adding UTF-8 charsets and Happ subscription response headers."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".svg": "image/svg+xml",
    }

    def end_headers(self) -> None:
        clean_path = self.path.split("?", 1)[0]
        self.send_header("Access-Control-Allow-Origin", "*")
        if clean_path.startswith("/sub/"):
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            if clean_path.endswith((".txt", ".json")) and not clean_path.endswith("stats.json"):
                self.send_header("Profile-Title", "Zippy VPN")
                self.send_header("Profile-Update-Interval", "3")
                self.send_header(
                    "Subscription-Userinfo",
                    "upload=0; download=0; total=0; expire=0",
                )
        super().end_headers()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve Zippy VPN Web Panel.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="TCP port (default: 8080)")
    args = parser.parse_args()

    handler = partial(ZippyPanelHandler, directory=str(DOCS_DIR))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"[Zippy] Web Panel running on http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
