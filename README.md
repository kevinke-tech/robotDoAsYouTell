# vox

A self-extending voice + vision agent: listens through the laptop mic, sees through the laptop camera, and grows its own toolset at runtime by calling Claude Code (via the Claude Agent SDK) to synthesize new skill modules on demand.

**Phase 6 (current)**: skill synthesizer is live. When the planner classifies an utterance as `synthesize_one_shot` or `synthesize_background`, the synthesizer invokes the **Claude Agent SDK** in a sandbox, writes a fresh `skills/<name>.py`, runs its embedded smoke test, AST-checks it, runs an independent smoke test as belt-and-suspenders, and hot-reloads the registry on success. For one-shot syntheses, the new skill is immediately invoked so "Open Hacker News" produces both the synthesis AND the result in one turn.

---

## Architecture (target)

```
                    Browser
       mic ─VAD─▶ /asr (FunASR)            camera ─▶ snapshot per utterance
            \                                  /
             ▼                                ▼
                   /plan  (transcript + frame_b64)
                              │
                              ▼
                       Claude (vision)
                  ┌─────────┴────────┐
                  ▼                  ▼
          call existing skill   synthesize new skill
          (Playwright + vision) (Claude Agent SDK)
                  │
                  └──▶ result ──▶ /tts ──▶ 🔊

   Watcher mode (phase 4): camera streams at 1 fps to /ws/frames;
   pHash filter → Opus vision per filtered frame → server-initiated TTS
   pushed back via /ws/output.
```

## Stack

| Layer | What |
|---|---|
| ASR | FunASR `paraformer-zh`, local CPU (reused from `../vui`) |
| TTS | Volcano Engine OpenSpeech (reused from `../vui`) |
| Backend | FastAPI on `:5001` (`server.py`) |
| Frontend | vanilla HTML/JS, Web Audio API, `getUserMedia` |
| Planner | Claude Opus 4.7 (vision) — via the limtok proxy |
| Synthesizer | Claude Agent SDK — phase 6 |
| Body | Playwright (headed) — phase 3 |
| Watcher trigger | Claude Opus 4.7 (vision) + perceptual-hash pre-filter — phase 4 |

## Setup

```bash
# 0. (Users in mainland China — optional, dramatically faster downloads)
sudo sed -i 's|http://.*archive.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list && sudo apt update

# 1. Python deps
python3 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1a. Playwright Chromium binary (~150 MB download)
# China mirror: export PLAYWRIGHT_DOWNLOAD_HOST=https://registry.npmmirror.com/-/binary/playwright
playwright install chromium

# 2. Node deps (just http-server for the frontend)
npm install

# 3. Configure secrets
cp .env.example .env.local          # if you haven't already
# Edit .env.local — fill ANTHROPIC_API_KEY (from your limtok account).
# The VOLC_TTS_* keys are pre-copied from vui/.env.local; replace if rotated.

# 4. Verify the proxy supports what we need (BEFORE building any planner code).
python scripts/probe_proxy.py
# Should print PASS for: text, vision, tool use, streaming, prompt caching.
```

## Running

In two terminals:

```bash
# Terminal 1 — backend (loads FunASR on first request, ~10s)
source .venv/bin/activate
python server.py
# → http://localhost:5001
```

```bash
# Terminal 2 — frontend
npm start
# → http://localhost:8080
```

Open `http://localhost:8080`. The page asks for mic + camera permission. Click "start mic" + "start camera", then talk. Phase-1 stub: the agent will speak your transcript back at you and note that it received a camera frame.

You can also type into the input box — it goes through the same `/plan` path.

## Quality Gates (Invariant-Based)

Vox now uses fixed platform invariants instead of case-by-case feature rules.

Run invariant checks:

```bash
python scripts/e2e_invariants.py --port 5001
```

Run unified quality gate (recommended before merge/release):

```bash
python scripts/quality_gate.py --port 5001
```

Run high-volume invariant stress (same fixed gates, more perturbed inputs):

```bash
python scripts/quality_gate.py --port 5001 --mass-eval --mass-eval-count 200
```

By default, mass eval uses `scripts/mass_eval_seeds.txt` (lightweight seeds)
and writes failures to `logs/mass_eval_failures.json`.

Run random-10 self-healing evaluation (intent randomization + auto reinforcement):

