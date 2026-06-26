"""持续监视通话姿势，命中后进行语音提醒。"""
import runtime

RUN_SPEC = {
    "name": "background_phone_near_ear_call_pose_watcher",
    "description": "监视手机贴近耳朵的通话姿势并提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 20},
            "rate_hz": {"type": "number", "default": 1.0},
            "ui_on_match": {"type": "object"},
        },
    },
}


async def run(
    cooldown_sec: float = 20,
    rate_hz: float = 1.0,
    ui_on_match: dict | None = None,
    **kwargs,
):
    trigger = "画面中可见有人将手机贴近耳朵，或手持手机于耳边呈现通话姿势"
    say_on_match = "上班不要打电话！"
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器，稍后我再帮你盯着。",
            "render": "[错误] 后台运行器未就绪\nsource: runtime.RUNNER\nevidence: RUNNER is None",
            "ui": {"type": "info_card", "title": "监视器未启动", "message": "后台运行器未就绪"},
        }
    try:
        chosen_ui = ui_on_match if isinstance(ui_on_match, dict) else {
            "type": "info_card",
            "title": "已检测到通话姿势",
            "message": "上班不要打电话！",
        }
        watcher_id = await runtime.RUNNER.add_vision_watcher(
            trigger=trigger,
            say_on_match=say_on_match,
            ui_on_match=chosen_ui,
            cooldown_sec=float(cooldown_sec),
            rate_hz=float(rate_hz),
        )
        return {
            "speak": "好，我会持续看着，发现打电话姿势就马上提醒。",
            "render": (
                f"已启动视觉监视器: {watcher_id}\n"
                f"source: runtime.RUNNER.add_vision_watcher\n"
                f"evidence: trigger={trigger}; say_on_match={say_on_match}; "
                f"cooldown_sec={float(cooldown_sec)}; rate_hz={float(rate_hz)}"
            ),
            "ui": {
                "type": "info_card",
                "title": "通话姿势监视已开启",
                "message": f"监视器ID: {watcher_id}，命中后将播报“{say_on_match}”",
            },
        }
    except Exception as e:
        return {
            "speak": "监视器启动失败了，我可以再试一次。",
            "render": f"[失败] 启动视觉监视器异常\nsource: runtime.RUNNER.add_vision_watcher\nevidence: {e}",
            "ui": {"type": "info_card", "title": "启动失败", "message": str(e)},
        }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run(cooldown_sec=10, rate_hz=1.0))
    assert isinstance(result, dict) and "speak" in result and "render" in result and "ui" in result
    print("OK")
