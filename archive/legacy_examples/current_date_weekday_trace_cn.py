"""一次性技能：返回当前完整日期与星期（中文）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_date_weekday_trace_cn",
    "description": "获取当前日期和星期并用中文返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
        full_date = f"{now.year}年{now.month}月{now.day}日"
        ts = now.isoformat()
        source = "system_local_clock"
        evidence = {"iso_datetime": ts, "tz": str(now.tzinfo), "weekday_index": now.weekday()}
        return {
            "speak": f"今天是{weekday_cn}，日期是{full_date}。",
            "render": (
                f"今天：{full_date}\n"
                f"星期：{weekday_cn}\n"
                f"source: {source}\n"
                f"evidence: iso_datetime={ts}, tz={now.tzinfo}, weekday_index={now.weekday()}"
            ),
            "ui": {
                "type": "info_card",
                "title": "当前日期与星期",
                "message": f"{full_date} {weekday_cn}",
                "source": source,
                "evidence": evidence,
            },
        }
    except Exception as e:
        return {
            "speak": "我暂时没法确认当前日期和星期。",
            "render": f"获取失败\nsource: system_local_clock\nevidence: error={type(e).__name__}: {e}",
            "ui": {
                "type": "info_card",
                "title": "日期获取失败",
                "message": "暂时无法读取本地时间，请稍后再试。",
                "source": "system_local_clock",
                "evidence": {"error": f"{type(e).__name__}: {e}"},
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert "source" in result["render"] or "evidence" in result["render"]
    print("OK")
