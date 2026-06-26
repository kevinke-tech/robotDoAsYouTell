"""一次性技能：返回今天的完整日期与星期（中文）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "today_full_date_weekday_cn",
    "description": "获取当前完整日期并告知星期几。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday_cn = weekdays[now.weekday()]
    full_date = now.strftime("%Y年%m月%d日")
    iso_now = now.isoformat(timespec="seconds")
    speak = f"今天是{full_date}，{weekday_cn}。"
    render = (
        f"今天日期: {full_date}\n"
        f"今天星期: {weekday_cn}\n"
        f"source: system_local_datetime\n"
        f"evidence: iso_datetime={iso_now}, weekday_index={now.weekday()}"
    )
    return {
        "speak": speak,
        "render": render,
        "ui": {
            "type": "info_card",
            "title": "今日日期与星期",
            "message": f"{full_date} {weekday_cn}",
        },
        "source": "system_local_datetime",
        "evidence": {
            "iso_datetime": iso_now,
            "weekday_index": now.weekday(),
            "weekday_cn": weekday_cn,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert isinstance(result.get("speak"), str) and result["speak"]
    assert isinstance(result.get("render"), str) and result["render"]
    assert "source" in result or "evidence" in result or "references" in result
    print("OK")
