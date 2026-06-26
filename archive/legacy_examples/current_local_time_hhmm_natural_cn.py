"""一次性技能：报告当前本地时间（中文自然表达）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_local_time_hhmm_natural_cn",
    "description": "获取当前本地时间并用中文自然语言报告几点几分。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        hour = now.hour
        minute = now.minute
        tz_name = now.tzname() or "LOCAL"
        iso_time = now.isoformat()
        natural = f"现在是{hour}点{minute}分。"
        return {
            "speak": natural,
            "render": (
                "source: system_local_clock\n"
                f"evidence: iso_time={iso_time}, timezone={tz_name}, hour={hour}, minute={minute}\n"
                f"result: {natural}"
            ),
            "ui": {
                "type": "info_card",
                "title": "当前本地时间",
                "message": natural,
                "source": "system_local_clock",
            },
            "source": "system_local_clock",
            "evidence": {
                "iso_time": iso_time,
                "timezone": tz_name,
                "hour": hour,
                "minute": minute,
            },
        }
    except Exception as exc:
        reason = str(exc) or "unknown_error"
        return {
            "speak": "我现在没读到本地时间，请稍后再试。",
            "render": (
                "source: system_local_clock\n"
                f"evidence: error={reason}\n"
                "result: 时间获取失败"
            ),
            "ui": {
                "type": "info_card",
                "title": "当前本地时间",
                "message": "时间获取失败，请稍后重试。",
                "source": "system_local_clock",
            },
            "source": "system_local_clock",
            "evidence": {"error": reason},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert any(k in result for k in ("source", "source_url", "evidence", "references"))
    print("OK")
