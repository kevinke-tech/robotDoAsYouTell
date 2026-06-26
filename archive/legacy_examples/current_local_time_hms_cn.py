"""一次性技能：获取当前本地时间（时分秒）并中文播报。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_local_time_hms_cn",
    "description": "获取当前本地时间并返回时分秒。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now().astimezone()
    hour = now.hour
    minute = now.minute
    second = now.second
    tz_name = now.tzname() or "未知时区"
    iso_time = now.isoformat(timespec="seconds")
    speak = f"现在是{hour}点{minute}分{second}秒。"
    render = (
        "来源: system_local_clock\n"
        "source_url: local://system/clock\n"
        f"获取时间: {iso_time}\n"
        f"时区: {tz_name}\n"
        f"关键字段: hour={hour}, minute={minute}, second={second}"
    )
    ui = {
        "type": "info_card",
        "title": "当前本地时间",
        "message": (
            f"{hour:02d}:{minute:02d}:{second:02d}\n"
            f"时区: {tz_name}\n"
            f"获取时间: {iso_time}"
        ),
    }
    return {"speak": speak, "render": render, "ui": ui}


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(test_mode=True))
    assert isinstance(result, dict)
    assert isinstance(result.get("speak"), str) and result["speak"].strip()
    assert isinstance(result.get("render"), str) and result["render"].strip()
    print("OK")
