"""一次性技能：返回当前日期与星期几（中文）。"""
from datetime import datetime


RUN_SPEC = {
    "name": "today_weekday_date_cn",
    "description": "获取当前日期和星期并用中文返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    try:
        now = datetime.now()
        weekday_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_cn = weekday_map[now.weekday()]
        date_cn = f"{now.year}年{now.month}月{now.day}日"
        sentence = f"今天是{date_cn}，{weekday_cn}。"
        render = (
            f"今天是 {date_cn}，{weekday_cn}。\n"
            "source: system_local_datetime\n"
            f"evidence: now_iso={now.isoformat(timespec='seconds')}, weekday_index={now.weekday()}\n"
            "references: Python datetime.now()"
        )
        return {
            "speak": sentence,
            "render": render,
            "ui": {
                "type": "info_card",
                "title": "日期与星期",
                "message": sentence,
            },
        }
    except Exception as exc:
        return {
            "speak": "抱歉，我刚才没能读取到本地日期时间。",
            "render": (
                "日期获取失败。\n"
                "source: system_local_datetime\n"
                f"evidence: error={type(exc).__name__}: {exc}\n"
                "references: Python datetime.now()"
            ),
            "ui": {
                "type": "info_card",
                "title": "日期获取失败",
                "message": "暂时无法读取本地日期时间，请稍后再试。",
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    print("OK")
