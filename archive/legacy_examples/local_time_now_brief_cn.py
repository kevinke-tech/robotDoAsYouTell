"""Vox one-shot skill: report current local time in Chinese."""
from datetime import datetime

RUN_SPEC = {
    "name": "local_time_now_brief_cn",
    "description": "获取当前本地时间并用中文自然表达。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def _natural_cn(hour: int, minute: int) -> str:
    period = "凌晨" if hour < 6 else "上午" if hour < 12 else "下午" if hour < 18 else "晚上"
    hour12 = hour % 12 or 12
    if minute == 0:
        return f"{period}{hour12}点整"
    return f"{period}{hour12}点{minute}分"


async def run(**kwargs):
    try:
        now = datetime.now().astimezone()
        hhmm = now.strftime("%H:%M")
        natural = _natural_cn(now.hour, now.minute)
        speak = f"现在是{natural}。"
        render = (
            f"当前时间：{hhmm}\n"
            f"自然表达：{natural}\n"
            f"source: system_clock\n"
            f"evidence: iso_local={now.isoformat(timespec='seconds')}, hour={now.hour}, minute={now.minute}"
        )
        return {
            "speak": speak,
            "render": render,
            "ui": {
                "type": "info_card",
                "title": "当前本地时间",
                "message": f"现在是 {natural}（{hhmm}）",
                "source": "system_clock",
            },
        }
    except Exception as exc:
        msg = "我现在没法读取本地时间，请稍后再试。"
        return {
            "speak": msg,
            "render": f"获取时间失败\nsource: system_clock\nevidence: error={type(exc).__name__}: {exc}",
            "ui": {"type": "info_card", "title": "时间获取失败", "message": msg, "source": "system_clock"},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert "source:" in result["render"] or "evidence:" in result["render"]
    print("OK")
