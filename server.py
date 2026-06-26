#!/usr/bin/env python3
"""
vox backend — FastAPI

Endpoints:
  POST /asr            : WAV in → text out (FunASR local)
  POST /plan           : transcript + image_b64 → planner decision (Claude + tools)
  POST /tts            : text in → audio/mpeg out (Volc OpenSpeech)
  GET  /health         : service status
  GET  /watchers       : list active background skills (inspection)
  WS   /ws/output      : server → client push (watcher TTS, frames_required signal)
  WS   /ws/frames      : client → server stream of camera frames (for vision watchers)
"""

import io
import asyncio
import json
import os
import re
import threading
import time
import wave
import copy
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

load_dotenv(".env.local")

from dispatcher import SKILLS_DIR, SkillRegistry, run_one_shot  # noqa: E402
import planner as planner_mod  # noqa: E402
import runtime  # noqa: E402
from background import BackgroundRunner  # noqa: E402
import trigger_check  # noqa: E402
import synthesizer  # noqa: E402
from browser import BrowserHost  # noqa: E402
from ui_contract import validate_and_normalize_ui  # noqa: E402
import skill_manifest  # noqa: E402
from outcome_contract import normalize_outcome_contract, validate_outcome_payload  # noqa: E402
from deliverability_probe import probe_ui_deliverability  # noqa: E402
from intent_compiler import compile_intent_hints  # noqa: E402
from web_search import search_web, format_search_hits  # noqa: E402
from web_fetch import fetch_page  # noqa: E402
from evidence_utils import build_render_evidence_block  # noqa: E402
from runtime_judge import (
    classify_error,
    is_recoverable_synthesis_error as judge_recoverable_synthesis_error,
    is_transient_external_error as judge_transient_external_error,
)  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FUNASR_MODEL = os.getenv("FUNASR_OFFLINE_MODEL", "paraformer-zh")
SAMPLE_RATE = 16000

VOLC_TTS_APP_ID = os.getenv("VOLC_TTS_APP_ID", "")
VOLC_TTS_ACCESS_TOKEN = os.getenv("VOLC_TTS_ACCESS_TOKEN", "")
VOLC_TTS_SECRET_KEY = os.getenv("VOLC_TTS_SECRET_KEY", "")
VOLC_TTS_VOICE_TYPE = os.getenv("VOLC_TTS_VOICE_TYPE", "zh_female_sajiaonvyou_moon_bigtts")
VOLC_TTS_URL = os.getenv("VOLC_TTS_URL", "https://openspeech.bytedance.com/api/v1/tts")
VOLC_TTS_CLUSTER = os.getenv("VOLC_TTS_CLUSTER", "volcano_tts")

SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5001"))
VOX_DEPLOY_REGION = os.getenv("VOX_DEPLOY_REGION", "CN").strip().upper() or "CN"
VOX_PRIMARY_LOCALE = os.getenv("VOX_PRIMARY_LOCALE", "zh-CN")
try:
    ONE_SHOT_TRANSIENT_RETRY_MAX = max(0, int(os.getenv("ONE_SHOT_TRANSIENT_RETRY_MAX", "2")))
except Exception:
    ONE_SHOT_TRANSIENT_RETRY_MAX = 2
try:
    ONE_SHOT_TRANSIENT_REPAIR_MAX = max(0, int(os.getenv("ONE_SHOT_TRANSIENT_REPAIR_MAX", "2")))
except Exception:
    ONE_SHOT_TRANSIENT_REPAIR_MAX = 2
try:
    ONE_SHOT_SYNTH_RECOVERY_MAX = max(0, int(os.getenv("ONE_SHOT_SYNTH_RECOVERY_MAX", "2")))
except Exception:
    ONE_SHOT_SYNTH_RECOVERY_MAX = 2
try:
    ONE_SHOT_VALIDATION_REPAIR_MAX = max(0, int(os.getenv("ONE_SHOT_VALIDATION_REPAIR_MAX", "2")))
except Exception:
    ONE_SHOT_VALIDATION_REPAIR_MAX = 2
try:
    DELIVERABILITY_PROBE_ENABLED = str(os.getenv("VOX_DELIVERABILITY_PROBE", "1")).strip().lower() not in ("0", "false", "no")
except Exception:
    DELIVERABILITY_PROBE_ENABLED = True
try:
    DELIVERABILITY_PROBE_TIMEOUT_SEC = max(1.0, float(os.getenv("VOX_DELIVERABILITY_PROBE_TIMEOUT_SEC", "6")))
except Exception:
    DELIVERABILITY_PROBE_TIMEOUT_SEC = 6.0
try:
    ONE_SHOT_TOTAL_BUDGET_SEC = max(30.0, float(os.getenv("ONE_SHOT_TOTAL_BUDGET_SEC", "120")))
except Exception:
    ONE_SHOT_TOTAL_BUDGET_SEC = 120.0
try:
    ONE_SHOT_SYNTH_CALL_TIMEOUT_SEC = max(20.0, float(os.getenv("ONE_SHOT_SYNTH_CALL_TIMEOUT_SEC", "75")))
except Exception:
    ONE_SHOT_SYNTH_CALL_TIMEOUT_SEC = 75.0

print(f"[vox] ASR model   : {FUNASR_MODEL} (FunASR local)", flush=True)
print(f"[vox] TTS         : {'Volc (' + VOLC_TTS_VOICE_TYPE + ')' if VOLC_TTS_APP_ID else 'NOT CONFIGURED'}", flush=True)
print(f"[vox] Trigger     : {trigger_check.backend_label()}", flush=True)

# ---------------------------------------------------------------------------
# FunASR singleton (lifted from vui)
# ---------------------------------------------------------------------------

_asr_model = None
_asr_model_lock = threading.Lock()


def _get_asr_model():
    global _asr_model
    with _asr_model_lock:
        if _asr_model is not None:
            return _asr_model
        os.environ.setdefault("TQDM_DISABLE", "1")
        from funasr import AutoModel
        print(f"[ASR] Loading FunASR model '{FUNASR_MODEL}' …", flush=True)
        _asr_model = AutoModel(model=FUNASR_MODEL, disable_update=True)
        print("[ASR] Model loaded", flush=True)
        return _asr_model


def _wav_bytes_to_float32(wav_bytes: bytes) -> np.ndarray:
    with io.BytesIO(wav_bytes) as bio, wave.open(bio, "rb") as w:
        nch = w.getnchannels()
        sampw = w.getsampwidth()
        framerate = w.getframerate()
        raw = w.readframes(w.getnframes())

    if sampw == 2:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampw == 1:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 128.0) - 1.0
    else:
        raise ValueError(f"Unsupported sample width: {sampw}")

    if nch > 1:
        arr = arr.reshape(-1, nch)[:, 0]

    if framerate != SAMPLE_RATE:
        n_old = arr.size
        n_new = int(round(n_old * SAMPLE_RATE / framerate))
        arr = np.interp(
            np.linspace(0, 1, n_new),
            np.linspace(0, 1, n_old),
            arr,
        ).astype(np.float32)

    return arr


def _extract_asr_text(res) -> str:
    if not res:
        return ""
    parts = []
    for item in res if isinstance(res, list) else [res]:
        if isinstance(item, str):
            parts.append(item.strip())
        elif isinstance(item, dict):
            parts.append((item.get("text") or "").strip())
        elif isinstance(item, list):
            for x in item:
                if isinstance(x, dict):
                    parts.append((x.get("text") or "").strip())
                elif isinstance(x, str):
                    parts.append(x.strip())
    return "".join(parts)


def transcribe_wav(wav_bytes: bytes) -> str:
    import time
    t0 = time.perf_counter()
    arr = _wav_bytes_to_float32(wav_bytes)
    if arr.size < 400:
        return ""

    audio_dur = arr.size / SAMPLE_RATE
    model = _get_asr_model()
    t1 = time.perf_counter()
    res = model.generate(input=np.ascontiguousarray(arr, dtype=np.float32))
    t2 = time.perf_counter()
    text = _extract_asr_text(res)
    rtf = (t2 - t1) / audio_dur if audio_dur > 0 else 0
    print(
        f"[ASR] '{text}' | audio={audio_dur:.1f}s | infer={(t2-t1)*1000:.0f}ms "
        f"| RTF={rtf:.2f} | total={(t2-t0)*1000:.0f}ms",
        flush=True,
    )
    return text


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PlanRequest(BaseModel):
    transcript: str
    image_b64: Optional[str] = None  # JPEG b64 from camera, sans data: prefix
    context: Optional[dict] = None
    session_id: Optional[str] = None


class TTSRequest(BaseModel):
    text: str
    voice_type: Optional[str] = None
    speed_ratio: Optional[float] = None
    pitch_ratio: Optional[float] = None
    volume_ratio: Optional[float] = None


class MediaPlaybackFeedback(BaseModel):
    session_id: Optional[str] = None
    skill: Optional[str] = None
    ui_type: Optional[str] = None
    media_url: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="vox", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


REGISTRY = SkillRegistry()
REGISTRY.load_all()

# ───── /ws/output client set + broadcast ─────
output_clients: set[WebSocket] = set()


