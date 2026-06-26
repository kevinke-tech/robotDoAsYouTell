"""一次性技能：获取本地时间并用中文自然语句播报。"""
from datetime import datetime
import time

RUN_SPEC = {
    "name": "local_time_hhmm_evidence_cn_oneshot",
    "description": "获取当前本地时间并用中文自然语言报告几点几分。",
    "args_schema": {
        "type": "object",
        "properties": {"style": {"type": "string", "enum": ["normal"], "default": "normal"}},
        "required": [],
    },
}


def _natural_cn(hour: int, minute: int) -> str:
    if minute == 0:
        return f"{hour}点整"
    if minute < 10:
        return f"{hour}点零{minute}分"
    return f"{hour}点{minute}分"


async def run(style: str = "normal", **kwargs):
    evidence = []
    hour = minute = None
    try:
        now = datetime.now().astimezone()
        hour, minute = now.hour, now.minute
        evidence.append({"method": "datetime.now().astimezone()", "iso": now.isoformat()})
    except Exception as e:
        evidence.append({"method": "datetime.now().astimezone()", "error": str(e)})
    if hour is None or minute is None:
        try:
            lt = time.localtime()
            hour, minute = int(lt.tm_hour), int(lt.tm_min)
            evidence.append(
                {"method": "time.localtime()", "key_fields": {"tm_hour": hour, "tm_min": minute}}
            )
        except Exception as e:
            evidence.append({"method": "time.localtime()", "error": str(e)})
    if hour is None or minute is None:
        return {
            "speak": "抱歉，我现在没法可靠读取本地时间。",
            "render": "结果: 读取本地时间失败\nsource: system_local_clock\nevidence: " + str(evidence),
            "ui": {
                "type": "info_card",
                "title": "本地时间获取失败",
                "message": "无法从系统时钟读取时间，请稍后重试。",
                "source": "system_local_clock",
                "evidence": evidence,
            },
        }
    time_text = _natural_cn(hour, minute)
    return {
        "speak": f"现在是{time_text}。",
        "render": (
            f"现在时间: {time_text}\nsource: system_local_clock\n"
            f"key_fields: hour={hour}, minute={minute}\nevidence: {evidence}"
        ),
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": f"现在是{time_text}",
            "source": "system_local_clock",
            "evidence": evidence,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(style="normal"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
