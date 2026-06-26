"""一次性技能：返回本地完整日期与星期信息。"""
from datetime import datetime


RUN_SPEC = {
    "name": "today_full_date_weekday_cn_one_shot",
    "description": "获取当前本地日期并用中文返回星期与完整日期。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_idx = now.weekday()
        weekday_cn = weekday_names[weekday_idx]
        date_text = f"{now.year}年{now.month}月{now.day}日"
        full_text = f"{date_text}，{weekday_cn}"
        source = "system_local_datetime"
        evidence = {
            "timestamp_iso": now.isoformat(),
            "weekday_index": weekday_idx,
            "timezone": str(now.tzinfo),
        }
        return {
            "speak": f"今天是{weekday_cn}，{date_text}。",
            "render": (
                f"今天：{full_text}\n"
                f"source: {source}\n"
                f"evidence.timestamp_iso: {evidence['timestamp_iso']}\n"
                f"evidence.weekday_index: {evidence['weekday_index']}\n"
                f"evidence.timezone: {evidence['timezone']}"
            ),
            "ui": {"type": "info_card", "title": "今天的日期", "message": full_text},
            "source": source,
            "evidence": evidence,
        }
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        return {
            "speak": "我读取本地日期时出了点问题，但我已经记录原因。",
            "render": f"日期获取失败\nsource: system_local_datetime\nevidence.error: {reason}",
            "ui": {"type": "info_card", "title": "日期获取失败", "message": "请稍后重试。"},
            "source": "system_local_datetime",
            "evidence": {"error": reason},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert any(k in result for k in ("source", "source_url", "evidence", "references"))
    print("OK")
