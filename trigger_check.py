"""
Per-frame trigger-match check via Claude vision.

Called from BackgroundRunner.evaluate_frame() after the pHash filter passes.
Uses a single tool with a boolean output so the model can't wander off in prose.
"""

import os
from typing import Optional

import anthropic

API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
TRIGGER_MODEL = os.getenv("TRIGGER_MODEL", "claude-sonnet-4-6")

_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set — trigger checks cannot run.")
        _client = anthropic.AsyncAnthropic(api_key=API_KEY, base_url=BASE_URL)
    return _client


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


async def check(frame_jpeg_b64: str, trigger: str) -> tuple[bool, str]:
    """Return (is_match, reason). On API error, returns (False, error_string)."""
    client = _get_client()
    try:
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
    except Exception as e:
        return False, f"api error: {type(e).__name__}: {e}"

    for block in msg.content:
        if block.type == "tool_use" and block.name == "match":
            inp = dict(block.input) if block.input else {}
            return bool(inp.get("is_match", False)), str(inp.get("reason", ""))

    return False, "no tool_use block in response"
