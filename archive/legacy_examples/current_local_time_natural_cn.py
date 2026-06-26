"""一次性技能：获取本地时间并用中文自然播报。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_local_time_natural_cn",
    "description": "获取当前本地时间，并用中文口语化返回几点几分。",
    "args_schema": {
        "type": "object",
        "properties": {
            "now_iso": {"type": "string", "description": "可选，用于测试的 ISO 时间字符串"}
        },
        "required": [],
    },
}


def _spoken_time(dt: datetime) -> str:
    hour = dt.hour
    minute = dt.minute
    hour_12 = hour % 12 or 12
    if 0 <= hour <= 5:
        period = "凌晨"
    elif hour <= 8:
        period = "早上"
    elif hour <= 11:
        period = "上午"
    elif hour == 12:
        period = "中午"
    elif hour <= 17:
        period = "下午"
    else:
        period = "晚上"
    return f"现在是{period}{hour_12}点{minute}分"


async def run(now_iso: str = "", **kwargs):
    source = "system_localtime"
    parse_error = ""
    try:
        dt = datetime.fromisoformat(now_iso) if now_iso else datetime.now()
    except Exception as exc:
        dt = datetime.now()
        parse_error = f"{type(exc).__name__}: {exc}"
    spoken = _spoken_time(dt)
    lines = [
        f"source: {source}",
        f"evidence: local_iso={dt.isoformat(timespec='minutes')}",
    ]
    if parse_error:
        lines.append(f"evidence_parse_error: {parse_error}")
    lines.append(f"result: {spoken}")
    return {
        "speak": spoken,
        "render": "\n".join(lines),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": spoken,
            "source": source,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(now_iso="2026-06-18T15:45:00"))
    assert isinstance(result, dict)
    assert isinstance(result.get("speak"), str) and result["speak"]
    assert isinstance(result.get("render"), str) and "source:" in result["render"]
    print("OK")
