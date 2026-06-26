"""一次性技能：返回当前日期和星期（中文）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_date_weekday_cn_oneshot",
    "description": "获取当前日期并用中文说明今天星期几。",
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
        full_date = f"{now.year}年{now.month}月{now.day}日"
        speak = f"今天是{full_date}，{weekday}。"
        render = (
            f"今天日期: {full_date}\n"
            f"星期: {weekday}\n"
            "source: 系统本地时间 (datetime.now)\n"
            f"evidence: iso={now.isoformat(timespec='seconds')}, weekday_index={now.weekday()}"
        )
        return {
            "speak": speak,
            "render": render,
            "ui": {
                "type": "info_card",
                "title": "当前日期与星期",
                "message": f"{full_date}，{weekday}",
            },
        }
    except Exception as exc:
        return {
            "speak": "抱歉，我刚才没能读取本地日期时间。",
            "render": (
                "结果: 获取失败\n"
                "source: 系统本地时间 (datetime.now)\n"
                f"evidence: error={type(exc).__name__}: {exc}"
            ),
            "ui": {
                "type": "info_card",
                "title": "日期获取失败",
                "message": f"失败原因: {type(exc).__name__}",
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(test_mode=True))
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    print("OK")
