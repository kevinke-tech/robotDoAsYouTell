#!/usr/bin/env python3
"""
Regression: transient invoke failures must trigger runtime resilience repair
and eventually return a usable payload (not just keep a degraded skill).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


async def _run_case() -> int:
    synth_calls = {"n": 0}
    invoke_calls = {"n": 0}

    original_synth = server.synthesizer.synthesize_one_shot
    original_run = server.run_one_shot
    original_remove = server._remove_skill_artifacts
    original_broadcast_skills_changed = server._broadcast_skills_changed
    original_broadcast_progress = server._broadcast_progress
    original_transient_repair_max = server.ONE_SHOT_TRANSIENT_REPAIR_MAX
    original_transient_retry_max = server.ONE_SHOT_TRANSIENT_RETRY_MAX

    async def fake_synthesize(spec: str, registry: Any) -> dict:
        synth_calls["n"] += 1
        return {
            "ok": True,
            "name": "fake_transient_skill",
            "cost_usd": 0.0,
            "transcript": spec,
        }

    async def fake_run_one_shot(registry: Any, name: str, args: dict[str, Any]) -> dict:
        invoke_calls["n"] += 1
        # First invoke path fails with transient timeout, then recovery succeeds.
        if invoke_calls["n"] <= 2:
            return {"ok": False, "error": "ConnectTimeout: simulated timeout"}
        return {
            "ok": True,
            "result": {
                "speak": "恢复成功，结果可用。",
                "render": (
                    "source: regression_test\n"
                    "source_url: https://example.test/transient-repair\n"
                    "evidence: recovered_after_transient_timeout"
                ),
                "source_url": "https://example.test/transient-repair",
                "ui": {"type": "info_card", "title": "恢复成功", "message": "技能已恢复可用"},
            },
        }

    async def noop_remove(name: str) -> None:
        return None

    async def noop_broadcast_skills_changed() -> None:
        return None

    async def noop_broadcast_progress(message: str, session_id: str = "") -> None:
        return None

    try:
        server.synthesizer.synthesize_one_shot = fake_synthesize
        server.run_one_shot = fake_run_one_shot
        server._remove_skill_artifacts = noop_remove
        server._broadcast_skills_changed = noop_broadcast_skills_changed
        server._broadcast_progress = noop_broadcast_progress
        server.ONE_SHOT_TRANSIENT_REPAIR_MAX = 2
        server.ONE_SHOT_TRANSIENT_RETRY_MAX = 1

        out = await server._synthesize_and_validate_one_shot(
            spec="Build a generic one-shot skill for regression test.",
            transcript="regression transient invoke",
            outcome_contract={"delivery": "informational", "checks": ["non_empty_output", "evidence_present"]},
            session_id="regression",
        )
    finally:
        server.synthesizer.synthesize_one_shot = original_synth
        server.run_one_shot = original_run
        server._remove_skill_artifacts = original_remove
        server._broadcast_skills_changed = original_broadcast_skills_changed
        server._broadcast_progress = original_broadcast_progress
        server.ONE_SHOT_TRANSIENT_REPAIR_MAX = original_transient_repair_max
        server.ONE_SHOT_TRANSIENT_RETRY_MAX = original_transient_retry_max

    if not out.get("ok"):
        print(f"FAIL: expected usable result after transient repair, got: {out}")
        return 1
    if synth_calls["n"] < 2:
        print(f"FAIL: expected re-synthesis after transient failure, synth_calls={synth_calls['n']}")
        return 1
    payload = out.get("payload") if isinstance(out, dict) else {}
    if not isinstance(payload, dict) or not str(payload.get("speak") or "").strip():
        print(f"FAIL: usable payload missing speak: {payload}")
        return 1
    if "source" not in str(payload.get("render") or "").lower():
        print(f"FAIL: payload missing evidence marker in render: {payload.get('render')}")
        return 1

    print("PASS: transient invoke repair produced usable payload")
    return 0


def main() -> int:
    return asyncio.run(_run_case())


if __name__ == "__main__":
    raise SystemExit(main())

