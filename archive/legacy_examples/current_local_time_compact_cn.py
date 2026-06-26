"""一次性技能：获取当前本地时间并返回中文播报。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_local_time_compact_cn",
    "description": "获取当前本地时间并用简洁中文返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _to_spoken_time(dt: datetime) -> str:
    hour = dt.hour
    minute = dt.minute
    hour12 = hour % 12 or 12
    if 0 <= hour < 6:
        period = "凌晨"
    elif hour < 12:
        period = "上午"
    elif hour < 13:
        period = "中午"
    elif hour < 18:
        period = "下午"
    else:
        period = "晚上"
    return f"现在是{period}{hour12}点{minute}分"


async def run(**kwargs):
    try:
        mock_now = kwargs.get("_mock_now")
        now = datetime.fromisoformat(mock_now) if isinstance(mock_now, str) else datetime.now()
        spoken = _to_spoken_time(now)
        iso_now = now.astimezone().isoformat()
        render = (
            f"{spoken}\n"
            f"source: system_local_time\n"
            f"evidence: iso_datetime={iso_now}, hour={now.hour}, minute={now.minute}"
        )
        return {
            "speak": f"{spoken}。",
            "render": render,
            "ui": {
                "type": "info_card",
                "title": "当前本地时间",
                "message": spoken,
                "source": "system_local_time",
            },
        }
    except Exception as exc:
        return {
            "speak": "抱歉，我这次没能读到本地时间。",
            "render": f"source: system_local_time\nevidence: error={type(exc).__name__}: {exc}",
            "ui": {
                "type": "info_card",
                "title": "时间获取失败",
                "message": "暂时无法读取本地时间，请稍后重试。",
                "source": "system_local_time",
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(_mock_now="2026-06-18T15:25:00"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
