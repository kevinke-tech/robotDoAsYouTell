"""告诉用户当前时间。"""
from datetime import datetime

RUN_SPEC = {
    "name": "current_time",
    "description": (
        "告诉用户当前本地时间,无需参数。"
        "用户问 '现在几点'、'几点了'、'what time is it' 等时调用。"
    ),
    "args_schema": {"type": "object", "properties": {}, "required": []},
}


async def run(**kwargs):
    now = datetime.now()
    hh_mm = now.strftime("%H:%M")
    return {
        "speak": f"现在是 {hh_mm}。",
        "render": f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}",
    }


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(run())
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
