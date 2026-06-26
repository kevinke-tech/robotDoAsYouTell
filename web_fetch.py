"""Generic web fetch backbone for synthesized skills.

Features:
- URL safety guard (basic SSRF protection)
- timeout / max-bytes caps from env
- browser-like user agent
- HTML to plain text extraction
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import os
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in ("1", "true", "yes", "on")


WEB_FETCH_TIMEOUT_MS = max(1000, _env_int("WEB_FETCH_TIMEOUT_MS", 25000))
WEB_FETCH_MAX_BYTES = max(2048, _env_int("WEB_FETCH_MAX_BYTES", 2 * 1024 * 1024))
WEB_FETCH_ALLOW_PRIVATE = _env_bool("WEB_FETCH_ALLOW_PRIVATE", False)
WEB_FETCH_USER_AGENT = (
    str(os.getenv("WEB_FETCH_USER_AGENT") or "").strip()
    or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_TAG_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_ANY_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)


@dataclass
class FetchResult:
    ok: bool
    url: str
    final_url: str
    status: int | None
    text: str
    error: str | None = None
    content_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_url_key(url: str) -> str:
    u = str(url or "").strip()
    if not u:
        return ""
    try:
        p = urlparse(u)
        base = f"{p.scheme}://{p.netloc}{p.path}"
        query = f"?{p.query}" if p.query else ""
        return (base + query).strip()
    except Exception:
        return u.split("#", 1)[0].strip()


def extract_http_urls_from_text(text: str) -> list[str]:
    urls = [m.group(0).strip() for m in _URL_RE.finditer(str(text or ""))]
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        k = normalize_url_key(u)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(u)
    return out


def html_to_plain_text(content: str) -> str:
    s = str(content or "")
    s = _TAG_SCRIPT_STYLE_RE.sub(" ", s)
    s = _TAG_ANY_RE.sub(" ", s)
    s = html.unescape(s)
    s = _SPACE_RE.sub(" ", s).strip()
    return s


def is_url_allowed(url: str, allow_private: bool = WEB_FETCH_ALLOW_PRIVATE) -> bool:
    u = str(url or "").strip()
    if not u:
        return False
    try:
        p = urlparse(u)
    except Exception:
        return False
    if p.scheme not in ("http", "https") or not p.netloc:
        return False
    host = (p.hostname or "").strip().lower()
    if not host:
        return False
    if host in ("localhost",):
        return bool(allow_private)
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return bool(allow_private)
        return True
    except Exception:
        # Domain name host: allow by default.
        return True


async def fetch_page(
    url: str,
    *,
    timeout_ms: int = WEB_FETCH_TIMEOUT_MS,
    max_bytes: int = WEB_FETCH_MAX_BYTES,
    user_agent: str = WEB_FETCH_USER_AGENT,
) -> FetchResult:
    u = str(url or "").strip()
    if not is_url_allowed(u):
        return FetchResult(ok=False, url=u, final_url=u, status=None, text="", error="blocked_or_invalid_url")
    timeout_sec = max(1.0, float(timeout_ms) / 1000.0)
    max_bytes = max(2048, int(max_bytes))
    headers = {"User-Agent": user_agent, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"}

    try:
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            async with client.stream("GET", u, headers=headers) as resp:
                status = int(resp.status_code)
                final_url = str(resp.url)
                chunks: list[bytes] = []
                total = 0
                async for b in resp.aiter_bytes():
                    if not b:
                        continue
                    total += len(b)
                    if total > max_bytes:
                        cut = len(b) - (total - max_bytes)
                        if cut > 0:
                            chunks.append(b[:cut])
                        break
                    chunks.append(b)
                raw = b"".join(chunks)
                enc = resp.encoding or "utf-8"
                html_text = raw.decode(enc, errors="ignore")
                text = html_to_plain_text(html_text)
                digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest() if text else None
                if status >= 400:
                    return FetchResult(
                        ok=False,
                        url=u,
                        final_url=final_url,
                        status=status,
                        text=text[:8000],
                        error=f"http_{status}",
                        content_hash=digest,
                    )
                return FetchResult(
                    ok=True,
                    url=u,
                    final_url=final_url,
                    status=status,
                    text=text[:8000],
                    error=None,
                    content_hash=digest,
                )
    except Exception as e:
        return FetchResult(ok=False, url=u, final_url=u, status=None, text="", error=f"{type(e).__name__}: {e}")

