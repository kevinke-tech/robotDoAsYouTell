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
import json
import os
import threading
import wave
from typing import Optional

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

print(f"[vox] ASR model   : {FUNASR_MODEL} (FunASR local)", flush=True)
print(f"[vox] TTS         : {'Volc (' + VOLC_TTS_VOICE_TYPE + ')' if VOLC_TTS_APP_ID else 'NOT CONFIGURED'}", flush=True)

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


class TTSRequest(BaseModel):
    text: str


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
    instances = [inst for inst in RUNNER.list() if inst.get("source_skill") == name]
    is_spawning = RUNNER.is_spawning_skill(name) or len(instances) > 0
    running = [inst for inst in instances if inst.get("is_active")]
    return {
        "name": name,
        "description": spec.get("description", ""),
        "kind": "background" if is_spawning else "one_shot",
        "required_args": required,
        "active_instances": instances,
        "running_count": len(running),
        "is_active": len(running) > 0,
    }


@app.get("/skills")
async def list_skills():
    return {"skills": [_skill_view(n, i) for n, i in REGISTRY.skills.items()]}


async def _broadcast_skills_changed() -> None:
    await output_broadcast({"type": "skills_changed"})


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
    result = await run_one_shot(REGISTRY, name, args or {})
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
    info = REGISTRY.get(name)
    if info is None:
        return JSONResponse({"ok": False, "error": "unknown skill"}, status_code=404)
    if info["kind"] != "background":
        # generic_vision_watcher / generic_timer are one_shot wrappers in this codebase;
        # they spawn instances *as a side-effect* of being run. So we route through run().
        pass
    try:
        body = await request.json()
    except Exception:
        body = {}
    args = (body.get("args") if isinstance(body, dict) else None) or {}

    required = list((info["spec"].get("args_schema") or {}).get("required") or [])
    missing = [r for r in required if r not in args]
    if missing:
        return JSONResponse(
            {"ok": False, "error": f"this skill needs args: {missing} — invoke it by voice instead"},
            status_code=400,
        )

    result = await run_one_shot(REGISTRY, name, args)
    if result.get("ok"):
        await _broadcast_skills_changed()
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
    REGISTRY.load_all()
    await _broadcast_skills_changed()
    return {"ok": True, "deleted": name}


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

    try:
        decision = await planner_mod.plan(
            transcript=transcript,
            image_b64=req.image_b64,
            registry_summary=REGISTRY.summary_for_planner(),
        )
    except RuntimeError as e:
        # Missing key, etc.
        msg = str(e)
        print(f"[Plan] config error: {msg}", flush=True)
        return {"kind": "error", "speak": msg, "render": msg}
    except Exception as e:
        msg = f"planner failed: {type(e).__name__}: {e}"
        print(f"[Plan] error: {msg}", flush=True)
        return {"kind": "error", "speak": "Planner failed. Check server logs.", "render": msg}

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
        return {"kind": "chat", "speak": speak, "render": speak}

    # ── call_skill ──
    if tool == "call_skill":
        name = inp.get("name") or ""
        args = inp.get("args") or {}
        say_first = (inp.get("say_first") or "").strip()
        result = await run_one_shot(REGISTRY, name, args)
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
        skill_speak = (r.get("speak") if isinstance(r, dict) else None) or ""
        skill_render = (r.get("render") if isinstance(r, dict) else None) or str(r)
        speak_parts = [s for s in (say_first, skill_speak) if s]
        return {
            "kind": "skill_result",
            "skill": name,
            "speak": " ".join(speak_parts),
            "render": skill_render,
        }

    # ── synthesize_one_shot — real (phase 6) ──
    if tool == "synthesize_one_shot":
        spec = (inp.get("spec") or "").strip()
        say_first = (inp.get("say_first") or "").strip()
        if say_first:
            await output_broadcast({"type": "speak", "text": say_first, "from": "planner", "collide": "tone_interrupt"})
        print(f"[Plan] synthesize_one_shot spec={spec!r}", flush=True)
        result = await synthesizer.synthesize_one_shot(spec, REGISTRY)
        if not result["ok"]:
            err = result["error"]
            return {
                "kind": "error",
                "speak": f"I couldn't build that skill: {err[:120]}",
                "render": f"[synth one-shot failed]\nspec: {spec}\nerror: {err}\nlast transcript: {result.get('transcript','')[-400:]}",
            }
        name = result["name"]
        cost = result.get("cost_usd", 0.0)
        await _broadcast_skills_changed()
        # Immediately invoke the newly-created skill (no args inferred — let it run defaults if any)
        invoke_result = await run_one_shot(REGISTRY, name, {})
        if invoke_result["ok"]:
            r = invoke_result["result"] or {}
            skill_speak = (r.get("speak") if isinstance(r, dict) else None) or ""
            return {
                "kind": "skill_result",
                "skill": name,
                "speak": f"Made a new skill called {name} and ran it. {skill_speak}".strip(),
                "render": f"[synthesized] {name} (cost ${cost:.4f})\n{r.get('render','') if isinstance(r, dict) else r}",
            }
        return {
            "kind": "skill_result",
            "skill": name,
            "speak": f"Made a new skill called {name}, but it errored on first run.",
            "render": f"[synthesized] {name} (cost ${cost:.4f})\n[invoke error] {invoke_result['error']}",
        }

    # ── synthesize_background — real (phase 6) ──
    if tool == "synthesize_background":
        trigger_kind = inp.get("trigger_kind") or ""
        spec = (inp.get("spec") or "").strip()
        say_first = (inp.get("say_first") or "").strip()
        if trigger_kind not in ("timer", "vision"):
            return {"kind": "error", "speak": "I'm not sure what kind of background skill that is.",
                    "render": f"[bad trigger_kind] {trigger_kind!r}"}
        if say_first:
            await output_broadcast({"type": "speak", "text": say_first, "from": "planner", "collide": "tone_interrupt"})
        print(f"[Plan] synthesize_background kind={trigger_kind} spec={spec!r}", flush=True)
        result = await synthesizer.synthesize_background(trigger_kind, spec, REGISTRY)
        if not result["ok"]:
            err = result["error"]
            return {
                "kind": "error",
                "speak": f"I couldn't build that watcher: {err[:120]}",
                "render": f"[synth background failed]\ntrigger_kind: {trigger_kind}\nspec: {spec}\nerror: {err}",
            }
        name = result["name"]
        cost = result.get("cost_usd", 0.0)
        await _broadcast_skills_changed()
        return {
            "kind": "skill_result",
            "skill": name,
            "speak": f"OK, built a new {trigger_kind} skill called {name}. Say its name with your request to invoke it.",
            "render": f"[synthesized] {name} ({trigger_kind}, cost ${cost:.4f})",
        }

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

    import uuid
    payload = {
        "app": {
            "appid": VOLC_TTS_APP_ID,
            "token": VOLC_TTS_SECRET_KEY or VOLC_TTS_ACCESS_TOKEN,
            "cluster": VOLC_TTS_CLUSTER,
        },
        "user": {"uid": "vox-user"},
        "audio": {
            "voice_type": VOLC_TTS_VOICE_TYPE,
            "encoding": "mp3",
            "speed_ratio": 1.0,
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
    output_clients.add(ws)
    print(f"[ws/output] client connected ({len(output_clients)} total)", flush=True)
    try:
        await ws.send_text(json.dumps({
            "type": "hello",
            "phase": 4,
            "active_background": len(RUNNER.list()),
            "frames_required": RUNNER.has_vision_watchers(),
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
