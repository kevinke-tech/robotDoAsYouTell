"""一次性技能：返回当前日期与星期（中文）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "today_date_weekday_cn_direct",
    "description": "获取本地当前日期并告知今天星期几。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now()
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday_idx = now.weekday()
    weekday_cn = weekday_names[weekday_idx]
    result_text = f"今天是{now.year}年{now.month}月{now.day}日，{weekday_cn}"
    speak_text = f"{result_text}。"
    render_text = (
        "source: local_system_datetime\n"
        f"evidence: iso_date={now.date().isoformat()}, weekday_index={weekday_idx}\n"
        f"result: {result_text}"
    )
    return {
        "speak": speak_text,
        "render": render_text,
        "ui": {
            "type": "info_card",
            "title": "日期与星期",
            "message": result_text,
            "source": "local_system_datetime",
        },
    }


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(run())
    assert isinstance(r, dict) and "speak" in r and "render" in r
    assert isinstance(r.get("ui"), dict) and r["ui"].get("type") == "info_card"
    print("OK")
