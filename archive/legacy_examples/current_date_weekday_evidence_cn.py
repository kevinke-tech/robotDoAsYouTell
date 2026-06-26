"""一次性技能：返回当前日期和星期（含证据字段）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_date_weekday_evidence_cn",
    "description": "获取当前日期和星期并用中文返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_cn = weekdays[now.weekday()]
        date_text = f"{now.year}年{now.month}月{now.day}日"
        speak = f"今天是{date_text}，{weekday_cn}。"
        source = "system_localtime"
        evidence = {
            "iso_datetime": now.isoformat(),
            "weekday_index": now.weekday(),
            "timezone": str(now.tzinfo) if now.tzinfo else "local",
        }
        render = (
            f"今天是{date_text}，{weekday_cn}。\n"
            f"source: {source}\n"
            f"evidence: iso_datetime={evidence['iso_datetime']}, "
            f"weekday_index={evidence['weekday_index']}, timezone={evidence['timezone']}"
        )
        return {
            "speak": speak,
            "render": render,
            "ui": {"type": "info_card", "title": "当前日期与星期", "message": speak},
            "source": source,
            "evidence": evidence,
        }
    except Exception as e:
        reason = str(e)[:160] or "unknown_error"
        return {
            "speak": "我暂时没法读取系统日期，请稍后再试。",
            "render": f"日期读取失败。\nsource: system_localtime\nevidence: error={reason}",
            "ui": {"type": "info_card", "title": "日期读取失败", "message": "无法读取系统日期。"},
            "source": "system_localtime",
            "evidence": {"error": reason},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(test_mode=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
