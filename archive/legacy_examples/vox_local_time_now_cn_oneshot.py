"""一次性技能：获取当前本地时间并中文播报。"""
from datetime import datetime

RUN_SPEC = {
    "name": "vox_local_time_now_cn_oneshot",
    "description": "获取当前本地时间并返回中文播报。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _cn_time_phrase(now: datetime) -> str:
    hour = now.hour
    minute = now.minute
    if hour < 6:
        period = "凌晨"
    elif hour < 12:
        period = "上午"
    elif hour < 18:
        period = "下午"
    else:
        period = "晚上"
    hour12 = hour % 12 or 12
    return f"现在是{period}{hour12}点{minute}分"


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        phrase = _cn_time_phrase(now)
        tz = now.tzname() or "local"
        return {
            "speak": phrase,
            "render": (
                f"{phrase}\n"
                "source: system_local_clock\n"
                f"evidence: iso_local={now.isoformat()} timezone={tz}"
            ),
            "ui": {"type": "info_card", "title": "本地时间", "message": phrase},
        }
    except Exception as e:
        return {
            "speak": "抱歉，我现在没法读取本地时间。",
            "render": (
                "读取本地时间失败。\n"
                "source: system_local_clock\n"
                f"evidence: error={type(e).__name__}: {e}"
            ),
            "ui": {"type": "info_card", "title": "本地时间", "message": "读取失败，请稍后重试。"},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(test_mode=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert isinstance(result["speak"], str) and isinstance(result["render"], str)
    print("OK")
