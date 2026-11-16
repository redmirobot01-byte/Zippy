"""Resilient HTTPS subscription fetcher with GitHub API fallback."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
import json
import os
import re
import subprocess
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 4 * 1024 * 1024  # 4 MB safety ceiling per source
USER_AGENT = "ZippyVPN-Updater/1.0 (+https://github.com)"

_RAW_GH_RE = re.compile(
    r"^https://raw\.githubusercontent\.com/"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/"
    r"(?:refs/heads/)?(?P<branch>[^/]+)/(?P<path>.+)$"
)


def _resolve_github_token() -> str:
    """Resolve optional GitHub token from env or gh CLI for API fallback."""
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        tok = os.environ.get(var, "").strip()
        if tok:
            return tok
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    return ""


def _http_get(url: str, headers: dict[str, str], timeout: float) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS sources are allowed: {url}")
    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            data = data[:MAX_RESPONSE_BYTES]
        return data


def _fetch_via_github_api(
    owner: str,
    repo: str,
    branch: str,
    path: str,
    token: str,
    timeout: float,
) -> str:
    decoded_path = unquote(path)
    safe_path = "/".join(quote(seg, safe="") for seg in decoded_path.split("/"))
    api_url = (
        f"https://api.github.com/repos/{owner}/{repo}/contents/{safe_path}"
        f"?ref={quote(branch, safe='')}"
    )
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github.raw+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    raw = _http_get(api_url, headers=headers, timeout=timeout)
    text = raw.decode("utf-8", errors="ignore")
    # In case API returned JSON envelope instead of raw stream
    if text.startswith("{") and '"encoding":"base64"' in text.replace(" ", ""):
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("content"):
            return base64.b64decode(obj["content"]).decode("utf-8", errors="ignore")
    return text


def fetch_single_source(
    source: dict,
    timeout: float = 12.0,
    github_token: str = "",
    prefer_api: bool = False,
) -> tuple[dict, str, str | None]:
    """Fetch one upstream source; returns (source, text, error_or_none)."""
    url = str(source.get("url") or "").strip()
    if not url:
        return source, "", "empty url"

    gh_match = _RAW_GH_RE.match(url)
    last_err: str | None = None

    if not prefer_api:
        try:
            raw = _http_get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            return source, raw.decode("utf-8", errors="ignore"), None
        except Exception as exc:
            last_err = str(exc)

    if gh_match:
        try:
            text = _fetch_via_github_api(
                owner=gh_match.group("owner"),
                repo=gh_match.group("repo"),
                branch=gh_match.group("branch"),
                path=gh_match.group("path"),
                token=github_token,
                timeout=max(timeout, 15.0),
            )
            return source, text, None
        except Exception as exc:
            last_err = str(exc)

    if prefer_api:
        try:
            raw = _http_get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            return source, raw.decode("utf-8", errors="ignore"), None
        except Exception as exc:
            last_err = str(exc)

    return source, "", last_err or "fetch failed"


def fetch_all_sources(
    sources: list[dict],
    timeout: float = 12.0,
    max_workers: int = 6,
    prefer_api: bool = False,
) -> list[tuple[dict, str, str | None]]:
    """Concurrently download all enabled subscription sources."""
    enabled = [s for s in sources if s.get("enabled", True)]
    if not enabled:
        return []

    token = _resolve_github_token()
    results: list[tuple[dict, str, str | None]] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(enabled))) as pool:
        future_map = {
            pool.submit(
                fetch_single_source,
                src,
                timeout=timeout,
                github_token=token,
                prefer_api=prefer_api,
            ): src
            for src in enabled
        }
        for fut in as_completed(future_map):
            results.append(fut.result())

    # Preserve original source order for deterministic output
    order = {s.get("name", ""): idx for idx, s in enumerate(enabled)}
    results.sort(key=lambda item: order.get(item[0].get("name", ""), 999))
    return results
