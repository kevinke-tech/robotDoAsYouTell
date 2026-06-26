"""Outcome contract normalization and result validation."""

from __future__ import annotations

import re
from typing import Any

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_VALID_CHECKS = {
    "non_empty_output",
    "ui_present",
    "evidence_present",
    "not_link_only",
    "not_placeholder_output",
}
_VALID_FULFILLMENT_MODES = {
    "auto",
    "task_completion",
    "address_lookup",
    "background_ack",
}
_PLAYABLE_UI_TYPES = {"music_player", "video_player", "iframe_card"}
_VISUAL_UI_TYPES = {"image_card", "card_grid", "iframe_card", "html_card"}


def _strip_urls(text: str) -> str:
    return _URL_RE.sub(" ", str(text or ""))


def _has_substantive_text(text: str) -> bool:
    s = _strip_urls(text)
    s = re.sub(r"\s+", " ", s).strip()
    # Keep this generic: if there is meaningful non-URL content, don't treat as link-only.
    return len(s) >= 24


def normalize_outcome_contract(contract: Any) -> dict:
    if not isinstance(contract, dict):
        contract = {}
    checks = contract.get("checks")
    if not isinstance(checks, list):
        checks = ["non_empty_output"]
    normalized_checks: list[str] = []
    for c in checks:
        key = str(c or "").strip().lower()
        if key in _VALID_CHECKS and key not in normalized_checks:
            normalized_checks.append(key)
    if not normalized_checks:
        normalized_checks = ["non_empty_output"]
    return {
        "delivery": str(contract.get("delivery") or "auto").strip().lower() or "auto",
        "fulfillment_mode": (
            str(contract.get("fulfillment_mode") or "auto").strip().lower() or "auto"
        ),
        "requires_ui_delivery": bool(contract.get("requires_ui_delivery", False)),
        "require_playable_media": bool(contract.get("require_playable_media", False)),
        "require_visual_media": bool(contract.get("require_visual_media", False)),
        "explicit_min_count": (
            int(contract.get("explicit_min_count"))
            if str(contract.get("explicit_min_count") or "").strip().isdigit()
            else None
        ),
        "checks": normalized_checks,
        "notes": str(contract.get("notes") or "").strip(),
    }


def _has_evidence(payload: dict) -> bool:
    for k in ("source", "source_url", "evidence", "references"):
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return True
    ui = payload.get("ui")
    if isinstance(ui, dict):
        for k in ("source", "source_url", "evidence", "references"):
            v = ui.get(k)
            if isinstance(v, str) and v.strip():
                return True
    render = str(payload.get("render") or "")
    if _URL_RE.search(render):
        return True
    lower_render = render.lower()
    marker_patterns = (
        "source:",
        "source_url:",
        "evidence:",
        "references:",
        "来源:",
        "依据:",
    )
    return any(m in lower_render for m in marker_patterns)


def _is_link_only(payload: dict) -> bool:
    ui = payload.get("ui")
    ui_msg = ""
    ui_title = ""
    if isinstance(ui, dict):
        t = str(ui.get("type") or "").strip().lower()
        if t and t != "info_card":
            return False
        ui_msg = str(ui.get("message") or ui.get("text") or "").strip()
        ui_title = str(ui.get("title") or "").strip()
        if isinstance(ui.get("audio_url"), str) and ui.get("audio_url").strip():
            return False
        if isinstance(ui.get("video_url"), str) and ui.get("video_url").strip():
            return False
    text_blob = " ".join([
        str(payload.get("speak") or ""),
        str(payload.get("render") or ""),
        str((ui or {}).get("message") if isinstance(ui, dict) else ""),
    ])
    has_url = bool(_URL_RE.search(text_blob))
    has_actionable_media = isinstance(ui, dict) and (
        bool(str(ui.get("audio_url") or "").strip()) or bool(str(ui.get("video_url") or "").strip())
    )
    if has_actionable_media:
        return False
    # Informational cards with substantive explanation + evidence URLs are valid.
    if _has_substantive_text(" ".join([str(payload.get("speak") or ""), str(payload.get("render") or ""), ui_title, ui_msg])):
        return False
    return has_url


