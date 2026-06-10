"""
BrowserHost — owns the Playwright lifecycle for the lifetime of the server.

Lazy-launched on first use, shared across all skill invocations. One Chromium
process, one shared BrowserContext (shared cookie jar / viewport), per-skill
pages that close on context-manager exit.

Headed by default (so demos are visible). Falls back to headless on launch
failure (typical on WSL2 without WSLg). Force headless via env BROWSER_HEADLESS=true.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").lower() in ("1", "true", "yes")
BROWSER_VIEWPORT = {"width": 1280, "height": 800}
BROWSER_NEW_PAGE_TIMEOUT_MS = 30_000


class BrowserHost:
    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._context = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Idempotent. Launches Chromium + a shared context if not already running."""
        async with self._lock:
            if self._context is not None:
                return
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            launch_kwargs = {"headless": BROWSER_HEADLESS}
            try:
                self._browser = await self._pw.chromium.launch(**launch_kwargs)
                print(f"[browser] launched chromium (headless={BROWSER_HEADLESS})", flush=True)
            except Exception as e:
                if BROWSER_HEADLESS:
                    raise
                # Headed launch failed (likely WSL without display) — retry headless
                print(f"[browser] headed launch failed ({e}); retrying headless", flush=True)
                self._browser = await self._pw.chromium.launch(headless=True)
            self._context = await self._browser.new_context(viewport=BROWSER_VIEWPORT)
            self._context.set_default_timeout(BROWSER_NEW_PAGE_TIMEOUT_MS)
            print("[browser] shared context ready", flush=True)

    async def stop(self) -> None:
        async with self._lock:
            try:
                if self._context is not None:
                    await self._context.close()
            except Exception as e:
                print(f"[browser] context close error: {e}", flush=True)
            try:
                if self._browser is not None:
                    await self._browser.close()
            except Exception as e:
                print(f"[browser] browser close error: {e}", flush=True)
            try:
                if self._pw is not None:
                    await self._pw.stop()
            except Exception as e:
                print(f"[browser] playwright stop error: {e}", flush=True)
            self._context = self._browser = self._pw = None
            print("[browser] stopped", flush=True)

    def is_running(self) -> bool:
        return self._context is not None

    @asynccontextmanager
    async def new_page(self):
        """Yield a fresh page bound to the shared context. Closes on exit."""
        if self._context is None:
            await self.start()
        assert self._context is not None
        page = await self._context.new_page()
        try:
            yield page
        finally:
            try:
                await page.close()
            except Exception as e:
                print(f"[browser] page close error: {e}", flush=True)
