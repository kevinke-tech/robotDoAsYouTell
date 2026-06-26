"""
Skill synthesizer — invokes the Claude Agent SDK to write a new skill file
on demand, runs a sandboxed smoke test, and registers the skill on success.

Flow per synthesis:
  1. Create scratch dir skills/_scratch/<uuid>/
  2. Spawn the Agent SDK with:
       - cwd = scratch dir
       - allowed_tools = Write / Read / Edit / Bash
       - disallowed_tools = WebFetch / WebSearch
       - permission_mode = "bypassPermissions"  (headless — no interactive prompts)
       - max_turns = 12
       - max_budget_usd = 0.50  (hard cost ceiling)
       - env passes ANTHROPIC_BASE_URL + ANTHROPIC_API_KEY explicitly
       - system_prompt embeds the vox skill API and a worked example
  3. Wait for ResultMessage; collect transcript + token usage
  4. Locate the .py file the agent wrote; AST-check for RUN_SPEC + run()
  5. Run an independent smoke test via subprocess (30s timeout, scratch cwd)
  6. On pass: copy to skills/<name>.py, reload registry
  7. Return {ok, name, transcript, cost_usd, error?}

Three skill shapes are supported:
  - one_shot         — request-response skill
  - background_timer — schedules runtime.RUNNER.add_timer(...)
  - background_vision — schedules runtime.RUNNER.add_vision_watcher(...)
"""

import ast
import asyncio
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

import skill_manifest
from skill_preflight import run_skill_preflight

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        SystemMessage,
        TextBlock,
        query,
    )
    _HAS_CLAUDE_AGENT_SDK = True
except Exception:
    AssistantMessage = ClaudeAgentOptions = ResultMessage = SystemMessage = TextBlock = query = None
    _HAS_CLAUDE_AGENT_SDK = False

ROOT = Path(__file__).resolve().parent
SKILLS_DIR = ROOT / "skills"
SCRATCH_ROOT = SKILLS_DIR / "_scratch"
SMOKE_TEST_TIMEOUT_SEC = 30.0
SYNTHESIZER_MODEL = os.getenv("SYNTHESIZER_MODEL", "claude-opus-4-7")
SYNTHESIZER_BACKEND = os.getenv("SYNTHESIZER_BACKEND", "claude_agent_sdk").strip().lower()
SYNTHESIZER_CURSOR_MODEL = os.getenv("SYNTHESIZER_CURSOR_MODEL", "auto")
MAX_BUDGET_USD = float(os.getenv("SYNTHESIZER_MAX_BUDGET_USD", "0.50"))
MAX_TURNS = int(os.getenv("SYNTHESIZER_MAX_TURNS", "12"))
VOX_DEPLOY_REGION = os.getenv("VOX_DEPLOY_REGION", "CN").strip().upper() or "CN"
VOX_PRIMARY_LOCALE = os.getenv("VOX_PRIMARY_LOCALE", "zh-CN")


# ───── prompt templates ────────────────────────────────────────────────────────

_ONE_SHOT_EXAMPLE = '''\
"""通用一次性技能：通过公开 API 获取内容并返回可读卡片。"""
import httpx

RUN_SPEC = {
    "name": "daily_quote",
    "description": "获取一句公开每日语录并返回结果卡片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "lang": {"type": "string", "default": "en"},
        },
        "required": [],
    },
}

async def run(lang: str = "en", **kwargs):
    url = "https://api.quotable.io/random"
    quote = ""
    author = ""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
        data = r.json() if r.status_code == 200 else {}
        quote = str(data.get("content") or "").strip()
        author = str(data.get("author") or "").strip()
    if not quote:
        return {
            "speak": "我暂时没获取到语录，请稍后再试。",
            "render": f"来源: {url}\\n结果: 空",
            "ui": {"type": "info_card", "title": "语录获取失败", "message": "暂时未获取到内容"},
        }
    msg = f"{quote} — {author}" if author else quote
    return {
        "speak": "我找到了今天的一句话。",
        "render": f"来源: {url}\\nquote: {quote}\\nauthor: {author}",
        "ui": {"type": "info_card", "title": "每日语录", "message": msg, "source_url": url},
    }


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(run())
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
'''

_BACKGROUND_TIMER_EXAMPLE = '''\
"""延时之后做一次语音提醒。"""
import runtime
import skill_manifest

RUN_SPEC = {
    "name": "generic_timer",
    "description": "安排一次语音提醒。参数：delay_seconds, message。",
    "args_schema": {
        "type": "object",
        "properties": {
            "delay_seconds": {"type": "number"},
            "message": {"type": "string"},
        },
        "required": ["delay_seconds", "message"],
    },
}

async def run(delay_seconds: float, message: str, **kwargs):
    if runtime.RUNNER is None:
        return {"speak": "现在还没法定时。", "render": "[错误] 后台运行器未就绪"}
    id_ = await runtime.RUNNER.add_timer(float(delay_seconds), message)
    return {
        "speak": "好的,到点提醒你。",
        "render": f"已安排定时: {id_}, {delay_seconds} 秒后触发",
    }


if __name__ == "__main__":
    # 冒烟测试: 实盘外 runtime.RUNNER 为 None, 这里只走 import 路径和错误分支。
    import asyncio, runtime
    runtime.RUNNER = None
    r = asyncio.run(run(delay_seconds=1, message="测试"))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
'''

