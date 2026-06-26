"""返回当前日期与星期几的一次性技能。"""
from datetime import datetime


RUN_SPEC = {
    "name": "date_weekday_cn",
    "description": "获取当前日期和星期几并用中文返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    try:
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekdays[now.weekday()]
        date_text = f"{now.year}年{now.month}月{now.day}日"
        spoken = f"今天是{date_text}，{weekday}。"
        render = (
            f"今天是{date_text}，{weekday}。\n"
            "source: system_local_datetime\n"
            f"evidence: iso={now.isoformat(timespec='seconds')}, weekday_index={now.weekday()}\n"
            "references: datetime.datetime.now"
        )
        return {
            "speak": spoken,
            "render": render,
            "ui": {
                "type": "info_card",
                "title": "今日日期",
                "message": spoken,
            },
        }
    except Exception as exc:
        return {
            "speak": "抱歉，我现在没能读取系统时间。",
            "render": (
                "暂时无法获取当前日期和星期。\n"
                "source: system_local_datetime\n"
                f"evidence: error={type(exc).__name__}: {exc}\n"
                "references: datetime.datetime.now"
            ),
            "ui": {
                "type": "info_card",
                "title": "日期获取失败",
                "message": "系统时间读取失败，请稍后再试。",
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert "source:" in result["render"] or "evidence:" in result["render"] or "references:" in result["render"]
    print("OK")
