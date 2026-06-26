"""一次性技能：获取并展示当前本地时间（中文）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "local_time_full_cn",
    "description": "获取当前本地日期与时间并格式化展示。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now().astimezone()
    date_text = f"{now.year}年{now.month:02d}月{now.day:02d}日"
    time_text = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
    weekday_text = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    tz_name = now.tzname() or "本地时区"
    tz_offset = now.strftime("%z")
    offset_text = f"UTC{tz_offset[:3]}:{tz_offset[3:]}" if len(tz_offset) == 5 else "未知偏移"
    human_text = f"{date_text} {weekday_text} {time_text}（{tz_name}, {offset_text}）"
    return {
        "speak": f"现在时间是{time_text}，今天是{date_text}，{weekday_text}。",
        "render": (
            f"当前本地时间：{time_text}\n"
            f"当前日期：{date_text}（{weekday_text}）\n"
            f"时区：{tz_name}，偏移：{offset_text}\n"
            f"来源：system_local_clock\n"
            f"取值时间：{now.isoformat()}"
        ),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": human_text,
            "source": "system_local_clock",
            "captured_at": now.isoformat(),
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
