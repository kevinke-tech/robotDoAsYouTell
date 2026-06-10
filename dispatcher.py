"""
Skill registry + one-shot runner.

A "skill" is a Python file in skills/ that exports either:
  - RUN_SPEC dict + async def run(**kwargs)              → one-shot
  - WATCH_SPEC dict + async def on_match(frame, **kwargs)→ background (phase 4)

The registry scans skills/ at startup, indexes each, and exposes:
  - summary_for_planner() — list of {name, description, kind} sent to Claude
  - get(name) — fetch a loaded skill's spec/module/kind
  - run_one_shot(name, args) — invoke an async run() with timeout + error capture
"""

import asyncio
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any

import runtime

SKILLS_DIR = Path(__file__).parent / "skills"
SKILL_RUN_TIMEOUT_SEC = 30.0


class SkillRegistry:
    def __init__(self) -> None:
        self.skills: dict[str, dict] = {}

    def load_all(self) -> dict[str, dict]:
        self.skills = {}
        if not SKILLS_DIR.exists():
            return self.skills

        for f in sorted(SKILLS_DIR.glob("*.py")):
            if f.name == "__init__.py" or f.name.startswith("_"):
                continue
            mod_name = f"vox_skills_{f.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, f)
            if spec is None or spec.loader is None:
                print(f"[registry] cannot load spec for {f.name}", flush=True)
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                print(f"[registry] failed to import {f.name}: {e}", flush=True)
                continue

            run_spec = getattr(module, "RUN_SPEC", None)
            if run_spec and hasattr(module, "run"):
                name = run_spec.get("name") or f.stem
                self.skills[name] = {
                    "kind": "one_shot",
                    "spec": run_spec,
                    "module": module,
                }
                print(f"[registry] loaded one-shot skill: {name}", flush=True)
                continue

            watch_spec = getattr(module, "WATCH_SPEC", None)
            if watch_spec and hasattr(module, "on_match"):
                name = watch_spec.get("name") or f.stem
                self.skills[name] = {
                    "kind": "background",
                    "spec": watch_spec,
                    "module": module,
                }
                print(f"[registry] loaded background skill: {name}", flush=True)
                continue

            print(f"[registry] skipped {f.name}: no RUN_SPEC/WATCH_SPEC + matching fn", flush=True)

        print(f"[registry] {len(self.skills)} skill(s) loaded", flush=True)
        return self.skills

    def summary_for_planner(self) -> list[dict]:
        return [
            {
                "name": name,
                "description": info["spec"].get("description", ""),
                "kind": info["kind"],
                "args_schema": info["spec"].get("args_schema", {}),
            }
            for name, info in self.skills.items()
        ]

    def get(self, name: str) -> dict | None:
        return self.skills.get(name)


async def run_one_shot(registry: SkillRegistry, name: str, args: dict[str, Any]) -> dict:
    """Invoke a one-shot skill. Returns {ok, result|error}."""
    info = registry.get(name)
    if info is None:
        return {"ok": False, "error": f"unknown skill: {name}"}
    if info["kind"] != "one_shot":
        return {"ok": False, "error": f"skill '{name}' is not a one-shot skill"}

    run_fn = info["module"].run
    args = args or {}

    token = runtime.set_current_skill(name)
    try:
        if inspect.iscoroutinefunction(run_fn):
            coro = run_fn(**args)
        else:
            coro = asyncio.to_thread(run_fn, **args)
        result = await asyncio.wait_for(coro, timeout=SKILL_RUN_TIMEOUT_SEC)
        return {"ok": True, "result": result}
    except asyncio.TimeoutError:
        return {"ok": False, "error": f"skill timeout (>{SKILL_RUN_TIMEOUT_SEC:.0f}s)"}
    except TypeError as e:
        return {"ok": False, "error": f"bad args: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        runtime.reset_current_skill(token)
