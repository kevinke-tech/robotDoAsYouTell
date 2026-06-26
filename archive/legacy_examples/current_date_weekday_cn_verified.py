"""一次性技能：返回当前日期与星期（中文）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_date_weekday_cn_verified",
    "description": "获取当前日期和星期几并用中文返回。",
    "args_schema": {
        "type": "object",
        "properties": {
            "now_iso": {"type": "string", "description": "可选，用于测试的 ISO 时间字符串"},
        },
        "required": [],
    },
}

_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


async def run(now_iso: str | None = None, **kwargs):
    try:
        now = datetime.fromisoformat(now_iso) if now_iso else datetime.now().astimezone()
        weekday = _WEEKDAYS[now.weekday()]
        date_text = f"{now.year}年{now.month}月{now.day}日"
        speak = f"今天是{date_text}，{weekday}。"
        source = "system_local_clock"
        evidence = {
            "iso_datetime": now.isoformat(),
            "weekday_index": now.weekday(),
            "weekday_cn": weekday,
            "timezone": str(now.tzinfo),
        }
        render = (
            f"今天是{date_text}，{weekday}。\n"
            f"source: {source}\n"
            f"evidence: {evidence}"
        )
        return {
            "speak": speak,
            "render": render,
            "ui": {
                "type": "info_card",
                "title": "日期与星期",
                "message": speak,
                "source": source,
                "evidence": evidence,
            },
            "source": source,
            "evidence": evidence,
        }
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"
        return {
            "speak": "我暂时没能读出当前日期和星期，请稍后再试。",
            "render": f"日期获取失败。\nsource: system_local_clock\nevidence: {{'error': '{reason}'}}",
            "ui": {"type": "info_card", "title": "日期获取失败", "message": "系统时间读取异常"},
            "source": "system_local_clock",
            "evidence": {"error": reason},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(now_iso="2026-06-18T10:38:00+08:00"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