```bash
python scripts/random10_self_heal.py --host 127.0.0.1 --port 5001 --count 10 --run-gate-after-heal
```

Feed your own large transcript set (e.g. 10k cases) without adding new rules:

```bash
python scripts/e2e_invariants.py --port 5001 --transcript-file scripts/invariant_cases.txt
```

## What's wired today (phase 6)

- ✅ Mic + camera capture, VAD, ASR, TTS — vui-derived voice stack
- ✅ Planner: Claude Opus 4.7 vision call, 4-tool router (chat / call_skill / synthesize_one_shot / synthesize_background)
- ✅ Skill registry: `current_time`, `generic_timer`, `generic_vision_watcher`, `list_active`, `stop_active`, **`open_url`**, plus anything the synthesizer adds at runtime
- ✅ **Playwright browser body**: persistent shared Chromium context, lazy-launched on first browser-skill call. Skills use `async with runtime.new_page() as page:` to drive it. The synthesizer detects browser-shaped specs and emits skills that use the same pattern.
- ✅ Background runner: timers + vision watchers (pHash filter → Opus vision trigger check → tone + TTS fire)
- ✅ **Skill synthesizer (phase 6)**: Claude Agent SDK writes a skill on demand, runs a sandboxed smoke test, registers on pass — see Synthesizer section below
- ✅ TTS playback + barge-in

## Try it

After `python server.py` + `npm start`:

| Say / type | Planner tool | Behavior |
|---|---|---|
| "What time is it?" / "现在几点" | `call_skill(current_time)` | speaks the time |
| "What do you see?" | `chat` | Claude describes the camera frame |
| **"Remind me to drink water in 30 seconds"** | `call_skill(generic_timer)` | 30s later, tone + spoken reminder |
| **"Tell me when you see me raise my hand"** | `call_skill(generic_vision_watcher)` | starts frame stream; speaks when match |
| "What are you watching for?" | `call_skill(list_active)` | lists active timers + watchers |
| "Stop the hand watcher" | `call_skill(stop_active)` | cancels the matching background skill |
| "Open Hacker News" | `synthesize_one_shot` | *stub* — synthesizer lands in phase 6 |
| "Every 5 minutes, summarize my screen" | `synthesize_background` | *stub* — generics can't express this |

## Synthesizer

When `/plan` returns `synthesize_one_shot` or `synthesize_background`, the synthesizer (`synthesizer.py`) runs the following pipeline:

1. Create a scratch dir at `skills/_scratch/<uuid>/`.
2. Spawn the **Claude Agent SDK** (`claude-agent-sdk`) via `query(prompt=spec, options=...)` with:
   - `cwd` = the scratch dir
   - `allowed_tools = ["Write", "Read", "Edit", "Bash"]`, `disallowed_tools = ["WebFetch", "WebSearch"]`
   - `permission_mode = "bypassPermissions"` (headless — no interactive prompts)
   - `max_turns = 12`, `max_budget_usd = 0.50` (hard cost cap; tunable via env)
   - `env` explicitly passes `ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL` so the SDK uses the limtok proxy
   - `system_prompt` embeds the vox skill API and a worked example for the requested kind
3. Wait for `ResultMessage`; collect transcript and `total_cost_usd`.
4. Locate the single `.py` file the agent wrote; AST-check for `RUN_SPEC` + `async def run()`.
5. Run an independent smoke test via `subprocess.run([python3, file], cwd=scratch, timeout=30)`. Expects `"OK"` in stdout.
6. On pass: copy to `skills/<name>.py` and call `registry.load_all()` to hot-reload. For one-shots, immediately invoke the new skill.
7. Return `{ok, name, transcript, cost_usd, error?}`.

**Cost reality**:
- A typical one-shot synthesis is **~$0.05–0.30** (planner call + Agent SDK turns).
- Hard cap is `SYNTHESIZER_MAX_BUDGET_USD` (default `0.50`).
- Failed syntheses still cost money — log them so you can tune the system prompt.

**Sandbox model** (defense in depth, not perfect):
- Scratch cwd contains all file ops by default.
- `allowed_tools` excludes web access.
- Independent smoke test runs in scratch dir, not in vox/.
- AST check rejects files that don't match the skill API.
- Promotion to `skills/<name>.py` only happens after both checks pass.
- `skills/_scratch/` is gitignored; periodically delete it to reclaim disk.

