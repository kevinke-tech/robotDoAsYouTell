from __future__ import annotations

import tempfile
from pathlib import Path

from dotenv import load_dotenv
from cursor_sdk import Agent, AgentOptions, LocalAgentOptions


def main() -> int:
    load_dotenv(".env.local")
    import os

    api_key = (os.getenv("CURSOR_API_KEY") or "").strip()
    model = (os.getenv("SYNTHESIZER_CURSOR_MODEL") or "auto").strip()
    if not api_key:
        print("ERR: CURSOR_API_KEY missing")
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="cursor-sdk-write-"))
    prompt = (
        "Write exactly one python file named probe_skill.py in current cwd. "
        "File content must define RUN_SPEC with name 'probe_skill' and async run(**kwargs) "
        "returning {'speak':'ok','render':'ok'}. Include __main__ that prints OK. "
        "After writing file, reply exactly: SYNTHESIS_COMPLETE probe_skill.py"
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
        tool_uses = 0
        assistant_msgs = 0
        for msg in run.messages():
            t = getattr(msg, "type", "?")
            if t == "tool_use":
                tool_uses += 1
            if t == "assistant":
                assistant_msgs += 1
            print(f"MSG type={t}")
        result = run.wait()
        status = getattr(result, "status", "?")
        text = str(getattr(result, "result", "") or "")
        print(f"RUN status={status}")
        print(f"RUN text_head={text[:200]!r}")
        print(f"assistant_msgs={assistant_msgs} tool_uses={tool_uses}")
    finally:
        agent.close()

    files = sorted([p.name for p in tmp.iterdir() if p.is_file()])
    print(f"FILES={files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
