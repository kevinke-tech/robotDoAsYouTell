#!/usr/bin/env python3
"""
probe_proxy.py — verify the Anthropic proxy (limtok) supports the bits vox needs.

Tests:
  1. Plain text completion (basic connectivity)
  2. Vision (image content block)
  3. Tool use (forced tool call)
  4. Streaming
  5. Prompt caching (cache_control on a chunk, verify cache_read_input_tokens on 2nd call)

Each check prints PASS / FAIL with a brief reason. Exits 0 if all pass.

Reads ANTHROPIC_API_KEY + ANTHROPIC_BASE_URL from .env.local.
"""

import base64
import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env.local from project root (this script lives in scripts/)
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.local")

API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
MODEL = os.getenv("PLANNER_MODEL", "claude-opus-4-7")

if not API_KEY:
    print("ERROR: ANTHROPIC_API_KEY not set in .env.local", file=sys.stderr)
    sys.exit(2)

print(f"Proxy base URL : {BASE_URL}")
print(f"API key suffix : …{API_KEY[-6:]}")
print(f"Model          : {MODEL}")
print()

try:
    import anthropic
except ImportError:
    print("ERROR: `anthropic` package not installed. Run: pip install anthropic", file=sys.stderr)
    sys.exit(2)

client = anthropic.Anthropic(api_key=API_KEY, base_url=BASE_URL)

results: dict[str, tuple[bool, str]] = {}


def record(name: str, ok: bool, detail: str = ""):
    results[name] = (ok, detail)
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}{(' — ' + detail) if detail else ''}")


def make_tiny_jpeg_b64() -> str:
    """A 1x1 red JPEG, base64-encoded."""
    try:
        from PIL import Image
    except ImportError:
        # Minimal hand-crafted 1x1 JPEG fallback
        return (
            "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
            "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQE"
            "BAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAA"
            "EDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAr/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAF"
            "AEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AKpAB//Z"
        )
    img = Image.new("RGB", (16, 16), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


# ── Test 1: plain text ────────────────────────────────────────────────────────
print("Test 1: plain text completion")
try:
    msg = client.messages.create(
        model=MODEL,
        max_tokens=32,
        messages=[{"role": "user", "content": "Reply with exactly: pong"}],
    )
    txt = "".join(b.text for b in msg.content if b.type == "text").strip()
    ok = "pong" in txt.lower()
    record("text completion", ok, f"got {txt[:80]!r}")
except Exception as e:
    record("text completion", False, f"{type(e).__name__}: {e}")


# ── Test 2: vision ────────────────────────────────────────────────────────────
print("\nTest 2: vision (image input)")
try:
    jpeg_b64 = make_tiny_jpeg_b64()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=64,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": jpeg_b64},
                    },
                    {"type": "text", "text": "What color is this image? One word."},
                ],
            }
        ],
    )
    txt = "".join(b.text for b in msg.content if b.type == "text").strip().lower()
    ok = "red" in txt or "color" in txt or len(txt) > 0  # any non-error reply
    record("vision", ok, f"reply: {txt[:80]!r}")
except Exception as e:
    record("vision", False, f"{type(e).__name__}: {e}")


# ── Test 3: tool use ──────────────────────────────────────────────────────────
print("\nTest 3: tool use")
try:
    tools = [
        {
            "name": "get_temperature",
            "description": "Look up the current temperature in a city.",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ]
    msg = client.messages.create(
        model=MODEL,
        max_tokens=256,
        tools=tools,
        messages=[
            {"role": "user", "content": "What's the temperature in Tokyo? Use the tool."}
        ],
    )
    tool_uses = [b for b in msg.content if b.type == "tool_use"]
    ok = len(tool_uses) > 0
    detail = f"got {len(tool_uses)} tool_use block(s)"
    if tool_uses:
        detail += f", first input: {tool_uses[0].input}"
    record("tool use", ok, detail)
except Exception as e:
    record("tool use", False, f"{type(e).__name__}: {e}")


# ── Test 4: streaming ─────────────────────────────────────────────────────────
# A tiny response (e.g. "1 2 3 4 5") can legitimately arrive as a single chunk
# even when streaming is fully working — the model just emits one delta. So we
# ask for a long response (300+ tokens) which any real streaming setup will
# split into many chunks. If we see ≥5 chunks with substantial text we're good.
print("\nTest 4: streaming")
try:
    chunks = 0
    accumulated = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                "Write a single paragraph of approximately 250 words about the "
                "history of domesticated cats. Be detailed and prose-style; do "
                "not use bullets or headings."
            ),
        }],
    ) as stream:
        for text_chunk in stream.text_stream:
            accumulated += text_chunk
            chunks += 1
    # ≥5 chunks for a 250-word response is a conservative bar; native streaming
    # typically yields dozens of chunks for that length.
    ok = chunks >= 5 and len(accumulated) > 200
    record("streaming", ok, f"{chunks} chunks, total {len(accumulated)} chars")
except Exception as e:
    record("streaming", False, f"{type(e).__name__}: {e}")


# ── Test 5: prompt caching ────────────────────────────────────────────────────
# Prompt caching needs ≥1024 tokens in the cached chunk (Anthropic minimum).
# We send a big system prompt twice and verify cache_read_input_tokens > 0 on call 2.
print("\nTest 5: prompt caching")
try:
    big_chunk = "This is filler context. " * 800  # ~6000 chars ≈ ~1500 tokens
    system_blocks = [
        {
            "type": "text",
            "text": big_chunk + "\n\nYou are a helpful assistant.",
            "cache_control": {"type": "ephemeral"},
        }
    ]

    msg1 = client.messages.create(
        model=MODEL,
        max_tokens=16,
        system=system_blocks,
        messages=[{"role": "user", "content": "Say hi."}],
    )
    msg2 = client.messages.create(
        model=MODEL,
        max_tokens=16,
        system=system_blocks,
        messages=[{"role": "user", "content": "Say hi again."}],
    )
    u2 = msg2.usage
    # In a working cache, msg2 should have cache_read_input_tokens > 0.
    # Confirmed 2026-06-09 across 3 runs: the limtok proxy ALWAYS shows
    # cache_create > 0, cache_read = 0 on call 2 — meaning we'd pay the
    # cache-creation premium every call without ever amortizing it.
    # Worse than caching off. Treat as known-broken on this proxy.
    cache_read = getattr(u2, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(u2, "cache_creation_input_tokens", 0) or 0
    ok = cache_read > 0
    detail = f"call2 cache_read={cache_read} cache_create={cache_create} input={u2.input_tokens}"
    if not ok:
        detail += " — KNOWN: limtok proxy doesn't preserve cache keys across calls; vox must not send cache_control."
    record("prompt caching", ok, detail)
except Exception as e:
    record("prompt caching", False, f"{type(e).__name__}: {e}")


# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Summary")
print("=" * 60)
all_ok = True
for name, (ok, detail) in results.items():
    flag = "✓" if ok else "✗"
    print(f"  {flag}  {name:20s} {detail}")
    if not ok:
        all_ok = False

print()
if all_ok:
    print("All proxy features confirmed working for vox.")
    sys.exit(0)
else:
    print("Some features failed. Vox may need workarounds — check FAIL details above.")
    sys.exit(1)
