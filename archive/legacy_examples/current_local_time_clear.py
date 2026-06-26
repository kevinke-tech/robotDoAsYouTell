"""一次性技能：返回当前本地时间（含证据字段）。"""
from datetime import datetime


RUN_SPEC = {
    "name": "current_local_time_clear",
    "description": "获取当前本地时间，并用清晰格式返回。",
    "args_schema": {"type": "object", "properties": {}, "required": []},
}


def _cn_period(hour: int) -> str:
    if hour < 6:
        return "凌晨"
    if hour < 12:
        return "上午"
    if hour < 13:
        return "中午"
    if hour < 18:
        return "下午"
    return "晚上"


async def run(**kwargs):
    now = datetime.now().astimezone()
    hour12 = now.hour % 12 or 12
    clear_time = f"{_cn_period(now.hour)} {hour12}:{now.minute:02d}（{now.hour:02d}:{now.minute:02d}）"
    source = "system_clock: datetime.now().astimezone()"
    render = (
        f"来源: {source}\n"
        f"采集时间: {now.isoformat()}\n"
        f"时区: {now.tzname()}\n"
        f"当前本地时间: {clear_time}"
    )
    return {
        "speak": f"现在时间是{clear_time}。",
        "render": render,
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": clear_time,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict) and result.get("speak") and result.get("render")
    assert "来源:" in result["render"] and "当前本地时间:" in result["render"]
    print("OK")
