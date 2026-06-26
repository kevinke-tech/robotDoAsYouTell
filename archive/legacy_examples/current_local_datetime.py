"""One-shot skill: return local time and full date in Chinese."""
from datetime import datetime


RUN_SPEC = {
    "name": "current_local_datetime",
    "description": "获取当前本地时间（HH:MM:SS）与完整日期信息，并以中文返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now().astimezone()
    time_hms = now.strftime("%H:%M:%S")
    date_full = now.strftime("%Y-%m-%d")
    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    timezone_name = now.tzname() or "未知时区"
    iso_time = now.isoformat(timespec="seconds")

    speak = f"现在是{time_hms}，{date_full}，{weekday_cn}。"
    render = (
        "来源: 系统本地时钟\n"
        "source: system_local_clock\n"
        f"timestamp_iso: {iso_time}\n"
        f"time_hms: {time_hms}\n"
        f"date: {date_full}\n"
        f"weekday: {weekday_cn}\n"
        f"timezone: {timezone_name}"
    )
    return {
        "speak": speak,
        "render": render,
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": f"{date_full} {weekday_cn}\n{time_hms} ({timezone_name})",
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(test_mode=True))
    assert isinstance(result, dict)
    assert isinstance(result.get("speak"), str) and result["speak"].strip()
    assert isinstance(result.get("render"), str) and result["render"].strip()
    assert "source:" in result["render"]
    print("OK")
