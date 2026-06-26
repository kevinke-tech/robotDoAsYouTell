"""一次性技能：获取本地时间并用中文自然表达。"""
from datetime import datetime
import asyncio
import time

RUN_SPEC = {
    "name": "vox_local_time_natural_cn_oneshot",
    "description": "获取当前本地时间并用中文口语化报告。",
    "args_schema": {
        "type": "object",
        "properties": {
            "mock_iso_time": {"type": "string", "description": "仅用于测试的ISO时间"},
        },
        "required": [],
    },
}


def _cn_period(hour: int) -> str:
    if hour < 6:
        return "凌晨"
    if hour < 12:
        return "上午"
    if hour < 13:
        return "中午"
    if hour < 19:
        return "下午"
    return "晚上"


async def run(mock_iso_time: str = "", **kwargs):
    evidence = []
    try:
        if mock_iso_time:
            dt = datetime.fromisoformat(mock_iso_time)
            hour, minute = dt.hour, dt.minute
            tz = dt.tzname() or "unknown"
            evidence.append({"source": "mock_iso_time", "iso": dt.isoformat()})
        else:
            dt = datetime.now().astimezone()
            hour, minute = dt.hour, dt.minute
            tz = dt.tzname() or "local"
            evidence.append({"source": "python_datetime", "iso": dt.isoformat(), "tz": tz})
    except Exception as e:
        evidence.append({"source": "python_datetime", "error": str(e)})
        try:
            t = time.localtime()
            hour, minute, tz = t.tm_hour, t.tm_min, str(time.tzname[0] if time.tzname else "local")
            evidence.append({"source": "python_time_localtime", "hour": hour, "minute": minute, "tz": tz})
        except Exception as e2:
            evidence.append({"source": "python_time_localtime", "error": str(e2)})
            return {
                "speak": "抱歉，我现在没法可靠读取本地时间。",
                "render": f"结果: 读取失败\nevidence: {evidence}",
                "ui": {"type": "info_card", "title": "本地时间获取失败", "message": "两种本地策略都失败了。", "evidence": evidence},
                "evidence": evidence,
            }

    phrase = f"{_cn_period(hour)}{hour}点{minute}分"
    return {
        "speak": f"现在是{phrase}。",
        "render": f"当前本地时间: {phrase}\nsource: local_system_clock\nevidence: {evidence}\nkey_fields: hour={hour}, minute={minute}, tz={tz}",
        "ui": {"type": "info_card", "title": "当前本地时间", "message": phrase, "source": "local_system_clock", "evidence": evidence},
        "source": "local_system_clock",
        "evidence": evidence,
    }


if __name__ == "__main__":
    r = asyncio.run(run(mock_iso_time="2026-06-18T10:48:00+08:00"))
    assert isinstance(r, dict) and "speak" in r and "render" in r and ("source" in r or "evidence" in r)
    print("OK")
