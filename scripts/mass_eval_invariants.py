#!/usr/bin/env python3
"""
Mass-evaluate fixed invariants with transcript perturbations.

This script does NOT add new gates. It scales sample volume while reusing the
same invariant checks defined in e2e_invariants.py.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from e2e_invariants import _check_invariants, _load_transcripts, post_json  # type: ignore
from runtime_judge import classify_error


_PREFIXES = [
    "",
    "请你",
    "麻烦你",
    "帮我",
    "现在",
]
_SUFFIXES = [
    "",
    "谢谢",
    "尽快",
    "可以吗",
    "吧",
]
_PUNCT = ["", "。", "！", "?", "？"]
_SPACER = ["", " ", "  "]


def _perturb(text: str, rng: random.Random) -> str:
    t = str(text or "").strip()
    if not t:
        return t
    prefix = rng.choice(_PREFIXES)
    suffix = rng.choice(_SUFFIXES)
    punct = rng.choice(_PUNCT)
    spacer = rng.choice(_SPACER)

    out = t
    # Light perturbations: polite wrappers / punctuation / spacing noise.
    if prefix:
        out = f"{prefix}{spacer}{out}"
    if suffix:
        out = f"{out}{spacer}{suffix}"
    if punct:
        out = f"{out}{punct}"
    return out.strip()


def _generate_cases(seeds: list[str], target_count: int, seed_value: int) -> list[str]:
    if not seeds:
        return []
    rng = random.Random(seed_value)
    out: list[str] = []
    i = 0
    while len(out) < target_count:
        base = seeds[i % len(seeds)]
        out.append(_perturb(base, rng))
        i += 1
    # Deduplicate while preserving order, then top up if needed.
    dedup: list[str] = []
    seen = set()
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        dedup.append(x)
    j = 0
    while len(dedup) < target_count:
        base = seeds[j % len(seeds)]
        dedup.append(f"{base} #{j+1}")
        j += 1
    return dedup[:target_count]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument(
        "--seed-transcript-file",
        default=str((ROOT / "scripts" / "mass_eval_seeds.txt")),
        help="Seed transcript file (one per line).",
    )
    ap.add_argument(
        "--count",
        type=int,
        default=80,
        help="How many perturbed transcripts to run.",
    )
    ap.add_argument(
        "--rng-seed",
        type=int,
        default=42,
        help="Random seed for deterministic perturbations.",
    )
    ap.add_argument(
        "--request-timeout",
        type=int,
        default=120,
        help="Per /plan request timeout in seconds.",
    )
    ap.add_argument(
        "--max-retries-per-case",
        type=int,
        default=1,
        help="Retry count for transient runtime failures.",
    )
    ap.add_argument(
        "--failures-json",
        default=str((ROOT / "logs" / "mass_eval_failures.json")),
        help="Where to write failing cases with details.",
    )
    args = ap.parse_args()

    seeds = _load_transcripts([], args.seed_transcript_file)
    if not seeds:
        print("FAIL: no seed transcripts")
        return 2

    cases = _generate_cases(seeds, max(1, int(args.count)), int(args.rng_seed))
    base_url = f"http://{args.host}:{args.port}"

    failures: list[dict[str, Any]] = []
    for idx, transcript in enumerate(cases, start=1):
        reasons: list[str] = []
        plan: dict[str, Any] = {"kind": "error", "speak": "", "render": ""}
        max_tries = max(0, int(args.max_retries_per_case)) + 1
        for attempt in range(1, max_tries + 1):
            try:
                plan = post_json(
                    f"{base_url}/plan",
                    {"transcript": transcript, "image_b64": None},
                    timeout=max(10, int(args.request_timeout)),
                )
                reasons = _check_invariants(transcript, plan)
                break
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                judged = classify_error(err, stage="invoke")
                reasons = [f"runtime_error: {err}"]
                plan = {"kind": "error", "speak": "", "render": ""}
                if bool(judged.get("transient")) and attempt < max_tries:
                    continue
                break
        if reasons:
            failures.append(
                {
                    "index": idx,
                    "transcript": transcript,
                    "reasons": reasons,
                    "plan": plan,
                }
            )
            print(f"[mass-eval] case#{idx} FAIL: {transcript}")
        else:
            print(f"[mass-eval] case#{idx} PASS")

    total = len(cases)
    failed = len(failures)
    passed = total - failed
    pass_rate = (passed / total) if total else 0.0
    print(
        json.dumps(
            {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": round(pass_rate, 4),
            },
            ensure_ascii=False,
        )
    )

    fail_path = Path(args.failures_json)
    fail_path.parent.mkdir(parents=True, exist_ok=True)
    fail_path.write_text(
        json.dumps(
            {
                "summary": {
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "pass_rate": pass_rate,
                },
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote failures: {fail_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

