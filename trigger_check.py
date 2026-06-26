"""
Per-frame trigger-match check via a vision model.

Called from BackgroundRunner.evaluate_frame() after the pHash filter passes.

Backends (TRIGGER_BACKEND):
  - anthropic (default): Claude via Anthropic SDK + tool_use
  - bicv: company OpenAI-compatible server (Qwen3-VL, etc.)
"""

import json
import os
import re
from typing import Any, Optional

import anthropic
import httpx

API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
TRIGGER_BACKEND = os.getenv("TRIGGER_BACKEND", "anthropic").strip().lower()
TRIGGER_MODEL = os.getenv("TRIGGER_MODEL", "claude-sonnet-4-6")

TRIGGER_BICV_BASE_URL = os.getenv(
    "TRIGGER_BICV_BASE_URL",
    "http://192.168.125.91:30080/v1/chat/completions",
)
TRIGGER_BICV_MODEL = os.getenv(
    "TRIGGER_BICV_MODEL",
    "/huggingface/models/Qwen/Qwen3-VL-4B-Instruct",
)
TRIGGER_BICV_MAX_TOKENS = int(os.getenv("TRIGGER_BICV_MAX_TOKENS", "128"))
TRIGGER_BICV_API_KEY = os.getenv("TRIGGER_BICV_API_KEY", "")
TRIGGER_BICV_TIMEOUT_SEC = float(os.getenv("TRIGGER_BICV_TIMEOUT_SEC", "30"))

_client: Optional[anthropic.AsyncAnthropic] = None
_http_client: Optional[httpx.AsyncClient] = None


def backend_label() -> str:
    if TRIGGER_BACKEND == "bicv":
        return f"bicv ({TRIGGER_BICV_MODEL})"
    return f"anthropic ({TRIGGER_MODEL})"


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set — trigger checks cannot run.")
        _client = anthropic.AsyncAnthropic(api_key=API_KEY, base_url=BASE_URL)
    return _client


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=TRIGGER_BICV_TIMEOUT_SEC)
    return _http_client


SYSTEM = (
    "You are a vision-trigger matcher. You will be shown a single camera frame "
    "and a description of a visual state the user wants you to watch for. Decide "
    "whether THIS frame matches that state description.\n\n"
    "The description may be either:\n"
    "  (a) a PRESENCE state — something is visible (e.g. 'a person is holding a "
    "      phone', 'the desk has a red cup on it').\n"
    "  (b) an ABSENCE state — something the user cares about is not visible "
    "      (e.g. 'no cup is on the desk', 'the person is no longer in frame', "
    "      'the phone is gone from the desk').\n\n"
    "Decision rules:\n"
    "- For PRESENCE states: return true only when the described thing is clearly "
    "  visible in the frame. If you are unsure, return false.\n"
    "- For ABSENCE states: return true when the described thing is NOT plainly "
    "  visible anywhere in the frame. Do NOT require certainty that it is gone "
    "  for good, is not just occluded, or is not just off-camera — the watcher "
    "  only sees this one frame, and 'not visible right now' is exactly what the "
    "  user is asking about. Only return false if you can actually see the thing.\n\n"
    "Always answer via the `match` tool; do not respond in prose."
)

BICV_SYSTEM = (
    SYSTEM.replace("Always answer via the `match` tool; do not respond in prose.", "")
    + "\nRespond with ONLY a JSON object on one line, no markdown:\n"
    '{"is_match": true|false, "reason": "one short sentence"}'
)

TOOLS = [
    {
        "name": "match",
        "description": "Report whether the camera frame matches the trigger.",
        "input_schema": {
            "type": "object",
            "properties": {
                "is_match": {
                    "type": "boolean",
                    "description": "True only if the frame clearly satisfies the trigger description.",
                },
                "reason": {
                    "type": "string",
                    "description": "One short sentence explaining the decision.",
                },
            },
            "required": ["is_match"],
        },
    }
]


def _parse_match_json(text: str) -> tuple[bool, str]:
    text = (text or "").strip()
    if not text:
        return False, "empty model response"

    candidates = [text]
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        candidates.insert(0, fence.group(1).strip())
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        candidates.insert(0, brace.group(0))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "is_match" in data:
            return bool(data.get("is_match", False)), str(data.get("reason", ""))

    return False, f"could not parse JSON from response: {text[:120]!r}"


async def _check_anthropic(frame_jpeg_b64: str, trigger: str) -> tuple[bool, str]:
    client = _get_client()
    msg = await client.messages.create(
        model=TRIGGER_MODEL,
        max_tokens=256,
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": frame_jpeg_b64,
                        },
                    },
                    {"type": "text", "text": f"Trigger: {trigger}"},
                ],
            }
        ],
        tools=TOOLS,
        tool_choice={"type": "tool", "name": "match"},
    )

    for block in msg.content:
        if block.type == "tool_use" and block.name == "match":
            inp = dict(block.input) if block.input else {}
            return bool(inp.get("is_match", False)), str(inp.get("reason", ""))

    return False, "no tool_use block in response"


async def _check_bicv(frame_jpeg_b64: str, trigger: str) -> tuple[bool, str]:
    payload: dict[str, Any] = {
        "model": TRIGGER_BICV_MODEL,
        "messages": [
            {"role": "system", "content": BICV_SYSTEM},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{frame_jpeg_b64}",
                        },
                    },
                    {"type": "text", "text": f"Trigger: {trigger}"},
                ],
            },
        ],
        "max_tokens": TRIGGER_BICV_MAX_TOKENS,
    }

    headers = {"Content-Type": "application/json"}
    if TRIGGER_BICV_API_KEY:
        headers["Authorization"] = f"Bearer {TRIGGER_BICV_API_KEY}"

    client = _get_http_client()
    resp = await client.post(TRIGGER_BICV_BASE_URL, headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()

    choices = data.get("choices") or []
    if not choices:
        return False, "bicv response missing choices"

    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        content = "".join(text_parts)

    return _parse_match_json(str(content))


async def check(frame_jpeg_b64: str, trigger: str) -> tuple[bool, str]:
    """Return (is_match, reason). On API error, returns (False, error_string)."""
    try:
        if TRIGGER_BACKEND == "bicv":
            return await _check_bicv(frame_jpeg_b64, trigger)
        if TRIGGER_BACKEND != "anthropic":
            return False, f"unknown TRIGGER_BACKEND: {TRIGGER_BACKEND!r}"
        return await _check_anthropic(frame_jpeg_b64, trigger)
    except Exception as e:
        return False, f"api error: {type(e).__name__}: {e}"
