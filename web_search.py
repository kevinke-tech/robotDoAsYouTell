"""Generic web search backbone with provider fallback."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


WEB_SEARCH_MAX_RESULTS = max(1, _env_int("WEB_SEARCH_MAX_RESULTS", 6))
SERPAPI_KEY = str(os.getenv("SERPAPI_KEY") or "").strip()

_DDG_RESULT_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_DDG_SNIPPET_RE = re.compile(
    r'<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(?P<snippet2>.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _clean_html_text(s: str) -> str:
    t = _TAG_RE.sub(" ", str(s or ""))
    t = t.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    return _WS_RE.sub(" ", t).strip()


def _decode_ddg_url(url: str) -> str:
    u = str(url or "").strip()
    if not u:
        return ""
    try:
        p = urlparse(u)
        if p.netloc.endswith("duckduckgo.com") and p.path.startswith("/l/"):
            q = parse_qs(p.query)
            uddg = (q.get("uddg") or [""])[0].strip()
            if uddg:
                return uddg
    except Exception:
        return u
    return u


async def _search_serpapi(query: str, max_results: int) -> list[SearchHit]:
    if not SERPAPI_KEY:
        return []
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google",
        "q": query,
        "hl": "zh-cn",
        "gl": "cn",
        "num": max(1, min(int(max_results), 10)),
        "api_key": SERPAPI_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return []
            data = r.json()
    except Exception:
        return []
    out: list[SearchHit] = []
    for item in (data.get("organic_results") or [])[:max_results]:
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if title and link:
            out.append(SearchHit(title=title, url=link, snippet=snippet))
    return out


async def _search_ddg_html(query: str, max_results: int) -> list[SearchHit]:
    q = quote_plus(str(query or "").strip())
    url = f"https://duckduckgo.com/html/?q={q}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                },
            )
            if r.status_code != 200:
                return []
            html_text = r.text or ""
    except Exception:
        return []

    items = list(_DDG_RESULT_RE.finditer(html_text))
    snippets = list(_DDG_SNIPPET_RE.finditer(html_text))
    out: list[SearchHit] = []
    for i, m in enumerate(items[:max_results]):
        href = _decode_ddg_url(m.group("href") or "")
        title = _clean_html_text(m.group("title") or "")
        snippet = ""
        if i < len(snippets):
            snippet = _clean_html_text(snippets[i].group("snippet") or snippets[i].group("snippet2") or "")
        if title and href:
            out.append(SearchHit(title=title, url=href, snippet=snippet))
    return out


async def _search_ddg_instant(query: str, max_results: int) -> list[SearchHit]:
    params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
    url = "https://api.duckduckgo.com/"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return []
            data = r.json()
    except Exception:
        return []
    out: list[SearchHit] = []
    abstract = str(data.get("AbstractText") or "").strip()
    abstract_url = str(data.get("AbstractURL") or "").strip()
    heading = str(data.get("Heading") or "").strip() or "DuckDuckGo Instant"
    if abstract and abstract_url:
        out.append(SearchHit(title=heading, url=abstract_url, snippet=abstract))
    for t in (data.get("RelatedTopics") or []):
        if not isinstance(t, dict):
            continue
        text = str(t.get("Text") or "").strip()
        first_url = str(t.get("FirstURL") or "").strip()
        if text and first_url:
            out.append(SearchHit(title=text[:80], url=first_url, snippet=text))
        if len(out) >= max_results:
            break
    return out[:max_results]


async def search_web(query: str, max_results: int = WEB_SEARCH_MAX_RESULTS) -> dict[str, Any]:
    q = str(query or "").strip()
    if not q:
        return {"ok": False, "provider": "none", "hits": [], "error": "empty query"}
    n = max(1, min(int(max_results or WEB_SEARCH_MAX_RESULTS), 10))

    for provider, fn in (
        ("serpapi_google", _search_serpapi),
        ("duckduckgo_html", _search_ddg_html),
        ("duckduckgo_instant", _search_ddg_instant),
    ):
        hits = await fn(q, n)
        if hits:
            return {
                "ok": True,
                "provider": provider,
                "hits": [h.to_dict() for h in hits],
                "evidence": {"query": q, "provider": provider, "count": len(hits)},
            }
    return {"ok": False, "provider": "none", "hits": [], "error": "no_search_results"}


def format_search_hits(query: str, hits: list[dict[str, Any]] | list[SearchHit], limit: int = 6) -> str:
    q = str(query or "").strip()
    raw = hits or []
    lines = [f"query: {q}", "results:"]
    count = 0
    for idx, item in enumerate(raw, start=1):
        if count >= max(1, int(limit)):
            break
        if isinstance(item, SearchHit):
            title, url, snippet = item.title, item.url, item.snippet
        elif isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
        else:
            continue
        if not title or not url:
            continue
        lines.append(f"{idx}. {title}")
        lines.append(f"   url: {url}")
        if snippet:
            lines.append(f"   snippet: {snippet}")
        count += 1
    return "\n".join(lines)


if __name__ == "__main__":
    # Smoke test: no external call to keep it deterministic.
    s = format_search_hits("test", [{"title": "a", "url": "https://example.com", "snippet": "b"}])
    assert "https://example.com" in s
    print("OK")

