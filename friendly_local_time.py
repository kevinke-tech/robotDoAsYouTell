"""one-shot: 返回当前本地时间（中文友好格式）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "friendly_local_time",
    "description": "获取当前本地时间并用中文友好格式返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _format_cn_time(now: datetime) -> str:
    hour = now.hour
    minute = now.minute
    if 0 <= hour < 6:
        period, h12 = "凌晨", 12 if hour == 0 else hour
    elif hour < 12:
        period, h12 = "上午", hour
    elif hour == 12:
        period, h12 = "中午", 12
    elif hour < 18:
        period, h12 = "下午", hour - 12
    else:
        period, h12 = "晚上", hour - 12
    return f"现在是{period}{h12}点{minute}分"


async def run(**kwargs):
    now = datetime.now()
    msg = _format_cn_time(now)
    iso = now.isoformat(timespec="seconds")
    return {
        "speak": msg,
        "render": f"{msg}\nsource: system_local_clock\nevidence: local_iso={iso}",
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": msg,
            "source": "system_local_clock",
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert "source:" in result["render"] or "evidence:" in result["render"]
    print("OK")
