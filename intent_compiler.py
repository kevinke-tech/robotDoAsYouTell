"""Compile intent semantics into runtime-checkable contract hints."""

from __future__ import annotations

import re
from typing import Any


_COUNT_RE = re.compile(
    r"(?:至少|不少于|不低于|最少|at\s+least|no\s+less\s+than|\bminimum\b)\s*([0-9]+)",
    re.IGNORECASE,
)
_COUNT_UNIT_RE = re.compile(
    r"\b([0-9]+)\s*(?:items?|results?|photos?|images?|videos?)\b|([0-9]+)\s*(?:张|个|条|首|段)",
    re.IGNORECASE,
)

_LINK_ADDRESS_RE = re.compile(
    r"(?:\burl\b|\blink\b|网址|链接|网站地址|网页地址|官网地址|site\s+url|website\s+link|what(?:'s| is)\s+.*(?:url|link))",
    re.IGNORECASE,
)
_UI_DELIVERY_RE = re.compile(
    r"(?:播放|听|看|展示|显示|show|display|render|play|watch|listen|gallery|照片|图片|视频|音乐)",
    re.IGNORECASE,
)
_PLAYABLE_MEDIA_RE = re.compile(
    r"(?:播放|听|音乐|歌曲|视频|watch|listen|play|music|song|video|stream)",
    re.IGNORECASE,
)
_VISUAL_MEDIA_RE = re.compile(
    r"(?:图片|照片|图像|photo|image|picture|gallery|show me|给我看一张|看一张)",
    re.IGNORECASE,
)


def _extract_explicit_min_count(text: str) -> int | None:
    if not text:
        return None
    m = _COUNT_RE.search(text)
    if m:
        try:
            return max(1, int(m.group(1)))
        except Exception:
            return None
    m2 = _COUNT_UNIT_RE.search(text)
    if m2:
        raw = m2.group(1) or m2.group(2) or ""
        try:
            return max(1, int(raw))
        except Exception:
            return None
    return None


def compile_intent_hints(
    transcript: str,
    spec: str,
    intent_kind: str = "one_shot",
) -> dict[str, Any]:
    t = str(transcript or "").strip()
    s = str(spec or "").strip()
    merged = (t + "\n" + s).strip()

    asks_link_address = bool(_LINK_ADDRESS_RE.search(merged))
    explicit_min_count = _extract_explicit_min_count(t)
    requires_ui_delivery = bool(_UI_DELIVERY_RE.search(merged))
    require_playable_media = bool(_PLAYABLE_MEDIA_RE.search(merged))
    require_visual_media = bool(_VISUAL_MEDIA_RE.search(merged))

    if intent_kind == "background":
        fulfillment_mode = "background_ack"
    elif asks_link_address:
        fulfillment_mode = "address_lookup"
    else:
        fulfillment_mode = "task_completion"

    return {
        "fulfillment_mode": fulfillment_mode,
        "requires_ui_delivery": requires_ui_delivery and not asks_link_address,
        "require_playable_media": require_playable_media and not asks_link_address,
        "require_visual_media": require_visual_media and not asks_link_address,
        "explicit_min_count": explicit_min_count,
    }

