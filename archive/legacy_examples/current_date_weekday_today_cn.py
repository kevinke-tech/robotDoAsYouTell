"""一次性技能：返回当前日期与星期（中文）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_date_weekday_today_cn",
    "description": "获取当前日期和星期并用中文返回。",
    "args_schema": {
        "type": "object",
        "properties": {
            "timezone_hint": {"type": "string", "default": "local"},
        },
        "required": [],
    },
}


async def run(timezone_hint: str = "local", **kwargs):
    try:
        now = datetime.now()
        weekday_cn = "一二三四五六日"[now.weekday()]
        date_cn = f"{now.year}年{now.month}月{now.day}日"
        iso_local = now.isoformat(timespec="seconds")
        speak = f"今天是{date_cn}，星期{weekday_cn}。"
        render = (
            f"今天是{date_cn}，星期{weekday_cn}。\n"
            f"source: system_local_datetime\n"
            f"evidence: iso_local={iso_local}, weekday_index={now.weekday()}, timezone_hint={timezone_hint}"
        )
        return {
            "speak": speak,
            "render": render,
            "ui": {
                "type": "info_card",
                "title": "今天日期与星期",
                "message": speak,
                "source": "system_local_datetime",
            },
        }
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"
        return {
            "speak": "抱歉，我现在没法读取本地日期时间。",
            "render": f"获取失败。\nsource: system_local_datetime\nevidence: error={reason}",
            "ui": {
                "type": "info_card",
                "title": "日期获取失败",
                "message": "暂时无法获取当前日期和星期，请稍后重试。",
                "source": "system_local_datetime",
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(timezone_hint="local"))
    assert isinstance(result, dict)
    assert isinstance(result.get("speak"), str) and result["speak"]
    assert isinstance(result.get("render"), str) and "source:" in result["render"]
    print("OK")
