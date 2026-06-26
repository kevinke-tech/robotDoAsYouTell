"""一次性技能：返回当前完整日期与星期几（中文）。"""
from datetime import datetime


RUN_SPEC = {
    "name": "current_date_weekday_cn_contract",
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
        weekday_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_cn = weekday_map[now.weekday()]
        full_date = f"{now.year}年{now.month}月{now.day}日"
        speak = f"今天是{weekday_cn}，日期是{full_date}。"
        source = "system_local_datetime"
        evidence = {
            "iso_datetime": now.isoformat(),
            "timezone": str(now.tzinfo),
            "weekday_index": now.weekday(),
        }
        render = (
            f"source: {source}\n"
            f"evidence: iso_datetime={evidence['iso_datetime']}, timezone={evidence['timezone']}, "
            f"weekday_index={evidence['weekday_index']}\n"
            f"完整日期: {full_date}\n"
            f"星期: {weekday_cn}"
        )
        return {
            "speak": speak,
            "render": render,
            "source": source,
            "evidence": evidence,
            "ui": {
                "type": "info_card",
                "title": "今天的日期信息",
                "message": f"{full_date}，{weekday_cn}",
            },
        }
    except Exception as exc:
        msg = "我现在没法读取本地日期时间，不过你可以稍后再试一次。"
        return {
            "speak": msg,
            "render": f"source: system_local_datetime\nevidence: error={type(exc).__name__}: {exc}",
            "source": "system_local_datetime",
            "evidence": {"error": f"{type(exc).__name__}: {exc}"},
            "ui": {"type": "info_card", "title": "日期获取失败", "message": "读取本地时间失败"},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(mock=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert any(k in result for k in ("source", "source_url", "evidence", "references"))
    print("OK")
