"""持续监控摄像头，清晰看到纸巾时触发播报。"""
import runtime

RUN_SPEC = {
    "name": "tissue_vision_watcher",
    "description": "启动纸巾视觉监视器。参数：trigger、say_on_match、cooldown_sec。",
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {
                "type": "string",
                "default": "画面中清晰可见纸巾（面巾纸、抽纸盒、或有人手持纸巾）",
            },
            "say_on_match": {"type": "string", "default": "感冒了么？"},
            "cooldown_sec": {"type": "number", "default": 30},
        },
        "required": [],
    },
}


async def run(
    trigger: str = "画面中清晰可见纸巾（面巾纸、抽纸盒、或有人手持纸巾）",
    say_on_match: str = "感冒了么？",
    cooldown_sec: float = 30,
    **kwargs,
):
    if runtime.RUNNER is None:
        return {
            "speak": "现在还启动不了监视器。",
            "render": "[错误] 后台运行器未就绪，暂时无法开始监控纸巾画面。",
            "ui": {
                "type": "info_card",
                "title": "纸巾监控未启动",
                "message": "后台运行器未就绪，请稍后再试。",
            },
        }
    watcher_id = await runtime.RUNNER.add_vision_watcher(
        trigger=trigger,
        say_on_match=say_on_match,
        cooldown_sec=float(cooldown_sec),
        rate_hz=1.0,
    )
    return {
        "speak": "好，我会持续看着，看到纸巾就提醒你。",
        "render": f"已启动纸巾视觉监视器：{watcher_id}\n触发条件：{trigger}\n触发播报：{say_on_match}",
        "ui": {
            "type": "info_card",
            "title": "纸巾视觉监控已启动",
            "message": f"监视器 ID：{watcher_id}\n检测到纸巾时将播报：{say_on_match}",
        },
    }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
