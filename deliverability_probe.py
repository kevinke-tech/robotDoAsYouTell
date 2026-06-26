"""Runtime deliverability probe for URL-based UI payloads."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg")
_AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".opus", ".m3u8", ".weba")
_VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".m3u8")


def _normalized_type(ui: Any) -> str:
    if not isinstance(ui, dict):
        return ""
    return str(ui.get("type") or "").strip().lower()


def _looks_like_ext(url: str, exts: tuple[str, ...]) -> bool:
    low = str(url or "").strip().lower()
    if not low:
        return False
    base = low.split("?", 1)[0]
    return any(base.endswith(ext) for ext in exts)


def _is_http_url(url: str) -> bool:
    try:
        p = urlparse(str(url or "").strip())
    except Exception:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)


def _collect_ui_urls(ui: Any) -> list[tuple[str, str]]:
    """Return (kind, url) candidates from a ui object."""
    out: list[tuple[str, str]] = []
    if not isinstance(ui, dict):
        return out
    t = _normalized_type(ui)
    if t == "image_card":
        url = str(ui.get("image_url") or ui.get("imageUrl") or ui.get("url") or "").strip()
        if url:
            out.append(("image", url))
    elif t == "card_grid":
        cards = ui.get("cards")
        if isinstance(cards, list):
            for c in cards:
                if not isinstance(c, dict):
                    continue
                url = str(c.get("image_url") or c.get("thumbnail") or "").strip()
                if url:
                    out.append(("image", url))
    elif t == "music_player":
        url = str(ui.get("audio_url") or "").strip()
        if url:
            out.append(("audio", url))
    elif t == "video_player":
        url = str(ui.get("video_url") or ui.get("videoUrl") or ui.get("url") or "").strip()
        if url:
            out.append(("video", url))
    elif t == "iframe_card":
        url = str(ui.get("iframe_url") or ui.get("url") or "").strip()
        if url:
            out.append(("iframe", url))
    return out


def _kind_matches_content_type(kind: str, content_type: str, url: str) -> bool:
    ct = str(content_type or "").strip().lower()
    if kind == "image":
        return ct.startswith("image/") or _looks_like_ext(url, _IMAGE_EXTS)
    if kind == "audio":
        return (
            ct.startswith("audio/")
            or "application/vnd.apple.mpegurl" in ct
            or _looks_like_ext(url, _AUDIO_EXTS)
        )
    if kind == "video":
        return (
            ct.startswith("video/")
            or "application/vnd.apple.mpegurl" in ct
            or _looks_like_ext(url, _VIDEO_EXTS)
        )
    if kind == "iframe":
        # iframe can host multiple kinds; only require successful fetch.
        return True
    return False


async def probe_ui_deliverability(
    ui: Any,
    timeout_sec: float = 6.0,
    max_urls: int = 8,
) -> tuple[bool, list[str], dict[str, Any]]:
    """
    Probe URL-based UI assets for basic reachability.

    Returns: (ok, reasons, summary)
    """
    targets = _collect_ui_urls(ui)
    if not targets:
        return True, [], {"probed": 0, "ok": 0, "failed": 0, "details": []}

    reasons: list[str] = []
    details: list[dict[str, Any]] = []
    checked = 0
    ok_count = 0

    async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
        for kind, raw_url in targets[: max(1, int(max_urls))]:
            url = str(raw_url or "").strip()
            checked += 1
            if not _is_http_url(url):
                reasons.append(f"{kind} asset url is not http/https: {url}")
                details.append({"kind": kind, "url": url, "ok": False, "error": "bad_url"})
                continue
            try:
                resp = await client.get(
                    url,
                    headers={"Range": "bytes=0-1024", "User-Agent": "vox-deliverability-probe/1.0"},
                )
                status = int(resp.status_code)
                ct = str(resp.headers.get("content-type") or "")
                reachable = 200 <= status < 400
                type_ok = _kind_matches_content_type(kind, ct, url)
                item_ok = bool(reachable and type_ok)
                if item_ok:
                    ok_count += 1
                else:
                    reasons.append(f"{kind} asset not deliverable: status={status}, content_type={ct or 'n/a'}")
                details.append(
                    {
                        "kind": kind,
                        "url": url,
                        "ok": item_ok,
                        "status": status,
                        "content_type": ct,
                    }
                )
            except Exception as e:
                reasons.append(f"{kind} asset probe error: {type(e).__name__}: {e}")
                details.append(
                    {
                        "kind": kind,
                        "url": url,
                        "ok": False,
                        "error": f"{type(e).__name__}: {e}",
                    }
                )

    # For URL-bearing UI, require at least one successful deliverable asset.
    all_ok = ok_count > 0
    if not all_ok and not reasons:
        reasons.append("url-based ui has no deliverable assets")
    summary = {
        "probed": checked,
        "ok": ok_count,
        "failed": max(0, checked - ok_count),
        "details": details,
    }
    return all_ok, reasons, summary

