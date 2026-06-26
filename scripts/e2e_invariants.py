#!/usr/bin/env python3
"""
Invariant-oriented /plan checks.

This script enforces a *fixed* set of platform invariants. It is not a
case-by-case rules engine: you can feed 10 or 10,000 transcripts without
adding new gate types.

Run:
  python scripts/e2e_invariants.py --port 5001
  python scripts/e2e_invariants.py --port 5001 --transcript-file logs/cases.txt
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
from typing import Any


def post_json(url: str, payload: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_ui_types(plan: dict[str, Any]) -> list[str]:
    out: list[str] = []
    ui = plan.get("ui")
    if isinstance(ui, dict):
        out.append(str(ui.get("type") or "").strip().lower())
    cards = plan.get("ui_cards")
    if isinstance(cards, list):
        for c in cards:
            if isinstance(c, dict):
                out.append(str(c.get("type") or "").strip().lower())
    return [x for x in out if x]


def _looks_media_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    patterns = (
        r"\bmusic\b",
        r"\bvideo\b",
        r"\bsong\b",
        r"\baudio\b",
        r"\bmovie\b",
        r"音乐|视频|歌曲|电影|音频|来点",
    )
    return any(re.search(p, t, re.IGNORECASE) for p in patterns)


def _looks_factual_query(text: str) -> bool:
    t = (text or "").strip().lower()
    patterns = (
        r"\bwhat time\b",
        r"\bcurrent time\b",
        r"\bdate\b",
        r"\bweather\b",
        r"\btemperature\b",
        r"\bprice\b",
        r"\bexchange rate\b",
        r"\bnews\b",
        r"\bscore\b",
        r"几点|时间|日期|天气|温度|价格|汇率|新闻|比分|星期几|周几",
    )
    return any(re.search(p, t, re.IGNORECASE) for p in patterns)


def _is_non_empty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _has_placeholder_markers(plan: dict[str, Any]) -> bool:
    blob = " ".join(
        [
            str(plan.get("speak") or ""),
            str(plan.get("render") or ""),
            json.dumps(plan.get("ui") or {}, ensure_ascii=False),
            json.dumps(plan.get("ui_cards") or [], ensure_ascii=False),
        ]
    ).lower()
    markers = (
        "task_input:",
        "original_spec:",
        "generic one-shot",
        "通用技能执行结果",
        "已创建并执行一个通用技能实例",
    )
    return any(m in blob for m in markers)


def _is_link_only_success(plan: dict[str, Any]) -> bool:
    if str(plan.get("kind") or "").strip().lower() != "skill_result":
        return False
    text_blob = " ".join(
        [
            str(plan.get("speak") or ""),
            str(plan.get("render") or ""),
        ]
    )
    has_url = bool(re.search(r"https?://\S+", text_blob, re.IGNORECASE))
    if not has_url:
        return False
    ui_types = _extract_ui_types(plan)
    if not ui_types:
        return True
    if all(t in ("info_card", "key_value") for t in ui_types):
        ui = plan.get("ui")
        if isinstance(ui, dict):
            msg = str(ui.get("message") or ui.get("text") or "")
            title = str(ui.get("title") or "")
            data_blob = json.dumps(ui.get("data") or {}, ensure_ascii=False)
            if len((title + " " + msg).strip()) >= 24:
                return False
            if isinstance(ui.get("data"), dict) and len(data_blob) >= 40:
                return False
        return True
    return False


def _has_verifiability_markers(plan: dict[str, Any]) -> bool:
    ui = plan.get("ui")
    cards = plan.get("ui_cards")
    blobs = [
        str(plan.get("render") or ""),
        str(plan.get("speak") or ""),
        json.dumps(ui if isinstance(ui, dict) else {}, ensure_ascii=False),
        json.dumps(cards if isinstance(cards, list) else [], ensure_ascii=False),
    ]
    text = "\n".join(blobs).lower()
    markers = (
        "source",
        "source_url",
        "evidence",
        "references",
        "http://",
        "https://",
        "system_clock",
        "utc",
        "timezone",
        "来源",
        "依据",
    )
    return any(m in text for m in markers)


def _check_invariants(transcript: str, plan: dict[str, Any]) -> list[str]:
    failures: list[str] = []

    # INV-01: response envelope sanity
    if not _is_non_empty_str(plan.get("kind")):
        failures.append("INV-01: missing non-empty `kind`")
    if "speak" not in plan or "render" not in plan:
        failures.append("INV-01: missing `speak` or `render` field")

    # INV-02: no placeholder pseudo-success
    if _has_placeholder_markers(plan):
        failures.append("INV-02: placeholder markers detected in successful output")

    # INV-03: no link-only pseudo-completion
    if _is_link_only_success(plan):
        failures.append("INV-03: link-only skill_result without actionable UI")

    # INV-04: intent-modality consistency (generic anti-drift guard)
    ui_types = _extract_ui_types(plan)
    has_media_ui = any(t in {"music_player", "video_player"} for t in ui_types)
    if (not _looks_media_intent(transcript)) and has_media_ui:
        failures.append(f"INV-04: non-media intent returned media UI: {ui_types}")

    # INV-05: factual answers must be verifiable.
    if _looks_factual_query(transcript):
        kind = str(plan.get("kind") or "").strip().lower()
        if kind == "chat" and (not _has_verifiability_markers(plan)):
            failures.append("INV-05: factual chat response lacks verifiability markers/evidence")
        if kind == "skill_result" and (not _has_verifiability_markers(plan)):
            failures.append("INV-05: factual skill_result lacks verifiability markers/evidence")

    return failures


def _load_transcripts(args_transcripts: list[str], transcript_file: str) -> list[str]:
    transcripts: list[str] = [str(x).strip() for x in (args_transcripts or []) if str(x).strip()]
    if transcript_file:
        p = Path(transcript_file)
        lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
        transcripts.extend([ln for ln in lines if ln and not ln.startswith("#")])
    # Keep order, remove duplicates.
    out: list[str] = []
    seen = set()
    for t in transcripts:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument(
        "--transcript",
        action="append",
        default=[
            "现在几点了？",
            "请告诉我今天是星期几",
        ],
        help="Input transcript. Can be repeated.",
    )
    ap.add_argument(
        "--transcript-file",
        default="",
        help="Optional UTF-8 text file with one transcript per line (# starts a comment).",
    )
    args = ap.parse_args()
    base_url = f"http://{args.host}:{args.port}"
    transcripts = _load_transcripts(args.transcript, args.transcript_file)
    if not transcripts:
        print("No transcripts provided.")
        return 2

    ok_all = True
    for idx, t in enumerate(transcripts, start=1):
        try:
            plan = post_json(f"{base_url}/plan", {"transcript": t, "image_b64": None}, timeout=240)
            failures = _check_invariants(t, plan)
        except urllib.error.URLError as e:
            print(f"FAIL case#{idx}: cannot reach backend: {e}")
            return 2
        except Exception as e:
            print(f"FAIL case#{idx}: {type(e).__name__}: {e}")
            return 2

        print("\n" + "=" * 80)
        print(f"CASE {idx}: {t}")
        print("=" * 80)
        print(json.dumps(plan, ensure_ascii=True, indent=2))

        if not failures:
            print(f"PASS case#{idx}")
        else:
            ok_all = False
            print(f"FAIL case#{idx}:")
            for f in failures:
                print(f"  - {f}")

    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())

