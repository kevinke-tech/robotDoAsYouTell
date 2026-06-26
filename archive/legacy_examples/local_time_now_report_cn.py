"""一次性技能：获取本地时间并用自然中文报告。"""
from datetime import datetime

RUN_SPEC = {
    "name": "local_time_now_report_cn",
    "description": "获取当前本地时间并用自然中文返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        hh = now.hour
        mm = now.minute
        tz = now.tzname() or "本地时区"
        speak = f"现在是{hh}点{mm}分。"
        render = (
            "结果: 当前本地时间\n"
            f"time_hhmm: {hh:02d}:{mm:02d}\n"
            f"timezone: {tz}\n"
            f"iso_time: {now.isoformat()}\n"
            "source: system_local_clock\n"
            "evidence: datetime.now().astimezone()"
        )
        return {
            "speak": speak,
            "render": render,
            "source": "system_local_clock",
            "evidence": {
                "method": "datetime.now().astimezone()",
                "timezone": tz,
                "iso_time": now.isoformat(),
            },
            "ui": {
                "type": "info_card",
                "title": "当前本地时间",
                "message": f"现在是{hh}点{mm}分（{tz}）",
            },
        }
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        return {
            "speak": "我暂时没法读取本地时间，请稍后再试。",
            "render": (
                "结果: 读取失败\n"
                "source: system_local_clock\n"
                "evidence: exception_caught\n"
                f"error: {reason}"
            ),
            "source": "system_local_clock",
            "evidence": {"error": reason},
            "ui": {"type": "info_card", "title": "时间读取失败", "message": reason},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert isinstance(result.get("speak"), str) and result["speak"].strip()
    assert isinstance(result.get("render"), str) and result["render"].strip()
    assert any(k in result for k in ("source", "source_url", "evidence", "references"))
    print("OK")
