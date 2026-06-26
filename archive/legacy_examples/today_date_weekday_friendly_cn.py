"""一次性技能：返回当前日期与星期（中文友好）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "today_date_weekday_friendly_cn",
    "description": "获取当前日期并用中文返回年、月、日、星期。",
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
        msg = f"今天是{date_text}，{weekday_cn}。"
        iso_local = now.isoformat(timespec="seconds")
        render = (
            f"{msg}\n"
            f"source: system_local_datetime\n"
            f"evidence: iso_local={iso_local}, weekday_index={now.weekday()}\n"
            f"references: python_datetime_now_astimezone"
        )
        return {
            "speak": msg,
            "render": render,
            "ui": {
                "type": "info_card",
                "title": "当前日期",
                "message": msg,
                "source": "system_local_datetime",
            },
        }
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"
        return {
            "speak": "抱歉，我这次没能读取到当前日期。",
            "render": f"日期获取失败。\nsource: system_local_datetime\nevidence: {reason}",
            "ui": {
                "type": "info_card",
                "title": "日期获取失败",
                "message": "暂时无法读取系统日期，请稍后重试。",
                "source": "system_local_datetime",
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(mock="smoke"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
