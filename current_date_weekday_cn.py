"""一次性技能：返回今天日期与中文星期。"""
from datetime import datetime


RUN_SPEC = {
    "name": "current_date_weekday_cn",
    "description": "获取今天是星期几及完整日期（中文）。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _weekday_cn(idx: int) -> str:
    return ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][idx]


async def run(**kwargs):
    now = datetime.now()
    weekday = _weekday_cn(now.weekday())
    full_date = f"{now.year}年{now.month}月{now.day}日"
    speak = f"今天是{full_date}，{weekday}。"
    render = (
        f"今天：{full_date}\n"
        f"星期：{weekday}\n"
        f"source: local_system_clock\n"
        f"evidence: iso_datetime={now.isoformat(timespec='seconds')}"
    )
    ui = {
        "type": "info_card",
        "title": "日期与星期",
        "message": f"{full_date} · {weekday}",
    }
    return {"speak": speak, "render": render, "ui": ui}


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    print("OK")
