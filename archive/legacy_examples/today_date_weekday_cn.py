"""一次性技能：返回今天的中文日期与星期信息。"""
from datetime import datetime

RUN_SPEC = {
    "name": "today_date_weekday_cn",
    "description": "获取当前完整日期并用中文说明今天是星期几。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now().astimezone()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekdays[now.weekday()]
    full_date_cn = f"{now.year}年{now.month}月{now.day}日"
    conclusion = f"今天是{weekday}，完整日期是{full_date_cn}。"
    return {
        "speak": conclusion,
        "render": (
            "来源: 系统本地时间(datetime.now().astimezone())\n"
            f"source_time_iso: {now.isoformat()}\n"
            f"year: {now.year}\nmonth: {now.month}\nday: {now.day}\n"
            f"weekday_index: {now.weekday()} (0=星期一)\n"
            f"结论: {conclusion}"
        ),
        "ui": {
            "type": "info_card",
            "title": "日期与星期",
            "message": conclusion,
        },
    }


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(run(test_mode=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
