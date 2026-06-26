"""一次性技能：读取系统本地时间并返回中文结果。"""
from datetime import datetime


RUN_SPEC = {
    "name": "current_local_time_voice_cn",
    "description": "获取当前本地时间并用中文简洁返回。",
    "args_schema": {
        "type": "object",
        "properties": {
            "style": {"type": "string", "enum": ["short"], "default": "short"}
        },
        "required": [],
    },
}


def _period_cn(hour: int) -> str:
    if 0 <= hour < 6:
        return "凌晨"
    if hour < 12:
        return "上午"
    if hour < 18:
        return "下午"
    return "晚上"


async def run(style: str = "short", **kwargs):
    now = datetime.now().astimezone()
    hour_24 = now.hour
    minute = now.minute
    period = _period_cn(hour_24)
    hour_12 = hour_24 % 12 or 12
    time_text = f"{period}{hour_12}点{minute}分"
    source = "system_local_clock"
    source_url = "local://datetime.now"
    evidence = {
        "iso_time": now.isoformat(timespec="seconds"),
        "timezone": str(now.tzinfo),
        "hour_24": hour_24,
        "minute": minute,
    }
    return {
        "speak": f"现在是{time_text}。",
        "render": (
            f"现在是{time_text}\n"
            f"source: {source}\n"
            f"source_url: {source_url}\n"
            f"evidence: iso_time={evidence['iso_time']}, timezone={evidence['timezone']}, "
            f"hour_24={hour_24}, minute={minute}"
        ),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": f"现在是{time_text}",
            "source": source,
            "source_url": source_url,
            "evidence": evidence,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(style="short"))
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    assert "source:" in result["render"] or "evidence:" in result["render"]
    print("OK")
