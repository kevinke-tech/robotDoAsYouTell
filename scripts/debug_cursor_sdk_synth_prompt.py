from __future__ import annotations

import tempfile
from pathlib import Path
import sys

from dotenv import load_dotenv
from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import synthesizer


SPEC = (
    "Create a one-shot video skill that returns a generative ephemeral UI player for immediate playback. "
    "Use query='funny video' and retrieve a directly playable video URL (mp4/webm/m3u8) via API/httpx or hidden/headless fetch. "
    "Return speak/render plus ui dict: {type:'video_player', title, video_title, video_url, autoplay:true, loop:false, source, source_url, query}. "
    "Do NOT return a link-list UI (such as video_list). Do NOT require user to open a website manually. "
    "Do NOT open visible browser windows for playback. If no directly playable media is found, return a clear error with evidence."
)


def main() -> int:
    load_dotenv(".env.local")
    import os

    api_key = (os.getenv("CURSOR_API_KEY") or "").strip()
    model = (os.getenv("SYNTHESIZER_CURSOR_MODEL") or "auto").strip()
    if not api_key:
        print("ERR: CURSOR_API_KEY missing")
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="cursor-sdk-synth-"))
    prompt = (
        synthesizer._build_system_prompt("one_shot", SPEC)
        + "\n\n用户需求（再次给出，确保不遗漏）:\n"
        + SPEC
        + "\n\n记住：你的最后一条消息必须是 SYNTHESIS_COMPLETE <filename>.py"
    )

    print(f"tmp={tmp}")
    agent = Agent.create(
        AgentOptions(
            api_key=api_key,
            model=model,
            local=LocalAgentOptions(cwd=str(tmp)),
            mode="agent",
        )
    )
    try:
        run = agent.send(prompt)
        counts: dict[str, int] = {}
        for msg in run.messages():
            t = str(getattr(msg, "type", "?"))
            counts[t] = counts.get(t, 0) + 1
        result = run.wait()
        status = getattr(result, "status", "?")
        text = str(getattr(result, "result", "") or "")
        print(f"RUN status={status}")
        print(f"RUN text_head={text[:240]!r}")
        print(f"COUNTS={counts}")
    finally:
        agent.close()

    files = sorted([p.name for p in tmp.iterdir() if p.is_file()])
    print(f"FILES={files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
