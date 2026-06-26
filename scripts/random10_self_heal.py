#!/usr/bin/env python3
"""
Random 10-case end-to-end evaluator with self-healing reinforcement.

What it automates:
1) Randomly generate intent-diverse test cases.
2) Run /plan for each case.
3) Validate by fixed invariants + intent-compiled outcome contract.
4) Retry transient failures automatically.
5) Reinforce regression coverage by appending failed transcripts to
   scripts/mass_eval_seeds.txt, then re-run quality gate (optional).
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from e2e_invariants import _check_invariants, post_json  # type: ignore
from intent_compiler import compile_intent_hints
from outcome_contract import validate_outcome_payload
from runtime_judge import classify_error


def _generate_random_intents(count: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    cities = ["深圳", "广州", "上海", "北京", "成都", "杭州"]
    poi_types = ["餐饮店", "咖啡店", "火锅店", "早餐店", "药店"]
    route_pairs = [("深圳湾公园", "南山书城"), ("广州塔", "珠江新城"), ("上海虹桥站", "外滩"), ("北京南站", "国贸")]
    story_styles = ["科幻", "悬疑", "治愈", "冒险", "职场"]
    joke_styles = ["冷笑话", "职场段子", "程序员笑话", "家庭笑话"]
    wiki_topics = ["图灵测试", "量子计算", "区块链", "黑洞", "CRISPR"]
    news_topics = ["AI", "新能源", "芯片", "国际经济", "体育头条"]
    trips = [("深圳", "北京"), ("上海", "成都"), ("广州", "杭州"), ("北京", "重庆")]

    template_fns = [
        # Encyclopedia / knowledge retrieval
        lambda: f"查一下“{rng.choice(wiki_topics)}”的百科，给我一个简明总结并附上来源",
        # Storytelling
        lambda: f"讲一个{rng.choice(story_styles)}风格的短故事，控制在200字左右",
        # Jokes
        lambda: f"来一个{rng.choice(joke_styles)}，要简短一点",
        # Navigation / route
        lambda: (lambda p: f"从{p[0]}到{p[1]}怎么走？给我一个导航建议，尽量含出行方式")(rng.choice(route_pairs)),
        # Flight + hotel
        lambda: (lambda t: f"帮我查下周从{t[0]}到{t[1]}的机票和酒店大致信息，给我建议")(rng.choice(trips)),
        # Nearby POI
        lambda: f"查一下{rng.choice(cities)}某个地铁站附近的{rng.choice(poi_types)}，推荐3个并说明理由",
        # Headlines
        lambda: f"给我看今天{rng.choice(news_topics)}相关的头条新闻，做要点摘要",
        # Mixed intent with constraints
        lambda: f"我准备周末去{rng.choice(cities)}，请先给我一个半天游玩+餐饮安排建议",
        # Practical lookup
        lambda: f"查一下{rng.choice(cities)}今天的天气和体感，顺便给穿衣建议",
        # Actionable media intent
        lambda: f"给我来一个{rng.choice(['放松', '专注', '轻音乐'])}的可播放音频",
        lambda: f"给我来一个{rng.choice(['城市风光', '健身', '科普'])}主题的可播放视频",
    ]

    pool: list[str] = []
    # Build a larger candidate pool first, then sample unique.
    for _ in range(max(40, count * 4)):
        pool.append(rng.choice(template_fns)())
    unique: list[str] = []
    seen = set()
    for t in pool:
        if t in seen:
            continue
        seen.add(t)
        unique.append(t)
        if len(unique) >= count:
            break
    return unique[:count]


def _infer_intent_kind(transcript: str) -> str:
    t = (transcript or "").strip().lower()
    if ("看到" in t and "就说" in t) or ("秒后提醒" in t) or ("分钟后提醒" in t):
        return "background"
    return "one_shot"


def _build_contract_from_intent(transcript: str) -> dict:
    kind = _infer_intent_kind(transcript)
    hints = compile_intent_hints(transcript=transcript, spec=transcript, intent_kind=kind)
    checks = ["non_empty_output", "not_placeholder_output"]
    if hints.get("requires_ui_delivery"):
        checks.append("ui_present")
    if hints.get("fulfillment_mode") != "address_lookup":
        checks.append("not_link_only")
    if any(k in transcript.lower() for k in ["几点", "星期", "日期", "weather", "time", "date"]):
        checks.append("evidence_present")
    # dedup keep order
    seen = set()
    checks = [c for c in checks if not (c in seen or seen.add(c))]
    return {
        "delivery": "auto",
        "fulfillment_mode": str(hints.get("fulfillment_mode") or "task_completion"),
        "requires_ui_delivery": bool(hints.get("requires_ui_delivery", False)),
        "require_playable_media": bool(hints.get("require_playable_media", False)),
        "require_visual_media": bool(hints.get("require_visual_media", False)),
        "explicit_min_count": hints.get("explicit_min_count"),
        "checks": checks,
    }


def _append_seed_if_missing(seed_file: Path, transcript: str) -> bool:
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if seed_file.exists():
        for ln in seed_file.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if s and not s.startswith("#"):
                existing.add(s)
    if transcript in existing:
        return False
    with seed_file.open("a", encoding="utf-8") as f:
        if seed_file.stat().st_size > 0:
            f.write("\n")
        f.write(transcript)
        f.write("\n")
    return True


def _run_one_case(base_url: str, transcript: str, timeout: int) -> dict[str, Any]:
    try:
        plan = post_json(
            f"{base_url}/plan",
            {"transcript": transcript, "image_b64": None},
            timeout=timeout,
        )
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        judged = classify_error(err, stage="invoke")
        return {
            "ok": False,
            "transcript": transcript,
            "plan": {"kind": "error", "speak": "", "render": ""},
            "invariant_failures": [f"runtime_error: {err}"],
            "contract_failures": [],
            "transient": bool(judged.get("transient")),
            "error": err,
        }

    invariant_failures = _check_invariants(transcript, plan)
    contract = _build_contract_from_intent(transcript)
    ok_contract, _, contract_failures = validate_outcome_payload(plan, contract)
    kind = str(plan.get("kind") or "").strip().lower()
    hard_fail = kind == "error"
    if hard_fail:
        invariant_failures = list(invariant_failures) + ["runtime_result_kind_error"]
    ok = (len(invariant_failures) == 0) and bool(ok_contract) and (not hard_fail)
    return {
        "ok": ok,
        "transcript": transcript,
        "plan": plan,
        "invariant_failures": invariant_failures,
        "contract_failures": list(contract_failures),
        "transient": False,
        "error": "",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--rng-seed", type=int, default=20260618)
    ap.add_argument("--request-timeout", type=int, default=120)
    ap.add_argument("--max-retries-per-case", type=int, default=1)
    ap.add_argument(
        "--seed-file",
        default=str(SCRIPTS / "mass_eval_seeds.txt"),
        help="Where to append failed transcripts for regression reinforcement.",
    )
    ap.add_argument(
        "--report-json",
        default=str(ROOT / "logs" / "random10_self_heal_report.json"),
        help="Report output path.",
    )
    ap.add_argument(
        "--run-gate-after-heal",
        action="store_true",
        help="Run quality_gate --mass-eval after reinforcing seeds.",
    )
    ap.add_argument("--gate-mass-eval-count", type=int, default=20)
    args = ap.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    intents = _generate_random_intents(max(1, int(args.count)), int(args.rng_seed))
    results: list[dict[str, Any]] = []
    reinforced = 0

    for idx, t in enumerate(intents, start=1):
        final = None
        for attempt in range(max(0, int(args.max_retries_per_case)) + 1):
            r = _run_one_case(base_url, t, timeout=max(20, int(args.request_timeout)))
            r["attempt"] = attempt + 1
            if r.get("ok"):
                final = r
                print(f"[random10] case#{idx} PASS on attempt {attempt+1}: {t}")
                break
            if bool(r.get("transient")) and attempt < int(args.max_retries_per_case):
                print(f"[random10] case#{idx} transient retry {attempt+1}: {t}")
                continue
            final = r
            print(f"[random10] case#{idx} FAIL on attempt {attempt+1}: {t}")
            break
        assert final is not None
        results.append(final)
        if not final.get("ok"):
            if _append_seed_if_missing(Path(args.seed_file), t):
                reinforced += 1

    failed = [x for x in results if not x.get("ok")]
    summary: dict[str, Any] = {
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "reinforced_seeds_added": reinforced,
        "rng_seed": int(args.rng_seed),
        "host": args.host,
        "port": int(args.port),
    }

    gate_rc = None
    gate_cmd = None
    if args.run_gate_after_heal:
        gate_cmd = [
            sys.executable,
            str(SCRIPTS / "quality_gate.py"),
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--mass-eval",
            "--mass-eval-count",
            str(max(1, int(args.gate_mass_eval_count))),
        ]
        print(f"[random10] running gate after heal: {' '.join(gate_cmd)}")
        gate_rc = subprocess.run(gate_cmd).returncode
        summary["post_heal_gate_passed"] = (gate_rc == 0)
        summary["post_heal_gate_rc"] = gate_rc
    else:
        summary["post_heal_gate_passed"] = None

    report = {
        "summary": summary,
        "intents": intents,
        "results": results,
        "gate_cmd": gate_cmd,
    }
    out = Path(args.report_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print(f"[random10] wrote report: {out}")
    return 0 if (len(failed) == 0 and (gate_rc in (None, 0))) else 1


if __name__ == "__main__":
    raise SystemExit(main())

