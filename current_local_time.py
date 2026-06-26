"""返回当前本地时间的一次性技能。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_local_time",
    "description": "获取当前本地时间并用中文返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now()
    text = f"现在是{now.hour:02d}点{now.minute:02d}分"
    iso_local = now.astimezone().isoformat(timespec="seconds")
    return {
        "speak": text,
        "render": f"{text}\nsource: system_local_clock\nevidence: local_iso_time={iso_local}",
        "ui": {
            "type": "info_card",
            "title": "本地时间",
            "message": text,
            "source": "system_local_clock",
        },
    }


if __name__ == "__main__":
    import asyncio
    import re

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    assert re.match(r"^现在是\d{2}点\d{2}分$", result["speak"])
    assert "source:" in result["render"] or "evidence:" in result["render"]
    print("OK")