_BACKGROUND_VISION_EXAMPLE = '''\
"""持续看摄像头, 当画面满足条件时说一句话。"""
import runtime

RUN_SPEC = {
    "name": "generic_vision_watcher",
    "description": "启动一个视觉监视器。参数：trigger, say_on_match, ui_on_match, cooldown_sec。",
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {"type": "string"},
            "say_on_match": {"type": "string"},
            "ui_on_match": {"type": "object"},
            "cooldown_sec": {"type": "number", "default": 30},
        },
        "required": ["trigger", "say_on_match"],
    },
}

async def run(trigger: str, say_on_match: str, ui_on_match: dict | None = None, cooldown_sec: float = 30, **kwargs):
    if runtime.RUNNER is None:
        return {"speak": "现在还没法启动监视器。", "render": "[错误] 后台运行器未就绪"}
    id_ = await runtime.RUNNER.add_vision_watcher(
        trigger=trigger, say_on_match=say_on_match,
        ui_on_match=ui_on_match if isinstance(ui_on_match, dict) else None,
        cooldown_sec=float(cooldown_sec), rate_hz=1.0,
    )
    return {
        "speak": "好的,我盯着看,看到了就告诉你。",
        "render": f"已启动视觉监视器: {id_}\\n  触发条件: {trigger}\\n  触发UI: {bool(ui_on_match)}",
    }


if __name__ == "__main__":
    import asyncio, runtime
    runtime.RUNNER = None
    r = asyncio.run(run(trigger="有人举手", say_on_match="看到了", ui_on_match={"type":"info_card","title":"触发","message":"已命中"}, cooldown_sec=10))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
'''


_VOX_ARCHITECTURE_BRIEF = """\
VOX runtime contract (must follow exactly):
- You are generating ONE skill file for Vox dynamic runtime.
- The file must expose:
  1) RUN_SPEC dict with:
     - name: snake_case, stable, unique
     - description: short
     - args_schema: valid JSON schema object
  2) async def run(...):
     - returns dict with at least "speak" and "render"
     - may include optional "ui" object
- The generated skill will be invoked by Vox runtime immediately after synthesis.
- Do NOT depend on manual browser operations for completion.
- If network retrieval is needed, do it in code and include evidence fields in render/ui.
- Prefer reusing shared backbone modules when possible:
  - web_search.search_web(query, max_results=...)
  - web_fetch.fetch_page(url, timeout_ms=..., max_bytes=...)
  - evidence_utils.build_render_evidence_block(...)
"""


def _build_system_prompt(kind: str, spec: str = "") -> str:
    if kind == "one_shot":
        example = _ONE_SHOT_EXAMPLE
        kind_notes = (
            "这是一个 ONE-SHOT skill —— 请求/响应一次。被调用时返回一个字典 "
            "{'speak': str, 'render': str}。"
        )
    elif kind == "background_timer":
        example = _BACKGROUND_TIMER_EXAMPLE
        kind_notes = (
            "这是一个后台定时器类 skill。它的 run() 通过 "
            "runtime.RUNNER.add_timer(delay_seconds, message) 安排一次触发, "
            "然后立刻返回一个确认字典。"
        )
    elif kind == "background_vision":
        example = _BACKGROUND_VISION_EXAMPLE
        kind_notes = (
            "这是一个后台视觉监视类 skill。它的 run() 通过 "
            "runtime.RUNNER.add_vision_watcher(trigger, say_on_match, ui_on_match, ...) "
            "启动一个监视器。若用户期望触发后展示内容，必须通过 ui_on_match 传入可渲染 UI。"
        )
    else:
        raise ValueError(f"unknown kind: {kind}")

    return f"""你为 vox agent 在当前工作目录下写恰好一个 Python 文件。

{_VOX_ARCHITECTURE_BRIEF}

约束 —— 请逐条严格遵守:
1. 只写一个文件, 文件名是 <snake_case_name>.py, 与 RUN_SPEC 的 name 字段一致。
2. 只用 Python 标准库, 以及父级 venv 已安装的包 (httpx、anthropic、runtime)。绝对不要 pip install。
3. 文件必须遵循下面"参考示例"中展示的 vox skill API。
4. 文件结尾必须有一个 `if __name__ == "__main__":` 块, 跑一次冒烟测试, 成功时打印且只打印 "OK"。请使用合成的测试参数。
5. 写完后, 用 Bash 工具执行 `python <filename>.py`。如果 stdout 里没有 "OK", 立刻修, 然后重试。最多重试 3 次, 仍失败就报告错误。
6. 文件保持小巧 —— 一般不超过 80 行。不要引入超出需求的抽象。
7. 完成时, 你的最后一条 assistant 消息必须严格是: SYNTHESIS_COMPLETE <filename>.py
8. 在输出 SYNTHESIS_COMPLETE 之前，必须先输出一行写入确认:
   WRITE_CONFIRMED <filename>.py
   （仅当该文件已实际写到当前工作目录时才可输出）
9. 面向用户交互时, 优先返回结构化的生成式 UI 描述到返回字典的 "ui" 字段 (例如 info_card/自定义卡片), 而不是让用户去操作网站页面。
10. 需要联网查询时, 优先用 API/httpx 或隐式(无头)抓取获取数据, 再把结果与证据组织进 speak/render/ui。不要依赖“打开可见浏览器 + 手工点击网页”作为主流程。
11. render 必须包含可验收证据标记，至少出现以下字段之一: source / source_url / evidence / references。
12. 若涉及结论判断(如天气好坏), render 必须包含信息来源与关键依据(来源URL/时间/关键字段), 再给出判断。
13. 任何外部网络调用必须设置 timeout 且用 try/except 包裹，禁止让异常冒泡导致 run() 抛错；失败时返回可解释的 speak/render/ui（含失败原因与证据），保证技能可降级返回。
14. `if __name__ == "__main__":` 冒烟测试必须在 3 秒内完成，禁止在冒烟测试中访问外网；可用 mock 数据或仅做结构性检查后打印 "OK"。
15. 部署环境与地域可达性约束:
    - deploy_region={VOX_DEPLOY_REGION}, primary_locale={VOX_PRIMARY_LOCALE}
    - 外部检索优先选择该地域可达且稳定的数据源，不要默认依赖单一国际端点。
    - 涉及地点/天气/路线等位置型任务时，至少准备两条可替代的数据获取路径（含地名归一化与坐标失败兜底）。
16. 若任务需要信息检索/网页提取，优先复用项目内通用底座模块（`web_search.py` / `web_fetch.py` / `evidence_utils.py`），不要在每个新技能中重复手写搜索引擎逻辑。

语言要求 (重要):
- 面向用户的字符串请匹配用户输入语言: 用户中文则中文输出, 用户英文则英文输出。
- "speak" 是给 TTS 念出来的, 写成自然的口语化短句, 不要太书面、不要 markdown、不要表情符号。
- "render" 是显示在聊天面板里的文本, 语言同用户输入; 可以稍长一点, 可以带换行。
- RUN_SPEC.name 保持英文 snake_case; Python 标识符、import 名、SYNTHESIS_COMPLETE 标记保持英文。

KIND: {kind}

{kind_notes}

本类型的参考示例:

```python
{example}```

vox skill API 摘要:
- RUN_SPEC 是一个字典, 键: name (snake_case)、description、args_schema (参数的 JSON Schema)。
- async def run(**kwargs) 返回一个字典, 必须包含 "speak" (适合 TTS 的简短中文) 与 "render" (面板显示的中文文本)。
- 如适用, 返回字典应包含 "ui" (dict), 让前端渲染一次性生成式 UI 卡片。
- 通用 UI schema（优先遵循）:
  - 信息卡: {{type: "info_card", title, message}}
  - 图片卡: {{type: "image_card", title, image_url, caption?}}
  - 卡片网格: {{type: "card_grid", title, cards:[{{title, image_url?, action_url?, subtitle?}}]}}
  - 内嵌内容: {{type: "iframe_card", title, iframe_url}}
  - 音频播放器: {{type: "music_player", audio_url, title?}}
  - 视频播放器: {{type: "video_player", video_url, title?}}
  - HTML 卡片: {{type: "html_card", html/srcdoc/js 至少一项}}
  - 等待补充: {{type: "awaiting_slot", slot, question}}
  - 若需用到任何特定组件，请严格满足该组件的必填字段与契约约束。
- skill 可以 `import runtime` 来访问运行中的 BackgroundRunner (只跟 background_* 类型相关; 冒烟测试期间 runtime.RUNNER 为 None, 这没关系)。
- skill 可用 httpx 做 HTTP、anthropic 调用 Claude API, 也可用 datetime、re、json 等标准库。
- 任务涉及“搜集网页信息并提取结论”时，优先采用:
  - `from web_search import search_web, format_search_hits`
  - `from web_fetch import fetch_page`
  - `from evidence_utils import build_render_evidence_block, attach_evidence_fields`

现在开始合成。
"""


