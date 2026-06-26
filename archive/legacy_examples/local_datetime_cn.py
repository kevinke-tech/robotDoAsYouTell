"""一次性技能：返回当前本地时间与日期（中文）。"""
from datetime import datetime


RUN_SPEC = {
    "name": "local_datetime_cn",
    "description": "获取当前本地时间并返回中文时间卡片。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _weekday_cn(weekday: int) -> str:
    names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return names[weekday] if 0 <= weekday < 7 else ""


async def run(**kwargs):
    now = datetime.now().astimezone()
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")
    weekday_str = _weekday_cn(now.weekday())
    tz_name = now.tzname() or "local"
    tz_offset = now.strftime("%z")
    human = f"{date_str} {weekday_str} {time_str}"
    return {
        "speak": f"现在是{time_str}，今天是{date_str}{weekday_str}。",
        "render": (
            f"当前本地时间: {time_str}\n"
            f"当前日期: {date_str} {weekday_str}\n"
            f"source: system_local_clock\n"
            f"evidence: timezone={tz_name}, offset={tz_offset}, iso={now.isoformat()}"
        ),
        "ui": {
            "type": "info_card",
            "title": "本地时间",
            "message": human,
            "source": "system_local_clock",
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
