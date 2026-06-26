"""
Planner — single Claude vision call that picks one tool.

Inputs:
  - transcript (user's utterance after ASR)
  - image_b64  (optional camera JPEG, no data: prefix)
  - registry_summary (list from SkillRegistry.summary_for_planner)

Returns a dict like:
  {"_tool": "chat" | "call_skill" | "synthesize_one_shot" | "synthesize_background" | "dispatch_actions",
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
VOX_DEPLOY_REGION = os.getenv("VOX_DEPLOY_REGION", "CN").strip().upper() or "CN"
VOX_PRIMARY_LOCALE = os.getenv("VOX_PRIMARY_LOCALE", "zh-CN")

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
                },
                "tts": {
                    "type": "object",
                    "description": (
                        "Optional TTS overrides when user explicitly requests a speaking style. "
                        "Supported keys: voice_type (string), speed_ratio (number), "
                        "pitch_ratio (number), volume_ratio (number)."
                    ),
                    "properties": {
                        "voice_type": {"type": "string"},
                        "speed_ratio": {"type": "number"},
                        "pitch_ratio": {"type": "number"},
                        "volume_ratio": {"type": "number"},
                    },
                },
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
                "outcome_contract": {
                    "type": "object",
                    "description": (
                        "Structured completion contract used by runtime validation. "
                        "delivery: auto|interactive|informational. "
                        "fulfillment_mode: auto|task_completion|address_lookup|background_ack. "
                        "requires_ui_delivery: bool (optional). "
                        "require_playable_media: bool (optional). "
                        "require_visual_media: bool (optional). "
                        "explicit_min_count: int (optional, only when user explicitly asks quantity). "
                        "checks: list from {non_empty_output, ui_present, evidence_present, not_link_only, not_placeholder_output}. "
                        "notes: optional short rationale."
                    ),
                    "properties": {
                        "delivery": {"type": "string"},
                        "fulfillment_mode": {"type": "string"},
                        "requires_ui_delivery": {"type": "boolean"},
                        "require_playable_media": {"type": "boolean"},
                        "require_visual_media": {"type": "boolean"},
                        "explicit_min_count": {"type": "integer"},
                        "checks": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": "string"},
                    },
                },
            },
            "required": ["spec", "outcome_contract"],
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
                "outcome_contract": {
                    "type": "object",
                    "description": (
                        "Structured completion contract used by runtime validation. "
                        "delivery: auto|interactive|informational. "
                        "fulfillment_mode: auto|task_completion|address_lookup|background_ack. "
                        "requires_ui_delivery: bool (optional). "
                        "require_playable_media: bool (optional). "
                        "require_visual_media: bool (optional). "
                        "explicit_min_count: int (optional, only when user explicitly asks quantity). "
                        "checks: list from {non_empty_output, ui_present, evidence_present, not_link_only, not_placeholder_output}. "
                        "notes: optional short rationale."
                    ),
                    "properties": {
                        "delivery": {"type": "string"},
                        "fulfillment_mode": {"type": "string"},
                        "requires_ui_delivery": {"type": "boolean"},
                        "require_playable_media": {"type": "boolean"},
                        "require_visual_media": {"type": "boolean"},
                        "explicit_min_count": {"type": "integer"},
                        "checks": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": "string"},
                    },
                },
            },
            "required": ["trigger_kind", "spec", "outcome_contract"],
        },
    },
    {
        "name": "dispatch_actions",
        "description": (
            "Plan and return an ordered list of actions when ONE user utterance "
            "contains MULTIPLE tasks that should all be carried out. Each action "
            "can be one of: call_skill / synthesize_one_shot / synthesize_background / ask_user / branch."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "say_first": {
                    "type": "string",
                    "description": "Optional short acknowledgement spoken before the queue starts.",
                },
                "actions": {
                    "type": "array",
                    "description": "Ordered action queue. Keep order exactly as the user intended.",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "action_type": {
                                "type": "string",
                                "enum": [
                                    "call_skill",
                                    "synthesize_one_shot",
                                    "synthesize_background",
                                    "ask_user",
                                    "branch",
                                ],
                            },
                            "name": {"type": "string"},
                            "args": {"type": "object"},
                            "spec": {"type": "string"},
                            "trigger_kind": {
                                "type": "string",
                                "enum": ["timer", "vision"],
                            },
                            "say_first": {"type": "string"},
                            "outcome_contract": {
                                "type": "object",
                                "properties": {
                                    "delivery": {"type": "string"},
                                    "fulfillment_mode": {"type": "string"},
                                    "requires_ui_delivery": {"type": "boolean"},
                                    "require_playable_media": {"type": "boolean"},
                                    "require_visual_media": {"type": "boolean"},
                                    "explicit_min_count": {"type": "integer"},
                                    "checks": {"type": "array", "items": {"type": "string"}},
                                    "notes": {"type": "string"},
                                },
                            },
                            "save_as": {
                                "type": "string",
                                "description": "Optional variable name to store this action's output for later actions.",
                            },
                            "slot": {
                                "type": "string",
                                "description": "For ask_user: slot key to save user's next reply into.",
                            },
                            "question": {
                                "type": "string",
                                "description": "For ask_user: question to ask user.",
                            },
                            "left": {
                                "description": "For branch: left operand, often {{vars.xxx}} or {{slots.xxx}}.",
                            },
                            "source": {
                                "type": "string",
                                "description": "For branch: fallback context path such as vars.weather.status.",
                            },
                            "op": {
                                "type": "string",
                                "enum": ["truthy", "eq", "ne", "in", "contains"],
                            },
                            "value": {
                                "description": "For branch: right operand for comparison.",
                            },
                            "then_actions": {
                                "type": "array",
                                "description": "For branch: actions when condition matches.",
                                "items": {"type": "object"},
                            },
                            "else_actions": {
                                "type": "array",
                                "description": "For branch: actions when condition does not match.",
                                "items": {"type": "object"},
                            },
                            "on_error": {
                                "type": "string",
                                "enum": ["continue", "stop"],
                            },
                        },
                        "required": ["action_type"],
                    },
                },
                "on_error": {
                    "type": "string",
                    "enum": ["continue", "stop"],
                    "description": (
                        "Queue-level fallback on first failure. "
                        "'continue' keeps executing later actions; "
                        "'stop' aborts the queue."
                    ),
                },
            },
            "required": ["actions"],
        },
    },
]


SYSTEM_TEMPLATE = """You are vox, a voice + vision assistant. The user speaks to you through their laptop microphone. You can see them and their environment through the laptop camera — a fresh frame is attached to each request when the camera is on.