# ───── helpers ────────────────────────────────────────────────────────────────


def _new_scratch_dir() -> Path:
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    d = SCRATCH_ROOT / uuid.uuid4().hex[:12]
    d.mkdir(parents=True, exist_ok=False)
    return d


def _build_env_passthrough() -> dict[str, str]:
    """Pass the proxy + API key through. Empty strings if unset."""
    env: dict[str, str] = {}
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"):
        v = os.getenv(k)
        if v:
            env[k] = v
    return env


def _find_produced_skill(
    scratch: Path,
    transcript: str = "",
    preferred_filename: str = "",
) -> Optional[Path]:
    """
    Return the best candidate .py file written by synthesis.
    Selection strategy:
      1) exactly one candidate
      2) preferred filename (if provided)
      3) filename from SYNTHESIS_COMPLETE marker in transcript
      4) exactly one AST-valid skill candidate
    """
    candidates = [
        p for p in scratch.iterdir()
        if p.is_file() and p.suffix == ".py" and not p.name.startswith("_")
    ]
    if len(candidates) == 1:
        return candidates[0]
    # If multiple .py files exist, prefer the newest generated file first.
    if len(candidates) > 1:
        newest = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
        valid_newest: list[Path] = []
        for p in newest[:3]:
            ok, _ = _ast_check_skill(p)
            if ok:
                valid_newest.append(p)
        if len(valid_newest) == 1:
            return valid_newest[0]
    if preferred_filename:
        for p in candidates:
            if p.name == preferred_filename:
                return p
    done_match = _DONE_RE.search(transcript or "")
    if done_match:
        wanted = done_match.group(1)
        for p in candidates:
            if p.name == wanted:
                return p
    valid: list[Path] = []
    for p in candidates:
        ok, _ = _ast_check_skill(p)
        if ok:
            valid.append(p)
    if len(valid) == 1:
        return valid[0]
    return None


async def _wait_for_produced_skill(
    scratch: Path,
    transcript: str = "",
    preferred_filename: str = "",
    timeout_sec: float = 6.0,
    interval_sec: float = 0.3,
) -> Optional[Path]:
    """
    Cursor SDK may report completion before file writes are fully flushed.
    Poll briefly for eventual file visibility.
    """
    deadline = asyncio.get_running_loop().time() + max(0.1, timeout_sec)
    while True:
        p = _find_produced_skill(
            scratch,
            transcript=transcript,
            preferred_filename=preferred_filename,
        )
        if p is not None:
            return p
        if asyncio.get_running_loop().time() >= deadline:
            return None
        await asyncio.sleep(max(0.05, interval_sec))


