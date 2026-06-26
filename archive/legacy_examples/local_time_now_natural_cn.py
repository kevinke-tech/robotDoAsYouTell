"""一次性技能：获取当前本地时间并用中文自然播报。"""
from datetime import datetime

RUN_SPEC = {
    "name": "local_time_now_natural_cn",
    "description": "获取当前本地时间，并用中文报告几点几分。",
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
        period = "凌晨"
        display_hour = hour if hour else 12
    elif hour < 12:
        period = "上午"
        display_hour = hour
    elif hour == 12:
        period = "中午"
        display_hour = 12
    elif hour < 18:
        period = "下午"
        display_hour = hour - 12
    else:
        period = "晚上"
        display_hour = hour - 12
    return f"现在是{period}{display_hour}点{minute}分"


async def run(**kwargs):
    try:
        now = datetime.now()
        spoken = _format_cn_time(now)
        iso = now.isoformat(timespec="seconds")
        source = "system_local_clock"
        render = f"source: {source}\nevidence: local_datetime={iso}\nresult: {spoken}"
        return {
            "speak": spoken,
            "render": render,
            "ui": {
                "type": "info_card",
                "title": "当前本地时间",
                "message": spoken,
                "source": source,
            },
        }
    except Exception as e:
        reason = str(e) or "unknown_error"
        return {
            "speak": "抱歉，我暂时读不出当前时间。",
            "render": f"source: system_local_clock\nevidence: exception={reason}\nresult: 获取失败",
            "ui": {
                "type": "info_card",
                "title": "时间获取失败",
                "message": f"失败原因：{reason}",
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    print("OK")
