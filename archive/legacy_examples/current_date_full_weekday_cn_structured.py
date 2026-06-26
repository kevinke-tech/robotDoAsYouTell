"""一次性技能：返回当前中文日期与星期信息。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_date_full_weekday_cn_structured",
    "description": "获取当前日期并以中文返回年月日和星期。",
    "args_schema": {
        "type": "object",
        "properties": {
            "now_iso": {"type": "string", "description": "可选，ISO 时间用于测试"},
        },
        "required": [],
    },
}


async def run(now_iso: str = "", **kwargs):
    try:
        if now_iso:
            dt = datetime.fromisoformat(now_iso)
        else:
            dt = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_cn = weekdays[dt.weekday()]
        date_cn = f"{dt.year}年{dt.month}月{dt.day}日，{weekday_cn}"
        evidence = {
            "iso_datetime": dt.isoformat(timespec="seconds"),
            "weekday_index": dt.weekday(),
            "weekday_cn": weekday_cn,
        }
        return {
            "speak": f"今天是{date_cn}。",
            "render": (
                f"日期: {date_cn}\n"
                "source: system_local_datetime\n"
                f"evidence: {evidence}"
            ),
            "ui": {
                "type": "info_card",
                "title": "当前日期",
                "message": date_cn,
                "source": "system_local_datetime",
            },
        }
    except Exception as e:
        return {
            "speak": "抱歉，我暂时没法正确读取当前日期。",
            "render": (
                "source: system_local_datetime\n"
                f"evidence: error={type(e).__name__}: {e}"
            ),
            "ui": {
                "type": "info_card",
                "title": "日期获取失败",
                "message": "读取日期时出现异常，请稍后重试。",
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(now_iso="2025-01-15T09:30:00"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