_DONE_RE = re.compile(r"SYNTHESIS_COMPLETE\s+([a-zA-Z0-9_]+\.py)")
_PY_FENCE_RE = re.compile(r"```python\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_CURSOR_FILE_FLUSH_WAIT_SEC = float(os.getenv("SYNTHESIZER_CURSOR_FILE_FLUSH_WAIT_SEC", "25"))


def _recover_skill_from_transcript(scratch: Path, transcript: str) -> tuple[bool, str]:
    """
    Cursor SDK may occasionally return completion text without applying file writes.
    Recover by extracting a python code block from transcript and writing it to disk.
    """
    if not transcript.strip():
        return False, "empty transcript"

    done_match = _DONE_RE.search(transcript)
    filename = done_match.group(1) if done_match else "recovered_skill.py"
    if not filename.endswith(".py"):
        filename = "recovered_skill.py"
    if not re.fullmatch(r"[a-zA-Z0-9_]+\.py", filename):
        filename = "recovered_skill.py"

    code_match = None
    for m in _PY_FENCE_RE.finditer(transcript):
        code_match = m
    if code_match is None:
        return False, "no python fenced code block found in transcript"

    code = (code_match.group(1) or "").strip()
    if not code:
        return False, "python fenced code block is empty"

    out = scratch / filename
    out.write_text(code + "\n", encoding="utf-8")
    return True, out.name


def _programmatic_dynamic_synthesis(spec: str, kind: str, scratch: Path) -> tuple[bool, str]:
    """
    Deterministic dynamic synthesis fallback when SDK returns no writable code.
    This preserves dynamic-creation flow without switching to prebuilt skills.
    """
    suffix = uuid.uuid4().hex[:6]

    if kind == "background_timer":
        skill_name = f"dynamic_timer_watcher_{suffix}"
        file_name = f"{skill_name}.py"
        code = '''"""Programmatically generated background timer skill."""
from __future__ import annotations
import runtime

RUN_SPEC = {
    "name": "__SKILL_NAME__",
    "description": "动态创建：启动一个定时提醒实例。",
    "args_schema": {
        "type": "object",
        "properties": {
            "delay_seconds": {"type": "number", "default": 30},
            "message": {"type": "string", "default": "到点提醒"},
        },
        "required": [],
    },
}

async def run(delay_seconds: float = 30, message: str = "到点提醒", **kwargs):
    if runtime.RUNNER is None:
        return {"speak": "现在还不能启动定时器。", "render": "[错误] RUNNER 未就绪"}
    id_ = await runtime.RUNNER.add_timer(float(delay_seconds), str(message))
    return {
        "speak": "好的，我已经创建了一个定时提醒。",
        "render": f"已创建定时实例: {id_}\\ndelay_seconds: {delay_seconds}\\nmessage: {message}",
    }

if __name__ == "__main__":
    import inspect
    assert isinstance(RUN_SPEC, dict) and RUN_SPEC.get("name")
    assert inspect.iscoroutinefunction(run)
    print("OK")
'''
        code = code.replace("__SKILL_NAME__", skill_name)
        p = scratch / file_name
        p.write_text(code, encoding="utf-8")
        return True, p.name

    if kind == "background_vision":
        skill_name = f"dynamic_vision_watcher_{suffix}"
        file_name = f"{skill_name}.py"
        code = '''"""Programmatically generated background vision watcher skill."""
from __future__ import annotations
import runtime

RUN_SPEC = {
    "name": "__SKILL_NAME__",
    "description": "动态创建：启动一个视觉触发实例。",
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {"type": "string", "default": "the requested condition is clearly visible in the camera frame"},
            "say_on_match": {"type": "string", "default": "已检测到触发条件"},
            "cooldown_sec": {"type": "number", "default": 30},
            "rate_hz": {"type": "number", "default": 1.0},
        },
        "required": [],
    },
}

async def run(trigger: str = "the requested condition is clearly visible in the camera frame", say_on_match: str = "已检测到触发条件", cooldown_sec: float = 30, rate_hz: float = 1.0, **kwargs):
    if runtime.RUNNER is None:
        return {"speak": "现在还不能启动视觉监视。", "render": "[错误] RUNNER 未就绪"}
    id_ = await runtime.RUNNER.add_vision_watcher(
        trigger=str(trigger),
        say_on_match=str(say_on_match),
        cooldown_sec=float(cooldown_sec),
        rate_hz=float(rate_hz),
    )
    return {
        "speak": "好的，我已经开始盯着看了。",
        "render": f"已创建视觉实例: {id_}\\ntrigger: {trigger}\\nsay_on_match: {say_on_match}\\ncooldown_sec: {cooldown_sec}\\nrate_hz: {rate_hz}",
    }

if __name__ == "__main__":
    import inspect
    assert isinstance(RUN_SPEC, dict) and RUN_SPEC.get("name")
    assert inspect.iscoroutinefunction(run)
    print("OK")
'''
        code = code.replace("__SKILL_NAME__", skill_name)
        p = scratch / file_name
        p.write_text(code, encoding="utf-8")
        return True, p.name

    if kind != "one_shot":
        return False, "unsupported kind for deterministic synthesis"

    return False, "deterministic one-shot fallback disabled to avoid intent guessing"


def _ast_check_skill(skill_path: Path) -> tuple[bool, str]:
    """Verify the file parses and exports RUN_SPEC + an async run()."""
    try:
        source = skill_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except SyntaxError as e:
        return False, f"syntax error: {e}"

    has_run_spec = False
    has_async_run = False
    run_spec_name: Optional[str] = None

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "RUN_SPEC":
                    has_run_spec = True
                    if isinstance(node.value, ast.Dict):
                        for k, v in zip(node.value.keys, node.value.values):
                            if isinstance(k, ast.Constant) and k.value == "name":
                                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                                    run_spec_name = v.value
        elif isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            has_async_run = True

    if not has_run_spec:
        return False, "missing RUN_SPEC dict"
    if not has_async_run:
        return False, "missing `async def run(...)`"
    if not run_spec_name:
        return False, "RUN_SPEC has no `name` string field"
    if not re.fullmatch(r"[a-z][a-z0-9_]*", run_spec_name):
        return False, f"RUN_SPEC name {run_spec_name!r} is not snake_case"
    return True, run_spec_name


def _run_smoke_test(skill_path: Path, scratch: Path) -> tuple[bool, str]:
    """Run `python <skill_path>` in scratch_dir; expect 'OK' in stdout."""
    try:
        # PYTHONPATH includes vox root so the skill can `import runtime`
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            ["python3", str(skill_path)],
            cwd=str(scratch),
            timeout=SMOKE_TEST_TIMEOUT_SEC,
            capture_output=True,
            text=True,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False, f"smoke test timed out (>{SMOKE_TEST_TIMEOUT_SEC:.0f}s)"
    except Exception as e:
        return False, f"smoke test launch failed: {type(e).__name__}: {e}"

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout)[-800:]
        return False, f"smoke test exited {proc.returncode}: {tail}"
    if "OK" not in proc.stdout:
        return False, f"smoke test ran but didn't print 'OK'. stdout: {proc.stdout[-400:]}"
    return True, "ok"


