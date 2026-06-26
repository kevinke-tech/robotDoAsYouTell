"""一次性技能：获取当前本地日期与星期并返回中文结果。"""
from datetime import datetime


RUN_SPEC = {
    "name": "today_date_weekday_truth_cn",
    "description": "获取当前本地日期和星期几并用中文播报。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekdays[now.weekday()]
    date_text = f"{now.year}年{now.month}月{now.day}日"
    answer = f"今天是{date_text}，{weekday}。"
    iso_now = now.isoformat(timespec="seconds")
    render = (
        f"{answer}\n"
        f"source: system_local_clock\n"
        f"evidence: iso_datetime={iso_now}, weekday_index={now.weekday()}\n"
        f"references: Python datetime.now()"
    )
    return {
        "speak": answer,
        "render": render,
        "ui": {
            "type": "info_card",
            "title": "今日日期",
            "message": answer,
            "source": "system_local_clock",
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    assert isinstance(result.get("ui"), dict) and result["ui"].get("type") == "info_card"
    assert "source:" in result["render"]
    print("OK")
