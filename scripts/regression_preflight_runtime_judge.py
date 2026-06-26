#!/usr/bin/env python3
"""Regression checks for skill preflight and runtime judge."""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_judge import classify_error
from skill_preflight import run_skill_preflight


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _write(p: Path, content: str) -> None:
    p.write_text(content, encoding="utf-8")


def main() -> int:
    # Runtime judge classification checks.
    c1 = classify_error("ConnectTimeout: upstream timed out", stage="invoke")
    _assert(c1.get("transient") is True and c1.get("category") == "transient_external", f"bad invoke classify: {c1}")

    c2 = classify_error("agent didn't produce a unique skill file", stage="synthesis")
    _assert(c2.get("recoverable") is True and c2.get("category") == "recoverable_synthesis", f"bad synthesis classify: {c2}")

    # Skill preflight must reject visible browser operations.
    with tempfile.TemporaryDirectory() as td:
        bad_skill = Path(td) / "bad_visible_browser.py"
        _write(
            bad_skill,
            '''import webbrowser

RUN_SPEC={"name":"bad_visible_browser","description":"x","args_schema":{"type":"object","properties":{},"required":[]}}

async def run(**kwargs):
    webbrowser.open("https://example.com")
    return {"speak":"ok","render":"source_url: https://example.com"}

if __name__ == "__main__":
    print("OK")
''',
        )
        ok, errs, warns = run_skill_preflight(bad_skill)
        _assert(not ok, "preflight should fail visible browser usage")
        _assert(any("webbrowser" in e.lower() or "visible browser" in e.lower() for e in errs), f"expected browser error, errs={errs}, warns={warns}")

    print("PASS: preflight + runtime judge regression checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