def _rewrite_main_block_for_fast_smoke(skill_path: Path) -> tuple[bool, str]:
    try:
        src = skill_path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"read failed: {e}"
    replacement = (
        'if __name__ == "__main__":\n'
        "    import inspect\n"
        "    assert isinstance(RUN_SPEC, dict)\n"
        "    assert inspect.iscoroutinefunction(run)\n"
        '    print("OK")\n'
    )
    pattern = re.compile(r'(?ms)^if __name__\s*==\s*[\'"]__main__[\'"]:\n.*\Z')
    if pattern.search(src):
        new_src = pattern.sub(replacement, src)
    else:
        new_src = src.rstrip() + "\n\n" + replacement
    try:
        skill_path.write_text(new_src, encoding="utf-8")
    except Exception as e:
        return False, f"write failed: {e}"
    return True, "patched"


def _rename_run_spec_name(skill_path: Path, old_name: str, new_name: str) -> tuple[bool, str]:
    if not old_name or not new_name or old_name == new_name:
        return False, "invalid rename args"
    try:
        src = skill_path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"read failed: {e}"
    pat_double = re.compile(
        r'("name"\s*:\s*")' + re.escape(old_name) + r'(")',
        re.MULTILINE,
    )
    pat_single = re.compile(
        r"('name'\s*:\s*')" + re.escape(old_name) + r"(')",
        re.MULTILINE,
    )
    changed = False
    if pat_double.search(src):
        src = pat_double.sub(r"\1" + new_name + r"\2", src, count=1)
        changed = True
    elif pat_single.search(src):
        src = pat_single.sub(r"\1" + new_name + r"\2", src, count=1)
        changed = True
    if not changed:
        return False, "RUN_SPEC.name not found for rename"
    try:
        skill_path.write_text(src, encoding="utf-8")
    except Exception as e:
        return False, f"write failed: {e}"
    return True, "renamed"


def _recover_skill_from_root_recent(
    root_snapshot: dict[str, float],
    synth_started_at: float,
    scratch: Path,
) -> tuple[bool, str]:
    """
    Recover when Cursor SDK writes skill file to repo root instead of scratch.
    """
    protected = {
        "server.py",
        "planner.py",
        "synthesizer.py",
        "dispatcher.py",
        "background.py",
        "runtime.py",
        "trigger_check.py",
        "ui_contract.py",
        "outcome_contract.py",
        "skill_manifest.py",
        "browser.py",
    }
    candidates: list[Path] = []
    for p in ROOT.glob("*.py"):
        if not p.is_file():
            continue
        if p.name in protected:
            continue
        mtime = p.stat().st_mtime
        old_mtime = float(root_snapshot.get(p.name, 0.0))
        if (p.name not in root_snapshot and mtime >= synth_started_at - 1.0) or (mtime > old_mtime + 1e-6):
            ok, _ = _ast_check_skill(p)
            if ok:
                candidates.append(p)

    if len(candidates) != 1:
        return False, f"root recovery candidate count={len(candidates)}"

    src = candidates[0]
    dst = scratch / src.name
    try:
        shutil.copy2(src, dst)
    except Exception as e:
        return False, f"root recovery copy failed: {e}"
    return True, dst.name