async def output_broadcast(message: dict) -> None:
    """Push a JSON message to every connected /ws/output client."""
    if not output_clients:
        return
    payload = json.dumps(message)
    dead: list[WebSocket] = []
    for ws in list(output_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        output_clients.discard(ws)


# ───── background runner — set as runtime global so skills can reach it ─────
RUNNER = BackgroundRunner(output_send=output_broadcast)
runtime.RUNNER = RUNNER
runtime.OUTPUT_BROADCAST = output_broadcast

# ───── browser host — Chromium lazy-launched on first new_page() ─────
BROWSER_HOST = BrowserHost()
runtime.BROWSER = BROWSER_HOST


@app.on_event("startup")
async def _restore_runner_state():
    # Re-create timers + vision watchers persisted from the previous session,
    # and rehydrate the spawning-skills set so synthesized background skills
    # show up with the right control type in the UI.
    await RUNNER.restore_from_disk()


@app.on_event("startup")
async def _warm_asr_model():
    # FunASR's torch/torchaudio/modelscope import is ~44s cold and the model
    # load is another ~5s; doing it on the request thread freezes /asr for
    # nearly a minute on the first call, and doing it before uvicorn.run blocks
    # the entire server from coming up. Warm it in a daemon thread so uvicorn
    # accepts connections immediately and only /asr waits if it lands during
    # the warmup window.
    def _warm():
        try:
            _get_asr_model()
        except Exception as e:
            print(f"[vox] WARNING: FunASR background warmup failed: {e}", flush=True)
            print("[vox] /asr will return 500 until the model is available.", flush=True)
    threading.Thread(target=_warm, name="asr-warmup", daemon=True).start()


@app.on_event("shutdown")
async def _shutdown_browser():
    if BROWSER_HOST.is_running():
        await BROWSER_HOST.stop()


@app.get("/")
async def root():
    return {"service": "vox", "version": "0.4.0", "phase": 4}


@app.get("/health")
async def health():
    return {
        "ok": True,
        "asr": "funasr_local",
        "tts": bool(VOLC_TTS_APP_ID and VOLC_TTS_ACCESS_TOKEN),
        "planner": "claude" if os.getenv("ANTHROPIC_API_KEY") else "missing_api_key",
        "trigger": trigger_check.backend_label(),
        "skills": list(REGISTRY.skills.keys()),
        "active_background": len(RUNNER.list()),
        "vision_watchers": sum(1 for x in RUNNER.list() if x["kind"] == "vision"),
    }


@app.get("/watchers")
async def watchers_endpoint():
    return {"active": RUNNER.list()}


# ---------------------------------------------------------------------------
# Skill management — list / run / activate / deactivate / delete
# ---------------------------------------------------------------------------

def _skill_view(name: str, info: dict) -> dict:
    spec = info["spec"]
    schema = spec.get("args_schema") or {}
    required = list(schema.get("required") or [])
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        properties = {}
    configurable_args = [k for k in properties.keys() if isinstance(k, str)]
    instances = [inst for inst in RUNNER.list() if inst.get("source_skill") == name]
    is_spawning = RUNNER.is_spawning_skill(name) or len(instances) > 0
    running = [inst for inst in instances if inst.get("is_active")]
    manifest_meta = skill_manifest.get_skill_meta(name)
    if not manifest_meta:
        manifest_meta = {
            "name": name,
            "source": "static_registry",
            "version": 1,
            "quality_state": "active",
        }
    behavior_preview = _build_skill_behavior_preview(spec, instances, manifest_meta)
    manifest_meta["instance_bindings"] = [
        {
            "instance_id": inst.get("id"),
            "kind": inst.get("kind"),
            "is_active": bool(inst.get("is_active")),
        }
        for inst in instances
    ]
    return {
        "name": name,
        "description": spec.get("description", ""),
        "kind": "background" if is_spawning else "one_shot",
        "required_args": required,
        "configurable_args": configurable_args,
        "has_instance_variants": len(configurable_args) > 0,
        "active_instances": instances,
        "running_count": len(running),
        "is_active": len(running) > 0,
        "quality_state": str(manifest_meta.get("quality_state") or "active"),
        "behavior_preview": behavior_preview,
        "manifest": manifest_meta,
    }


def _schema_default(spec: dict, key: str) -> str:
    schema = spec.get("args_schema") if isinstance(spec, dict) else None
    props = schema.get("properties") if isinstance(schema, dict) else None
    node = props.get(key) if isinstance(props, dict) else None
    if isinstance(node, dict) and node.get("default") is not None:
        return str(node.get("default"))
    return ""


def _build_skill_behavior_preview(spec: dict, instances: list[dict], manifest_meta: dict) -> dict:
    latest = instances[-1] if instances else None
    if isinstance(latest, dict):
        if latest.get("kind") == "vision":
            return {
                "mode": "background_vision",
                "watch_for": str(latest.get("trigger") or ""),
                "on_trigger": str(latest.get("say_on_match") or ""),
                "cooldown_sec": latest.get("cooldown_sec"),
                "source": "runtime_instance",
            }
        if latest.get("kind") == "timer":
            return {
                "mode": "background_timer",
                "delay_seconds": latest.get("delay_seconds"),
                "on_trigger": str(latest.get("message") or ""),
                "source": "runtime_instance",
            }

    # Fallback to last activation args in manifest (if any), then schema defaults.
    last_args = manifest_meta.get("last_activation_args")
    if not isinstance(last_args, dict):
        last_args = {}
    watch_for = str(last_args.get("trigger") or _schema_default(spec, "trigger") or "")
    on_trigger = str(last_args.get("say_on_match") or _schema_default(spec, "say_on_match") or "")
    delay_default = last_args.get("delay_seconds")
    if delay_default is None:
        d = _schema_default(spec, "delay_seconds")
        delay_default = float(d) if d.replace(".", "", 1).isdigit() else d
    msg_default = str(last_args.get("message") or _schema_default(spec, "message") or "")

    if watch_for or on_trigger:
        return {
            "mode": "background_vision",
            "watch_for": watch_for,
            "on_trigger": on_trigger,
            "source": "schema_or_last_args",
        }
    if msg_default or delay_default:
        return {
            "mode": "background_timer",
            "delay_seconds": delay_default,
            "on_trigger": msg_default,
            "source": "schema_or_last_args",
        }

    return {
        "mode": "generic",
        "summary": str(spec.get("description") or ""),
        "source": "description",
    }


def _extract_timer_args_from_text(text: str) -> dict:
    out: dict = {}
    t = str(text or "").strip()
    if not t:
        return out

    m = re.search(
        r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|秒钟?|秒|minutes?|mins?|分钟|分|hours?|hrs?|小时)",
        t,
        re.IGNORECASE,
    )
    if m:
        n = float(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("min") or unit == "分" or "分钟" in unit:
            n *= 60.0
        elif unit.startswith("hour") or unit.startswith("hr") or "小时" in unit:
            n *= 3600.0
        out["delay_seconds"] = n

    say_match = re.search(r"say\s*[:：]\s*[\"“']([^\"”'\n]+)[\"”']?", t, re.IGNORECASE)
    if say_match and say_match.group(1).strip():
        out["message"] = say_match.group(1).strip()
    else:
        quoted = re.search(r"[\"“']([^\"”']{1,120})[\"”']", t)
        if quoted and quoted.group(1).strip():
            out["message"] = quoted.group(1).strip()
        else:
            zh = re.search(r"提醒(?:我)?(.+?)(?:[。.!！]|$)", t)
            if zh and zh.group(1).strip():
                out["message"] = zh.group(1).strip()
    return out


def _extract_vision_args_from_text(text: str) -> dict:
    out: dict = {}
    t = str(text or "").strip()
    if not t:
        return out

    m_trigger = re.search(r"(?:^|\n)\s*trigger\s*[:：]\s*([^\n]+)", t, re.IGNORECASE)
    if m_trigger and m_trigger.group(1).strip():
        out["trigger"] = m_trigger.group(1).strip().strip(" .。")
    m_say = re.search(r"(?:^|\n)\s*(?:say_on_match|message)\s*[:：]\s*([^\n]+)", t, re.IGNORECASE)
    if m_say and m_say.group(1).strip():
        out["say_on_match"] = m_say.group(1).strip().strip(" .。")

    combo_cn = re.search(
        r"(?:看到|看见|见到|检测到)\s*(.+?)\s*(?:你就|就|时|后|，|,).{0,20}?(?:说|提醒|播报)\s*[\"“']([^\"”'\n]{1,180})[\"”']",
        t,
        re.IGNORECASE,
    )
    if combo_cn:
        trigger = combo_cn.group(1).strip(" ，,。.!！")
        say = combo_cn.group(2).strip()
        if trigger:
            out["trigger"] = trigger
        if say:
            out["say_on_match"] = say

    combo_en = re.search(
        r"(?:when|if)\s+(.+?)\s*(?:,|then)\s*(?:say|speak|remind)\s*[\"']([^\"'\n]{1,180})[\"']",
        t,
        re.IGNORECASE,
    )
    if combo_en:
        trigger = combo_en.group(1).strip(" ,.;")
        say = combo_en.group(2).strip()
        if trigger:
            out["trigger"] = trigger
        if say:
            out["say_on_match"] = say

    if not out.get("say_on_match"):
        quoted = re.search(r"[\"“']([^\"”'\n]{1,180})[\"”']", t)
        if quoted and quoted.group(1).strip():
            out["say_on_match"] = quoted.group(1).strip()

    if not out.get("trigger"):
        m = re.search(
            r"(?:看到|看见|见到|检测到|when\s+you\s+see|if\s+you\s+see)\s+(.+?)(?:[，,。.!！]|$)",
            t,
            re.IGNORECASE,
        )
        if m and m.group(1).strip():
            out["trigger"] = m.group(1).strip(" ，,。.!！")

    return out


def _infer_background_activation_args(trigger_kind: str, spec: str, transcript: str = "") -> dict:
    if trigger_kind == "timer":
        merged = f"{spec or ''}\n{transcript or ''}".strip()
        return _extract_timer_args_from_text(merged)
    if trigger_kind == "vision":
        primary = _extract_vision_args_from_text(transcript or "")
        fallback = _extract_vision_args_from_text(spec or "")
        out: dict = {}
        if primary.get("trigger") or fallback.get("trigger"):
            out["trigger"] = str(primary.get("trigger") or fallback.get("trigger") or "").strip()
        if primary.get("say_on_match") or fallback.get("say_on_match"):
            out["say_on_match"] = str(primary.get("say_on_match") or fallback.get("say_on_match") or "").strip()
        return {k: v for k, v in out.items() if v}
    return {}


async def _activate_skill_by_name(name: str, args: dict | None = None) -> dict:
    info = REGISTRY.get(name)
    if info is None:
        return {"ok": False, "error": "unknown skill"}

    args = args or {}
    instances = [inst for inst in RUNNER.list() if inst.get("source_skill") == name]
    inactive_ids = [inst.get("id") for inst in instances if not inst.get("is_active") and inst.get("id")]
    active_count = sum(1 for inst in instances if inst.get("is_active"))

    # Skill-level activation: if the skill already has runtime instances and no
    # new args are requested, reactivate existing instances instead of creating duplicates.
    if instances and not args:
        started = 0
        for id_ in inactive_ids:
            ok = await RUNNER.start(id_)
            if ok:
                started += 1
        await _broadcast_skills_changed()
        return {
            "ok": True,
            "result": {
                "speak": "技能已激活。",
                "render": f"activated skill={name}, started_instances={started}, already_active={active_count}",
            },
        }

    required = list((info["spec"].get("args_schema") or {}).get("required") or [])
    missing = [r for r in required if r not in args]
    if missing:
        return {"ok": False, "error": f"this skill needs args: {missing}"}

    result = await _run_one_shot_with_policy(name, args)
    result = _normalize_result_ui_payload(result)
    if result.get("ok"):
        try:
            skill_manifest.patch_skill_meta(
                name,
                {
                    "last_activation_args": dict(args or {}),
                },
            )
        except Exception:
            pass
        await _broadcast_skills_changed()
    return result


@app.get("/skills")
async def list_skills():
    return {"skills": [_skill_view(n, i) for n, i in REGISTRY.skills.items()]}


async def _broadcast_skills_changed() -> None:
    await output_broadcast({"type": "skills_changed"})


def _planner_registry_summary() -> list[dict]:
    base = REGISTRY.summary_for_planner()
    out: list[dict] = []
    for item in base:
        name = str(item.get("name") or "")
        if not name:
            continue
        meta = skill_manifest.get_skill_meta(name)
        quality = str(meta.get("quality_state") or "active").strip().lower()
        if quality == "degraded":
            continue
        # Keep planner context clean: dynamically generated one-shot skills are
        # request-specific artifacts and should not bias future unrelated intents.
        source = str(meta.get("source") or "").strip().lower()
        kind = str(meta.get("kind") or item.get("kind") or "").strip().lower()
        if source == "dynamic_synthesis" and kind == "one_shot":
            continue
        out.append(item)
    return out


@app.post("/skills/{name}/run")
async def run_skill(name: str, request: Request):
    info = REGISTRY.get(name)
    if info is None:
        return JSONResponse({"ok": False, "error": "unknown skill"}, status_code=404)
    if info["kind"] != "one_shot":
        return JSONResponse(
            {"ok": False, "error": "only one-shot skills can be run via this endpoint"},
            status_code=400,
        )
    try:
        body = await request.json()
    except Exception:
        body = {}
    args = body.get("args") if isinstance(body, dict) else None
    result = await _run_one_shot_with_policy(name, args or {})
    result = _normalize_result_ui_payload(result)
    if result.get("ok"):
        payload = result.get("result") or {}
        speak = payload.get("speak")
        if speak:
            await output_broadcast({
                "type": "speak",
                "text": speak,
                "from": f"manual:{name}",
                "collide": "tone_interrupt",
            })
    return result


@app.post("/skills/{name}/activate")
async def activate_skill(name: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    args = (body.get("args") if isinstance(body, dict) else None) or {}
    result = await _activate_skill_by_name(name, args)
    if result.get("error") == "unknown skill":
        return JSONResponse({"ok": False, "error": "unknown skill"}, status_code=404)
    if (not result.get("ok")) and "needs args" in str(result.get("error") or ""):
        return JSONResponse({"ok": False, "error": result.get("error")}, status_code=400)
    return result


@app.post("/skills/{name}/deactivate")
async def deactivate_skill(name: str):
    info = REGISTRY.get(name)
    if info is None:
        return JSONResponse({"ok": False, "error": "unknown skill"}, status_code=404)
    n = await RUNNER.stop_by_source_skill(name)
    await _broadcast_skills_changed()
    return {"ok": True, "stopped": n}


@app.post("/instances/{id_}/stop")
async def stop_instance(id_: str):
    ok = await RUNNER.stop(id_)
    if not ok:
        return JSONResponse({"ok": False, "error": "unknown instance"}, status_code=404)
    await _broadcast_skills_changed()
    return {"ok": True, "stopped": id_}


@app.post("/instances/{id_}/start")
async def start_instance(id_: str):
    ok = await RUNNER.start(id_)
    if not ok:
        return JSONResponse({"ok": False, "error": "unknown instance"}, status_code=404)
    await _broadcast_skills_changed()
    return {"ok": True, "started": id_}


@app.delete("/instances/{id_}")
async def delete_instance(id_: str):
    ok = await RUNNER.delete(id_)
    if not ok:
        return JSONResponse({"ok": False, "error": "unknown instance"}, status_code=404)
    await _broadcast_skills_changed()
    return {"ok": True, "deleted": id_}


@app.delete("/skills/{name}")
async def delete_skill(name: str):
    info = REGISTRY.get(name)
    path = SKILLS_DIR / f"{name}.py"
    if info is None and not path.exists():
        return JSONResponse({"ok": False, "error": "unknown skill"}, status_code=404)
    # Drop ALL instance entries (active or not) since the .py file is going away.
    await RUNNER.delete_by_source_skill(name)
    try:
        if path.exists():
            path.unlink()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"unlink failed: {e}"}, status_code=500)
    try:
        skill_manifest.remove_skill(name)
    except Exception:
        pass
    REGISTRY.load_all()
    await _broadcast_skills_changed()
    return {"ok": True, "deleted": name}


@app.post("/feedback/media_playback_failure")
async def media_playback_failure(req: MediaPlaybackFeedback):
    skill = str(req.skill or "").strip()
    err = str(req.error or "").strip() or "unknown playback error"
    ui_type = str(req.ui_type or "").strip()
    media_url = str(req.media_url or "").strip()
    if skill:
        try:
            skill_manifest.patch_skill_meta(
                skill,
                {
                    "quality_state": "degraded",
                    "quality_reason": "runtime playback failed",
                    "last_validation_reasons": [f"{ui_type or 'media'} playback failed: {err}"],
                    "last_failed_media_url": media_url,
                },
            )
        except Exception:
            pass
        await _broadcast_skills_changed()
    return {"ok": True, "recorded": True, "skill": skill}


@app.post("/queue/cancel")
async def cancel_pending_queue(request: Request):
    global _PENDING_QUEUE_BY_SESSION
    try:
        body = await request.json()
    except Exception:
        body = {}
    session_id = str((body or {}).get("session_id") or "default").strip() or "default"
    state = _PENDING_QUEUE_BY_SESSION.get(session_id) or {}
    slot = str(state.get("awaiting_slot") or "")
    if not slot:
        return {"ok": True, "cancelled": False}
    _PENDING_QUEUE_BY_SESSION.pop(session_id, None)
    await _broadcast_progress(f"已取消等待补充信息: {slot}", session_id=session_id)
    await output_broadcast({
        "type": "awaiting_slot",
        "active": False,
        "slot": slot,
        "reason": "user_cancelled",
        "session_id": session_id,
    })
    return {"ok": True, "cancelled": True, "slot": slot, "session_id": session_id}


# ---------------------------------------------------------------------------
# Filler filter — short-circuit single-character interjections before the
# planner runs. Saves ~$0.005 + ~2s per filler utterance and removes the
# "I'm here, what do you need?" reply that broke flow earlier.
# ---------------------------------------------------------------------------

_FILLER_ONLY = frozenset({
    # Chinese
    "嗯", "呃", "啊", "哦", "诶", "唔", "哼", "唉", "哈", "哎", "唉哟",
    "嗯嗯", "呃呃", "啊啊", "哦哦", "哈哈", "嗯哼",
    # English
    "um", "uh", "ah", "oh", "hmm", "mm", "eh", "huh",
    "umm", "uhh", "ahh", "ohh", "mmm", "hm",
})

_PUNCT_CHARS = set("。，、！？,.!?~…·-_— \t“”\"'()（）[]【】")


