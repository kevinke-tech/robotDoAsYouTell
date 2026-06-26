"""一次性技能：返回当前本地时间的中文口语描述。"""
from datetime import datetime


RUN_SPEC = {
    "name": "current_local_time_spoken_cn",
    "description": "获取当前本地时间并用中文清晰报告。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _to_cn_phrase(now: datetime) -> str:
    hour = now.hour
    minute = now.minute
    if 0 <= hour < 6:
        period, h12 = "凌晨", (12 if hour == 0 else hour)
    elif 6 <= hour < 12:
        period, h12 = "上午", hour
    elif hour == 12:
        period, h12 = "中午", 12
    elif 13 <= hour < 18:
        period, h12 = "下午", hour - 12
    else:
        period, h12 = "晚上", hour - 12
    return f"现在是{period}{h12}点{minute:02d}分"


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        phrase = _to_cn_phrase(now)
        iso_time = now.isoformat()
        tz_name = str(now.tzinfo or "local")
        render = (
            f"{phrase}\n"
            f"source: system_local_clock\n"
            f"evidence: iso_time={iso_time}, timezone={tz_name}"
        )
        return {
            "speak": phrase,
            "render": render,
            "ui": {"type": "info_card", "title": "当前本地时间", "message": phrase},
        }
    except Exception as e:
        reason = str(e) or "unknown_error"
        return {
            "speak": "抱歉，我暂时没法读取当前时间。",
            "render": f"source: system_local_clock\nevidence: failure_reason={reason}",
            "ui": {"type": "info_card", "title": "时间读取失败", "message": f"失败原因: {reason}"},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    print("OK")