async def _run_with_claude_agent_sdk(spec: str, kind: str, scratch: Path) -> dict:
    if not _HAS_CLAUDE_AGENT_SDK:
        return {
            "ok": False,
            "error": "claude-agent-sdk is not installed",
            "transcript": "",
            "cost_usd": 0.0,
            "stop_reason": "?",
            "saw_done_marker": False,
        }

    options = ClaudeAgentOptions(
        system_prompt=_build_system_prompt(kind, spec),
        cwd=str(scratch),
        allowed_tools=["Write", "Read", "Edit", "Bash"],
        disallowed_tools=["WebFetch", "WebSearch"],
        permission_mode="bypassPermissions",
        max_turns=MAX_TURNS,
        max_budget_usd=MAX_BUDGET_USD,
        model=SYNTHESIZER_MODEL,
        env=_build_env_passthrough(),
        mcp_servers={},
        add_dirs=[],
        extra_args={},
        betas=[],
        plugins=[],
    )

    transcript_parts: list[str] = []
    cost_usd = 0.0
    final_result: Optional[object] = None
    saw_done_marker = False

    try:
        async for msg in query(prompt=spec, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text = block.text
                        transcript_parts.append(text)
                        if "SYNTHESIS_COMPLETE" in text:
                            saw_done_marker = True
            elif isinstance(msg, SystemMessage):
                pass
            elif isinstance(msg, ResultMessage):
                final_result = msg
                cost_usd = float(getattr(msg, "total_cost_usd", 0.0) or 0.0)
    except Exception as e:
        return {
            "ok": False,
            "error": f"agent SDK error: {type(e).__name__}: {e}",
            "transcript": "".join(transcript_parts),
            "cost_usd": cost_usd,
            "stop_reason": "?",
            "saw_done_marker": saw_done_marker,
        }

    stop_reason = getattr(final_result, "stop_reason", "?") if final_result else "?"
    return {
        "ok": True,
        "error": "",
        "transcript": "".join(transcript_parts),
        "cost_usd": cost_usd,
        "stop_reason": stop_reason,
        "saw_done_marker": saw_done_marker,
    }


def _run_cursor_sdk_prompt_sync(prompt: str, cwd: str) -> dict:
    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
    except Exception as e:
        return {"ok": False, "error": f"cursor-sdk import failed: {e}", "transcript": ""}

    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "CURSOR_API_KEY is missing", "transcript": ""}

    try:
        agent = Agent.create(
            AgentOptions(
                api_key=api_key,
                model=SYNTHESIZER_CURSOR_MODEL,
                local=LocalAgentOptions(cwd=cwd),
                mode="agent",
            )
        )
    except Exception as e:
        return {"ok": False, "error": f"cursor-sdk create failed: {type(e).__name__}: {e}", "transcript": ""}

    transcript_parts: list[str] = []
    counts: dict[str, int] = {}
    try:
        run = agent.send(prompt)
        for msg in run.messages():
            t = str(getattr(msg, "type", "?"))
            counts[t] = counts.get(t, 0) + 1
            if t != "assistant":
                continue
            content = getattr(getattr(msg, "message", None), "content", ())
            for block in content:
                text = str(getattr(block, "text", "") or "")
                if text:
                    transcript_parts.append(text)
        result = run.wait()
    except Exception as e:
        return {
            "ok": False,
            "error": f"cursor-sdk run failed: {type(e).__name__}: {e} counts={counts}",
            "transcript": "".join(transcript_parts),
        }
    finally:
        try:
            agent.close()
        except Exception:
            pass

    status = str(getattr(result, "status", "") or "").lower()
    terminal_text = str(getattr(result, "result", "") or "")
    combined = "".join(transcript_parts) + ("\n" + terminal_text if terminal_text else "")
    if status == "error":
        return {
            "ok": False,
            "error": f"cursor-sdk returned error status: {terminal_text[:300]} counts={counts}",
            "transcript": combined,
        }
    print(f"[synth/cursor] counts={counts}", flush=True)
    return {"ok": True, "error": "", "transcript": combined}


async def _run_with_cursor_sdk(spec: str, kind: str, scratch: Path, force_emit_code: bool = False) -> dict:
    prompt = (
        _build_system_prompt(kind, spec)
        + "\n\n用户需求（再次给出，确保不遗漏）:\n"
        + spec
        + "\n\n执行协议（严格）:\n"
        + "1) 先写文件到当前工作目录。\n"
        + "2) 用 Bash 运行: python <filename>.py\n"
        + "3) 确认 stdout 包含 OK。\n"
        + "4) 输出 WRITE_CONFIRMED <filename>.py\n"
        + "5) 最后一条消息输出 SYNTHESIS_COMPLETE <filename>.py\n"
    )
    if force_emit_code:
        prompt += (
            "\n\n额外要求（严格）:\n"
            "如果工具写文件失败，你必须在最终消息里提供完整 Python 文件，"
            "放在 ```python ... ``` 代码块中，且与 SYNTHESIS_COMPLETE 的文件名一致。"
            "如果你无法给出完整代码块，必须输出 ERROR_NO_CODE_FENCE。"
        )
    r = await asyncio.to_thread(_run_cursor_sdk_prompt_sync, prompt, str(scratch))
    transcript = str(r.get("transcript") or "")
    return {
        "ok": bool(r.get("ok")),
        "error": str(r.get("error") or ""),
        "transcript": transcript,
        "cost_usd": 0.0,  # Cursor SDK currently doesn't expose Claude-style USD usage here.
        "stop_reason": "cursor_sdk",
        "saw_done_marker": ("SYNTHESIS_COMPLETE" in transcript),
    }


async def _run_synthesis_agent(spec: str, kind: str, scratch: Path) -> dict:
    backend = SYNTHESIZER_BACKEND
    if backend == "cursor_sdk":
        return await _run_with_cursor_sdk(spec, kind, scratch)
    if backend == "claude_agent_sdk":
        return await _run_with_claude_agent_sdk(spec, kind, scratch)
    return {
        "ok": False,
        "error": f"unknown SYNTHESIZER_BACKEND: {backend}",
        "transcript": "",
        "cost_usd": 0.0,
        "stop_reason": "?",
        "saw_done_marker": False,
    }


