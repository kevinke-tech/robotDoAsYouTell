"""一次性技能：返回当前中文日期与星期。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_date_full_weekday_cn_oneshot",
    "description": "获取当前日期并以中文返回年月日和星期。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

_WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        weekday_cn = _WEEKDAY_CN[now.weekday()]
        date_text = f"{now.year}年{now.month}月{now.day}日，{weekday_cn}"
        return {
            "speak": f"今天是{date_text}。",
            "render": (
                f"当前日期：{date_text}\n"
                f"source: system_local_datetime\n"
                f"evidence: iso={now.isoformat()}, weekday_index={now.weekday()}"
            ),
            "ui": {
                "type": "info_card",
                "title": "当前日期",
                "message": date_text,
            },
        }
    except Exception as e:
        return {
            "speak": "我现在没法读取本地日期时间，请稍后再试。",
            "render": f"日期获取失败\nsource: system_local_datetime\nevidence: error={type(e).__name__}: {e}",
            "ui": {
                "type": "info_card",
                "title": "日期获取失败",
                "message": "读取本地日期时间时发生错误，请稍后重试。",
            },
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    print("OK")
