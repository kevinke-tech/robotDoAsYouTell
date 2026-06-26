"""一次性技能：获取并展示当前本地时间（中文）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_local_time",
    "description": "获取当前本地时间，并用中文清晰显示小时和分钟。",
    "args_schema": {
        "type": "object",
        "properties": {
            "display_style": {"type": "string", "default": "ampm"},
        },
        "required": [],
    },
}


def _format_cn_time(now: datetime) -> str:
    period = "上午" if now.hour < 12 else "下午"
    hour12 = now.hour % 12 or 12
    return f"{period} {hour12}:{now.minute:02d}"


async def run(display_style: str = "ampm", **kwargs):
    now = datetime.now().astimezone()
    formatted = _format_cn_time(now) if display_style == "ampm" else f"{now.hour:02d}:{now.minute:02d}"
    unix_ts = int(now.timestamp())
    return {
        "speak": f"现在是{formatted}。",
        "render": (
            "source: local_system_clock\n"
            "source_url: system://datetime.now\n"
            f"captured_at_iso: {now.isoformat()}\n"
            f"key_fields: unix_ts={unix_ts}, timezone={now.tzname() or '本地时区'}, hour={now.hour}, minute={now.minute}\n"
            f"结论: 现在是{formatted}"
        ),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": f"现在是{formatted}",
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(display_style="ampm"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
