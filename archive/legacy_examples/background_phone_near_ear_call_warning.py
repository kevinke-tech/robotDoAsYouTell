"""后台监视摄像头中的打电话姿势并触发提醒。"""
import runtime

RUN_SPEC = {
    "name": "background_phone_near_ear_call_warning",
    "description": "持续监视手机贴耳或打电话姿势并播报提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {"type": "string", "default": "手机贴近耳朵或打电话姿势"},
            "say_on_match": {"type": "string", "default": "上班不要打电话，谢谢！"},
            "ui_on_match": {"type": "object"},
            "cooldown_sec": {"type": "number", "default": 20},
            "rate_hz": {"type": "number", "default": 1.0},
        },
    },
}


async def run(
    trigger: str = "手机贴近耳朵或打电话姿势",
    say_on_match: str = "上班不要打电话，谢谢！",
    ui_on_match: dict | None = None,
    cooldown_sec: float = 20,
    rate_hz: float = 1.0,
    **kwargs,
):
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器，稍后再试一下。",
            "render": (
                "[错误] 后台运行器未就绪\n"
                "source: runtime.RUNNER.add_vision_watcher\n"
                "evidence: runner_state=None"
            ),
            "ui": {"type": "info_card", "title": "监视器未启动", "message": "后台运行器未就绪，请稍后重试。"},
        }
    trigger_ui = ui_on_match if isinstance(ui_on_match, dict) else {
        "type": "info_card",
        "title": "电话行为提醒",
        "message": "检测到手机贴耳或打电话姿势，已播报提醒：上班不要打电话，谢谢！",
    }
    watcher_id = await runtime.RUNNER.add_vision_watcher(
        trigger=trigger,
        say_on_match=say_on_match,
        ui_on_match=trigger_ui,
        cooldown_sec=float(cooldown_sec),
        rate_hz=float(rate_hz),
    )
    return {
        "speak": "好的，我会持续看着，发现打电话姿势就提醒。",
        "render": (
            f"已启动视觉监视器: {watcher_id}\n"
            f"触发条件: {trigger}\n"
            f"触发播报: {say_on_match}\n"
            f"source: runtime.RUNNER.add_vision_watcher\n"
            f"evidence: cooldown_sec={float(cooldown_sec)}, rate_hz={float(rate_hz)}"
        ),
        "ui": {"type": "info_card", "title": "监视已开启", "message": f"正在监视：{trigger}"},
    }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    r = asyncio.run(run())
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