def _is_substantive_utterance(text: str) -> bool:
    """True if the transcript is worth handing to the planner."""
    if not text:
        return False
    # FunASR can emit space-separated CJK ("嗯 嗯"). Strip whitespace before matching.
    no_space = text.replace(" ", "").strip()
    if not no_space:
        return False
    if all(c in _PUNCT_CHARS for c in no_space):
        return False
    if no_space.lower() in _FILLER_ONLY:
        return False
    return True


_CANCEL_PENDING_WORDS = (
    "取消",
    "算了",
    "不用了",
    "停止",
    "cancel",
    "never mind",
    "nevermind",
    "stop",
)
_NEW_TASK_HINTS = (
    "请",
    "帮我",
    "打开",
    "播放",
    "搜索",
    "查询",
    "查一下",
    "新建",
    "创建",
    "运行",
    "提醒",
    "tell me",
    "what",
    "how",
    "search",
    "open",
    "play",
    "run",
    "create",
)


def _looks_cancel_pending(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    return any(w in low for w in _CANCEL_PENDING_WORDS)


def _looks_like_new_task_while_waiting(slot: str, text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    if any(h in low for h in _NEW_TASK_HINTS):
        return True
    # Typical slot answers are short (city/address/token-like). Treat long free-form
    # sentences with punctuation as likely a new intent rather than a slot value.
    if len(t) >= 18 and any(ch in t for ch in "，。,.!?！？"):
        return True
    # If the user explicitly references another slot-like field, this is likely a task.
    slot_low = (slot or "").strip().lower()
    if slot_low and slot_low not in low and re.search(r"(提醒|打开|搜索|播放|create|open|search|play|remind)", low):
        return True
    return False


def _fallback_planner_decision(transcript: str) -> dict:
    """
    Local fallback when planner model is unavailable (quota/subscription/network).
    Keeps core UX usable instead of returning planner hard-error.
    """
    t = (transcript or "").strip()
    # Safety-first fallback: never synthesize on planner outage.
    # Return explicit degraded-mode chat so requests do not drift into unrelated skills.
    return {
        "_tool": "chat",
        "_input": {
            "speak": (
                "当前规划服务暂时不可用，无法安全执行动态构建。"
                + (" 我已收到你的请求，请稍后重试。" if t else " 请稍后重试。")
            ),
        },
        "_meta": {"fallback": "safe_chat_only", "reason": "planner_unavailable"},
    }


async def _broadcast_progress(text: str, session_id: str = "") -> None:
    msg = {"type": "progress", "text": text}
    if session_id:
        msg["session_id"] = session_id
    await output_broadcast(msg)


def _normalize_ui_or_info(ui_obj):
    ok, norm, err = validate_and_normalize_ui(ui_obj)
    if ok:
        return norm
    return {
        "type": "info_card",
        "title": "UI payload invalid",
        "message": err,
    }


def _normalize_result_ui_payload(result: dict) -> dict:
    if not isinstance(result, dict):
        return result
    payload = result.get("result")
    if not isinstance(payload, dict):
        return result
    ui = _normalize_ui_or_info(payload.get("ui"))
    if isinstance(ui, dict):
        payload["ui"] = ui
    result["result"] = payload
    return result


def _validate_and_normalize_payload_ui(payload: dict) -> tuple[dict, list[str]]:
    if not isinstance(payload, dict):
        return payload, ["skill result payload is not an object"]
    if "ui" not in payload:
        return payload, []
    ok, norm_ui, err = validate_and_normalize_ui(payload.get("ui"))
    if not ok:
        return payload, [f"ui contract invalid: {err}"]
    if isinstance(norm_ui, dict):
        payload["ui"] = norm_ui
    elif norm_ui is None and "ui" in payload:
        payload.pop("ui", None)
    return payload, []


def _clamp_float(v, lo: float, hi: float, default: float) -> float:
    try:
        x = float(v)
    except Exception:
        return default
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _normalize_tts_options(obj) -> dict:
    if not isinstance(obj, dict):
        return {}
    out: dict = {}
    voice_type = str(obj.get("voice_type") or "").strip()
    if voice_type:
        out["voice_type"] = voice_type
    if obj.get("speed_ratio") is not None:
        out["speed_ratio"] = _clamp_float(obj.get("speed_ratio"), 0.5, 2.0, 1.0)
    if obj.get("pitch_ratio") is not None:
        out["pitch_ratio"] = _clamp_float(obj.get("pitch_ratio"), 0.5, 2.0, 1.0)
    if obj.get("volume_ratio") is not None:
        out["volume_ratio"] = _clamp_float(obj.get("volume_ratio"), 0.1, 3.0, 1.0)
    return out


def _user_facing_render(text: str) -> str:
    """Strip internal execution/debug metadata from render text."""
    s = str(text or "").strip()
    if not s:
        return ""
    cleaned: list[str] = []
    for ln in s.splitlines():
        t = ln.strip()
        low = t.lower()
        if low.startswith("[synthesized]"):
            continue
        if low.startswith("[fallback"):
            continue
        if low.startswith("[fastpath"):
            continue
        if re.match(r"^\[action\s+\d+/\d+\]", low):
            continue
        if "cost $" in low:
            continue
        cleaned.append(ln)
    return "\n".join(cleaned).strip()


_VISUAL_CAPABILITY_HINTS = ("image", "photo", "picture", "gallery", "图", "图片", "相册", "画廊", "写真")
_PLAYABLE_CAPABILITY_HINTS = ("audio", "music", "song", "video", "播放", "音频", "视频", "音乐")
_GENERIC_CAPABILITY_HINTS = (
    "天气", "weather", "时间", "date", "weekday", "导航", "route", "地图",
    "机票", "flight", "酒店", "hotel", "新闻", "news", "图片", "image",
    "视频", "video", "音乐", "music", "笑话", "joke", "故事", "story",
    "百科", "wiki", "poi", "餐饮", "餐厅",
)
_UNSAFE_VISUAL_RE = re.compile(
    r"(?:porn|nsfw|xxx|nude|sex|hentai|faggot|nigger|裸体|色情|成人视频|成人视频|成人内容|约炮|做爱)",
    re.IGNORECASE,
)


def _score_skill_for_transcript(skill: dict, transcript: str, intent_hints: dict) -> int:
    t = str(transcript or "").strip().lower()
    name = str(skill.get("name") or "").strip().lower()
    desc = str(skill.get("description") or "").strip().lower()
    text = f"{name} {desc}"
    score = 0
    if bool(intent_hints.get("require_visual_media")) and any(k in text for k in _VISUAL_CAPABILITY_HINTS):
        score += 5
    if bool(intent_hints.get("require_playable_media")) and any(k in text for k in _PLAYABLE_CAPABILITY_HINTS):
        score += 5
    for k in _GENERIC_CAPABILITY_HINTS:
        if k in t and k in text:
            score += 2
    words = [w for w in re.split(r"[^a-z0-9\u4e00-\u9fff]+", str(transcript or "").lower()) if len(w) >= 2]
    overlap = 0
    for w in words[:24]:
        if w in text:
            overlap += 1
    score += min(6, overlap)
    return score


def _sanitize_visual_cards(cards: Any) -> list[dict]:
    if not isinstance(cards, list):
        return []
    out: list[dict] = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        title = str(c.get("title") or "").strip()
        subtitle = str(c.get("subtitle") or "").strip()
        image_url = str(c.get("image_url") or "").strip()
        action_url = str(c.get("action_url") or "").strip()
        blob = " ".join([title, subtitle, action_url]).lower()
        if _UNSAFE_VISUAL_RE.search(blob):
            continue
        if not image_url.startswith("http"):
            continue
        out.append(c)
    return out


def _sanitize_visual_ui(ui: Any) -> dict | None:
    if not isinstance(ui, dict):
        return None
    t = str(ui.get("type") or "").strip().lower()
    if t != "card_grid":
        return ui
    cards = _sanitize_visual_cards(ui.get("cards"))
    if not cards:
        return None
    clean = dict(ui)
    clean["cards"] = cards
    return clean


def _sanitize_visual_ui_for_query(ui: Any, query: str) -> dict | None:
    clean = _sanitize_visual_ui(ui)
    if not isinstance(clean, dict):
        return None
    if str(clean.get("type") or "").strip().lower() != "card_grid":
        return clean
    cards = _filter_visual_cards_by_query(clean.get("cards") if isinstance(clean.get("cards"), list) else [], query)
    if not cards:
        return None
    out = dict(clean)
    out["cards"] = cards
    return out


def _query_relevance_aliases(query: str) -> list[str]:
    q = str(query or "").strip().lower()
    aliases: list[str] = []
    if not q:
        return aliases
    if ("狗" in q) or ("dog" in q) or ("puppy" in q):
        aliases.extend(["狗", "狗狗", "犬", "dog", "dogs", "puppy", "puppies", "canine"])
    if ("猫" in q) or ("cat" in q) or ("kitty" in q):
        aliases.extend(["猫", "小猫", "cat", "cats", "kitty", "feline"])
    if ("美女" in q) or ("woman" in q) or ("women" in q) or ("girl" in q) or ("写真" in q) or ("人像" in q):
        aliases.extend(["美女", "写真", "人像", "模特", "woman", "women", "girl", "portrait", "fashion", "model"])
    if ("风景" in q) or ("landscape" in q):
        aliases.extend(["风景", "山", "海", "景色", "landscape", "scenery", "mountain", "sea", "nature"])
    # Fallback: extract basic latin tokens (>=3 chars)
    if not aliases:
        aliases.extend([w for w in re.split(r"[^a-z0-9]+", q) if len(w) >= 3][:4])
    # dedup preserve order
    out: list[str] = []
    seen: set[str] = set()
    for a in aliases:
        k = str(a or "").strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def _filter_visual_cards_by_query(cards: list[dict], query: str) -> list[dict]:
    q = str(query or "").strip().lower()
    if not q:
        return cards
    required = _query_relevance_aliases(q)
    if not required:
        return cards
    out: list[dict] = []
    for c in cards:
        title = str(c.get("title") or "").lower()
        subtitle = str(c.get("subtitle") or "").lower()
        url = str(c.get("action_url") or "").lower()
        blob = " ".join([title, subtitle, url])
        if any(k in blob for k in required):
            out.append(c)
    return out


def _visual_search_query_hint(text: str) -> str:
    q = str(text or "").strip()
    low = q.lower()
    if "美女" in q or "woman" in low or "women" in low:
        return "woman portrait fashion"
    if "风景" in q or "landscape" in low:
        return "city landscape photography"
    return q


async def _fetch_openverse_image_cards(query: str, limit: int = 8) -> list[dict]:
    url = "https://api.openverse.engineering/v1/images/"
    params = {"q": query, "page_size": max(1, min(limit, 20))}
    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, params=params, headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"})
            if r.status_code != 200:
                return []
            data = r.json() if r.content else {}
    except Exception:
        return []
    for item in (data.get("results") or []):
        if not isinstance(item, dict):
            continue
        image_url = str(item.get("url") or item.get("thumbnail") or "").strip()
        if not image_url.startswith("http"):
            continue
        title = str(item.get("title") or "").strip() or "图片"
        source = str(item.get("source") or "Openverse").strip()
        out.append(
            {
                "title": title[:80],
                "subtitle": f"来源: {source}",
                "image_url": image_url,
                "action_url": image_url,
            }
        )
        if len(out) >= limit:
            break
    return out


async def _fetch_wikimedia_image_cards(query: str, limit: int = 8) -> list[dict]:
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": str(max(1, min(limit * 2, 20))),
        "prop": "imageinfo",
        "iiprop": "url",
    }
    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, params=params, headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"})
            if r.status_code != 200:
                return []
            data = r.json() if r.content else {}
    except Exception:
        return []
    pages = ((data.get("query") or {}).get("pages") or {})
    if isinstance(pages, dict):
        for p in pages.values():
            if not isinstance(p, dict):
                continue
            infos = p.get("imageinfo")
            if not isinstance(infos, list) or not infos:
                continue
            image_url = str((infos[0] or {}).get("url") or "").strip()
            if not image_url.startswith("http"):
                continue
            title = str(p.get("title") or "").replace("File:", "").strip() or "图片"
            out.append(
                {
                    "title": title[:80],
                    "subtitle": "来源: Wikimedia Commons",
                    "image_url": image_url,
                    "action_url": image_url,
                }
            )
            if len(out) >= limit:
                break
    return out


async def _fetch_baidu_image_cards(query: str, limit: int = 8) -> list[dict]:
    q = quote_plus(str(query or "").strip())
    url = f"https://image.baidu.com/search/index?tn=baiduimage&word={q}"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                },
            )
            if r.status_code != 200:
                return []
            html_text = str(r.text or "")
    except Exception:
        return []
    # Baidu pages usually embed img URLs in JSON-like snippets:
    # "middleURL":"..." / "thumbURL":"..." / "objURL":"..."
    matches = re.findall(
        r'"(?:middleURL|thumbURL|objURL)":"(https?:\\\\?/\\\\?/[^"]+)"',
        html_text,
        flags=re.IGNORECASE,
    )
    out: list[dict] = []
    seen: set[str] = set()
    for i, raw in enumerate(matches[: max(1, min(limit * 4, 80))]):
        img = raw.replace("\\/", "/").replace("\\u002f", "/").strip()
        if not img.startswith("http") or img in seen:
            continue
        seen.add(img)
        out.append(
            {
                "title": f"图片{i+1}",
                "subtitle": "来源: Baidu Images",
                "image_url": img,
                "action_url": img,
            }
        )
        if len(out) >= limit:
            break
    return out


async def _fetch_bing_image_cards(query: str, limit: int = 8) -> list[dict]:
    q = quote_plus(str(query or "").strip())
    url = f"https://www.bing.com/images/search?q={q}&form=HDRSC2"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                },
            )
            if r.status_code != 200:
                return []
            html_text = str(r.text or "")
    except Exception:
        return []
    # Bing page embeds metadata json snippets with murl (full image) and t (title).
    murl_matches = re.findall(r'"murl":"(https?:\\\\?/\\\\?/[^"]+)"', html_text, flags=re.IGNORECASE)
    title_matches = re.findall(r'"t":"([^"]+)"', html_text, flags=re.IGNORECASE)
    out: list[dict] = []
    for i, raw in enumerate(murl_matches[: max(1, min(limit * 3, 40))]):
        img = raw.replace("\\/", "/").replace("\\u002f", "/").strip()
        if not img.startswith("http"):
            continue
        title = title_matches[i].replace("\\/", "/").strip() if i < len(title_matches) else ""
        out.append(
            {
                "title": (title or f"图片{i+1}")[:80],
                "subtitle": "来源: Bing Images",
                "image_url": img,
                "action_url": img,
            }
        )
        if len(out) >= limit:
            break
    return out


