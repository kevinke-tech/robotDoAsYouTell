"""一次性技能：获取本地时间并中文播报。"""
from datetime import datetime

RUN_SPEC = {
    "name": "local_time_voice_broadcast_cn",
    "description": "获取当前本地时间并用中文播报几点几分。",
    "args_schema": {"type": "object", "properties": {}, "required": []},
}


def _format_cn_time(now: datetime) -> str:
    hour = now.hour
    minute = now.minute
    if 0 <= hour < 6:
        period = "凌晨"
    elif hour < 12:
        period = "上午"
    elif hour == 12:
        period = "中午"
    elif hour < 18:
        period = "下午"
    else:
        period = "晚上"
    hour12 = hour % 12 or 12
    return f"现在是{period}{hour12}点{minute:02d}分"


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        time_text = _format_cn_time(now)
        source = "system_local_clock"
        evidence = {"iso_time": now.isoformat(), "timezone": str(now.tzinfo)}
        return {
            "speak": time_text,
            "render": (
                f"当前时间: {time_text}\n"
                f"source: {source}\n"
                f"evidence: {evidence}"
            ),
            "ui": {
                "type": "info_card",
                "title": "本地时间播报",
                "message": time_text,
                "source": source,
            },
        }
    except Exception as e:
        return {
            "speak": "我暂时读不到本地时间，请稍后再试。",
            "render": f"时间获取失败\nsource: system_local_clock\nevidence: error={e!r}",
            "ui": {
                "type": "info_card",
                "title": "时间获取失败",
                "message": "无法读取本地系统时钟，请稍后重试。",
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(mock=True))
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    print("OK")
