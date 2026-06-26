"""一次性技能：获取当前本地时间（时分秒）并返回中文卡片。"""
from datetime import datetime


RUN_SPEC = {
    "name": "local_time_hms_cn_card",
    "description": "获取当前本地时间并以中文时分秒格式返回。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now()
    time_text = now.strftime("%H:%M:%S")
    iso_local = now.isoformat(timespec="seconds")
    source = "system_local_clock"
    render = (
        f"当前本地时间: {time_text}\n"
        f"source: {source}\n"
        f"evidence: iso_local={iso_local}, format=%H:%M:%S"
    )
    return {
        "speak": f"现在本地时间是{time_text}。",
        "render": render,
        "ui": {
            "type": "info_card",
            "title": "当前本地时间",
            "message": f"{time_text}（时:分:秒）",
            "source": source,
            "evidence": {"iso_local": iso_local, "format": "%H:%M:%S"},
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(test_mode=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
