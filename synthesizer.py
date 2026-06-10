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
import uuid
from pathlib import Path
from typing import Any, Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    query,
)

ROOT = Path(__file__).resolve().parent
SKILLS_DIR = ROOT / "skills"
SCRATCH_ROOT = SKILLS_DIR / "_scratch"
SMOKE_TEST_TIMEOUT_SEC = 30.0
SYNTHESIZER_MODEL = os.getenv("SYNTHESIZER_MODEL", "claude-opus-4-7")
MAX_BUDGET_USD = float(os.getenv("SYNTHESIZER_MAX_BUDGET_USD", "0.50"))
MAX_TURNS = int(os.getenv("SYNTHESIZER_MAX_TURNS", "12"))


# ───── prompt templates ────────────────────────────────────────────────────────

_ONE_SHOT_EXAMPLE = '''\
"""告诉用户当前本地时间。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_time",
    "description": "告诉用户当前本地时间。无参数。",
    "args_schema": {"type": "object", "properties": {}, "required": []},
}

async def run(**kwargs):
    now = datetime.now()
    return {
        "speak": f"现在是 {now.strftime('%H:%M')}。",
        "render": f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}",
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

_BROWSER_ONE_SHOT_EXAMPLE = '''\
"""打开一个网址并返回页面标题。"""
import runtime

RUN_SPEC = {
    "name": "page_title",
    "description": "打开一个网址并返回它的标题。参数：url。",
    "args_schema": {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
}

async def run(url: str, **kwargs):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    async with runtime.new_page() as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        title = (await page.title() or "").strip()
    return {
        "speak": f"页面标题是: {title}。" if title else "页面没有标题。",
        "render": f"URL: {url}\\n标题: {title or '(无标题)'}",
    }


if __name__ == "__main__":
    # 浏览器类 skill 的冒烟测试约定: 只检查结构 —— 不要调用 run(),
    # 因为合成时的冒烟环境里没有运行中的 Chromium。
    import inspect
    assert isinstance(RUN_SPEC, dict) and RUN_SPEC.get("name")
    assert inspect.iscoroutinefunction(run)
    print("OK")
'''


_BACKGROUND_VISION_EXAMPLE = '''\
"""持续看摄像头, 当画面满足条件时说一句话。"""
import runtime

RUN_SPEC = {
    "name": "generic_vision_watcher",
    "description": "启动一个视觉监视器。参数：trigger, say_on_match, cooldown_sec。",
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {"type": "string"},
            "say_on_match": {"type": "string"},
            "cooldown_sec": {"type": "number", "default": 30},
        },
        "required": ["trigger", "say_on_match"],
    },
}

async def run(trigger: str, say_on_match: str, cooldown_sec: float = 30, **kwargs):
    if runtime.RUNNER is None:
        return {"speak": "现在还没法启动监视器。", "render": "[错误] 后台运行器未就绪"}
    id_ = await runtime.RUNNER.add_vision_watcher(
        trigger=trigger, say_on_match=say_on_match,
        cooldown_sec=float(cooldown_sec), rate_hz=1.0,
    )
    return {
        "speak": "好的,我盯着看,看到了就告诉你。",
        "render": f"已启动视觉监视器: {id_}\\n  触发条件: {trigger}",
    }


if __name__ == "__main__":
    import asyncio, runtime
    runtime.RUNNER = None
    r = asyncio.run(run(trigger="有人举手", say_on_match="看到了", cooldown_sec=10))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