async def _fallback_search_backbone_result(transcript: str, session_id: str = "") -> dict | None:
    q = str(transcript or "").strip()
    if not q:
        return None
    await _broadcast_progress("合成失败，切换通用检索底座", session_id=session_id)
    intent_hints = compile_intent_hints(q, q, "one_shot")
    require_visual = bool(intent_hints.get("require_visual_media"))

    search_res = await search_web(q, max_results=6)
    hits = search_res.get("hits") if isinstance(search_res, dict) else []
    if not isinstance(hits, list):
        hits = []
    if not hits and not require_visual:
        return None

    references: list[str] = []
    extracts: list[dict] = []
    for item in hits[:2]:
        if not isinstance(item, dict):
            continue
        u = str(item.get("url") or "").strip()
        if not u:
            continue
        references.append(u)
        fr = await fetch_page(u, timeout_ms=9000, max_bytes=120000)
        if fr.ok and fr.text:
            extracts.append({
                "url": u,
                "text": str(fr.text or "")[:180],
                "status": fr.status,
            })

    if require_visual:
        vq = _visual_search_query_hint(q)
        is_cn = str(VOX_DEPLOY_REGION or "").strip().upper() == "CN"
        cards_ov: list[dict] = []
        cards_wm: list[dict] = []
        cards_baidu: list[dict] = []
        cards_bing: list[dict] = []
        if is_cn:
            # China deployment default: avoid Openverse/Wikimedia in primary path.
            cards_baidu = await _fetch_baidu_image_cards(vq, limit=8)
            cards_bing = await _fetch_bing_image_cards(vq, limit=8)
        else:
            cards_ov = await _fetch_openverse_image_cards(vq, limit=6)
            cards_wm = await _fetch_wikimedia_image_cards(vq, limit=6)
            cards_bing = await _fetch_bing_image_cards(vq, limit=8)
        seen_img: set[str] = set()
        visual_cards: list[dict] = []
        for c in cards_baidu + cards_bing + cards_ov + cards_wm:
            if not isinstance(c, dict):
                continue
            img = str(c.get("image_url") or "").strip()
            if not img or img in seen_img:
                continue
            seen_img.add(img)
            visual_cards.append(c)
            if len(visual_cards) >= 8:
                break
        visual_cards = _sanitize_visual_cards(visual_cards)
        visual_cards = _filter_visual_cards_by_query(visual_cards, q)
        if visual_cards:
            ui = {
                "type": "card_grid",
                "title": f"{q} - 图片结果",
                "cards": visual_cards,
            }
            d_ok, _, _ = await probe_ui_deliverability(ui, timeout_sec=5.0)
            if d_ok:
                render = (
                    f"query: {q}\n"
                    + build_render_evidence_block(
                        source="web_search_backbone_visual",
                        source_url=str(visual_cards[0].get("action_url") or ""),
                        evidence={
                            "deploy_region": VOX_DEPLOY_REGION,
                            "baidu_count": len(cards_baidu),
                            "bing_count": len(cards_bing),
                            "openverse_count": len(cards_ov),
                            "wikimedia_count": len(cards_wm),
                            "selected_count": len(visual_cards),
                        },
                        references=[str(c.get("action_url") or "") for c in visual_cards[:6]],
                    )
                )
                return {
                    "kind": "skill_result",
                    "skill": "__search_backbone_fallback__",
                    "speak": f"我先给你展示了 {len(visual_cards)} 张可直接浏览的图片，并附上来源。",
                    "render": render.strip(),
                    "ui": ui,
                    "ui_cards": [ui],
                }
        fallback_cards: list[dict] = []
        for item in hits[:6]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if not title or not url:
                continue
            fallback_cards.append(
                {
                    "title": title[:90],
                    "subtitle": (snippet[:120] if snippet else "检索结果链接"),
                    "action_url": url,
                }
            )
        if not fallback_cards:
            image_search_url = f"https://www.bing.com/images/search?q={quote_plus(q)}"
            fallback_cards = [
                {
                    "title": "打开图像搜索结果",
                    "subtitle": "未获取到稳定直链图片，先返回检索入口",
                    "action_url": image_search_url,
                }
            ]
        ui = {
            "type": "card_grid",
            "title": f"{q} - 检索结果",
            "cards": fallback_cards,
        }
        render = (
            f"query: {q}\n"
            + format_search_hits(q, hits, limit=4)
            + "\n\n"
            + build_render_evidence_block(
                source="web_search_backbone",
                source_url=str(fallback_cards[0].get("action_url") or ""),
                evidence={
                    "provider": search_res.get("provider"),
                    "hit_count": len(hits),
                    "extract_count": len(extracts),
                    "deploy_region": VOX_DEPLOY_REGION,
                    "baidu_count": len(cards_baidu),
                    "visual_card_candidates": len(visual_cards),
                    "bing_count": len(cards_bing),
                },
                references=references,
            )
        )
        return {
            "kind": "skill_result",
            "skill": "__search_backbone_fallback__",
            "speak": "我先返回结构化检索结果卡片，你可以直接点开查看。",
            "render": render.strip(),
            "ui": ui,
            "ui_cards": [ui],
        }

    cards: list[dict] = []
    for item in hits[:6]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if not title or not url:
            continue
        cards.append({
            "title": title[:90],
            "subtitle": snippet[:120] if snippet else "web result",
            "action_url": url,
        })
    if not cards:
        return None

    render = (
        format_search_hits(q, hits, limit=6)
        + "\n\n"
        + build_render_evidence_block(
            source="web_search_backbone",
            source_url=str(cards[0].get("action_url") or ""),
            evidence={
                "provider": search_res.get("provider"),
                "hit_count": len(hits),
                "extracts": extracts,
            },
            references=references,
        )
    )
    ui = {
        "type": "card_grid",
        "title": f"检索结果：{q}",
        "cards": cards,
    }
    return {
        "kind": "skill_result",
        "skill": "__search_backbone_fallback__",
        "speak": f"我先通过通用检索底座给你整理了 {len(cards)} 条可用结果。",
        "render": render.strip(),
        "ui": ui,
        "ui_cards": [ui],
    }


async def _fallback_existing_skill_for_transcript(transcript: str, session_id: str = "") -> dict | None:
    intent_hints = compile_intent_hints(transcript, "fallback_existing_skill", "one_shot")
    candidates: list[tuple[int, dict]] = []
    for s in REGISTRY.summary_for_planner():
        if str(s.get("kind") or "") != "one_shot":
            continue
        name = str(s.get("name") or "").strip()
        if not name:
            continue
        meta = skill_manifest.get_skill_meta(name)
        quality_state = str(meta.get("quality_state") or "").strip().lower()
        if quality_state and quality_state not in ("active", "draft"):
            continue
        score = _score_skill_for_transcript(s, transcript, intent_hints)
        if score > 0:
            candidates.append((score, s))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    contract = _enrich_outcome_contract(
        transcript=transcript,
        spec="fallback_existing_skill",
        provided={},
        intent_kind="one_shot",
    )
    for _, s in candidates[:4]:
        name = str(s.get("name") or "").strip()
        await _broadcast_progress(f"合成失败，尝试复用已有技能: {name}", session_id=session_id)
        invoke_result = await _run_one_shot_with_policy(
            name,
            {"task_input": transcript, "request": transcript, "spec": "fallback_existing_skill"},
        )
        if not invoke_result.get("ok"):
            continue
        payload = invoke_result.get("result") or {}
        payload, ui_reasons = _validate_and_normalize_payload_ui(payload if isinstance(payload, dict) else {})
        ok, _, reasons = validate_outcome_payload(payload, contract)
        if ui_reasons:
            ok = False
            reasons = list(reasons) + list(ui_reasons)
        if DELIVERABILITY_PROBE_ENABLED and isinstance(payload, dict):
            d_ok, d_reasons, _ = await probe_ui_deliverability(
                payload.get("ui"),
                timeout_sec=DELIVERABILITY_PROBE_TIMEOUT_SEC,
            )
            if not d_ok:
                ok = False
                reasons = list(reasons) + [f"deliverability: {x}" for x in d_reasons]
        if ok:
            return {"name": name, "payload": payload}
    return None


async def _remove_skill_artifacts(name: str) -> None:
    if not name:
        return
    try:
        await RUNNER.delete_by_source_skill(name)
    except Exception:
        pass
    try:
        p = SKILLS_DIR / f"{name}.py"
        if p.exists():
            p.unlink()
    except Exception:
        pass
    try:
        skill_manifest.remove_skill(name)
    except Exception:
        pass
    try:
        REGISTRY.load_all()
    except Exception:
        pass
    await _broadcast_skills_changed()


def _mark_skill_quality(
    name: str,
    quality_state: str,
    reason: str = "",
    outcome_contract: dict | None = None,
    validation_reasons: list[str] | None = None,
) -> None:
    if not name:
        return
    patch = {
        "quality_state": quality_state,
        "quality_reason": reason,
    }
    if outcome_contract:
        patch["last_outcome_contract"] = outcome_contract
    if validation_reasons:
        patch["last_validation_reasons"] = list(validation_reasons)
    try:
        skill_manifest.patch_skill_meta(name, patch)
    except Exception:
        pass


def _is_transient_invoke_error(err: str) -> bool:
    return judge_transient_external_error(err)


def _is_recoverable_synthesis_error(err: str) -> bool:
    return judge_recoverable_synthesis_error(err)


async def _run_one_shot_with_policy(name: str, args: dict | None = None) -> dict:
    invoke_args = args if isinstance(args, dict) else {}
    result = await run_one_shot(REGISTRY, name, invoke_args)
    if not result.get("ok"):
        err = str(result.get("error") or "")
        judged = classify_error(err, stage="invoke")
        if judged.get("bad_args"):
            result = await run_one_shot(REGISTRY, name, {})
    retries = 0
    while (
        not result.get("ok")
        and bool(classify_error(str(result.get("error") or ""), stage="invoke").get("transient"))
        and retries < ONE_SHOT_TRANSIENT_RETRY_MAX
    ):
        retries += 1
        print(
            f"[invoke] transient failure on {name}, retry {retries}/{ONE_SHOT_TRANSIENT_RETRY_MAX}: {result.get('error')}",
            flush=True,
        )
        result = await run_one_shot(REGISTRY, name, invoke_args)
        if not result.get("ok"):
            err = str(result.get("error") or "")
            judged = classify_error(err, stage="invoke")
            if judged.get("bad_args"):
                result = await run_one_shot(REGISTRY, name, {})
    return result


def _build_repair_spec(original_spec: str, contract: dict, reasons: list[str]) -> str:
    reason_text = "; ".join(reasons) if reasons else "unknown validation failure"
    evidence_fix = ""
    if any("missing evidence fields/source" in str(r or "") for r in (reasons or [])):
        evidence_fix = (
            "\nMandatory fix for this repair:\n"
            "- Your result must include explicit evidence markers.\n"
            "- Add at least one of these in output payload: source / source_url / evidence / references.\n"
            "- Also include key fields in render for traceability.\n"
        )
    return (
        (original_spec or "").strip()
        + "\n\n[REPAIR REQUIREMENTS]\n"
        + "The previous generated skill failed runtime outcome validation.\n"
        + f"Contract: {json.dumps(contract, ensure_ascii=False)}\n"
        + f"Failure reasons: {reason_text}\n"
        + "You must satisfy the contract checks exactly and avoid link-only responses."
        + evidence_fix
    )


def _build_runtime_resilience_repair_spec(
    original_spec: str,
    contract: dict,
    runtime_error: str,
    attempt_idx: int,
) -> str:
    require_playable = bool(contract.get("require_playable_media", False))
    require_visual = bool(contract.get("require_visual_media", False))
    media_fix = ""
    if require_playable or require_visual:
        media_fix = (
            "- Media-delivery intents must return media-renderable UI, not info-only fallback.\n"
            "- For playable media: prefer music_player/video_player; if direct stream unavailable, use iframe_card with a truly embeddable URL.\n"
            "- For visual media: prefer image_card/card_grid with browser-consumable image URLs.\n"
            "- If a source fails, try alternate sources; do not degrade to plain link/info card when contract requires media delivery.\n"
        )
    return (
        (original_spec or "").strip()
        + "\n\n[RUNTIME RESILIENCE REPAIR]\n"
        + f"Attempt: {attempt_idx}\n"
        + "The previous generated skill failed at runtime due to transient external dependency failure.\n"
        + f"Runtime error: {runtime_error}\n"
        + f"Contract: {json.dumps(contract, ensure_ascii=False)}\n"
        + "Mandatory fixes:\n"
        + "- Keep user intent unchanged. Do not switch task/domain/modality.\n"
        + f"- Respect deployment region/locale: region={VOX_DEPLOY_REGION}, locale={VOX_PRIMARY_LOCALE}; prefer region-reachable sources first.\n"
        + "- External calls must use timeout and try/except; run() must not raise to caller.\n"
        + "- Avoid single-source brittle dependency; provide at least one alternate retrieval strategy in code.\n"
        + "- If one source fails, continue with next source; only return failure after all strategies are exhausted.\n"
        + "- The final payload must still satisfy outcome contract checks (including evidence fields).\n"
        + media_fix
    )


def _compact_spec_for_retry(spec: str, max_chars: int = 900) -> str:
    s = str(spec or "").strip()
    if len(s) <= max_chars:
        return s
    return (s[:max_chars] + "\n...[truncated for recovery retry]").strip()


