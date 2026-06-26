"""一次性技能：获取本地时间并播报几点几分。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_time_hhmm_voice_cn",
    "description": "获取当前本地时间并用中文口语播报。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _cn_period(hour: int) -> str:
    if 0 <= hour < 6:
        return "凌晨"
    if hour < 12:
        return "上午"
    if hour == 12:
        return "中午"
    if hour < 18:
        return "下午"
    return "晚上"


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        period = _cn_period(now.hour)
        h12 = now.hour % 12 or 12
        minute = now.minute
        time_text = f"现在是{period}{h12}点{minute}分"
        return {
            "speak": time_text,
            "render": (
                f"{time_text}\n"
                f"source: system_local_time\n"
                f"evidence: iso={now.isoformat()}, hour={now.hour}, minute={minute}"
            ),
            "ui": {
                "type": "info_card",
                "title": "当前时间",
                "message": time_text,
            },
        }
    except Exception as exc:
        msg = "我暂时没读到本地时间，请稍后再试。"
        return {
            "speak": msg,
            "render": f"{msg}\nsource: system_local_time\nevidence: error={exc}",
            "ui": {"type": "info_card", "title": "时间获取失败", "message": msg},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert isinstance(result.get("speak"), str) and result["speak"]
    assert isinstance(result.get("render"), str) and "source:" in result["render"]
    print("OK")
