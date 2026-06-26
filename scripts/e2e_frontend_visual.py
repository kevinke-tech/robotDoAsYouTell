#!/usr/bin/env python3
"""
Frontend visual E2E checks using Playwright screenshots.

Goal:
- Validate "eyes-see" fulfillment on the browser UI, not only backend JSON.
- Submit transcript from frontend input, wait for rendered UI card, then assert
  real render outcomes (e.g. image actually loaded pixels).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = ROOT / "scripts" / "frontend_visual_cases.json"
DEFAULT_SHOTS = ROOT / "logs" / "frontend_visual_screenshots"
DEFAULT_REPORT = ROOT / "logs" / "frontend_visual_report.json"


def _frontend_url() -> str:
    return (ROOT / "frontend" / "index.html").resolve().as_uri()


def _load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("cases must be a JSON array")
    out: list[dict[str, Any]] = []
    for i, c in enumerate(data, start=1):
        if not isinstance(c, dict):
            continue
        transcript = str(c.get("transcript") or "").strip()
        if not transcript:
            continue
        out.append(
            {
                "name": str(c.get("name") or f"case_{i}"),
                "transcript": transcript,
                "expect": c.get("expect") if isinstance(c.get("expect"), dict) else {},
            }
        )
    if not out:
        raise ValueError("no valid cases")
    return out


async def _probe_last_ui(page) -> dict[str, Any]:
    return await page.evaluate(
        """