Your job: decide what to do with each utterance, by calling exactly one tool.

EXISTING SKILLS (registry):
{registry_summary}

RUNTIME INTERACTION ASSUMPTIONS (STRICT):
- The user is in front of a computer that has speaker, camera, and screen.
- The user interacts with vox through a browser-based frontend.
- Default expectation: the task should be completed directly by vox in this conversation/UI without requiring extra manual operations on OS/browser/sites.
- Therefore, avoid guidance like "please click/open/select/operate in browser/computer" unless the user explicitly asks for manual control UX.

DEPLOYMENT CONTEXT (STRICT):
- Deploy region: {deploy_region}
- Primary user locale: {primary_locale}
- For external retrieval, prefer sources/endpoints that are reachable and stable in the deploy region.
- Avoid single-source dependency for factual/location/network tasks; plan with multi-source fallback.
- If one source is blocked/timeout/cert-failed/geo-failed, switch to alternate source path instead of ending early.

VOX SYSTEM MODEL (UNDERSTAND BEFORE PLANNING):
- vox is an execution system, not just a chatbot:
  - planner decides actions
  - server executes actions
  - synthesizer writes runnable skills
  - runtime executes skills
  - frontend renders ui cards + plays tts
- `synthesize_one_shot` means:
  - create a new runnable one-shot skill file
  - server immediately executes it once
  - runtime validates whether result actually fulfills intent
  - failed/placeholder/link-only outputs may trigger automatic repair synthesis
- `synthesize_background` means:
  - create a new background-capable skill
  - server immediately activates it
  - background behavior should be explicit (what to watch/when to trigger/what to do on trigger)
- Existing skills are real deployable units in registry, not examples.
- Planning quality is judged by whether the user gets usable final outcome in current session:
  - speak content
  - render content
  - actionable ui (when task is interactive)
  - evidence fields when information claims are made

DELIVERY THINKING MODEL:
- Plan from "user expected end state" backward.
- Your action choice should minimize semantic gap between user intent and final delivered experience.
- For interaction-heavy intents, think in terms of "result objects shown in UI" instead of "instructions for manual browser operation".
- When choosing between alternatives, prefer the one with clearer completion signal (user can directly see/hear/use the result).

DECISION RULES (in priority order):

1. **Dynamic creation first unless a clearly matching registered skill already exists.**
   - Use `call_skill` ONLY when the exact skill is present in the registry list above and clearly matches intent.
   - If the candidate skill name is not present in registry, NEVER call it; synthesize instead.
   - Prefer dynamic creation for new capabilities instead of assuming generic built-ins exist.

2. If the user's request is a SINGLE discrete action and no existing registry skill clearly covers it → `synthesize_one_shot`.

3. If the user wants something ONGOING (watch, remind, monitor, periodic checks, scene triggers) and no existing registry skill clearly covers it → `synthesize_background` (trigger_kind=timer or vision).

4. If the user asks for MULTIPLE actions in one utterance (e.g., "do A, then B, and also C"), use dispatch_actions and return an ordered queue of all actions. Do not drop any requested action.
   - For action_type=call_skill: include name + args; use save_as if later actions need its output.
   - For action_type=synthesize_one_shot: include spec + outcome_contract; use save_as if later actions need its output.
   - For action_type=synthesize_background: include trigger_kind + spec + outcome_contract.
   - For action_type=ask_user: include slot + question when required input is missing.
   - For action_type=branch: include condition (left/source + op + value) and then_actions/else_actions.
   - For errors, default to queue on_error=continue unless the user clearly asks to stop on first failure.
   - Keep each action minimal and executable; preserve user order.

