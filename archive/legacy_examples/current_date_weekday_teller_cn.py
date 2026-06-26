"""一次性技能：返回当前日期和星期（中文）并附带证据字段。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_date_weekday_teller_cn",
    "description": "获取当前本地日期和星期并用中文告知用户。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now()
    weekday_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday_cn = weekday_map[now.weekday()]
    date_text = now.strftime("%Y年%m月%d日")
    time_iso = now.isoformat(timespec="seconds")
    source = "python_datetime_now_local"
    speak = f"今天是{date_text}，{weekday_cn}。"
    render = (
        f"今天是 {date_text}，{weekday_cn}。\n"
        f"source: {source}\n"
        f"evidence: local_iso={time_iso}, weekday_index={now.weekday()}, calendar={now.strftime('%Y-%m-%d')}"
    )
    return {
        "speak": speak,
        "render": render,
        "ui": {
            "type": "info_card",
            "title": "今日日期",
            "message": f"{date_text} · {weekday_cn}",
        },
        "source": source,
        "evidence": {
            "local_iso": time_iso,
            "weekday_index": now.weekday(),
            "calendar": now.strftime("%Y-%m-%d"),
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    assert result.get("source") or result.get("evidence")
    print("OK")
