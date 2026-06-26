#!/usr/bin/env python3
"""Regression checks for intent compiler + contract validator."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intent_compiler import compile_intent_hints
from outcome_contract import validate_outcome_payload


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    # 1) Link address intent: should compile to address_lookup.
    h = compile_intent_hints(
        transcript="google 的网址是什么？",
        spec="return website link",
        intent_kind="one_shot",
    )
    _assert(h.get("fulfillment_mode") == "address_lookup", f"bad mode: {h}")

    ok, _, reasons = validate_outcome_payload(
        payload={
            "speak": "Google 网址是 https://www.google.com",
            "render": "source_url: https://www.google.com",
            "ui": {"type": "info_card", "title": "Google", "message": "https://www.google.com"},
        },
        contract={
            "delivery": "interactive",
            "fulfillment_mode": "address_lookup",
            "checks": ["not_link_only", "ui_present", "evidence_present"],
        },
    )
    _assert(ok, f"address_lookup should allow link completion, reasons={reasons}")

    # 2) Play music intent: must require playable media and reject info-only.
    h2 = compile_intent_hints(
        transcript="来点柔和音乐",
        spec="play soft music",
        intent_kind="one_shot",
    )
    _assert(h2.get("require_playable_media") is True, f"missing media requirement: {h2}")

    ok2, _, reasons2 = validate_outcome_payload(
        payload={
            "speak": "给你一个链接",
            "render": "source_url: https://example.com/music",
            "ui": {"type": "info_card", "title": "音乐", "message": "请点击链接播放"},
        },
        contract={
            "delivery": "interactive",
            "fulfillment_mode": "task_completion",
            "requires_ui_delivery": True,
            "require_playable_media": True,
            "checks": ["ui_present", "not_link_only", "evidence_present"],
        },
    )
    _assert((not ok2) and any("playable media required" in r for r in reasons2), f"expected playable failure, got ok={ok2}, reasons={reasons2}")

    # 2b) Image intent: must require visual media and reject info-only fallback.
    h2b = compile_intent_hints(
        transcript="给我看一张小狗图片",
        spec="show a puppy image",
        intent_kind="one_shot",
    )
    _assert(h2b.get("require_visual_media") is True, f"missing visual requirement: {h2b}")
    ok2b, _, reasons2b = validate_outcome_payload(
        payload={
            "speak": "没找到图，给你说明",
            "render": "source: sample\nsource_url: https://example.com/dog",
            "ui": {"type": "info_card", "title": "说明", "message": "请稍后再试"},
        },
        contract={
            "delivery": "interactive",
            "fulfillment_mode": "task_completion",
            "requires_ui_delivery": True,
            "require_visual_media": True,
            "checks": ["ui_present", "evidence_present"],
        },
    )
    _assert((not ok2b) and any("visual media required" in r for r in reasons2b), f"expected visual failure, got ok={ok2b}, reasons={reasons2b}")

    # 3) Explicit count intent should be enforced on card_grid.
    h3 = compile_intent_hints(
        transcript="给我至少6张小狗照片",
        spec="show puppy photos",
        intent_kind="one_shot",
    )
    _assert(h3.get("explicit_min_count") == 6, f"bad explicit count: {h3}")

    ok3, _, reasons3 = validate_outcome_payload(
        payload={
            "speak": "找到了几张",
            "render": "source: test",
            "ui": {"type": "card_grid", "title": "狗狗", "cards": [{"title": "1"}, {"title": "2"}]},
        },
        contract={
            "delivery": "interactive",
            "fulfillment_mode": "task_completion",
            "explicit_min_count": 6,
            "checks": ["ui_present"],
        },
    )
    _assert((not ok3) and any("explicit_min_count not met" in r for r in reasons3), f"expected count failure, got ok={ok3}, reasons={reasons3}")

    # 4) Evidence markers in render should satisfy evidence_present.
    ok4, _, reasons4 = validate_outcome_payload(
        payload={
            "speak": "完成了",
            "render": "source: local_clock\nevidence: iso=2026-06-18T11:00:00+08:00",
            "ui": {"type": "info_card", "title": "时间", "message": "11:00"},
        },
        contract={
            "delivery": "informational",
            "fulfillment_mode": "task_completion",
            "checks": ["evidence_present"],
        },
    )
    _assert(ok4, f"render evidence markers should pass, reasons={reasons4}")

    print("PASS: intent-contract regression checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

