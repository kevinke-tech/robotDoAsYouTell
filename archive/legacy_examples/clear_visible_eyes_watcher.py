"""后台监控眼睛是否清晰可见，命中后播报提醒。"""
import runtime

RUN_SPEC = {
    "name": "clear_visible_eyes_watcher",
    "description": "启动眼睛清晰可见的后台视觉监视器。",
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {
                "type": "string",
                "default": "人物的眼睛在画面中清晰可见且未被遮挡",
            },
            "say_on_match": {
                "type": "string",
                "default": "你近视么？注意保护眼睛",
            },
            "cooldown_sec": {"type": "number", "default": 30},
        },
        "required": [],
    },
}


async def run(
    trigger: str = "人物的眼睛在画面中清晰可见且未被遮挡",
    say_on_match: str = "你近视么？注意保护眼睛",
    cooldown_sec: float = 30,
    **kwargs
):
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监控。",
            "render": "[错误] 后台运行器未就绪\nsource: runtime.RUNNER",
            "ui": {
                "type": "info_card",
                "title": "视觉监控未启动",
                "message": "后台运行器未就绪，请稍后重试。",
            },
        }
    watcher_id = await runtime.RUNNER.add_vision_watcher(
        trigger=trigger,
        say_on_match=say_on_match,
        cooldown_sec=float(cooldown_sec),
        rate_hz=1.0,
    )
    return {
        "speak": "好的，我会盯着画面，看到眼睛清晰可见就提醒你。",
        "render": (
            f"已启动视觉监视器: {watcher_id}\n"
            f"触发条件: {trigger}\n"
            f"提醒语: {say_on_match}\n"
            "source: runtime.RUNNER.add_vision_watcher"
        ),
        "ui": {
            "type": "info_card",
            "title": "眼睛可见监控已启动",
            "message": f"当检测到眼睛清晰可见且无遮挡时，将提醒：{say_on_match}",
        },
    }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
