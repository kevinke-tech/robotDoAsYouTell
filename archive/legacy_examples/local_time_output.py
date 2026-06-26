"""一次性技能：返回当前本地时间字符串。"""
from datetime import datetime

RUN_SPEC = {
    "name": "local_time_output",
    "description": "获取当前本地时间，并以清晰格式返回。",
    "args_schema": {
        "type": "object",
        "properties": {
            "use_24h": {"type": "boolean", "default": True},
        },
        "required": [],
    },
}


def _format_cn_ampm(dt: datetime) -> str:
    hour = dt.hour
    minute = dt.minute
    period = "上午" if hour < 12 else "下午"
    h12 = hour % 12 or 12
    return f"{period} {h12}:{minute:02d}"


async def run(use_24h: bool = True, **kwargs):
    now = datetime.now().astimezone()
    tz_name = now.tzname() or "local"
    time_str = now.strftime("%H:%M") if use_24h else _format_cn_ampm(now)
    return {
        "speak": f"现在时间是{time_str}。",
        "render": (
            f"当前本地时间: {time_str}\n"
            f"来源: system_local_clock\n"
            f"采集时间: {now.isoformat()}\n"
            f"时区: {tz_name}\n"
            f"关键字段: hour={now.hour}, minute={now.minute}, format="
            f"{'24h' if use_24h else '12h_cn'}"
        ),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": time_str,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(use_24h=False))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert str(result.get("ui", {}).get("message", "")).strip()
    print("OK")