def validate_outcome_payload(payload: Any, contract: Any) -> tuple[bool, dict, list[str]]:
    norm = normalize_outcome_contract(contract)
    delivery = str(norm.get("delivery") or "auto").strip().lower()
    fulfillment_mode = str(norm.get("fulfillment_mode") or "auto").strip().lower()
    if fulfillment_mode not in _VALID_FULFILLMENT_MODES:
        fulfillment_mode = "auto"
    checks = list(norm.get("checks") or [])
    requires_ui_delivery = bool(norm.get("requires_ui_delivery", False))
    require_playable_media = bool(norm.get("require_playable_media", False))
    require_visual_media = bool(norm.get("require_visual_media", False))
    explicit_min_count = norm.get("explicit_min_count")
    if fulfillment_mode == "address_lookup":
        checks = [c for c in checks if c != "not_link_only"]
    elif fulfillment_mode == "background_ack":
        checks = [c for c in checks if c in {"non_empty_output", "not_placeholder_output"}]
    if delivery == "interactive":
        if "ui_present" not in checks:
            checks.append("ui_present")
        if fulfillment_mode != "address_lookup" and "not_link_only" not in checks:
            checks.append("not_link_only")
    elif delivery == "informational":
        if "evidence_present" not in checks:
            checks.append("evidence_present")
    if not isinstance(payload, dict):
        return False, norm, ["skill result payload is not an object"]

    reasons: list[str] = []
    speak = str(payload.get("speak") or "").strip()
    render = str(payload.get("render") or "").strip()
    ui = payload.get("ui")

    if "non_empty_output" in checks:
        if not speak and not render:
            reasons.append("empty output: both speak and render are empty")
    if "ui_present" in checks:
        if not isinstance(ui, dict):
            reasons.append("missing ui object")
    if requires_ui_delivery and not isinstance(ui, dict):
        reasons.append("ui delivery required by intent but ui object is missing")
    if require_playable_media:
        ui_type = str((ui or {}).get("type") if isinstance(ui, dict) else "").strip().lower()
        if ui_type not in _PLAYABLE_UI_TYPES:
            reasons.append("playable media required by intent but payload is not playable")
    if require_visual_media:
        ui_type = str((ui or {}).get("type") if isinstance(ui, dict) else "").strip().lower()
        if ui_type not in _VISUAL_UI_TYPES:
            reasons.append("visual media required by intent but payload is not visual")
    if isinstance(explicit_min_count, int) and explicit_min_count > 0:
        ui_type = str((ui or {}).get("type") if isinstance(ui, dict) else "").strip().lower()
        if ui_type == "card_grid":
            cards = (ui or {}).get("cards")
            count = len(cards) if isinstance(cards, list) else 0
            if count < explicit_min_count:
                reasons.append(
                    f"explicit_min_count not met: expected >= {explicit_min_count}, got {count}"
                )
        elif ui_type == "image_card":
            if explicit_min_count > 1:
                reasons.append(
                    f"explicit_min_count not met: expected >= {explicit_min_count}, got 1"
                )
    if "evidence_present" in checks:
        if not _has_evidence(payload):
            reasons.append("missing evidence fields/source")
    if "not_link_only" in checks:
        if _is_link_only(payload):
            reasons.append("link-only response without actionable result")
    if "not_placeholder_output" in checks:
        ui = payload.get("ui")
        ui_title = str((ui or {}).get("title") if isinstance(ui, dict) else "").strip()
        speak_low = str(payload.get("speak") or "").strip().lower()
        render_low = str(payload.get("render") or "").strip().lower()
        if (
            "通用技能执行结果" in ui_title
            or "task_input:" in render_low
            or "original_spec:" in render_low
            or "已创建并执行一个通用技能实例" in str(payload.get("speak") or "")
            or "generic one-shot" in speak_low
        ):
            reasons.append("placeholder output detected (generic fallback content)")
    return len(reasons) == 0, norm, reasons
