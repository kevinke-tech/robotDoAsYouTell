#!/usr/bin/env python3
"""
Unified quality gate runner.

Purpose:
- Run a fixed set of platform invariant gates before release/merge.
- Keep gates stable and domain-agnostic (not case-by-case feature rules).

Current gates:
1) e2e_invariants.py
2) regression_transient_invoke_repair.py
3) regression_intent_contract.py
4) regression_preflight_runtime_judge.py
Optional:
- e2e_live_transient_probe.py (semi-live network fluctuation probe)
- mass_eval_invariants.py (high-volume invariant stress)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INVARIANTS = ROOT / "scripts" / "e2e_invariants.py"
REGRESSION_TRANSIENT_REPAIR = ROOT / "scripts" / "regression_transient_invoke_repair.py"
REGRESSION_INTENT_CONTRACT = ROOT / "scripts" / "regression_intent_contract.py"
REGRESSION_PREFLIGHT_RUNTIME_JUDGE = ROOT / "scripts" / "regression_preflight_runtime_judge.py"
LIVE_TRANSIENT_PROBE = ROOT / "scripts" / "e2e_live_transient_probe.py"
MASS_EVAL = ROOT / "scripts" / "mass_eval_invariants.py"
FRONTEND_VISUAL_E2E = ROOT / "scripts" / "e2e_frontend_visual.py"
DEFAULT_CASES = ROOT / "scripts" / "invariant_cases.txt"


def _to_wsl_path(path: Path) -> str:
    s = str(path).replace("\\", "/")
    if len(s) >= 2 and s[1] == ":":
        drive = s[0].lower()
        rest = s[2:]
        if not rest.startswith("/"):
            rest = "/" + rest
        return f"/mnt/{drive}{rest}"
    return s


def _preferred_python() -> tuple[str, str]:
    win_venv = ROOT / ".venv" / "Scripts" / "python.exe"
    unix_venv = ROOT / ".venv" / "bin" / "python"
    unix_activate = ROOT / ".venv" / "bin" / "activate"
    if win_venv.exists():
        return ("native", str(win_venv))
    # On Windows + WSL-style venv, execute through `wsl bash -lc`.
    if os.name == "nt" and unix_activate.exists():
        return ("wsl", _to_wsl_path(ROOT / ".venv" / "bin" / "python3"))
    if unix_venv.exists():
        return ("native", str(unix_venv))
    return ("native", sys.executable)


def run_cmd(cmd: list[str]) -> int:
    print(f"[gate] running: {' '.join(cmd)}")
    proc = subprocess.run(cmd)
    return int(proc.returncode)


def _python_script_cmd(mode: str, py: str, script: Path, extra_args: list[str]) -> list[str]:
    if mode == "wsl":
        root_wsl = _to_wsl_path(ROOT)
        script_wsl = _to_wsl_path(script)
        args = " ".join(extra_args)
        return ["wsl", "bash", "-lc", f"cd {root_wsl} && {py} {script_wsl} {args}".strip()]
    return [py, str(script), *extra_args]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument(
        "--transcript-file",
        default=str(DEFAULT_CASES if DEFAULT_CASES.exists() else ""),
        help="Optional transcript file for invariant checks.",
    )
    ap.add_argument(
        "--live-probe",
        action="store_true",
        help="Run semi-live transient network probe against /plan.",
    )
    ap.add_argument(
        "--mass-eval",
        action="store_true",
        help="Run high-volume invariant stress using perturbed transcripts.",
    )
    ap.add_argument(
        "--mass-eval-count",
        type=int,
        default=80,
        help="Number of perturbed transcripts for --mass-eval.",
    )
    ap.add_argument(
        "--mass-eval-timeout",
        type=int,
        default=120,
        help="Per-request timeout seconds for mass eval.",
    )
    ap.add_argument(
        "--mass-eval-retries",
        type=int,
        default=1,
        help="Transient retry count per mass-eval case.",
    )
    ap.add_argument(
        "--mass-eval-seed-file",
        default=str(ROOT / "scripts" / "mass_eval_seeds.txt"),
        help="Seed transcript file for --mass-eval.",
    )
    ap.add_argument(
        "--visual-e2e",
        action="store_true",
        help="Run frontend screenshot-based visual E2E checks.",
    )
    ap.add_argument(
        "--visual-e2e-cases",
        default=str(ROOT / "scripts" / "frontend_visual_cases.json"),
        help="Case file for --visual-e2e.",
    )
    args = ap.parse_args()
    mode, py = _preferred_python()

    inv_args = ["--host", args.host, "--port", str(args.port)]
    if args.transcript_file:
        tf = args.transcript_file
        if mode == "wsl":
            tf = _to_wsl_path(Path(tf))
        inv_args.extend(["--transcript-file", tf])
    cmd = _python_script_cmd(mode, py, INVARIANTS, inv_args)

    rc = run_cmd(cmd)
    if rc != 0:
        print("[gate] FAIL: invariant gates failed")
        return rc

    rc = run_cmd(_python_script_cmd(mode, py, REGRESSION_TRANSIENT_REPAIR, []))
    if rc != 0:
        print("[gate] FAIL: transient invoke repair regression failed")
        return rc

    rc = run_cmd(_python_script_cmd(mode, py, REGRESSION_INTENT_CONTRACT, []))
    if rc != 0:
        print("[gate] FAIL: intent-contract regression failed")
        return rc

    rc = run_cmd(_python_script_cmd(mode, py, REGRESSION_PREFLIGHT_RUNTIME_JUDGE, []))
    if rc != 0:
        print("[gate] FAIL: preflight/runtime-judge regression failed")
        return rc

    if args.live_probe:
        rc = run_cmd(
            _python_script_cmd(
                mode,
                py,
                LIVE_TRANSIENT_PROBE,
                ["--host", args.host, "--port", str(args.port)],
            )
        )
        if rc != 0:
            print("[gate] FAIL: live transient probe failed")
            return rc

    if args.mass_eval:
        seed_tf = args.mass_eval_seed_file
        if mode == "wsl":
            seed_tf = _to_wsl_path(Path(seed_tf))
        rc = run_cmd(
            _python_script_cmd(
                mode,
                py,
                MASS_EVAL,
                [
                    "--host",
                    args.host,
                    "--port",
                    str(args.port),
                    "--seed-transcript-file",
                    seed_tf,
                    "--count",
                    str(max(1, int(args.mass_eval_count))),
                    "--request-timeout",
                    str(max(10, int(args.mass_eval_timeout))),
                    "--max-retries-per-case",
                    str(max(0, int(args.mass_eval_retries))),
                ],
            )
        )
        if rc != 0:
            print("[gate] FAIL: mass eval invariant stress failed")
            return rc

    if args.visual_e2e:
        cases_path = args.visual_e2e_cases
        if mode == "wsl":
            cases_path = _to_wsl_path(Path(cases_path))
        rc = run_cmd(
            _python_script_cmd(
                mode,
                py,
                FRONTEND_VISUAL_E2E,
                [
                    "--host",
                    args.host,
                    "--port",
                    str(args.port),
                    "--cases",
                    cases_path,
                ],
            )
        )
        if rc != 0:
            print("[gate] FAIL: frontend visual e2e failed")
            return rc

    print("[gate] PASS: all quality gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

