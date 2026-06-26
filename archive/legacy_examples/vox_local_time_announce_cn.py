"""一次性技能：获取并播报当前本地时间（中文）。"""
from datetime import datetime


RUN_SPEC = {
    "name": "vox_local_time_announce_cn",
    "description": "获取当前本地时间并用中文播报。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _period_cn(hour: int) -> str:
    if hour < 6:
        return "凌晨"
    if hour < 12:
        return "上午"
    if hour < 18:
        return "下午"
    return "晚上"


async def run(**kwargs):
    now = datetime.now().astimezone()
    hour_12 = now.hour % 12 or 12
    minute = now.minute
    spoken_time = f"{_period_cn(now.hour)}{hour_12}点{minute}分"
    clock_text = now.strftime("%Y-%m-%d %H:%M:%S")
    tz_name = now.tzname() or "local"
    return {
        "speak": f"现在是{spoken_time}。",
        "render": (
            f"当前时间字符串: {clock_text}\n"
            "source: system_local_clock\n"
            f"evidence: timezone={tz_name}, iso={now.isoformat(timespec='seconds')}"
        ),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": f"现在是{spoken_time}",
            "source": "system_local_clock",
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert isinstance(result.get("speak"), str) and result["speak"]
    assert isinstance(result.get("render"), str) and "source:" in result["render"]
    print("OK")