def _effective_model() -> str:
    if SYNTHESIZER_BACKEND == "cursor_sdk":
        return str(SYNTHESIZER_CURSOR_MODEL or "auto")
    return str(SYNTHESIZER_MODEL or "")


def _extract_args_signature(skill_path: Path) -> dict:
    try:
        tree = ast.parse(skill_path.read_text(encoding="utf-8"), filename=str(skill_path))
    except Exception:
        return {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "RUN_SPEC":
                    try:
                        run_spec = ast.literal_eval(node.value)
                    except Exception:
                        return {}
                    if not isinstance(run_spec, dict):
                        return {}
                    args_schema = run_spec.get("args_schema")
                    return args_schema if isinstance(args_schema, dict) else {}
    return {}


# ───── main entry ──────────────────────────────────────────────────────────────


async def synthesize(spec: str, kind: str, registry: Any) -> dict:
    """
    Synthesize a new skill via the Claude Agent SDK.

    Args:
      spec: NL description of the desired skill (from the planner).
      kind: "one_shot" | "background_timer" | "background_vision".
      registry: the SkillRegistry instance to reload on success.

    Returns:
      {"ok": bool, "name": str, "transcript": str, "cost_usd": float, "error": str?}
    """
    if kind not in ("one_shot", "background_timer", "background_vision"):
        return {"ok": False, "error": f"unknown kind: {kind}", "name": "", "transcript": "", "cost_usd": 0.0}

    scratch = _new_scratch_dir()
    synth_started_at = time.time()
    root_snapshot = {
        p.name: p.stat().st_mtime
        for p in ROOT.glob("*.py")
        if p.is_file()
    }
    print(f"[synth] kind={kind} scratch={scratch.name} spec={spec[:80]!r}", flush=True)

    agent_result = await _run_synthesis_agent(spec, kind, scratch)
    if not agent_result.get("ok"):
        return {
            "ok": False,
            "error": str(agent_result.get("error") or "synthesis agent failed"),
            "name": "",
            "transcript": str(agent_result.get("transcript") or ""),
            "cost_usd": float(agent_result.get("cost_usd", 0.0) or 0.0),
        }

    transcript = str(agent_result.get("transcript") or "")
    cost_usd = float(agent_result.get("cost_usd", 0.0) or 0.0)
    stop_reason = str(agent_result.get("stop_reason") or "?")
    saw_done_marker = bool(agent_result.get("saw_done_marker"))
    print(f"[synth] agent done stop_reason={stop_reason} cost=${cost_usd:.4f}", flush=True)

    # Locate the produced file
    preferred_filename = ""
    skill_path = await _wait_for_produced_skill(scratch, transcript=transcript)
    if skill_path is None:
        recovered_ok, recovered_msg = _recover_skill_from_transcript(scratch, transcript)
        if recovered_ok:
            print(f"[synth] recovered missing file from transcript: {recovered_msg}", flush=True)
            skill_path = await _wait_for_produced_skill(scratch, transcript=transcript)
        else:
            print(f"[synth] transcript recovery not possible: {recovered_msg}", flush=True)
            # Dynamic-first retry: keep the same path (synthesize) instead of
            # falling back to prebuilt skills.
            if SYNTHESIZER_BACKEND == "cursor_sdk":
                retry = await _run_with_cursor_sdk(spec, kind, scratch, force_emit_code=True)
                if retry.get("ok"):
                    retry_transcript = str(retry.get("transcript") or "")
                    if retry_transcript:
                        transcript = retry_transcript
                    recovered_ok2, recovered_msg2 = _recover_skill_from_transcript(scratch, transcript)
                    if recovered_ok2:
                        print(f"[synth] recovered file after retry: {recovered_msg2}", flush=True)
                        skill_path = await _wait_for_produced_skill(scratch, transcript=transcript)
                    else:
                        print(f"[synth] retry recovery still failed: {recovered_msg2}", flush=True)
            if skill_path is None:
                prog_ok, prog_msg = _programmatic_dynamic_synthesis(spec, kind, scratch)
                if prog_ok:
                    print(f"[synth] deterministic dynamic synthesis produced: {prog_msg}", flush=True)
                    preferred_filename = str(prog_msg or "").strip()
                    skill_path = _find_produced_skill(
                        scratch,
                        transcript=transcript,
                        preferred_filename=preferred_filename,
                    )
                    if skill_path is None:
                        skill_path = await _wait_for_produced_skill(
                            scratch,
                            transcript=transcript,
                            preferred_filename=preferred_filename,
                        )
                else:
                    print(f"[synth] deterministic dynamic synthesis skipped: {prog_msg}", flush=True)
    if skill_path is None:
        if SYNTHESIZER_BACKEND == "cursor_sdk":
            # Cursor SDK can delay filesystem writes after run.wait() returns.
            # Give it one longer final window before declaring failure.
            skill_path = await _wait_for_produced_skill(
                scratch,
                transcript=transcript,
                preferred_filename=preferred_filename,
                timeout_sec=_CURSOR_FILE_FLUSH_WAIT_SEC,
                interval_sec=0.5,
            )
    if skill_path is None:
        recovered_root_ok, recovered_root_msg = _recover_skill_from_root_recent(
            root_snapshot=root_snapshot,
            synth_started_at=synth_started_at,
            scratch=scratch,
        )
        if recovered_root_ok:
            print(f"[synth] recovered skill file from repo root: {recovered_root_msg}", flush=True)
            skill_path = await _wait_for_produced_skill(
                scratch,
                transcript=transcript,
                preferred_filename=preferred_filename,
                timeout_sec=2.0,
                interval_sec=0.2,
            )
        else:
            print(f"[synth] root recovery skipped: {recovered_root_msg}", flush=True)
    if skill_path is None:
        candidates_now = [
            p for p in scratch.iterdir()
            if p.is_file() and p.suffix == ".py" and not p.name.startswith("_")
        ]
        if len(candidates_now) == 1:
            skill_path = candidates_now[0]
    if skill_path is None:
        py_files = [p.name for p in scratch.iterdir() if p.suffix == ".py"]
        marker_hint = ""
        if saw_done_marker:
            marker_hint = (
                " model returned SYNTHESIS_COMPLETE but no unique valid skill file "
                "was selected in time."
            )
        return {
            "ok": False,
            "error": (
                f"agent didn't produce a unique skill file (found: {py_files})."
                f"{marker_hint} backend={SYNTHESIZER_BACKEND}"
            ),
            "name": "",
            "transcript": transcript,
            "cost_usd": cost_usd,
        }

    # AST sanity check
    ast_ok, ast_msg = _ast_check_skill(skill_path)
    if not ast_ok:
        return {"ok": False, "error": f"file failed AST check: {ast_msg}",
                "name": "", "transcript": transcript, "cost_usd": cost_usd}
    skill_name = ast_msg  # success path returns the name

    # Static preflight guard: enforce platform-safe generated code before runtime smoke.
    preflight_ok, preflight_errors, preflight_warnings = run_skill_preflight(skill_path)
    if preflight_warnings:
        print(f"[synth] preflight warnings on {skill_name}: {preflight_warnings}", flush=True)
    if not preflight_ok:
        return {
            "ok": False,
            "error": f"skill preflight failed: {'; '.join(preflight_errors)}",
            "name": skill_name,
            "transcript": transcript,
            "cost_usd": cost_usd,
        }

    # Independent smoke test (belt-and-suspenders — the agent should have done one too)
    smoke_ok, smoke_msg = _run_smoke_test(skill_path, scratch)
    if (not smoke_ok) and ("timed out" in str(smoke_msg).lower()):
        patched, patch_msg = _rewrite_main_block_for_fast_smoke(skill_path)
        if patched:
            smoke_ok, smoke_msg = _run_smoke_test(skill_path, scratch)
            if smoke_ok:
                print("[synth] smoke timeout auto-patched __main__ block", flush=True)
        else:
            smoke_msg = f"{smoke_msg}; fast-smoke patch failed: {patch_msg}"
    if not smoke_ok:
        return {"ok": False, "error": f"smoke test failed: {smoke_msg}",
                "name": skill_name, "transcript": transcript, "cost_usd": cost_usd}

    # Avoid overwrite collisions by renaming generated skill deterministically.
    final_path = SKILLS_DIR / f"{skill_name}.py"
    if final_path.exists():
        renamed = False
        base = skill_name
        for _ in range(20):
            suffix = uuid.uuid4().hex[:6]
            candidate = f"{base}_{suffix}"
            candidate_path = SKILLS_DIR / f"{candidate}.py"
            if candidate_path.exists():
                continue
            ok_rename, rename_msg = _rename_run_spec_name(skill_path, skill_name, candidate)
            if not ok_rename:
                return {
                    "ok": False,
                    "error": f"skill name collision and rename failed: {rename_msg}",
                    "name": skill_name,
                    "transcript": transcript,
                    "cost_usd": cost_usd,
                }
            skill_name = candidate
            final_path = candidate_path
            renamed = True
            print(f"[synth] name collision auto-resolved: {base} -> {skill_name}", flush=True)
            break
        if not renamed:
            return {
                "ok": False,
                "error": f"skill {base!r} already exists and unique rename failed",
                "name": base,
                "transcript": transcript,
                "cost_usd": cost_usd,
            }

    # Promote
    shutil.copy2(skill_path, final_path)
    print(f"[synth] promoted {skill_name} → {final_path}", flush=True)

    # Persist generation metadata for traceability.
    try:
        skill_manifest.upsert_generated_skill(
            skill_name,
            {
                "source": "dynamic_synthesis",
                "kind": kind,
                "backend": SYNTHESIZER_BACKEND,
                "model": _effective_model(),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "file": str(final_path),
                "args_signature": _extract_args_signature(final_path),
                "instance_binding": "spawning" if kind.startswith("background_") else "one_shot",
                "version": 1,
                "preflight_warnings": preflight_warnings,
            },
        )
    except Exception as e:
        print(f"[synth] manifest write warning: {e}", flush=True)

    # Hot-reload the registry
    try:
        registry.load_all()
    except Exception as e:
        # Skill is on disk but registry didn't update — caller will see no change
        return {"ok": False, "error": f"registry reload failed: {e}",
                "name": skill_name, "transcript": transcript, "cost_usd": cost_usd}

    return {
        "ok": True,
        "name": skill_name,
        "transcript": transcript,
        "cost_usd": cost_usd,
        "stop_reason": stop_reason,
        "saw_done_marker": saw_done_marker,
    }


async def synthesize_one_shot(spec: str, registry: Any) -> dict:
    return await synthesize(spec, "one_shot", registry)


async def synthesize_background(trigger_kind: str, spec: str, registry: Any) -> dict:
    kind = f"background_{trigger_kind}"
    result = await synthesize(spec, kind, registry)
    if result.get("ok") and result.get("name"):
        import runtime
        if runtime.RUNNER is not None:
            runtime.RUNNER.mark_spawning_skill(result["name"])
    return result