**Requirements**:
- `pip install claude-agent-sdk` (verified against `0.2.94`).
- The `claude` Node CLI must be on PATH — the SDK auto-installs `@anthropic-ai/claude-code` when invoked.

**Tunables (env)**:
- `SYNTHESIZER_MODEL` — default `claude-opus-4-7`. Lower-cost alternative: `claude-sonnet-4-6` (smaller cost, may produce lower-quality skills).
- `SYNTHESIZER_MAX_BUDGET_USD` — default `0.50`.
- `SYNTHESIZER_MAX_TURNS` — default `12`.

## Cost reality (active vision watcher)

Each frame that survives the pHash filter triggers an Opus 4.7 vision call:
- Static scene (you're away) → ~0 calls/min, ~$0/hr
- Sitting still → ~3–10 calls/min, ~$1–4/hr
- Active (gesturing, moving) → ~30–50 calls/min, **~$10–20/hr**
- Constant motion → 60 calls/min capped, **~$25/hr**

If a watcher runs for hours, this adds up. Stop active watchers when you're done with the demo (`"stop everything"` works). Cost levers reserved for later: lower `rate_hz`, swap Opus→Haiku per skill, add a motion-detection pre-filter.

## Browser

The persistent Chromium lazy-launches on the first call to `runtime.new_page()`. One shared `BrowserContext` (1280×800, shared cookie jar) gives every skill a consistent session; per-call `page` instances are created and closed via the async context manager. The session-wide cookie jar means a skill that logs in once stays logged in for subsequent skills until the server restarts.

**Headed vs headless**: defaults to headed (visible window). On WSL2 without WSLg, headed launch will fail and the host auto-retries headless with a warning. Force headless with `BROWSER_HEADLESS=true` in `.env.local`.

**Browser-skill convention**: skills that use `runtime.new_page()` ship with **shape-only smoke tests** (assert `RUN_SPEC` + `inspect.iscoroutinefunction(run)` + print `"OK"`). They do not call `run()` in `__main__` because there's no live Chromium in the smoke-test subprocess. The synthesizer detects browser-shaped specs from keywords (`browser`, `page`, `url`, `navigate`, ...) and emits the same pattern.

**`open_url` skill**: the handwritten first browser skill — `open_url(url, screenshot=false)`. Auto-prepends `https://`, navigates, returns the page title; with `screenshot=true`, saves a PNG to `logs/screenshots/`.

## Not wired yet

- ⏳ Watcher persistence across restarts (in-memory only today)
- ⏳ `can_use_tool` per-call permission callback (would let the synthesizer deny `pip install`, file writes outside scratch, etc.)
- ⏳ In-flight synthesis dedup (today, two near-simultaneous identical requests run two full syntheses)

## Layout

```
vox/
├── server.py                       # FastAPI: /asr, /plan, /tts, /watchers, /ws/output, /ws/frames
├── planner.py                      # Claude vision + tool_use (4 tools)
├── dispatcher.py                   # skill registry + one-shot runner
├── background.py                   # BackgroundRunner (timers + vision watchers)
├── trigger_check.py                # per-frame Claude vision: match yes/no
├── frame_filter.py                 # pHash dedup helper
├── browser.py                      # BrowserHost — persistent Chromium via Playwright
├── synthesizer.py                  # Claude Agent SDK wrapper (writes skills on demand)
├── runtime.py                      # shared globals (RUNNER, OUTPUT_BROADCAST, BROWSER, new_page)
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── voice.js                # VAD + recording + TTS playback (ported from vui)
│       ├── camera.js               # getUserMedia + snapshot + frame stream
│       └── app.js                  # orchestrator + watcher tone-and-speak
├── skills/
│   ├── current_time.py
│   ├── generic_timer.py
│   ├── generic_vision_watcher.py
│   ├── list_active.py
│   ├── open_url.py
│   ├── stop_active.py
│   └── _scratch/                   # gitignored — synthesizer working dirs
│       └── <uuid>/                 # one per synthesis attempt
├── scripts/
│   └── probe_proxy.py
├── requirements.txt
├── package.json
├── .env.example
├── .env.local                      # gitignored — your secrets
└── .gitignore
```
