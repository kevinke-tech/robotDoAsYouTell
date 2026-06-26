"""Helpers for consistent evidence/source payload fields."""

from __future__ import annotations

import json
from typing import Any


def build_render_evidence_block(
    *,
    source: str = "",
    source_url: str = "",
    evidence: Any = None,
    references: list[Any] | None = None,
    extra_lines: list[str] | None = None,
) -> str:
    lines: list[str] = []
    if source:
        lines.append(f"source: {source}")
    if source_url:
        lines.append(f"source_url: {source_url}")
    if evidence is not None:
        if isinstance(evidence, str):
            lines.append(f"evidence: {evidence}")
        else:
            lines.append(f"evidence: {json.dumps(evidence, ensure_ascii=False)}")
    if isinstance(references, list) and references:
        lines.append(f"references: {json.dumps(references, ensure_ascii=False)}")
    if isinstance(extra_lines, list):
        for ln in extra_lines:
            t = str(ln or "").strip()
            if t:
                lines.append(t)
    return "\n".join(lines).strip()


def attach_evidence_fields(
    payload: dict[str, Any],
    *,
    source: str = "",
    source_url: str = "",
    evidence: Any = None,
    references: list[Any] | None = None,
) -> dict[str, Any]:
    p = dict(payload or {})
    if source:
        p["source"] = source
    if source_url:
        p["source_url"] = source_url
    if evidence is not None:
        p["evidence"] = evidence
    if isinstance(references, list) and references:
        p["references"] = references
    return p

