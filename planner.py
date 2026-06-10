"""
Planner — single Claude vision call that picks one of four tools.

Inputs:
  - transcript (user's utterance after ASR)
  - image_b64  (optional camera JPEG, no data: prefix)
  - registry_summary (list from SkillRegistry.summary_for_planner)

Returns a dict like:
  {"_tool": "chat" | "call_skill" | "synthesize_one_shot" | "synthesize_background",
   "_input": <dict from the tool call>,
   "_meta": {"stop_reason": ..., "usage": {...}}}

Uses AsyncAnthropic and honors ANTHROPIC_BASE_URL (limtok proxy).
Does NOT send cache_control — proxy doesn't support cache reads (see
reference_anthropic_proxy.md / probe_proxy.py).
"""

import os
from typing import Optional

import anthropic

API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "claude-sonnet-4-6")

# ───── Tool definitions ───────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "chat",
        "description": (
            "Reply conversationally without taking any action. Use when no skill is "
            "needed and you can answer directly from what you see in the camera or "
            "from general knowledge. Examples: 'what is this?', 'how are you?', "
            "'describe what you see', '现在好像没什么人'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "speak": {
                    "type": "string",
                    "description": (
                        "The natural conversational reply. Spoken via TTS, so keep "
                        "it brief — 1-2 sentences, no markdown, no lists."
                    ),
                }
            },
            "required": ["speak"],
        },
    },
    {
        "name": "call_skill",
        "description": (
            "Invoke an existing skill from the registry shown in the system prompt. "
            "Only use names that appear there. Prefer this over synthesis whenever an "
            "existing skill matches the user's request."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exact skill name from the registry.",
                },
                "args": {
                    "type": "object",
                    "description": "Arguments dict. Pass {} if the skill needs none.",
                },
                "say_first": {
                    "type": "string",
                    "description": (
                        "Optional brief acknowledgement to speak BEFORE invoking the "
                        "skill (e.g., 'one moment'). Omit for instant skills."
                    ),
                },
            },
            "required": ["name", "args"],
        },
    },
    {
        "name": "synthesize_one_shot",
        "description": (
            "Request creation of a brand-new one-shot (request-response) skill. Use "
            "ONLY when no existing skill matches and the user's request is a single "
            "discrete action that completes and returns (e.g., 'open hacker news', "
            "'search for a Thai curry recipe', 'take a screenshot'). NOT for "
            "reminders, watchers, or anything ongoing — those use synthesize_background."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "spec": {
                    "type": "string",
                    "description": (
                        "Detailed natural-language description of what the new skill "
                        "should do, the inputs it needs, and the expected output. The "
                        "code-gen agent will use this verbatim."
                    ),
                },
                "say_first": {
                    "type": "string",
                    "description": "Optional brief reply spoken before synthesis kicks off.",
                },
            },
            "required": ["spec"],
        },
    },
    {
        "name": "synthesize_background",
        "description": (
            "Request creation of a new background skill that runs continuously or on "
            "a schedule and emits async output via TTS when it fires."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "trigger_kind": {
                    "type": "string",
                    "enum": ["timer", "vision"],
                    "description": (
                        "'timer' for time-based fires ('in 1 minute', 'every hour', "
                        "'at 3pm'). 'vision' for camera-triggered fires ('when you "
                        "see X', 'if I raise my hand')."
                    ),
                },
                "spec": {
                    "type": "string",
                    "description": (
                        "Detailed natural-language description. For timer: include "
                        "precise timing ('after 60 seconds', 'every 5 minutes'). "
                        "For vision: describe the visual condition to watch for. "
                        "Also describe what to say/do when it fires."
                    ),
                },
                "say_first": {
                    "type": "string",
                    "description": "Optional brief acknowledgement spoken before setup.",
                },
            },
            "required": ["trigger_kind", "spec"],
        },
    },
]


