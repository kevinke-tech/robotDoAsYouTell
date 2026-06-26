"""UI payload contract validation and normalization."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

_SUPPORTED_UI_TYPES = {
    "info_card",
    "key_value",
    "html_card",
    "music_player",
    "video_player",
    "awaiting_slot",
    "image_card",
    "card_grid",
    "iframe_card",
}

_UI_TYPE_ALIASES = {
    "video_card_grid": "card_grid",
}


def _is_non_empty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


_DIRECT_AUDIO_EXTS = (
    ".mp3",
    ".wav",
    ".ogg",
    ".m4a",
    ".aac",
    ".flac",
    ".opus",
    ".weba",
    ".m3u8",
)
_DIRECT_VIDEO_EXTS = (
    ".mp4",
    ".webm",
    ".mov",
    ".mkv",
    ".m3u8",
)


def _looks_direct_media_url(url: str, media_kind: str) -> bool:
    u = str(url or "").strip()
    if not u:
        return False
    low = u.lower()
    exts = _DIRECT_AUDIO_EXTS if media_kind == "audio" else _DIRECT_VIDEO_EXTS
    if any(low.split("?", 1)[0].endswith(ext) for ext in exts):
        return True
    # Many CDN links include format hints in query strings.
    if "format=m3u8" in low or "mime=audio/" in low or "mime=video/" in low:
        return True
    return False


def _to_iframe_card(norm: dict, url_key: str) -> tuple[bool, dict | None, str]:
    iframe_url = str(norm.get(url_key) or "").strip()
    if not iframe_url:
        return False, None, f"missing {url_key} for iframe conversion"
    parsed = urlparse(iframe_url)
    if parsed.scheme not in ("http", "https"):
        return False, None, f"iframe url must be http/https: {iframe_url}"
    converted = dict(norm)
    converted["type"] = "iframe_card"
    converted["iframe_url"] = iframe_url
    # Preserve source URL for evidence and traceability.
    if not _is_non_empty_str(converted.get("source_url")):
        converted["source_url"] = iframe_url
    return True, converted, ""


def validate_and_normalize_ui(ui: Any) -> tuple[bool, dict | None, str]:
    """
    Validate UI payload and normalize common aliases.
    Returns: (ok, normalized_ui_or_none, error_message)
    """
    if ui is None:
        return True, None, ""
    if not isinstance(ui, dict):
        return False, None, "ui must be an object"

    t = str(ui.get("type") or "").strip().lower()
    if not t:
        return False, None, "ui.type is required"
    t = _UI_TYPE_ALIASES.get(t, t)
    if t not in _SUPPORTED_UI_TYPES:
        return False, None, f"unsupported ui.type: {t}"

    norm = dict(ui)
    norm["type"] = t

    if t == "music_player":
        if not _is_non_empty_str(norm.get("audio_url")):
            return False, None, "music_player requires non-empty audio_url"
        # If it's not a direct audio stream, treat it as embeddable content.
        if not _looks_direct_media_url(str(norm.get("audio_url")), "audio"):
            return _to_iframe_card(norm, "audio_url")
        return True, norm, ""

    if t == "video_player":
        if not _is_non_empty_str(norm.get("video_url")):
            alias = norm.get("videoUrl") or norm.get("url")
            if _is_non_empty_str(alias):
                norm["video_url"] = str(alias).strip()
            else:
                return False, None, "video_player requires non-empty video_url"
        # If it's not a direct video stream/file, render through iframe to avoid
        # <video> playback errors on embed/page URLs.
        if not _looks_direct_media_url(str(norm.get("video_url")), "video"):
            return _to_iframe_card(norm, "video_url")
        return True, norm, ""

    if t == "awaiting_slot":
        if not _is_non_empty_str(norm.get("slot")):
            return False, None, "awaiting_slot requires slot"
        if not _is_non_empty_str(norm.get("question")):
            return False, None, "awaiting_slot requires question"
        return True, norm, ""

    if t == "html_card":
        has_html = _is_non_empty_str(norm.get("html"))
        has_srcdoc = _is_non_empty_str(norm.get("srcdoc"))
        has_js = _is_non_empty_str(norm.get("js"))
        if not (has_html or has_srcdoc or has_js):
            return False, None, "html_card requires at least one of html/srcdoc/js"
        return True, norm, ""

    if t == "image_card":
        if not _is_non_empty_str(norm.get("image_url")):
            alias = norm.get("imageUrl") or norm.get("url")
            if _is_non_empty_str(alias):
                norm["image_url"] = str(alias).strip()
            else:
                return False, None, "image_card requires non-empty image_url"
        return True, norm, ""

    if t == "iframe_card":
        if not _is_non_empty_str(norm.get("iframe_url")):
            alias = norm.get("url")
            if _is_non_empty_str(alias):
                norm["iframe_url"] = str(alias).strip()
            else:
                return False, None, "iframe_card requires non-empty iframe_url"
        return True, norm, ""

    if t == "card_grid":
        cards = norm.get("cards")
        if cards is None and isinstance(norm.get("items"), list):
            cards = norm.get("items")
            norm["cards"] = cards
        if not isinstance(cards, list) or not cards:
            return False, None, "card_grid requires non-empty cards list"
        return True, norm, ""

    if t in ("info_card", "key_value"):
        return True, norm, ""

    return False, None, f"unsupported ui.type: {t}"