() => {
  const cards = Array.from(document.querySelectorAll('.msg.agent.ui-card'));
  const last = cards.length ? cards[cards.length - 1] : null;
  const agentMsgs = Array.from(document.querySelectorAll('.msg.agent'));
  const lastAgentText = agentMsgs.length
    ? String(agentMsgs[agentMsgs.length - 1].innerText || '')
    : '';
  if (!last) {
    return {
      has_ui: false,
      ui_type: '',
      loaded_images: 0,
      total_images: 0,
      iframe_count: 0,
      audio_count: 0,
      video_count: 0,
      card_text: '',
      last_agent_text: lastAgentText,
    };
  }
  const imgs = Array.from(last.querySelectorAll('img'));
  const loadedImages = imgs.filter((img) => img.complete && Number(img.naturalWidth || 0) > 2).length;
  const iframes = Array.from(last.querySelectorAll('iframe'));
  const audios = Array.from(last.querySelectorAll('audio'));
  const videos = Array.from(last.querySelectorAll('video'));
  return {
    has_ui: true,
    ui_type: String(last.dataset.uiType || ''),
    loaded_images: loadedImages,
    total_images: imgs.length,
    iframe_count: iframes.length,
    audio_count: audios.length,
    video_count: videos.length,
    card_text: String(last.innerText || ''),
    last_agent_text: lastAgentText,
  };
}
"""
    )


def _check_expect(probe: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if bool(expect.get("require_ui", True)) and not bool(probe.get("has_ui")):
        errs.append("no ui card rendered")
    expected_types = expect.get("allowed_ui_types")
    if isinstance(expected_types, list) and expected_types:
        ui_type = str(probe.get("ui_type") or "")
        if ui_type not in {str(x).strip().lower() for x in expected_types}:
            errs.append(f"ui_type mismatch: got '{ui_type}'")
    min_loaded_images = expect.get("min_loaded_images")
    if isinstance(min_loaded_images, int):
        if int(probe.get("loaded_images") or 0) < min_loaded_images:
            errs.append(
                f"loaded_images too low: {probe.get('loaded_images', 0)} < {min_loaded_images}"
            )
    required_patterns = expect.get("require_text_patterns")
    if isinstance(required_patterns, list) and required_patterns:
        text = f"{probe.get('card_text','')}\n{probe.get('last_agent_text','')}"
        for p in required_patterns:
            ps = str(p or "").strip()
            if not ps:
                continue
            if not re.search(ps, text, re.IGNORECASE):
                errs.append(f"text pattern missing: {ps}")
    return errs


async def _run_case(page, case: dict[str, Any], screenshot_dir: Path) -> dict[str, Any]:
    name = case["name"]
    transcript = case["transcript"]
    expect = case["expect"]
    timeout_ms = int(expect.get("timeout_ms") or 90000)

    await page.goto(_frontend_url(), wait_until="domcontentloaded")
    await page.wait_for_selector("#text-input", timeout=10000)
    base_agent_msgs = await page.evaluate("() => document.querySelectorAll('.msg.agent').length")
    base_ui_cards = await page.evaluate("() => document.querySelectorAll('.msg.agent.ui-card').length")
    await page.fill("#text-input", transcript)
    await page.click("#text-input-form button[type='submit']")

    # Wait for a meaningful completion signal instead of first progress line.
    await page.wait_for_function(
        """([baseAgent, baseUi]) => {
  const agents = Array.from(document.querySelectorAll('.msg.agent'));
  const uiCount = document.querySelectorAll('.msg.agent.ui-card').length;
  if (uiCount > baseUi) return true;
  if (agents.length <= baseAgent) return false;
  const lastTxt = String(agents[agents.length - 1].innerText || '').toLowerCase();
  if (!lastTxt) return false;
  const isProgressOnly = lastTxt.includes('[进展]');
  if (isProgressOnly) return false;
  // Completed output markers.
  if (lastTxt.includes('[synthesized]') || lastTxt.includes('agent-ui')) return true;
  if (lastTxt.includes('[skill error]') || lastTxt.includes('[synth one-shot failed]') || lastTxt.includes('[错误]')) return true;
  // If assistant pauses for missing slot, this is also a valid end state.
  if (lastTxt.includes('waiting for slot') || lastTxt.includes('等待补充信息')) return true;
  return false;
}""",
        arg=[base_agent_msgs, base_ui_cards],
        timeout=timeout_ms,
    )
    # Give media cards a short render window.
    await page.wait_for_timeout(3500)

    probe = await _probe_last_ui(page)
    errs = _check_expect(probe, expect)
    shot = screenshot_dir / f"{name}.png"
    await page.screenshot(path=str(shot), full_page=True)
    return {
        "name": name,
        "transcript": transcript,
        "ok": len(errs) == 0,
        "errors": errs,
        "probe": probe,
        "screenshot": str(shot),
    }


async def _amain(args) -> int:
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        print(f"FAIL: playwright import failed: {e}")
        print("Hint: pip install -r requirements.txt && playwright install chromium")
        return 2

    cases = _load_cases(Path(args.cases))
    screenshot_dir = Path(args.screenshot_dir)
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headful)
        context = await browser.new_context(
            viewport={"width": 1600, "height": 980},
            ignore_https_errors=True,
        )
        page = await context.new_page()
        for case in cases:
            try:
                r = await _run_case(page, case, screenshot_dir)
            except Exception as e:
                r = {
                    "name": case["name"],
                    "transcript": case["transcript"],
                    "ok": False,
                    "errors": [f"{type(e).__name__}: {e}"],
                    "probe": {},
                    "screenshot": "",
                }
            results.append(r)
            state = "PASS" if r["ok"] else "FAIL"
            print(f"[visual-e2e] {state} {r['name']}: {r['transcript']}")
        await context.close()
        await browser.close()

    failed = [r for r in results if not r.get("ok")]
    report = {
        "summary": {
            "total": len(results),
            "passed": len(results) - len(failed),
            "failed": len(failed),
        },
        "results": results,
    }
    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[visual-e2e] wrote report: {report_path}")
    return 0 if not failed else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1", help="reserved for compatibility")
    ap.add_argument("--port", type=int, default=5001, help="reserved for compatibility")
    ap.add_argument("--cases", default=str(DEFAULT_CASES))
    ap.add_argument("--screenshot-dir", default=str(DEFAULT_SHOTS))
    ap.add_argument("--report-json", default=str(DEFAULT_REPORT))
    ap.add_argument("--headful", action="store_true")
    args = ap.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())

