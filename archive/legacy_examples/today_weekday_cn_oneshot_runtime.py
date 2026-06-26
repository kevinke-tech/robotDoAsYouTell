"""一次性技能：返回当前日期和星期（中文）。"""
from datetime import datetime


RUN_SPEC = {
    "name": "today_weekday_cn_oneshot_runtime",
    "description": "获取今天的中文日期和星期并返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _format_today_cn(now: datetime) -> str:
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return f"今天是{now.year}年{now.month}月{now.day}日，{weekdays[now.weekday()]}"


async def run(**kwargs):
    try:
        now = datetime.now()
        text = _format_today_cn(now)
        source = "system_local_datetime"
        evidence = {
            "iso_local": now.isoformat(timespec="seconds"),
            "weekday_index": now.weekday(),
            "timezone_note": "使用运行环境本地系统时间",
        }
        return {
            "speak": text,
            "render": f"{text}\nsource: {source}\nevidence: {evidence}",
            "ui": {
                "type": "info_card",
                "title": "今日日期与星期",
                "message": text,
            },
        }
    except Exception as e:  # 防止异常冒泡，保证可降级返回
        return {
            "speak": "我暂时没法读取当前日期时间，请稍后再试。",
            "render": f"获取失败\nsource: system_local_datetime\nevidence: {{'error': '{type(e).__name__}: {e}'}}",
            "ui": {
                "type": "info_card",
                "title": "日期获取失败",
                "message": "读取本地系统时间失败，请稍后重试。",
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    print("OK")
