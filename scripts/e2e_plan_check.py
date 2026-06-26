#!/usr/bin/env python3
"""
Small, repeatable E2E checks for /plan without shell-escaping gymnastics.

Run from project root (recommended inside WSL venv):
  python scripts/e2e_plan_check.py --port 5001 --case all
"""

from __future__ import annotations

import argparse
import json
import sys
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


def print_result(title: str, data: dict[str, Any]) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    # Keep terminal output ASCII-only to avoid mixed-encoding mojibake
    # in PowerShell/WSL bridged sessions.
    print(json.dumps(data, ensure_ascii=True, indent=2))


def check_multi_background(base_url: str) -> bool:
    transcript = (
        "When you see me raise both hands, remind me to stay safe while exercising, "
        "and also set a 60 second timer to remind me to submit homework."
    )
    out = post_json(f"{base_url}/plan", {"transcript": transcript, "image_b64": None}, timeout=240)
    print_result("CASE: multi_background", out)
    render = str(out.get("render", ""))
    ok = "Completed 2/2 actions" in render and out.get("kind") in ("skill_result", "error")
    return ok


def check_ask_and_resume(base_url: str) -> bool:
    ask_transcript = "Check weather for me, but you must ask my city first."
    first = post_json(f"{base_url}/plan", {"transcript": ask_transcript, "image_b64": None}, timeout=240)
    print_result("CASE: ask_user_first_turn", first)
    awaiting_slot = str(first.get("awaiting_slot", "")).strip()
    if not awaiting_slot:
        return False

    second = post_json(f"{base_url}/plan", {"transcript": "Shanghai", "image_b64": None}, timeout=240)
    print_result("CASE: ask_user_resume_turn", second)
    render = str(second.get("render", ""))
    ok = second.get("kind") in ("skill_result", "error") and "Completed" in render
    return ok


def check_branch(base_url: str) -> bool:
    transcript = (
        "Please check weather. If weather is good, play cheerful music. "
        "If weather is bad, tell me a joke."
    )
    first = post_json(f"{base_url}/plan", {"transcript": transcript, "image_b64": None}, timeout=360)
    print_result("CASE: weather_branch_first_turn", first)

    if first.get("awaiting_slot"):
        second = post_json(f"{base_url}/plan", {"transcript": "Shanghai", "image_b64": None}, timeout=360)
        print_result("CASE: weather_branch_resume_turn", second)
        render = str(second.get("render", ""))
        return "branch" in render.lower() and "Completed" in render

    render = str(first.get("render", ""))
    return "branch" in render.lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument(
        "--case",
        choices=["all", "multi", "ask", "branch"],
        default="all",
        help="Which check to run.",
    )
    args = parser.parse_args()
    base_url = f"http://{args.host}:{args.port}"

    checks: list[tuple[str, bool]] = []
    try:
        if args.case in ("all", "multi"):
            checks.append(("multi_background", check_multi_background(base_url)))
        if args.case in ("all", "ask"):
            checks.append(("ask_user_resume", check_ask_and_resume(base_url)))
        if args.case in ("all", "branch"):
            checks.append(("branch", check_branch(base_url)))
    except urllib.error.URLError as e:
        print(f"ERROR: cannot reach {base_url}: {e}")
        return 2
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return 2

    print("\n" + "-" * 80)
    print("SUMMARY")
    print("-" * 80)
    all_ok = True
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        all_ok = all_ok and ok

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
