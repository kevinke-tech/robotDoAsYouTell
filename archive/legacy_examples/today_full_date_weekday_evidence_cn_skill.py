"""一次性技能：返回今天的完整日期与星期（中文），并附证据字段。"""
from datetime import datetime

RUN_SPEC = {
    "name": "today_full_date_weekday_evidence_cn_skill",
    "description": "获取当前本地日期和星期并用中文告知用户。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now().astimezone()
    weekday_map = {
        0: "星期一",
        1: "星期二",
        2: "星期三",
        3: "星期四",
        4: "星期五",
        5: "星期六",
        6: "星期日",
    }
    weekday_cn = weekday_map[now.weekday()]
    date_cn = f"{now.year}年{now.month}月{now.day}日"
    iso_time = now.isoformat()
    tz_name = str(now.tzinfo) if now.tzinfo else "local"

    speak = f"今天是{date_cn}，{weekday_cn}。"
    render = (
        f"今天日期: {date_cn}\n"
        f"星期: {weekday_cn}\n"
        f"source: system_local_datetime\n"
        f"evidence: iso_time={iso_time}, timezone={tz_name}, weekday_index={now.weekday()}"
    )
    return {
        "speak": speak,
        "render": render,
        "source": "system_local_datetime",
        "evidence": {
            "iso_time": iso_time,
            "timezone": tz_name,
            "weekday_index": now.weekday(),
            "weekday_cn": weekday_cn,
        },
        "ui": {
            "type": "info_card",
            "title": "今天的日期与星期",
            "message": f"{date_cn} {weekday_cn}",
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    assert "source" in result or "source_url" in result or "evidence" in result or "references" in result
    print("OK")
