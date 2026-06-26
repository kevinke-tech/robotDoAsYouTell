"""持续观察摄像头，看到矿泉水瓶时提醒想喝水。"""

import runtime

RUN_SPEC = {
    "name": "water_bottle_vision_watcher",
    "description": "启动后台视觉监视：当画面中清晰出现矿泉水瓶或类似塑料饮用水瓶时，说“我想喝水”。参数：cooldown_sec。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 30},
        },
    },
}

TRIGGER_TEXT = "画面任意位置清晰可见矿泉水瓶或任意塑料饮用水瓶"
SAY_TEXT = "我想喝水"


async def run(cooldown_sec: float = 30, **kwargs):
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动盯看的功能。",
            "render": "[错误] 后台运行器未就绪，无法启动矿泉水瓶监视器。",
            "ui": {
                "type": "info_card",
                "title": "矿泉水瓶监视器未启动",
                "message": "后台运行器未就绪，请稍后再试。",
            },
        }

    watcher_id = await runtime.RUNNER.add_vision_watcher(
        trigger=TRIGGER_TEXT,
        say_on_match=SAY_TEXT,
        cooldown_sec=float(cooldown_sec),
        rate_hz=1.0,
    )
    return {
        "speak": "好的，我会盯着看，看到水瓶就提醒你。",
        "render": (
            f"已启动矿泉水瓶监视器：{watcher_id}\n"
            f"触发条件：{TRIGGER_TEXT}\n"
            f"命中播报：{SAY_TEXT}"
        ),
        "ui": {
            "type": "info_card",
            "title": "矿泉水瓶监视中",
            "message": f"监视器 {watcher_id} 已启动，识别到水瓶会说“{SAY_TEXT}”。",
        },
    }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run(cooldown_sec=12))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