MISSING INPUT SAFETY (STRICT):
- If required input is missing, ask the user first via action_type=ask_user.
- Store the user reply into a slot and reference the slot in subsequent actions.
- Never fabricate missing parameters from unrelated context.

FACTUAL EVIDENCE RULE (STRICT):
- Never present unverified conclusions before obtaining real data.
- For claims derived from retrieval/query/external tools, include source/evidence in outputs.
- If downstream actions depend on a factual result, run the fact-gathering step first and save_as its output.

INTENT PRESERVATION RULE (STRICT):
- Preserve the user's explicit request semantics and constraints.
- Do not inject new objectives, hidden assumptions, or unrelated rewrites.
- Do not downgrade fulfillment into tutorial/instructional responses when the user asked for direct completion.
- Do NOT invent quantitative constraints (counts/minimum numbers like "at least 6 images") unless the user explicitly asks for a number.

GENERATIVE UI RULE (STRICT):
- For interactive result tasks, prefer generated ephemeral UI outputs over raw link dumps.
- Avoid planning visible-browser manual-click workflows unless the user explicitly asks for that UX.
- Specs should request evidence-bearing outputs (source/source_url/key fields) in render.

DIRECT FULFILLMENT RULE (STRICT):
- Prefer plans that directly produce the end result in chat/UI/audio.
- "Return a link and ask user to handle it" is considered incomplete unless user explicitly requests links-only behavior.
- "Open a page and ask user to continue manually" is considered incomplete unless user explicitly requests manual browsing.

REAL-TIME / FACTUAL QUERY RULE (STRICT):
- For requests requiring current/real-time/factual data (time/date/weather/price/news/status), do not answer from memory-style chat.
- Prefer calling an existing skill that can retrieve/produce verifiable data.
- If no matching skill exists, synthesize one-shot and require evidence-bearing output.

OUTCOME CONTRACT RULE (STRICT):
- Every synthesize_* call MUST include outcome_contract.
- outcome_contract.delivery: auto | interactive | informational.
- outcome_contract.fulfillment_mode: auto | task_completion | address_lookup | background_ack.
- optional outcome_contract.requires_ui_delivery: true when user expects visible UI result.
- optional outcome_contract.require_playable_media: true for "play/watch/listen" intents.
- optional outcome_contract.require_visual_media: true for "show image/photo/picture" intents.
- optional outcome_contract.explicit_min_count: ONLY when user explicitly asked a count.
- outcome_contract.checks uses only:
  - non_empty_output
  - ui_present
  - evidence_present
  - not_link_only
  - not_placeholder_output
- If the user explicitly asks for a URL/link/address, set fulfillment_mode=address_lookup (link-only may be valid).
- For execution/consumption intents (play/watch/do/run), set fulfillment_mode=task_completion and include ui_present + not_link_only.
- For background acknowledgement, set fulfillment_mode=background_ack.

5. Otherwise (questions, observations, small talk, "what do you see") → chat.

When synthesizing a skill that needs website interaction (forms/scraping/search), prefer hidden/headless retrieval and generated UI outputs. Use visible browser-driving only when the task explicitly requires interactive page manipulation.

For trigger / say_on_match strings: be specific. "raises a hand" is too vague — write "a person raises their hand visibly to or above shoulder/head level" so the per-frame trigger checker can decide reliably.

The per-frame checker sees only ONE frame at a time and has no memory of previous frames. So write the trigger as a STATE the frame should match, not a transition.
- Presence triggers ("when you see X") → describe X as visible. e.g. "a mobile phone is clearly visible in the person's hand".
- Absence / disappearance triggers ("when X is no longer there", "when you don't see X anymore", "tell me if I leave", "提醒我杯子不在桌上了") → describe the NEGATIVE state directly. e.g. "no mobile phone is visible anywhere in the camera frame", "the desk surface in front of the camera has no cup on it", "the person who was sitting at the desk is no longer visible in frame". Do NOT phrase it as a change ("the cup just disappeared") — the checker can't see change, only one frame.

STYLE:
- Spoken replies are processed by TTS, so keep them brief (1-2 short sentences). No markdown, no lists.
- Match the user's language (English in / English out, Chinese in / Chinese out).
- Acknowledge what you see in the camera when it's relevant to the user's request, but don't narrate it unprompted.
- If the user explicitly asks for a voice style/tempo/tone, include `chat.tts` overrides.
- Do not invent TTS style overrides unless the user explicitly asks.
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
    return SYSTEM_TEMPLATE.format(
        registry_summary=_registry_summary_text(registry_summary),
        deploy_region=VOX_DEPLOY_REGION,
        primary_locale=VOX_PRIMARY_LOCALE,
    )


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