async def _synthesize_and_validate_one_shot(
    spec: str,
    transcript: str,
    outcome_contract: dict,
    session_id: str = "",
) -> dict:
    contract = _enrich_outcome_contract(
        transcript=transcript,
        spec=spec,
        provided=outcome_contract,
        intent_kind="one_shot",
    )
    total_cost = 0.0
    repair_attempts = 0
    transient_repair_attempts = 0
    synth_recovery_attempts = 0
    current_spec = spec
    started_at = time.monotonic()

    while (
        repair_attempts <= ONE_SHOT_VALIDATION_REPAIR_MAX
        and transient_repair_attempts <= ONE_SHOT_TRANSIENT_REPAIR_MAX
        and synth_recovery_attempts <= ONE_SHOT_SYNTH_RECOVERY_MAX
    ):
        if (time.monotonic() - started_at) > ONE_SHOT_TOTAL_BUDGET_SEC:
            await _broadcast_progress("自动修复达到时长上限，正在返回当前最优结果", session_id=session_id)
            return {
                "ok": False,
                "error": (
                    "one-shot synthesis exceeded total time budget "
                    f"({ONE_SHOT_TOTAL_BUDGET_SEC:.0f}s) while auto-repairing"
                ),
                "cost_usd": total_cost,
                "repaired": repair_attempts > 0 or transient_repair_attempts > 0 or synth_recovery_attempts > 0,
                "retryable": True,
            }
        try:
            result = await asyncio.wait_for(
                synthesizer.synthesize_one_shot(current_spec, REGISTRY),
                timeout=ONE_SHOT_SYNTH_CALL_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            result = {
                "ok": False,
                "error": f"synthesis call timeout (>{ONE_SHOT_SYNTH_CALL_TIMEOUT_SEC:.0f}s)",
                "cost_usd": 0.0,
            }
        total_cost += float(result.get("cost_usd", 0.0) or 0.0)
        if not result.get("ok"):
            err = str(result.get("error") or "unknown synthesis error")
            synth_judged = classify_error(err, stage="synthesis")
            if bool(synth_judged.get("recoverable")) and synth_recovery_attempts < ONE_SHOT_SYNTH_RECOVERY_MAX:
                synth_recovery_attempts += 1
                await _broadcast_progress(
                    "合成阶段异常，正在自动恢复并重试",
                    session_id=session_id,
                )
                low_err = err.lower()
                if "timeout" in low_err:
                    # Keep retry prompt compact when the upstream synth call itself timed out.
                    current_spec = _compact_spec_for_retry(current_spec)
                else:
                    current_spec = _build_runtime_resilience_repair_spec(
                        current_spec,
                        contract,
                        f"synthesis failed: {err}",
                        synth_recovery_attempts,
                    )
                continue
            return {
                "ok": False,
                "error": f"synthesis failed: {err}",
                "cost_usd": total_cost,
                "repaired": repair_attempts > 0,
                "synth_recovery_attempts": synth_recovery_attempts,
            }

        name = str(result.get("name") or "")
        await _broadcast_skills_changed()
        invoke_args = {
            "task_input": transcript,
            "request": transcript,
            "spec": current_spec,
        }
        invoke_result = await _run_one_shot_with_policy(name, invoke_args)
        if not invoke_result.get("ok"):
            err = str(invoke_result.get("error") or "unknown invoke error")
            invoke_judged = classify_error(err, stage="invoke")
            transient = bool(invoke_judged.get("transient"))
            reason = f"invoke failed (transient external): {err}" if transient else f"invoke failed: {err}"
            _mark_skill_quality(name, "degraded", reason=reason, outcome_contract=contract)
            if transient:
                await _remove_skill_artifacts(name)
                if transient_repair_attempts < ONE_SHOT_TRANSIENT_REPAIR_MAX:
                    transient_repair_attempts += 1
                    await _broadcast_progress(
                        "检测到外部依赖失败，正在重构技能执行策略并重试",
                        session_id=session_id,
                    )
                    current_spec = _build_runtime_resilience_repair_spec(
                        current_spec,
                        contract,
                        err,
                        transient_repair_attempts,
                    )
                    continue
                return {
                    "ok": False,
                    "error": (
                        "invoke transient external failure after runtime resilience repairs: "
                        f"{err}"
                    ),
                    "cost_usd": total_cost,
                    "repaired": repair_attempts > 0,
                    "retryable": True,
                    "skill": name,
                    "transient_repair_attempts": transient_repair_attempts,
                }
            await _remove_skill_artifacts(name)
            if repair_attempts < ONE_SHOT_VALIDATION_REPAIR_MAX:
                await _broadcast_progress("首轮结果执行失败，自动修复重试", session_id=session_id)
                current_spec = _build_repair_spec(spec, contract, [f"invoke failed: {err}"])
                repair_attempts += 1
                continue
            return {"ok": False, "error": f"invoke failed after repair: {err}", "cost_usd": total_cost, "repaired": True}

        payload = invoke_result.get("result") or {}
        payload, ui_reasons = _validate_and_normalize_payload_ui(payload)
        ok, norm_contract, reasons = validate_outcome_payload(payload, contract)
        if ui_reasons:
            reasons = list(reasons) + list(ui_reasons)
            ok = False
        if DELIVERABILITY_PROBE_ENABLED and isinstance(payload, dict):
            ui_obj = payload.get("ui")
            d_ok, d_reasons, d_summary = await probe_ui_deliverability(
                ui_obj,
                timeout_sec=DELIVERABILITY_PROBE_TIMEOUT_SEC,
            )
            if not d_ok:
                ok = False
                reasons = list(reasons) + [f"deliverability: {r}" for r in d_reasons]
                try:
                    payload["render"] = (
                        str(payload.get("render") or "").strip()
                        + f"\n\ndeliverability_probe: {json.dumps(d_summary, ensure_ascii=False)}"
                    ).strip()
                except Exception:
                    pass
        if ok:
            _mark_skill_quality(name, "active", reason="outcome validated", outcome_contract=norm_contract)
            return {
                "ok": True,
                "name": name,
                "payload": payload,
                "cost_usd": total_cost,
                "repaired": repair_attempts > 0,
                "outcome_contract": norm_contract,
            }

        _mark_skill_quality(
            name,
            "degraded",
            reason="outcome validation failed",
            outcome_contract=norm_contract,
            validation_reasons=reasons,
        )
        await _remove_skill_artifacts(name)
        if repair_attempts < ONE_SHOT_VALIDATION_REPAIR_MAX:
            await _broadcast_progress("首轮结果未通过验收，自动修复重试", session_id=session_id)
            current_spec = _build_repair_spec(spec, norm_contract, reasons)
            repair_attempts += 1
            continue
        return {
            "ok": False,
            "error": f"outcome validation failed after repair: {'; '.join(reasons)}",
            "cost_usd": total_cost,
            "repaired": True,
            "reasons": reasons,
            "outcome_contract": norm_contract,
        }

    return {"ok": False, "error": "unexpected synthesis loop exit", "cost_usd": total_cost}


async def _synthesize_activate_and_validate_background(
    trigger_kind: str,
    spec: str,
    transcript: str,
    outcome_contract: dict,
    session_id: str = "",
) -> dict:
    contract = _enrich_outcome_contract(
        transcript=transcript,
        spec=spec,
        provided=outcome_contract,
        intent_kind="background",
    )
    total_cost = 0.0
    repair_attempts = 0
    current_spec = spec

    while repair_attempts <= 1:
        result = await synthesizer.synthesize_background(trigger_kind, current_spec, REGISTRY)
        total_cost += float(result.get("cost_usd", 0.0) or 0.0)
        if not result.get("ok"):
            return {
                "ok": False,
                "error": f"background synthesis failed: {result.get('error')}",
                "cost_usd": total_cost,
                "repaired": repair_attempts > 0,
            }

        name = str(result.get("name") or "")
        auto_args = _infer_background_activation_args(trigger_kind, current_spec, transcript=transcript)
        activate_result = await _activate_skill_by_name(name, auto_args)
        if not activate_result.get("ok"):
            err = str(activate_result.get("error") or "activation failed")
            _mark_skill_quality(name, "degraded", reason=f"activation failed: {err}", outcome_contract=contract)
            await _remove_skill_artifacts(name)
            if repair_attempts == 0:
                await _broadcast_progress("后台技能激活失败，自动修复重试", session_id=session_id)
                current_spec = _build_repair_spec(spec, contract, [f"activate failed: {err}"])
                repair_attempts += 1
                continue
            return {"ok": False, "error": f"activation failed after repair: {err}", "cost_usd": total_cost, "repaired": True}

        payload = activate_result.get("result") if isinstance(activate_result, dict) else {}
        payload, ui_reasons = _validate_and_normalize_payload_ui(payload if isinstance(payload, dict) else {})
        ok, norm_contract, reasons = validate_outcome_payload(payload, contract)
        if ui_reasons:
            reasons = list(reasons) + list(ui_reasons)
            ok = False
        if ok:
            _mark_skill_quality(name, "active", reason="outcome validated", outcome_contract=norm_contract)
            return {
                "ok": True,
                "name": name,
                "payload": payload if isinstance(payload, dict) else {},
                "cost_usd": total_cost,
                "repaired": repair_attempts > 0,
                "outcome_contract": norm_contract,
            }

        _mark_skill_quality(
            name,
            "degraded",
            reason="outcome validation failed",
            outcome_contract=norm_contract,
            validation_reasons=reasons,
        )
        await _remove_skill_artifacts(name)
        if repair_attempts == 0:
            await _broadcast_progress("后台技能首轮结果未通过验收，自动修复重试", session_id=session_id)
            current_spec = _build_repair_spec(spec, norm_contract, reasons)
            repair_attempts += 1
            continue
        return {
            "ok": False,
            "error": f"background outcome validation failed after repair: {'; '.join(reasons)}",
            "cost_usd": total_cost,
            "repaired": True,
            "reasons": reasons,
            "outcome_contract": norm_contract,
        }

    return {"ok": False, "error": "unexpected background synthesis loop exit", "cost_usd": total_cost}


_TPL_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_TPL_SINGLE_RE = re.compile(r"\{\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+)\s*\}")
_PENDING_QUEUE_BY_SESSION: dict[str, dict] = {}
_PLANNER_FALLBACK_UNTIL_TS = 0.0
_PLANNER_FALLBACK_BACKOFF_SEC = float(os.getenv("PLANNER_FALLBACK_BACKOFF_SEC", "120"))


def _ctx_get_path(ctx: dict, path: str):
    node = ctx
    for k in path.split("."):
        if isinstance(node, dict) and k in node:
            node = node[k]
        else:
            return None
    return node


def _ctx_set_var(ctx: dict, key: str, value):
    if not key:
        return
    ctx.setdefault("vars", {})
    ctx["vars"][key] = value


def _normalize_generic_synthesis_spec(spec: str, transcript: str = "") -> str:
    """
    Generic synthesis normalizer.
    Preserves user intent and only adds platform-level constraints:
    - Avoid visible browser interactions
    - Prefer ephemeral generated UI where applicable
    - Include source evidence in outputs
    """
    s = (spec or "").strip()
    if not s:
        return s
    # Guardrail: do not silently inject hard numeric/cardinality constraints
    # unless the user explicitly provided such constraints in their own request.
    t = str(transcript or "").strip()
    user_has_explicit_count = bool(
        re.search(
            r"(至少|不少于|不低于|最少|at\s+least|no\s+less\s+than|\bminimum\b)\s*([0-9]+|[一二三四五六七八九十两百千]+)",
            t,
            re.IGNORECASE,
        )
        or re.search(r"([0-9]+|[一二三四五六七八九十两百千]+)\s*(张|个|条|首|段|items?|results?|photos?|videos?)", t, re.IGNORECASE)
    )
    if not user_has_explicit_count:
        s = re.sub(
            r"(?:至少|不少于|不低于|最少|at\s+least|no\s+less\s+than|\bminimum\b)\s*([0-9]+|[一二三四五六七八九十两百千]+)\s*(张|个|条|首|段|items?|results?|photos?|videos?)?",
            "",
            s,
            flags=re.IGNORECASE,
        )
    contract = (
        "Preserve the user's original request exactly (task, constraints, wording intent). "
        "Do not inject unstated assumptions or replace the user's goal with a different one. "
        f"Deployment context: region={VOX_DEPLOY_REGION}, locale={VOX_PRIMARY_LOCALE}. "
        "Choose external data sources that are reachable/stable in this deployment region. "
        "Do not rely on a single foreign endpoint for factual/location retrieval; provide alternate source paths. "
        "Prefer hidden/headless retrieval over visible browser interactions. "
        "Do NOT use Python webbrowser module or visible browser opening as final delivery unless the user explicitly requests opening a webpage. "
        "Do NOT ask the user to manually operate computer/browser/site unless the user explicitly requests manual control. "
        "Returning only URL/link or only an info card is considered incomplete unless the user explicitly asks for links only. "
        "When suitable, return generated ephemeral UI via `ui` for direct interaction. "
        "If a UI schema uses URL fields, prefer direct browser-consumable URLs rather than page links. "
        "Always include evidence in render (source/source_url/key fields) before conclusions."
    )
    if contract in s:
        return s
    return s + "\n\n" + contract


def _enrich_outcome_contract(
    transcript: str,
    spec: str,
    provided: dict | None,
    intent_kind: str = "one_shot",
) -> dict:
    base = normalize_outcome_contract(provided or {})
    hints = compile_intent_hints(transcript=transcript, spec=spec, intent_kind=intent_kind)
    if intent_kind == "background":
        # Background activation result is an acknowledgement, not a rich interactive payload.
        # Keep only activation-safe checks to avoid false negatives and accidental deletions.
        keep = {"non_empty_output", "not_placeholder_output"}
        checks = [c for c in (base.get("checks") or []) if c in keep]
        if "non_empty_output" not in checks:
            checks.append("non_empty_output")
        if "not_placeholder_output" not in checks:
            checks.append("not_placeholder_output")
        base["checks"] = checks
        if base.get("delivery") == "interactive":
            base["delivery"] = "auto"
        base["fulfillment_mode"] = str(hints.get("fulfillment_mode") or "background_ack")
        base["requires_ui_delivery"] = bool(hints.get("requires_ui_delivery", False))
        base["require_playable_media"] = bool(hints.get("require_playable_media", False))
        base["require_visual_media"] = bool(hints.get("require_visual_media", False))
        base["explicit_min_count"] = hints.get("explicit_min_count")
        return base
    checks = list(base.get("checks") or [])

    def add_check(name: str):
        if name not in checks:
            checks.append(name)

    add_check("not_placeholder_output")
    mode = str(base.get("fulfillment_mode") or "auto").strip().lower() or "auto"
    if mode == "auto":
        mode = str(hints.get("fulfillment_mode") or "task_completion")

    if intent_kind != "background":
        delivery = str(base.get("delivery") or "auto").strip().lower()
        # Do not infer domain-specific intent here. Only honor explicit contract intent.
        if delivery == "interactive":
            add_check("ui_present")
            if mode != "address_lookup":
                add_check("not_link_only")
            add_check("evidence_present")
        elif delivery == "informational":
            add_check("evidence_present")

        # For address lookup intents, allow link-based completion.
        if mode == "address_lookup" and "not_link_only" in checks:
            checks = [c for c in checks if c != "not_link_only"]

    base["checks"] = checks
    base["fulfillment_mode"] = mode
    base["requires_ui_delivery"] = bool(base.get("requires_ui_delivery", hints.get("requires_ui_delivery", False)))
    base["require_playable_media"] = bool(base.get("require_playable_media", hints.get("require_playable_media", False)))
    base["require_visual_media"] = bool(base.get("require_visual_media", hints.get("require_visual_media", False)))
    if base.get("explicit_min_count") is None:
        base["explicit_min_count"] = hints.get("explicit_min_count")
    return base


def _resolve_templates(value, ctx: dict):
    if isinstance(value, str):
        m = _TPL_RE.fullmatch(value.strip())
        if m:
            return _ctx_get_path(ctx, m.group(1))
        m2 = _TPL_SINGLE_RE.fullmatch(value.strip())
        if m2:
            return _ctx_get_path(ctx, m2.group(1))

        def repl(match):
            v = _ctx_get_path(ctx, match.group(1))
            return "" if v is None else str(v)
        out = _TPL_RE.sub(repl, value)
        out = _TPL_SINGLE_RE.sub(repl, out)
        return out
    if isinstance(value, list):
        return [_resolve_templates(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_templates(v, ctx) for k, v in value.items()}
    return value


def _eval_branch_condition(left, op: str, right) -> bool:
    op = (op or "truthy").strip().lower()
    if op == "truthy":
        return bool(left)
    if op == "eq":
        return left == right
    if op == "ne":
        return left != right
    if op == "in":
        if isinstance(right, (list, tuple, set)):
            return left in right
        return False
    if op == "contains":
        if isinstance(left, (list, tuple, set, str)):
            return right in left
        return False
    return bool(left)


async def _execute_planned_action(
    action: dict,
    action_index: int,
    total_actions: int,
    ctx: dict,
    session_id: str = "",
    root_transcript: str = "",
) -> dict:
    """Execute one action from internal pending list."""
    action_type = str(action.get("action_type") or "").strip()
    say_first = str(_resolve_templates(action.get("say_first") or "", ctx) or "").strip()
    if say_first:
        await output_broadcast({"type": "speak", "text": say_first, "from": "planner", "collide": "tone_interrupt"})

    if action_type == "call_skill":
        name = str(_resolve_templates(action.get("name") or "", ctx) or "")
        await _broadcast_progress(f"正在执行技能: {name}", session_id=session_id)
        args = _resolve_templates(action.get("args") or {}, ctx) or {}
        if not isinstance(args, dict):
            args = {}
        result = await _run_one_shot_with_policy(name, args)
        if not result["ok"]:
            err = result["error"]
            return {
                "ok": False,
                "kind": "error",
                "speak": f"Step {action_index}/{total_actions} failed on skill {name}: {err}",
                "render": f"[action {action_index}/{total_actions}] call_skill {name} failed: {err}",
            }
        payload = result.get("result") or {}
        payload, ui_reasons = _validate_and_normalize_payload_ui(payload if isinstance(payload, dict) else {})
        action_contract = _enrich_outcome_contract(
            transcript=root_transcript or name,
            spec=name,
            provided={},
            intent_kind="one_shot",
        )
        ok_payload, _, reasons = validate_outcome_payload(payload, action_contract)
        if ui_reasons:
            reasons = list(reasons) + list(ui_reasons)
            ok_payload = False
        if DELIVERABILITY_PROBE_ENABLED and isinstance(payload, dict):
            d_ok, d_reasons, d_summary = await probe_ui_deliverability(
                payload.get("ui"),
                timeout_sec=DELIVERABILITY_PROBE_TIMEOUT_SEC,
            )
            if not d_ok:
                ok_payload = False
                reasons = list(reasons) + [f"deliverability: {r}" for r in d_reasons]
                payload["render"] = (
                    str(payload.get("render") or "").strip()
                    + f"\n\ndeliverability_probe: {json.dumps(d_summary, ensure_ascii=False)}"
                ).strip()
        if not ok_payload:
            return {
                "ok": False,
                "kind": "error",
                "speak": f"Step {action_index}/{total_actions} failed on skill {name}: payload validation failed",
                "render": (
                    f"[action {action_index}/{total_actions}] call_skill {name} payload invalid: "
                    + "; ".join(reasons)
                ),
            }
        save_as = str(action.get("save_as") or "").strip()
        if save_as:
            _ctx_set_var(ctx, save_as, payload)
        skill_speak = (payload.get("speak") if isinstance(payload, dict) else None) or ""
        skill_render = _user_facing_render((payload.get("render") if isinstance(payload, dict) else None) or str(payload))
        ui = _normalize_ui_or_info(payload.get("ui") if isinstance(payload, dict) else None)
        return {
            "ok": True,
            "kind": "skill_result",
            "skill": name,
            "speak": skill_speak,
            "render": skill_render,
            "ui": ui,
        }

    if action_type == "synthesize_one_shot":
        await _broadcast_progress("正在构建技能", session_id=session_id)
        spec = str(_resolve_templates(action.get("spec") or "", ctx) or "").strip()
        if not spec:
            return {
                "ok": False,
                "kind": "error",
                "speak": f"Step {action_index}/{total_actions} is missing synthesis spec.",
                "render": f"[action {action_index}/{total_actions}] synthesize_one_shot missing spec",
            }
        spec = _normalize_generic_synthesis_spec(spec, transcript=root_transcript)
        outcome_contract = _resolve_templates(action.get("outcome_contract") or {}, ctx) or {}
        intent_hints = compile_intent_hints(root_transcript or spec, spec, "one_shot")
        print(f"[Plan] action#{action_index} synthesize_one_shot spec={spec!r}", flush=True)
        if str(VOX_DEPLOY_REGION or "").strip().upper() == "CN" and bool(intent_hints.get("require_visual_media")):
            fast_search = await _fallback_search_backbone_result(root_transcript or spec, session_id=session_id)
            if fast_search:
                payload = {
                    "speak": fast_search.get("speak") or "",
                    "render": fast_search.get("render") or "",
                    "ui": fast_search.get("ui") if isinstance(fast_search.get("ui"), dict) else None,
                }
                save_as = str(action.get("save_as") or "").strip()
                if save_as:
                    _ctx_set_var(ctx, save_as, payload)
                return {
                    "ok": True,
                    "kind": "skill_result",
                    "skill": "__search_backbone_fallback__",
                    "speak": str(payload.get("speak") or ""),
                    "render": str(payload.get("render") or ""),
                    "ui": _normalize_ui_or_info(payload.get("ui")),
                }
        run_result = await _synthesize_and_validate_one_shot(
            spec=spec,
            transcript=root_transcript or spec,
            outcome_contract=outcome_contract,
            session_id=session_id,
        )
        if not run_result.get("ok"):
            err = str(run_result.get("error") or "unknown synthesis error")
            if bool(intent_hints.get("require_visual_media")):
                search_fallback = await _fallback_search_backbone_result(
                    root_transcript or spec,
                    session_id=session_id,
                )
                if search_fallback:
                    return {
                        "ok": True,
                        "kind": "skill_result",
                        "skill": "__search_backbone_fallback__",
                        "speak": str(search_fallback.get("speak") or ""),
                        "render": str(search_fallback.get("render") or ""),
                        "ui": _normalize_ui_or_info(search_fallback.get("ui")),
                    }
            fallback = await _fallback_existing_skill_for_transcript(
                root_transcript or spec,
                session_id=session_id,
            )
            if fallback:
                payload0 = fallback.get("payload") if isinstance(fallback.get("payload"), dict) else {}
                safe_ui0 = _sanitize_visual_ui_for_query(
                    payload0.get("ui") if isinstance(payload0, dict) else None,
                    root_transcript or spec,
                )
                if safe_ui0 is None and bool(intent_hints.get("require_visual_media")):
                    fallback = None
                elif safe_ui0 is not None and isinstance(payload0, dict):
                    payload0["ui"] = safe_ui0
            if fallback:
                name = str(fallback.get("name") or "")
                payload = fallback.get("payload") if isinstance(fallback.get("payload"), dict) else {}
                return {
                    "ok": True,
                    "kind": "skill_result",
                    "skill": name,
                    "speak": str(payload.get("speak") or f"Step {action_index}/{total_actions} used fallback skill {name}."),
                    "render": str(payload.get("render") or ""),
                    "ui": _normalize_ui_or_info(payload.get("ui") if isinstance(payload, dict) else None),
                }
            search_fallback = await _fallback_search_backbone_result(
                root_transcript or spec,
                session_id=session_id,
            )
            if search_fallback:
                return {
                    "ok": True,
                    "kind": "skill_result",
                    "skill": "__search_backbone_fallback__",
                    "speak": str(search_fallback.get("speak") or ""),
                    "render": str(search_fallback.get("render") or ""),
                    "ui": _normalize_ui_or_info(search_fallback.get("ui")),
                }
            return {
                "ok": False,
                "kind": "error",
                "speak": f"Step {action_index}/{total_actions} synthesis failed: {err[:120]}",
                "render": (
                    f"[action {action_index}/{total_actions}] synth one-shot failed\n"
                    f"spec: {spec}\nerror: {err}"
                ),
            }
        name = str(run_result.get("name") or "")
        payload = run_result.get("payload") if isinstance(run_result.get("payload"), dict) else {}
        save_as = str(action.get("save_as") or "").strip()
        if save_as:
            _ctx_set_var(ctx, save_as, payload)
        skill_speak = (payload.get("speak") if isinstance(payload, dict) else None) or ""
        ui = _normalize_ui_or_info(payload.get("ui") if isinstance(payload, dict) else None)
        repaired_suffix = " [auto-repaired]" if run_result.get("repaired") else ""
        return {
            "ok": True,
            "kind": "skill_result",
            "skill": name,
            "speak": (skill_speak or "结果已返回。").strip(),
            "render": _user_facing_render(str(payload.get("render", "") if isinstance(payload, dict) else payload)),
            "ui": ui,
        }

    if action_type == "synthesize_background":
        await _broadcast_progress("正在构建后台技能", session_id=session_id)
        trigger_kind = str(_resolve_templates(action.get("trigger_kind") or "", ctx) or "")
        spec = str(_resolve_templates(action.get("spec") or "", ctx) or "").strip()
        if trigger_kind not in ("timer", "vision"):
            return {
                "ok": False,
                "kind": "error",
                "speak": f"Step {action_index}/{total_actions} has invalid trigger kind.",
                "render": f"[action {action_index}/{total_actions}] bad trigger_kind: {trigger_kind!r}",
            }
        if not spec:
            return {
                "ok": False,
                "kind": "error",
                "speak": f"Step {action_index}/{total_actions} is missing background spec.",
                "render": f"[action {action_index}/{total_actions}] synthesize_background missing spec",
            }
        spec = _normalize_generic_synthesis_spec(spec, transcript=root_transcript)
        outcome_contract = _resolve_templates(action.get("outcome_contract") or {}, ctx) or {}
        print(f"[Plan] action#{action_index} synthesize_background kind={trigger_kind} spec={spec!r}", flush=True)
        run_result = await _synthesize_activate_and_validate_background(
            trigger_kind=trigger_kind,
            spec=spec,
            transcript=root_transcript or spec,
            outcome_contract=outcome_contract,
            session_id=session_id,
        )
        if not run_result.get("ok"):
            err = str(run_result.get("error") or "unknown background synthesis error")
            return {
                "ok": False,
                "kind": "error",
                "speak": f"Step {action_index}/{total_actions} background synthesis failed: {err[:120]}",
                "render": (
                    f"[action {action_index}/{total_actions}] synth background failed\n"
                    f"trigger_kind: {trigger_kind}\nspec: {spec}\nerror: {err}"
                ),
            }
        name = str(run_result.get("name") or "")
        cost = float(run_result.get("cost_usd", 0.0) or 0.0)
        save_as = str(action.get("save_as") or "").strip()
        if save_as:
            _ctx_set_var(ctx, save_as, {"name": name, "trigger_kind": trigger_kind, "cost_usd": cost})
        act_payload = run_result.get("payload") if isinstance(run_result.get("payload"), dict) else None
        act_speak = (act_payload.get("speak") if isinstance(act_payload, dict) else None) or ""
        act_render = (act_payload.get("render") if isinstance(act_payload, dict) else None) or ""
        ui = _normalize_ui_or_info(act_payload.get("ui") if isinstance(act_payload, dict) else None)
        repaired_suffix = " [auto-repaired]" if run_result.get("repaired") else ""
        return {
            "ok": True,
            "kind": "skill_result",
            "skill": name,
            "speak": (f"好的，已开始执行这个持续任务{repaired_suffix}。 {act_speak}").strip(),
            "render": _user_facing_render(str(act_render or "")),
            "ui": ui,
        }

    return {
        "ok": False,
        "kind": "error",
        "speak": f"Step {action_index}/{total_actions} has unknown action type.",
        "render": f"[action {action_index}/{total_actions}] unknown action_type: {action_type!r}",
    }


async def _execute_action_queue(
    actions: list[dict],
    queue_say_first: str = "",
    queue_on_error: str = "continue",
    start_index: int = 0,
    ctx: Optional[dict] = None,
    resumed_from_slot: str = "",
    session_id: str = "",
    root_transcript: str = "",
) -> dict:
    """Execute pending actions sequentially; supports ask_user pause/resume and branch."""
    global _PENDING_QUEUE_BY_SESSION
    if ctx is None:
        ctx = {"slots": {}, "vars": {}}
    if start_index == 0 and queue_say_first:
        await output_broadcast({"type": "speak", "text": queue_say_first, "from": "planner", "collide": "tone_interrupt"})
    if start_index == 0:
        await _broadcast_progress("正在拆解并执行任务", session_id=session_id)

    actions_working = copy.deepcopy(actions)
    speak_parts: list[str] = []
    render_lines: list[str] = []
    ui_cards: list[dict] = []
    failures = 0
    skipped = 0
    completed = 0
    pending_actions: list[dict] = []

    i = start_index
    while i < len(actions_working):
        action = actions_working[i] if isinstance(actions_working[i], dict) else {}
        action_type = str(action.get("action_type") or "").strip()
        action_no = i + 1
        pending_actions.append({"index": action_no, "action_type": action_type, "status": "running"})
        await output_broadcast({
            "type": "planner_queue_progress",
            "index": action_no,
            "total": len(actions_working),
            "status": "running",
            "action_type": action_type,
            "session_id": session_id,
        })

        if action_type == "ask_user":
            slot = str(action.get("slot") or "").strip() or "slot"
            question = str(_resolve_templates(action.get("question") or "", ctx) or "").strip()
            if not question:
                question = f"请告诉我 {slot}。"
            await _broadcast_progress(f"需要补充信息: {slot}", session_id=session_id)
            pending_actions[-1]["status"] = "paused"
            _PENDING_QUEUE_BY_SESSION[session_id or "default"] = {
                "actions": actions_working,
                "next_index": i + 1,
                "queue_on_error": queue_on_error,
                "ctx": ctx,
                "awaiting_slot": slot,
                "root_transcript": root_transcript,
            }
            await output_broadcast({
                "type": "planner_queue_progress",
                "index": action_no,
                "total": len(actions_working),
                "status": "paused",
                "action_type": action_type,
                "slot": slot,
                "session_id": session_id,
            })
            await output_broadcast({
                "type": "awaiting_slot",
                "active": True,
                "slot": slot,
                "question": question,
                "queue_index": action_no,
                "queue_total": len(actions_working),
                "session_id": session_id,
            })
            intro = f"已收到你的 {resumed_from_slot}，继续执行。 " if resumed_from_slot else ""
            return {
                "kind": "chat",
                "speak": intro + question,
                "render": (
                    f"Queue paused at action {action_no}/{len(actions_working)}.\n"
                    f"Waiting for slot: {slot}\nQuestion: {question}"
                ),
                "pending_actions": pending_actions,
                "awaiting_slot": slot,
                "ui": {
                    "type": "awaiting_slot",
                    "title": "等待补充信息",
                    "slot": slot,
                    "question": question,
                    "can_cancel": True,
                },
            }

        if action_type == "branch":
            await _broadcast_progress("正在根据已查询信息进行判断", session_id=session_id)
            left = _resolve_templates(action.get("left"), ctx)
            if left is None:
                source_path = str(action.get("source") or "").strip()
                if source_path:
                    left = _ctx_get_path(ctx, source_path)
            op = str(action.get("op") or "truthy")
            right = _resolve_templates(action.get("value"), ctx)
            matched = _eval_branch_condition(left, op, right)
            chosen_actions = action.get("then_actions") if matched else action.get("else_actions")
            chosen_actions = chosen_actions if isinstance(chosen_actions, list) else []
            render_lines.append(
                f"[action {action_no}/{len(actions_working)}] branch {op} -> {'then' if matched else 'else'} ({len(chosen_actions)} actions)"
            )
            pending_actions[-1]["status"] = "success"
            await output_broadcast({
                "type": "planner_queue_progress",
                "index": action_no,
                "total": len(actions_working),
                "status": "success",
                "action_type": "branch",
                "matched": matched,
                "session_id": session_id,
            })
            actions_working = actions_working[:i] + chosen_actions + actions_working[i + 1:]
            # Re-run current index at the first inserted child action.
            continue

        item = await _execute_planned_action(
            action,
            action_no,
            len(actions_working),
            ctx,
            session_id=session_id,
            root_transcript=root_transcript,
        )
        if item.get("ok"):
            pending_actions[-1]["status"] = "success"
            completed += 1
        else:
            pending_actions[-1]["status"] = "failed"
            failures += 1
        if item.get("speak"):
            speak_parts.append(str(item["speak"]))
        if item.get("render"):
            render_lines.append(str(item["render"]))
        ui = item.get("ui")
        if isinstance(ui, dict):
            ui_cards.append(ui)
        await output_broadcast({
            "type": "planner_queue_progress",
            "index": action_no,
            "total": len(actions_working),
            "status": pending_actions[-1]["status"],
            "action_type": action_type,
            "ok": bool(item.get("ok")),
            "session_id": session_id,
        })
        action_on_error = str(action.get("on_error") or "").strip().lower()
        effective_on_error = action_on_error if action_on_error in ("continue", "stop") else queue_on_error
        if (not item.get("ok")) and effective_on_error == "stop":
            skipped = max(0, len(actions_working) - (i + 1))
            break
        i += 1

    _PENDING_QUEUE_BY_SESSION.pop(session_id or "default", None)
    await _broadcast_progress("任务执行完成", session_id=session_id)
    # Use the runtime action counter (including branch-expanded children) as denominator,
    # so summaries stay consistent after dynamic branch expansion.
    total_runtime_actions = completed + failures + skipped
    summary = f"Completed {completed}/{total_runtime_actions} actions (failed: {failures}, skipped: {skipped})."
    if failures:
        speak = f"部分任务已完成。{summary}"
        kind = "error"
    else:
        speak = " ".join(speak_parts).strip() or "All requested actions are done."
        kind = "skill_result"
    render = "\n".join([summary] + render_lines)
    out = {"kind": kind, "speak": speak, "render": render, "pending_actions": pending_actions}
    if ui_cards:
        out["ui_cards"] = ui_cards
        out["ui"] = ui_cards[-1]
    return out


# ---------------------------------------------------------------------------
# /asr — lifted from vui (raw body or multipart)
# ---------------------------------------------------------------------------

@app.post("/asr")
async def asr_endpoint(request: Request):
    content_type = request.headers.get("content-type", "")
    if "multipart" in content_type:
        form = await request.form()
        f = form.get("file")
        if not f:
            return JSONResponse({"ok": False, "error": "no file in form"}, status_code=400)
        wav_bytes = await f.read()
    else:
        wav_bytes = await request.body()

    if not wav_bytes or len(wav_bytes) < 44:
        return JSONResponse({"ok": False, "error": "empty or too short"}, status_code=400)
    if len(wav_bytes) > 15 * 1024 * 1024:
        return JSONResponse({"ok": False, "error": "audio too large (max 15MB)"}, status_code=413)

    try:
        text = transcribe_wav(wav_bytes)
        return {"ok": True, "text": text}
    except Exception as e:
        print(f"[ASR] error: {e}", flush=True)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# /plan — real planner (phase 2)
# Claude vision call → one of four tools (chat / call_skill / synthesize_*).
# Synthesize_* tools return a phase-2 stub describing what would be created;
# actual code-gen + execution lands in phase 6 (synthesizer) and phase 4
# (background runner).
# ---------------------------------------------------------------------------

@app.post("/plan")
async def plan_endpoint(req: PlanRequest):
    global _PENDING_QUEUE_BY_SESSION, _PLANNER_FALLBACK_UNTIL_TS
    session_id = str(req.session_id or "default").strip() or "default"
    transcript = (req.transcript or "").strip()
    has_image = bool(req.image_b64)
    print(
        f"[Plan] transcript='{transcript}' image={'yes' if has_image else 'no'}",
        flush=True,
    )
    if not transcript:
        return {"kind": "noop", "speak": "", "render": ""}

    if not _is_substantive_utterance(transcript):
        print(f"[Plan] skip filler: {transcript!r}", flush=True)
        return {"kind": "noop", "speak": "", "render": ""}

    await _broadcast_progress("收到指令", session_id=session_id)

    # Resume a paused queue waiting for user-provided slot.
    session_state = _PENDING_QUEUE_BY_SESSION.get(session_id) or {}
    if session_state and session_state.get("awaiting_slot"):
        slot = str(session_state.get("awaiting_slot") or "slot")
        if _looks_cancel_pending(transcript):
            _PENDING_QUEUE_BY_SESSION.pop(session_id, None)
            await _broadcast_progress(f"已取消等待补充信息: {slot}", session_id=session_id)
            await output_broadcast({
                "type": "awaiting_slot",
                "active": False,
                "slot": slot,
                "reason": "user_cancelled",
                "session_id": session_id,
            })
            msg = f"已取消上一轮等待输入（{slot}）。你可以直接说新任务。"
            return {"kind": "chat", "speak": msg, "render": msg}
        if _looks_like_new_task_while_waiting(slot, transcript):
            _PENDING_QUEUE_BY_SESSION.pop(session_id, None)
            await _broadcast_progress(f"检测到新任务，已取消上一轮等待输入: {slot}", session_id=session_id)
            await output_broadcast({
                "type": "awaiting_slot",
                "active": False,
                "slot": slot,
                "reason": "interrupted_by_new_task",
                "session_id": session_id,
            })
        else:
            ctx = session_state.get("ctx") or {"slots": {}, "vars": {}}
            ctx.setdefault("slots", {})
            ctx["slots"][slot] = transcript
            session_state["ctx"] = ctx
            session_state["awaiting_slot"] = None
            _PENDING_QUEUE_BY_SESSION[session_id] = session_state
            print(f"[Plan] resume queue with slot {slot}={transcript!r}", flush=True)
            await _broadcast_progress(f"已收到补充信息: {slot}", session_id=session_id)
            await output_broadcast({
                "type": "awaiting_slot",
                "active": False,
                "slot": slot,
                "reason": "resumed",
                "session_id": session_id,
            })
            return await _execute_action_queue(
                actions=session_state.get("actions") or [],
                queue_say_first="",
                queue_on_error=str(session_state.get("queue_on_error") or "continue"),
                start_index=int(session_state.get("next_index") or 0),
                ctx=ctx,
                resumed_from_slot=slot,
                session_id=session_id,
                root_transcript=str(session_state.get("root_transcript") or ""),
            )

    # CN visual quick path: bypass slow planning/synthesis loops and return
    # directly deliverable image UI first.
    quick_intent = compile_intent_hints(transcript, transcript, "one_shot")
    if str(VOX_DEPLOY_REGION or "").strip().upper() == "CN" and bool(quick_intent.get("require_visual_media")):
        await _broadcast_progress("视觉请求快速路径：优先返回可直接浏览结果", session_id=session_id)
        fast_search = await _fallback_search_backbone_result(transcript, session_id=session_id)
        if fast_search:
            return fast_search

    now = time.time()
    if now < _PLANNER_FALLBACK_UNTIL_TS:
        remain = int(max(1, _PLANNER_FALLBACK_UNTIL_TS - now))
        await _broadcast_progress(f"规划模型暂时不可用，使用本地兜底（约 {remain}s）", session_id=session_id)
        decision = _fallback_planner_decision(transcript)
    else:
        try:
            await _broadcast_progress("正在理解意图", session_id=session_id)
            decision = await planner_mod.plan(
                transcript=transcript,
                image_b64=req.image_b64,
                registry_summary=_planner_registry_summary(),
            )
        except RuntimeError as e:
            msg = str(e)
            print(f"[Plan] config error: {msg}", flush=True)
            if ("SUBSCRIPTION_NOT_FOUND" in msg) or ("PermissionDeniedError" in msg) or ("403" in msg):
                _PLANNER_FALLBACK_UNTIL_TS = time.time() + _PLANNER_FALLBACK_BACKOFF_SEC
            await _broadcast_progress("规划模型不可用，切换本地兜底", session_id=session_id)
            decision = _fallback_planner_decision(transcript)
        except Exception as e:
            msg = f"planner failed: {type(e).__name__}: {e}"
            print(f"[Plan] error: {msg}", flush=True)
            if ("SUBSCRIPTION_NOT_FOUND" in msg) or ("PermissionDeniedError" in msg) or ("403" in msg):
                _PLANNER_FALLBACK_UNTIL_TS = time.time() + _PLANNER_FALLBACK_BACKOFF_SEC
            await _broadcast_progress("规划模型异常，切换本地兜底", session_id=session_id)
            decision = _fallback_planner_decision(transcript)

    tool = decision.get("_tool", "chat")
    inp = decision.get("_input", {}) or {}
    usage = decision.get("_meta", {}).get("usage", {})
    print(
        f"[Plan] tool={tool} input_keys={list(inp.keys())} usage={usage}",
        flush=True,
    )

    # ── chat ──
    if tool == "chat":
        speak = (inp.get("speak") or "").strip()
        out = {"kind": "chat", "speak": speak, "render": speak}
        tts = _normalize_tts_options(inp.get("tts"))
        if tts:
            out["tts"] = tts
        return out

    # ── dispatch_actions (internal pending action queue) ──
    if tool == "dispatch_actions":
        await _broadcast_progress("已拆解出多个动作，开始执行", session_id=session_id)
        queue_say_first = (inp.get("say_first") or "").strip()
        queue_on_error = str(inp.get("on_error") or "continue").strip().lower()
        if queue_on_error not in ("continue", "stop"):
            queue_on_error = "continue"
        actions = inp.get("actions") or []
        if not isinstance(actions, list) or not actions:
            return {
                "kind": "error",
                "speak": "I could not parse any actions from that request.",
                "render": "[dispatch_actions] empty actions",
            }
        normalized: list[dict] = []
        for action in actions:
            if isinstance(action, dict):
                normalized.append(action)
        if not normalized:
            return {
                "kind": "error",
                "speak": "I could not parse any valid actions from that request.",
                "render": "[dispatch_actions] no valid action objects",
            }
        print(f"[Plan] dispatch_actions count={len(normalized)} on_error={queue_on_error}", flush=True)
        return await _execute_action_queue(
            normalized,
            queue_say_first,
            queue_on_error,
            session_id=session_id,
            root_transcript=transcript,
        )

    # ── call_skill ──
    if tool == "call_skill":
        await _broadcast_progress("命中已有技能，开始执行", session_id=session_id)
        name = inp.get("name") or ""
        args = inp.get("args") or {}
        say_first = (inp.get("say_first") or "").strip()
        result = await _run_one_shot_with_policy(name, args)
        if not result["ok"]:
            err = result["error"]
            print(f"[Plan] skill error: {err}", flush=True)
            return {
                "kind": "error",
                "skill": name,
                "speak": f"Skill {name} failed: {err}",
                "render": f"[skill error] {name}: {err}",
            }
        r = result["result"] or {}
        r, ui_reasons = _validate_and_normalize_payload_ui(r if isinstance(r, dict) else {})
        call_contract = _enrich_outcome_contract(
            transcript=transcript,
            spec=name,
            provided={},
            intent_kind="one_shot",
        )
        ok_payload, _, reasons = validate_outcome_payload(r, call_contract)
        if ui_reasons:
            reasons = list(reasons) + list(ui_reasons)
            ok_payload = False
        if DELIVERABILITY_PROBE_ENABLED and isinstance(r, dict):
            d_ok, d_reasons, d_summary = await probe_ui_deliverability(
                r.get("ui"),
                timeout_sec=DELIVERABILITY_PROBE_TIMEOUT_SEC,
            )
            if not d_ok:
                ok_payload = False
                reasons = list(reasons) + [f"deliverability: {x}" for x in d_reasons]
                r["render"] = (
                    str(r.get("render") or "").strip()
                    + f"\n\ndeliverability_probe: {json.dumps(d_summary, ensure_ascii=False)}"
                ).strip()
        if not ok_payload:
            return {
                "kind": "error",
                "skill": name,
                "speak": f"Skill {name} payload validation failed.",
                "render": f"[skill payload invalid] {name}: {'; '.join(reasons)}",
            }
        skill_speak = (r.get("speak") if isinstance(r, dict) else None) or ""
        skill_render = (r.get("render") if isinstance(r, dict) else None) or str(r)
        ui = _normalize_ui_or_info(r.get("ui") if isinstance(r, dict) else None)
        speak_parts = [s for s in (say_first, skill_speak) if s]
        out = {
            "kind": "skill_result",
            "skill": name,
            "speak": " ".join(speak_parts),
            "render": skill_render,
        }
        tts = _normalize_tts_options(r.get("tts") if isinstance(r, dict) else None)
        if tts:
            out["tts"] = tts
        if isinstance(ui, dict):
            out["ui"] = ui
            out["ui_cards"] = [ui]
        return out

    # ── synthesize_one_shot — real (phase 6) ──
    if tool == "synthesize_one_shot":
        await _broadcast_progress("正在构建技能", session_id=session_id)
        spec = (inp.get("spec") or "").strip()
        spec = _normalize_generic_synthesis_spec(spec, transcript=transcript)
        outcome_contract = inp.get("outcome_contract") or {}
        intent_hints = compile_intent_hints(transcript, spec, "one_shot")
        say_first = (inp.get("say_first") or "").strip()
        if say_first:
            await output_broadcast({"type": "speak", "text": say_first, "from": "planner", "collide": "tone_interrupt"})
        # Fast path for CN visual intents: prioritize immediate usable delivery
        # over long synthesis-repair loops.
        if str(VOX_DEPLOY_REGION or "").strip().upper() == "CN" and bool(intent_hints.get("require_visual_media")):
            fast_search = await _fallback_search_backbone_result(transcript, session_id=session_id)
            if fast_search:
                return fast_search
        print(f"[Plan] synthesize_one_shot spec={spec!r}", flush=True)
        run_result = await _synthesize_and_validate_one_shot(
            spec=spec,
            transcript=transcript,
            outcome_contract=outcome_contract,
            session_id=session_id,
        )
        if not run_result.get("ok"):
            err = str(run_result.get("error") or "unknown synthesis error")
            if bool(intent_hints.get("require_visual_media")):
                search_fallback = await _fallback_search_backbone_result(transcript, session_id=session_id)
                if search_fallback:
                    return search_fallback
            fallback = await _fallback_existing_skill_for_transcript(transcript, session_id=session_id)
            if fallback:
                r0 = fallback.get("payload") if isinstance(fallback.get("payload"), dict) else {}
                safe_ui0 = _sanitize_visual_ui_for_query(
                    r0.get("ui") if isinstance(r0, dict) else None,
                    transcript,
                )
                if safe_ui0 is None and bool(intent_hints.get("require_visual_media")):
                    fallback = None
                elif safe_ui0 is not None and isinstance(r0, dict):
                    r0["ui"] = safe_ui0
            if fallback:
                name = str(fallback.get("name") or "")
                r = fallback.get("payload") if isinstance(fallback.get("payload"), dict) else {}
                skill_speak = (r.get("speak") if isinstance(r, dict) else None) or ""
                out = {
                    "kind": "skill_result",
                    "skill": name,
                    "speak": (skill_speak or "结果已返回。").strip(),
                    "render": _user_facing_render(str(r.get("render") if isinstance(r, dict) else r or "")),
                }
                tts = _normalize_tts_options(r.get("tts") if isinstance(r, dict) else None)
                if tts:
                    out["tts"] = tts
                ui = _normalize_ui_or_info(r.get("ui") if isinstance(r, dict) else None)
                if isinstance(ui, dict):
                    out["ui"] = ui
                    out["ui_cards"] = [ui]
                return out
            search_fallback = await _fallback_search_backbone_result(transcript, session_id=session_id)
            if search_fallback:
                return search_fallback
            return {
                "kind": "error",
                "speak": f"I couldn't build that skill: {err[:120]}",
                "render": f"[synth one-shot failed]\nspec: {spec}\nerror: {err}",
            }
        name = str(run_result.get("name") or "")
        r = run_result.get("payload") if isinstance(run_result.get("payload"), dict) else {}
        skill_speak = (r.get("speak") if isinstance(r, dict) else None) or ""
        repaired_suffix = " [auto-repaired]" if run_result.get("repaired") else ""
        out = {
            "kind": "skill_result",
            "skill": name,
            "speak": (skill_speak or "结果已返回。").strip(),
            "render": _user_facing_render(str(r.get("render", "") if isinstance(r, dict) else r)),
        }
        tts = _normalize_tts_options(r.get("tts") if isinstance(r, dict) else None)
        if tts:
            out["tts"] = tts
        ui = _normalize_ui_or_info(r.get("ui") if isinstance(r, dict) else None)
        if isinstance(ui, dict):
            out["ui"] = ui
            out["ui_cards"] = [ui]
        return out

    # ── synthesize_background — real (phase 6) ──
    if tool == "synthesize_background":
        await _broadcast_progress("正在构建后台技能", session_id=session_id)
        trigger_kind = inp.get("trigger_kind") or ""
        spec = (inp.get("spec") or "").strip()
        spec = _normalize_generic_synthesis_spec(spec, transcript=transcript)
        outcome_contract = inp.get("outcome_contract") or {}
        say_first = (inp.get("say_first") or "").strip()
        if trigger_kind not in ("timer", "vision"):
            return {"kind": "error", "speak": "I'm not sure what kind of background skill that is.",
                    "render": f"[bad trigger_kind] {trigger_kind!r}"}
        if say_first:
            await output_broadcast({"type": "speak", "text": say_first, "from": "planner", "collide": "tone_interrupt"})
        print(f"[Plan] synthesize_background kind={trigger_kind} spec={spec!r}", flush=True)
        run_result = await _synthesize_activate_and_validate_background(
            trigger_kind=trigger_kind,
            spec=spec,
            transcript=transcript,
            outcome_contract=outcome_contract,
            session_id=session_id,
        )
        if not run_result.get("ok"):
            err = str(run_result.get("error") or "unknown background synthesis error")
            return {
                "kind": "error",
                "speak": f"我没能完成这个持续任务：{err[:120]}",
                "render": f"[synth background failed]\ntrigger_kind: {trigger_kind}\nspec: {spec}\nerror: {err}",
            }
        name = str(run_result.get("name") or "")
        cost = float(run_result.get("cost_usd", 0.0) or 0.0)
        payload = run_result.get("payload") if isinstance(run_result.get("payload"), dict) else None
        ui = _normalize_ui_or_info(payload.get("ui") if isinstance(payload, dict) else None)
        act_speak = (payload.get("speak") if isinstance(payload, dict) else None) or ""
        act_render = (payload.get("render") if isinstance(payload, dict) else None) or ""
        repaired_suffix = " [auto-repaired]" if run_result.get("repaired") else ""
        out = {
            "kind": "skill_result",
            "skill": name,
            "speak": (act_speak or "持续任务已启动。").strip(),
            "render": _user_facing_render(str(act_render or "")),
            "ui": ui,
            "ui_cards": [ui] if isinstance(ui, dict) else [],
        }
        tts = _normalize_tts_options(payload.get("tts") if isinstance(payload, dict) else None)
        if tts:
            out["tts"] = tts
        return out

    # ── unknown tool (shouldn't happen) ──
    print(f"[Plan] unknown tool from planner: {tool}", flush=True)
    return {"kind": "error", "speak": "I'm not sure how to handle that.", "render": f"[unknown tool] {tool}"}


# ---------------------------------------------------------------------------
# /tts — Volc OpenSpeech (lifted from vui)
# ---------------------------------------------------------------------------

@app.post("/tts")
async def tts_endpoint(req: TTSRequest):
    if not VOLC_TTS_APP_ID or not VOLC_TTS_ACCESS_TOKEN:
        return JSONResponse({"ok": False, "error": "TTS not configured"}, status_code=503)

    text = req.text.strip()
    if not text:
        return JSONResponse({"ok": False, "error": "empty text"}, status_code=400)

    req_opts = _normalize_tts_options({
        "voice_type": req.voice_type,
        "speed_ratio": req.speed_ratio,
        "pitch_ratio": req.pitch_ratio,
        "volume_ratio": req.volume_ratio,
    })
    voice_type = str(req_opts.get("voice_type") or VOLC_TTS_VOICE_TYPE)
    speed_ratio = float(req_opts.get("speed_ratio", 1.0))
    pitch_ratio = float(req_opts.get("pitch_ratio", 1.0))
    volume_ratio = float(req_opts.get("volume_ratio", 1.0))

    import uuid
    payload = {
        "app": {
            "appid": VOLC_TTS_APP_ID,
            "token": VOLC_TTS_SECRET_KEY or VOLC_TTS_ACCESS_TOKEN,
            "cluster": VOLC_TTS_CLUSTER,
        },
        "user": {"uid": "vox-user"},
        "audio": {
            "voice_type": voice_type,
            "encoding": "mp3",
            "speed_ratio": speed_ratio,
            "pitch_ratio": pitch_ratio,
            "volume_ratio": volume_ratio,
            "sample_rate": 24000,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text,
            "operation": "query",
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                VOLC_TTS_URL,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer;{VOLC_TTS_ACCESS_TOKEN}",
                },
                json=payload,
                timeout=10.0,
            )
            data = resp.json()

        if data.get("code") != 3000:
            msg = data.get("message", "unknown error")
            print(f"[TTS] error: code={data.get('code')} msg={msg}", flush=True)
            return JSONResponse({"ok": False, "error": msg}, status_code=502)

        import base64
        audio_bytes = base64.b64decode(data["data"])
        print(f"[TTS] ok: {len(audio_bytes)} bytes for {len(text)} chars", flush=True)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        print(f"[TTS] exception: {e}", flush=True)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# /ws/output — server → client push (watcher fires, frames_required signal)
# /ws/frames — client → server camera frame stream for vision watchers
# ---------------------------------------------------------------------------

@app.websocket("/ws/output")
async def ws_output(ws: WebSocket):
    await ws.accept()
    session_id = str(ws.query_params.get("session_id") or "default").strip() or "default"
    output_clients.add(ws)
    print(f"[ws/output] client connected ({len(output_clients)} total)", flush=True)
    try:
        session_state = _PENDING_QUEUE_BY_SESSION.get(session_id) or {}
        await ws.send_text(json.dumps({
            "type": "hello",
            "phase": 4,
            "active_background": len(RUNNER.list()),
            "frames_required": RUNNER.has_vision_watchers(),
            "awaiting_slot": session_state.get("awaiting_slot"),
            "session_id": session_id,
        }))
        while True:
            msg = await ws.receive_text()
            print(f"[ws/output] recv: {msg[:80]}", flush=True)
    except WebSocketDisconnect:
        pass
    finally:
        output_clients.discard(ws)
        print(f"[ws/output] client disconnected ({len(output_clients)} remain)", flush=True)


@app.websocket("/ws/frames")
async def ws_frames(ws: WebSocket):
    await ws.accept()
    print("[ws/frames] client connected", flush=True)
    try:
        while True:
            msg = await ws.receive_text()
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                continue
            if data.get("type") != "frame":
                continue
            b64 = data.get("image_b64")
            if not b64:
                continue
            try:
                await RUNNER.evaluate_frame(b64, trigger_check.check)
            except Exception as e:
                print(f"[ws/frames] evaluate error: {e}", flush=True)
    except WebSocketDisconnect:
        pass
    finally:
        print("[ws/frames] client disconnected", flush=True)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
