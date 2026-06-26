"""一次性技能：获取本地时间与完整日期（中文）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "local_time_with_date",
    "description": "获取当前本地时间（HH:MM:SS）并返回完整日期信息。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now().astimezone()
    time_text = now.strftime("%H:%M:%S")
    date_text = now.strftime("%Y-%m-%d")
    weekday_map = {
        0: "星期一",
        1: "星期二",
        2: "星期三",
        3: "星期四",
        4: "星期五",
        5: "星期六",
        6: "星期日",
    }
    weekday_text = weekday_map[now.weekday()]
    tz_name = now.tzname() or "未知时区"
    tz_offset = now.strftime("%z")
    offset_text = f"{tz_offset[:3]}:{tz_offset[3:]}" if len(tz_offset) == 5 else "未知偏移"
    iso_text = now.isoformat(timespec="seconds")
    message = f"{date_text} {weekday_text} {time_text}（{tz_name} {offset_text}）"
    return {
        "speak": f"现在是{time_text}。今天是{date_text}，{weekday_text}。",
        "render": (
            "来源: system_local_clock\n"
            f"证据时间戳: {iso_text}\n"
            f"关键字段: time={time_text}, date={date_text}, weekday={weekday_text}, "
            f"timezone={tz_name}, utc_offset={offset_text}\n"
            f"结果: {message}"
        ),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": message,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert isinstance(result.get("speak"), str) and result["speak"].strip()
    assert isinstance(result.get("render"), str) and "来源:" in result["render"]
    print("OK")
