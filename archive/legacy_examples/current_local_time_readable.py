"""一次性技能：获取并返回当前本地时间（清晰易读格式）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_local_time_readable",
    "description": "获取当前本地时间并返回可读结果。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _format_cn_ampm(dt: datetime) -> str:
    hour = dt.hour
    minute = dt.minute
    if hour < 6:
        period = "凌晨"
    elif hour < 12:
        period = "上午"
    elif hour < 18:
        period = "下午"
    else:
        period = "晚上"
    hour12 = hour % 12 or 12
    return f"{period} {hour12}:{minute:02d}"


async def run(**kwargs):
    now = datetime.now().astimezone()
    time_text = _format_cn_ampm(now)
    iso_time = now.isoformat()
    source = "system_local_clock"
    evidence = {"timezone": str(now.tzinfo), "iso_timestamp": iso_time, "format": "cn_ampm_h:mm"}
    return {
        "speak": time_text,
        "render": (
            f"当前时间: {time_text}\n"
            f"source: {source}\n"
            f"evidence: timezone={evidence['timezone']}, iso_timestamp={evidence['iso_timestamp']}, format={evidence['format']}"
        ),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": time_text,
            "source": source,
            "evidence": evidence,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
