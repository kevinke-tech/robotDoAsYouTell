"""一次性技能：获取当前本地日期与时间（中文）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "local_time_date_cn",
    "description": "获取当前本地时间并清晰展示日期与时分秒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "style": {"type": "string", "enum": ["short", "full"], "default": "full"},
        },
        "required": [],
    },
}


async def run(style: str = "full", **kwargs):
    now = datetime.now().astimezone()
    date_text = now.strftime("%Y-%m-%d")
    time_text = now.strftime("%H:%M:%S")
    weekday_map = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday_text = weekday_map[now.weekday()]
    tz_text = now.tzname() or "本地时区"
    iso_text = now.isoformat(timespec="seconds")

    if style == "short":
        message = f"{date_text} {time_text}"
    else:
        message = f"{date_text} {weekday_text} {time_text}（{tz_text}）"

    return {
        "speak": f"现在是{time_text}，今天是{date_text}。",
        "render": (
            "来源: system_local_clock\n"
            "source_url: N/A\n"
            f"observed_iso: {iso_text}\n"
            f"date: {date_text}\n"
            f"time: {time_text}\n"
            f"weekday: {weekday_text}\n"
            f"timezone: {tz_text}\n"
            f"结果: {message}"
        ),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": message,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(style="full"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
