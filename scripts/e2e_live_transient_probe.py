#!/usr/bin/env python3
"""
Semi-live probe for transient network robustness on /plan.

Goal:
- Detect whether transient external failures (timeout/connect) are eventually
  recovered to a usable result within bounded retries.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def post_json(url: str, payload: dict[str, Any], timeout: int = 240) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _is_transient_error_text(s: str) -> bool:
    x = str(s or "").lower()
    hints = (
        "connecttimeout",
        "readtimeout",
        "timeout",
        "connecterror",
        "remoteprotocolerror",
        "bridge request failed",
        "peer closed connection",
        "temporary failure",
        "service unavailable",
        "dns",
    )
    return any(h in x for h in hints)


def _is_usable_plan(plan: dict[str, Any]) -> bool:
    kind = str(plan.get("kind") or "").strip().lower()
    if kind not in ("skill_result", "chat"):
        return False
    speak = str(plan.get("speak") or "").strip()
    render = str(plan.get("render") or "").strip()
    if not speak and not render:
        return False
    if "placeholder output detected" in render.lower():
        return False
    return True


def _extract_error_blob(plan: dict[str, Any]) -> str:
    return " | ".join(
        [
            str(plan.get("error") or ""),
            str(plan.get("speak") or ""),
            str(plan.get("render") or ""),
        ]
    ).strip()


def run_case(
    base_url: str,
    transcript: str,
    attempts: int,
    sleep_sec: float,
    request_timeout: int,
) -> tuple[bool, str]:
    saw_transient = False
    last_blob = ""
    for i in range(1, attempts + 1):
        print(f"  attempt {i}/{attempts} ...", flush=True)
        plan = post_json(
            f"{base_url}/plan",
            {"transcript": transcript, "image_b64": None},
            timeout=request_timeout,
        )
        if _is_usable_plan(plan):
            if saw_transient:
                return True, f"recovered on attempt {i}"
            return True, f"usable on attempt {i}"
        blob = _extract_error_blob(plan)
        last_blob = blob
        if _is_transient_error_text(blob):
            saw_transient = True
        else:
            return False, f"non-transient unusable result on attempt {i}: {blob[:220]}"
        if i < attempts:
            time.sleep(max(0.0, sleep_sec))
    if saw_transient:
        return False, f"transient failures persisted after {attempts} attempts: {last_blob[:220]}"
    return False, f"unusable result after {attempts} attempts: {last_blob[:220]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--sleep-sec", type=float, default=1.0)
    ap.add_argument("--request-timeout", type=int, default=120)
    ap.add_argument(
        "--transcript",
        action="append",
        default=[
            "来点搞笑的视频",
            "查一下深圳现在天气怎么样",
        ],
        help="Probe transcript. Can be repeated.",
    )
    args = ap.parse_args()
    base_url = f"http://{args.host}:{args.port}"

    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=5) as resp:
            if int(getattr(resp, "status", 0)) != 200:
                raise RuntimeError(f"health status={getattr(resp, 'status', 0)}")
    except Exception as e:
        print(f"FAIL: backend is not reachable: {type(e).__name__}: {e}")
        return 2

    overall_ok = True
    cases = [str(x).strip() for x in (args.transcript or []) if str(x).strip()]
    for idx, t in enumerate(cases, start=1):
        print(f"\nCASE {idx}: {t}", flush=True)
        try:
            ok, msg = run_case(
                base_url,
                t,
                max(1, args.attempts),
                args.sleep_sec,
                max(5, int(args.request_timeout)),
            )
        except urllib.error.URLError as e:
            print(f"FAIL case#{idx}: transport error: {e}")
            overall_ok = False
            continue
        except Exception as e:
            print(f"FAIL case#{idx}: {type(e).__name__}: {e}")
            overall_ok = False
            continue
        status = "PASS" if ok else "FAIL"
        print(f"{status} case#{idx}: {t} -> {msg}")
        if not ok:
            overall_ok = False

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

