"""一次性技能：读取系统本地时间并返回中文结果。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_local_time_simple_cn",
    "description": "获取当前本地时间并用中文简洁返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _period_cn(hour: int) -> str:
    if 0 <= hour < 6:
        return "凌晨"
    if hour < 11:
        return "上午"
    if hour < 13:
        return "中午"
    if hour < 18:
        return "下午"
    return "晚上"


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        period = _period_cn(now.hour)
        display_hour = now.hour % 12 or 12
        speak_text = f"现在是{period}{display_hour}点{now.minute}分。"
        source = "system_clock"
        evidence = {
            "source": source,
            "local_iso": now.isoformat(),
            "timezone": str(now.tzinfo),
            "hour_24": now.hour,
            "minute": now.minute,
        }
        render_text = (
            f"结果: {speak_text}\n"
            f"source: {source}\n"
            f"key_fields: local_iso={evidence['local_iso']}, timezone={evidence['timezone']}, "
            f"hour_24={evidence['hour_24']}, minute={evidence['minute']}"
        )
        return {
            "speak": speak_text,
            "render": render_text,
            "ui": {"type": "info_card", "title": "当前本地时间", "message": speak_text},
            "evidence": evidence,
        }
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        return {
            "speak": "我暂时没读到本地时间，请稍后再试。",
            "render": f"结果: 获取失败\nsource: system_clock\nevidence: {err}",
            "ui": {"type": "info_card", "title": "时间获取失败", "message": "读取系统时间失败"},
            "evidence": {"source": "system_clock", "error": err},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(mock=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert any(k in result for k in ("source", "source_url", "evidence", "references"))
    print("OK")
