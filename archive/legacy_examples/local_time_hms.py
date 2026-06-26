"""一次性技能：获取当前本地时间（时分秒）。"""
from datetime import datetime


RUN_SPEC = {
    "name": "local_time_hms",
    "description": "获取当前本地时间并返回时分秒字符串。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now().astimezone()
    time_text = now.strftime("%H:%M:%S")
    iso_text = now.isoformat(timespec="seconds")
    tz_name = str(now.tzname() or "local")
    return {
        "speak": f"现在时间是{time_text}。",
        "render": (
            f"当前本地时间: {time_text}\n"
            f"来源: system_local_clock\n"
            f"时间戳: {iso_text}\n"
            f"时区: {tz_name}"
        ),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": f"{time_text}（{tz_name}）",
            "source": "system_local_clock",
            "source_time": iso_text,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
