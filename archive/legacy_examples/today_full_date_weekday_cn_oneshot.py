"""一次性技能：获取当前日期与星期并生成中文播报。"""
from datetime import datetime

RUN_SPEC = {
    "name": "today_full_date_weekday_cn_oneshot",
    "description": "返回今天的完整日期和星期信息。",
    "args_schema": {
        "type": "object",
        "properties": {
            "style": {"type": "string", "enum": ["brief", "full"], "default": "full"}
        },
        "required": [],
    },
}


def _weekday_cn(index: int) -> str:
    days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return days[index] if 0 <= index < 7 else "星期未知"


async def run(style: str = "full", **kwargs):
    now = datetime.now()
    weekday = _weekday_cn(now.weekday())
    date_full = f"{now.year}年{now.month}月{now.day}日"
    datetime_iso = now.isoformat(timespec="seconds")
    speak = f"今天是{weekday}。"
    if style == "brief":
        render_title = "今日日期"
        render_msg = f"{date_full} {weekday}"
    else:
        render_title = "今天的完整日期"
        render_msg = f"{date_full}，{weekday}"
    render = (
        f"{render_title}\n"
        f"日期: {date_full}\n"
        f"星期: {weekday}\n"
        f"source: system_local_clock\n"
        f"evidence: now_iso={datetime_iso}, weekday_index={now.weekday()}"
    )
    return {
        "speak": speak,
        "render": render,
        "ui": {
            "type": "info_card",
            "title": "日期与星期",
            "message": render_msg,
            "source": "system_local_clock",
            "evidence": {"now_iso": datetime_iso, "weekday_index": now.weekday()},
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(style="full", request_id="smoke_test"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
