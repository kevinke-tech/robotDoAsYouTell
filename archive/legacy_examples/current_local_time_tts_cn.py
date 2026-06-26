"""一次性技能：返回当前本地时间的中文口语描述。"""
from datetime import datetime


RUN_SPEC = {
    "name": "current_local_time_tts_cn",
    "description": "获取当前本地时间并用中文口语化返回。",
    "args_schema": {
        "type": "object",
        "properties": {
            "now_iso": {"type": "string", "description": "可选：用于测试的本地时间 ISO 字符串"}
        },
        "required": [],
    },
}


def _cn_num(n: int) -> str:
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" if n == 10 else "十" + digits[n % 10]
    tens, ones = divmod(n, 10)
    return digits[tens] + "十" + (digits[ones] if ones else "")


def _period_and_hour(hour24: int) -> tuple[str, int]:
    if hour24 < 6:
        return "凌晨", 12 if hour24 in (0, 12) else hour24
    if hour24 < 12:
        return "上午", hour24
    if hour24 == 12:
        return "中午", 12
    if hour24 < 18:
        return "下午", hour24 - 12
    return "晚上", hour24 - 12


async def run(now_iso: str = "", **kwargs):
    try:
        now = datetime.fromisoformat(now_iso) if now_iso else datetime.now()
    except Exception as exc:
        speak = "时间参数格式不对，我先按当前本地时间告诉你。"
        now = datetime.now()
        parse_note = f"参数解析失败: {exc}"
    else:
        speak = ""
        parse_note = "参数解析成功" if now_iso else "未提供参数，使用系统本地时间"
    period, hour12 = _period_and_hour(now.hour)
    minute_text = "整" if now.minute == 0 else _cn_num(now.minute) + "分"
    phrase = f"现在是{period}{_cn_num(hour12)}点{minute_text}"
    return {
        "speak": speak or phrase,
        "render": (
            f"source: system_local_clock\n"
            f"evidence: now_iso={now.isoformat(timespec='seconds')}; {parse_note}\n"
            f"结果: {phrase}"
        ),
        "ui": {"type": "info_card", "title": "当前本地时间", "message": phrase},
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(now_iso="2026-06-18T15:25:00"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