'''


_BROWSER_KEYWORDS = (
    "browser", "page", " url", "url:", "url ", "website", "navigate", "playwright",
    "scrape", "scraping", "fill", "form", "click", "selector", "dom",
    "浏览器", "网页", "网址", "网站", "打开链接", "打开 http", "抓取", "爬取",
    "填表", "点击", "页面", "标签页",
)


def _looks_like_browser_skill(spec: str) -> bool:
    low = spec.lower()
    return any(kw in low for kw in _BROWSER_KEYWORDS)


def _build_system_prompt(kind: str, spec: str = "") -> str:
    if kind == "one_shot":
        if _looks_like_browser_skill(spec):
            example = _BROWSER_ONE_SHOT_EXAMPLE
            kind_notes = (
                "这是一个 ONE-SHOT 浏览器类 skill。运行时通过 Playwright 持有一个常驻 "
                "Chromium 浏览器；你通过 `async with runtime.new_page() as page:` 来用它。"
                "浏览器类 skill 的冒烟测试只校验结构 —— __main__ 里不要调用 run(), "
                "因为合成时的冒烟环境里没有运行中的 Chromium。"
            )
        else:
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
            "runtime.RUNNER.add_vision_watcher(trigger, say_on_match, ...) "
            "启动一个监视器, 然后立刻返回一个确认字典。"
        )
    else:
        raise ValueError(f"unknown kind: {kind}")

    return f"""你为 vox agent 在当前工作目录下写恰好一个 Python 文件。

约束 —— 请逐条严格遵守:
1. 只写一个文件, 文件名是 <snake_case_name>.py, 与 RUN_SPEC 的 name 字段一致。
2. 只用 Python 标准库, 以及父级 venv 已安装的包 (httpx、anthropic、runtime)。绝对不要 pip install。
3. 文件必须遵循下面"参考示例"中展示的 vox skill API。
4. 文件结尾必须有一个 `if __name__ == "__main__":` 块, 跑一次冒烟测试, 成功时打印且只打印 "OK"。请使用合成的测试参数。
5. 写完后, 用 Bash 工具执行 `python <filename>.py`。如果 stdout 里没有 "OK", 立刻修, 然后重试。最多重试 3 次, 仍失败就报告错误。
6. 文件保持小巧 —— 一般不超过 80 行。不要引入超出需求的抽象。
7. 完成时, 你的最后一条 assistant 消息必须严格是: SYNTHESIS_COMPLETE <filename>.py

语言要求 (重要):
- 面向用户的字符串必须用简体中文: RUN_SPEC.description、返回字典里的 "speak" 和 "render"、注释、docstring, 都用中文。
- "speak" 是给 TTS 念出来的, 写成自然的口语化中文短句, 不要太书面、不要 markdown、不要表情符号。
- "render" 是显示在聊天面板里的文本, 也用中文; 可以稍长一点, 可以带换行。
- 仅以下内容保持英文: RUN_SPEC.name (snake_case)、Python 标识符、import 名、SYNTHESIS_COMPLETE 标记。

KIND: {kind}

{kind_notes}

本类型的参考示例:

```python
{example}```

vox skill API 摘要:
- RUN_SPEC 是一个字典, 键: name (snake_case)、description、args_schema (参数的 JSON Schema)。
- async def run(**kwargs) 返回一个字典, 必须包含 "speak" (适合 TTS 的简短中文) 与 "render" (面板显示的中文文本)。
- skill 可以 `import runtime` 来访问运行中的 BackgroundRunner (只跟 background_* 类型相关; 冒烟测试期间 runtime.RUNNER 为 None, 这没关系)。
- skill 可用 httpx 做 HTTP、anthropic 调用 Claude API, 也可用 datetime、re、json 等标准库。

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


def _find_produced_skill(scratch: Path) -> Optional[Path]:
    """Return the single .py file the agent wrote (ignore __pycache__ etc.)."""
    candidates = [
        p for p in scratch.iterdir()
        if p.is_file() and p.suffix == ".py" and not p.name.startswith("_")
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


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
    print(f"[synth] kind={kind} scratch={scratch.name} spec={spec[:80]!r}", flush=True)

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
    final_result: Optional[ResultMessage] = None
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
                # ResultMessage has total_cost_usd, stop_reason, num_turns, etc.
                cost_usd = float(getattr(msg, "total_cost_usd", 0.0) or 0.0)
    except Exception as e:
        return {
            "ok": False,
            "error": f"agent SDK error: {type(e).__name__}: {e}",
            "name": "",
            "transcript": "".join(transcript_parts),
            "cost_usd": cost_usd,
        }

    transcript = "".join(transcript_parts)
    stop_reason = getattr(final_result, "stop_reason", "?") if final_result else "?"
    print(f"[synth] agent done stop_reason={stop_reason} cost=${cost_usd:.4f}", flush=True)

    # Locate the produced file
    skill_path = _find_produced_skill(scratch)
    if skill_path is None:
        py_files = [p.name for p in scratch.iterdir() if p.suffix == ".py"]
        return {
            "ok": False,
            "error": f"agent didn't produce a unique skill file (found: {py_files})",
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

    # Independent smoke test (belt-and-suspenders — the agent should have done one too)
    smoke_ok, smoke_msg = _run_smoke_test(skill_path, scratch)
    if not smoke_ok:
        return {"ok": False, "error": f"smoke test failed: {smoke_msg}",
                "name": skill_name, "transcript": transcript, "cost_usd": cost_usd}

    # Don't clobber an existing skill silently
    final_path = SKILLS_DIR / f"{skill_name}.py"
    if final_path.exists():
        return {"ok": False, "error": f"skill {skill_name!r} already exists; refusing to overwrite",
                "name": skill_name, "transcript": transcript, "cost_usd": cost_usd}

    # Promote
    shutil.copy2(skill_path, final_path)
    print(f"[synth] promoted {skill_name} → {final_path}", flush=True)

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