SYSTEM_TEMPLATE = """You are vox, a voice + vision assistant. The user speaks to you through their laptop microphone. You can see them and their environment through the laptop camera — a fresh frame is attached to each request when the camera is on.

Your job: decide what to do with each utterance, by calling exactly one of four tools.

EXISTING SKILLS (registry):
{registry_summary}

DECISION RULES (in priority order):

1. **Prefer call_skill whenever a registered skill matches.** Pay special attention to the GENERIC skills below — they cover most timer / watcher / lifecycle requests, so reach for synthesize_background only when nothing in the registry fits.

   Common routings:
   - "remind me in N seconds/minutes/hours to X" → call_skill(generic_timer, {{delay_seconds: ..., message: "X"}})
   - "in 5 minutes tell me to Y" → call_skill(generic_timer, ...)
   - "tell me when you see X" / "let me know if Y happens" / "watch for Z" → call_skill(generic_vision_watcher, {{trigger: "X precise", say_on_match: "..."}})
   - "what are you watching for" / "what reminders are active" / "list active" → call_skill(list_active, {{}})
   - "stop the pen watcher" / "cancel that reminder" / "forget about it" → call_skill(stop_active, {{identifier: "..."}})
   - "what time is it" / "现在几点" → call_skill(current_time, {{}})
   - "open <site>" / "go to <url>" / "navigate to X" / "open hacker news" → call_skill(open_url, {{url: "..."}}). For named sites, supply the obvious URL: hacker news → news.ycombinator.com, reddit → reddit.com, etc. If the user wants to "see" the page, add screenshot: true.

2. If the user's request is a SINGLE discrete action and nothing in the registry covers it → synthesize_one_shot.

3. If the user wants something ONGOING that the generic_timer / generic_vision_watcher cannot express (e.g., "every 5 minutes summarize my screen", "every hour at the top of the hour", complex compound conditions) → synthesize_background (trigger_kind=timer or vision).

4. Otherwise (questions, observations, small talk, "what do you see") → chat.

When synthesizing a skill that needs to drive a website (filling forms, scraping a page, searching, booking, posting), include in the spec: "Use `async with runtime.new_page() as page:` to drive a persistent Chromium browser (Playwright). The page is fresh; navigate via `await page.goto(url)`." This tells the synthesizer to write a browser-driven skill.

For trigger / say_on_match strings: be specific. "raises a hand" is too vague — write "a person raises their hand visibly to or above shoulder/head level" so the per-frame trigger checker can decide reliably.

The per-frame checker sees only ONE frame at a time and has no memory of previous frames. So write the trigger as a STATE the frame should match, not a transition.
- Presence triggers ("when you see X") → describe X as visible. e.g. "a mobile phone is clearly visible in the person's hand".
- Absence / disappearance triggers ("when X is no longer there", "when you don't see X anymore", "tell me if I leave", "提醒我杯子不在桌上了") → describe the NEGATIVE state directly. e.g. "no mobile phone is visible anywhere in the camera frame", "the desk surface in front of the camera has no cup on it", "the person who was sitting at the desk is no longer visible in frame". Do NOT phrase it as a change ("the cup just disappeared") — the checker can't see change, only one frame.

STYLE:
- Spoken replies are processed by TTS, so keep them brief (1-2 short sentences). No markdown, no lists.
- Match the user's language (English in / English out, Chinese in / Chinese out).
- Acknowledge what you see in the camera when it's relevant to the user's request, but don't narrate it unprompted.
"""


def _registry_summary_text(registry_summary: list[dict]) -> str:
    if not registry_summary:
        return "(no skills registered yet — only chat / synthesize_* available)"
    lines = []
    for s in registry_summary:
        kind = s.get("kind", "one_shot")
        name = s.get("name", "?")
        desc = s.get("description", "").strip()
        lines.append(f"- {name} ({kind}): {desc}")
    return "\n".join(lines)


def _build_system_prompt(registry_summary: list[dict]) -> str:
    return SYSTEM_TEMPLATE.format(registry_summary=_registry_summary_text(registry_summary))


def _build_user_content(transcript: str, image_b64: Optional[str]) -> list[dict]:
    blocks: list[dict] = []
    if image_b64:
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": image_b64,
            },
        })
    blocks.append({"type": "text", "text": f"User said: {transcript}"})
    return blocks


# ───── client (lazy singleton) ────────────────────────────────────────────────

_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set in .env.local — planner cannot run."
            )
        _client = anthropic.AsyncAnthropic(api_key=API_KEY, base_url=BASE_URL)
    return _client


# ───── main entry ─────────────────────────────────────────────────────────────


async def plan(
    transcript: str,
    image_b64: Optional[str],
    registry_summary: list[dict],
) -> dict:
    client = _get_client()
    system = _build_system_prompt(registry_summary)
    user_content = _build_user_content(transcript, image_b64)

    msg = await client.messages.create(
        model=PLANNER_MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        tools=TOOLS,
        tool_choice={"type": "any"},
    )

    tool_uses = [b for b in msg.content if b.type == "tool_use"]
    if not tool_uses:
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        # Should be rare with tool_choice="any". Treat as chat fallback.
        return {
            "_tool": "chat",
            "_input": {"speak": text or "I didn't catch that."},
            "_meta": {"fallback": True, "stop_reason": msg.stop_reason},
        }

    tu = tool_uses[0]
    return {
        "_tool": tu.name,
        "_input": dict(tu.input) if tu.input else {},
        "_meta": {
            "stop_reason": msg.stop_reason,
            "usage": {
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
            },
        },
    }
