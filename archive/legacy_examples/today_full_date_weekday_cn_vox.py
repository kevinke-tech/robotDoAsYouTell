"""一次性技能：返回今天的完整日期与中文星期。"""
from datetime import datetime

RUN_SPEC = {
    "name": "today_full_date_weekday_cn_vox",
    "description": "获取当前日期并用中文返回星期几。",
    "args_schema": {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "预留参数，当前版本使用系统本地时区。",
                "default": "local",
            }
        },
        "required": [],
    },
}


async def run(timezone: str = "local", **kwargs):
    now = datetime.now().astimezone()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday_cn = weekdays[now.weekday()]
    date_cn = f"{now.year}年{now.month}月{now.day}日"
    speak = f"今天是{date_cn}，{weekday_cn}。"
    source = "system_local_clock"
    evidence = {
        "iso_datetime": now.isoformat(),
        "timezone": str(now.tzinfo),
        "weekday_index_monday_0": now.weekday(),
    }
    render = (
        f"今天是：{date_cn}（{weekday_cn}）\n"
        f"source: {source}\n"
        f"evidence: {evidence}"
    )
    ui = {
        "type": "info_card",
        "title": "今日日期",
        "message": f"{date_cn} {weekday_cn}",
        "source": source,
        "evidence": evidence,
    }
    return {"speak": speak, "render": render, "ui": ui}


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(timezone="local"))
    assert isinstance(result, dict)
    assert isinstance(result.get("speak"), str) and result["speak"]
    assert isinstance(result.get("render"), str) and "source:" in result["render"]
    print("OK")
