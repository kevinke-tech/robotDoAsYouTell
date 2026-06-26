"""一次性技能：播报并展示当前本地时间。"""
from datetime import datetime

RUN_SPEC = {
    "name": "vox_local_time_tts_ui_cn",
    "description": "获取当前本地时间并返回播报与信息卡。",
    "args_schema": {
        "type": "object",
        "properties": {"mock_iso": {"type": "string", "description": "仅测试用，本地时间 ISO 字符串"}},
        "required": [],
    },
}


def _spoken_cn(dt: datetime) -> str:
    hour = dt.hour
    minute = dt.minute
    if 0 <= hour < 6:
        period = "凌晨"
    elif hour < 11:
        period = "早上"
    elif hour < 13:
        period = "中午"
    elif hour < 18:
        period = "下午"
    else:
        period = "晚上"
    h12 = hour % 12 or 12
    return f"{period}{h12}点{minute:02d}分"


async def run(mock_iso: str = "", **kwargs):
    try:
        dt = datetime.fromisoformat(mock_iso) if mock_iso else datetime.now().astimezone()
        readable = dt.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
        spoken = _spoken_cn(dt)
        return {
            "speak": f"现在是{spoken}。",
            "render": (
                f"当前时间: {readable}\n"
                f"source: local_system_clock\n"
                f"evidence: iso={dt.isoformat()}"
            ),
            "ui": {
                "type": "info_card",
                "title": "当前本地时间",
                "message": f"{spoken}（{readable}）",
            },
        }
    except Exception as e:
        return {
            "speak": "我现在没能读到本地时间，请稍后再试。",
            "render": f"读取失败\nsource: local_system_clock\nevidence: {type(e).__name__}: {e}",
            "ui": {"type": "info_card", "title": "时间获取失败", "message": f"{type(e).__name__}: {e}"},
        }


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(run(mock_iso="2026-06-18T15:25:00+08:00"))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
