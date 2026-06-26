"""返回当前日期与中文星期。"""
from datetime import datetime

RUN_SPEC = {
    "name": "today_weekday_date_cn",
    "description": "获取今天是星期几与完整日期（中文）。",
    "args_schema": {
        "type": "object",
        "properties": {
            "now_iso": {"type": "string", "description": "可选，ISO 时间字符串用于覆盖当前时间"},
        },
        "required": [],
    },
}


async def run(now_iso: str = "", **kwargs):
    try:
        now = datetime.fromisoformat(now_iso) if now_iso else datetime.now().astimezone()
        weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
        full_date = f"{now.year}年{now.month}月{now.day}日"
        message = f"今天是{weekday}，{full_date}。"
        evidence = {
            "source": "system_local_clock",
            "source_url": "local://system-clock",
            "time_iso": now.isoformat(timespec="seconds"),
            "key_fields": {"weekday": weekday, "full_date": full_date},
        }
        return {
            "speak": message,
            "render": (
                f"source: {evidence['source']}\n"
                f"source_url: {evidence['source_url']}\n"
                f"evidence: time_iso={evidence['time_iso']}, weekday={weekday}, full_date={full_date}\n"
                f"结果: {message}"
            ),
            "ui": {
                "type": "info_card",
                "title": "今天的日期",
                "message": f"{full_date}（{weekday}）",
            },
        }
    except Exception as e:
        return {
            "speak": "我这边暂时没法确认当前日期，请稍后再试。",
            "render": (
                "source: system_local_clock\n"
                "source_url: local://system-clock\n"
                f"evidence: error={type(e).__name__}: {e}\n"
                "结果: 日期获取失败。"
            ),
            "ui": {"type": "info_card", "title": "日期获取失败", "message": "无法读取当前日期时间"},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(now_iso="2026-06-18T14:32:00+08:00"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
