"""一次性技能：返回当前本地时间的中文口语化描述。"""
from datetime import datetime


RUN_SPEC = {
    "name": "local_time_chinese",
    "description": "获取当前本地时间，并返回中文语音友好的时间描述。",
    "args_schema": {
        "type": "object",
        "properties": {
            "now_iso": {"type": "string", "description": "可选：用于测试的 ISO 时间字符串"},
        },
        "required": [],
    },
}

_DIGITS = "零一二三四五六七八九"


def _num_cn(n: int) -> str:
    if n < 10:
        return _DIGITS[n]
    if n < 20:
        return "十" if n == 10 else "十" + _DIGITS[n % 10]
    tens, ones = divmod(n, 10)
    return _DIGITS[tens] + "十" + (_DIGITS[ones] if ones else "")


def _to_spoken(dt: datetime) -> tuple[str, str]:
    hour = dt.hour
    minute = dt.minute
    if 0 <= hour < 6:
        period = "凌晨"
    elif hour < 12:
        period = "上午"
    elif hour < 13:
        period = "中午"
    elif hour < 18:
        period = "下午"
    else:
        period = "晚上"
    hour12 = hour % 12 or 12
    minute_text = "整" if minute == 0 else _num_cn(minute) + "分"
    sentence = f"现在是{period}{_num_cn(hour12)}点{minute_text}"
    return sentence, period


async def run(now_iso: str = "", **kwargs):
    dt = datetime.now() if not now_iso else datetime.fromisoformat(now_iso)
    sentence, period = _to_spoken(dt)
    return {
        "speak": sentence,
        "render": (
            "source: local_system_clock(datetime.now)\n"
            f"source_time: {dt.isoformat(timespec='seconds')}\n"
            f"evidence: hour={dt.hour}, minute={dt.minute}, period={period}\n"
            f"结论: {sentence}"
        ),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": sentence,
            "source": "local_system_clock(datetime.now)",
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(now_iso="2026-06-16T15:25:00"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert "下午三点二十五分" in result["speak"]
    print("OK")
