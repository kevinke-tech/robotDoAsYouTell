"""
Globals shared between the server and skills loaded from skills/.

Skills must `import runtime` (NOT `from runtime import RUNNER`) so they pick up
the value set at server startup time, not the initial None.
"""

import contextvars
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional

# Set by server.py at startup.
RUNNER: Optional[Any] = None              # background.BackgroundRunner
OUTPUT_BROADCAST: Optional[Callable] = None  # async (dict) -> None — pushes to all /ws/output clients
BROWSER: Optional[Any] = None             # browser.BrowserHost — lazy-launches Chromium on first new_page()

# Tracks which skill is currently executing, so BackgroundRunner.add_*() calls
# made inside the skill can attribute new active instances back to it.
_CURRENT_SKILL: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "vox_current_skill", default=None
)


def get_current_skill() -> Optional[str]:
    return _CURRENT_SKILL.get()


def set_current_skill(name: Optional[str]) -> contextvars.Token:
    return _CURRENT_SKILL.set(name)


def reset_current_skill(token: contextvars.Token) -> None:
    _CURRENT_SKILL.reset(token)


@asynccontextmanager
async def new_page():
    """Skill-facing helper: `async with runtime.new_page() as page: ...`.

    Yields a fresh Playwright page on the shared BrowserContext. Closes on exit.
    """
    if BROWSER is None:
        raise RuntimeError("BrowserHost is not initialized — server must set runtime.BROWSER")
    async with BROWSER.new_page() as page:
        yield page
