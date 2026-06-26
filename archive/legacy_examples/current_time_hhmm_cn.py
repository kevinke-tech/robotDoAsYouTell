"""一次性技能：返回当前本地时间（中文时分格式）。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_time_hhmm_cn",
    "description": "获取当前本地时间并返回现在是XX点XX分。",
    "args_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


async def run(**kwargs):
    now = datetime.now()
    time_text = f"现在是{now.hour}点{now.minute:02d}分"
    return {
        "speak": time_text,
        "render": time_text,
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(test_mode=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
