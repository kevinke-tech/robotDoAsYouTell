"""后台视觉监视：检测手机贴耳通话姿势并提醒。"""
import runtime

RUN_SPEC = {
    "name": "background_phone_near_ear_call_guard",
    "description": "持续监视画面，检测手机贴近耳朵且呈通话姿势时提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 30},
            "trigger": {
                "type": "string",
                "default": "人物手持手机且手机清晰可见，位置贴近头部或耳朵，呈现接打电话姿势",
            },
            "say_on_match": {"type": "string", "default": "上班不要打电话！"},
            "ui_on_match": {"type": "object"},
        },
    },
}


async def run(
    cooldown_sec: float = 30,
    trigger: str = "人物手持手机且手机清晰可见，位置贴近头部或耳朵，呈现接打电话姿势",
    say_on_match: str = "上班不要打电话！",
    ui_on_match: dict | None = None,
    **kwargs,
):
    default_ui = {
        "type": "info_card",
        "title": "通话姿势提醒",
        "message": "检测到手机贴近耳朵并疑似通话：上班不要打电话！",
    }
    chosen_ui = ui_on_match if isinstance(ui_on_match, dict) else default_ui
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器。",
            "render": (
                "[错误] 后台运行器未就绪\n"
                "source: runtime.RUNNER\n"
                "evidence: RUNNER=None，未能调用 add_vision_watcher"
            ),
            "ui": {"type": "info_card", "title": "启动失败", "message": "后台运行器未就绪，请稍后重试。"},
        }

    watcher_id = await runtime.RUNNER.add_vision_watcher(
        trigger=trigger,
        say_on_match=say_on_match,
        ui_on_match=chosen_ui,
        cooldown_sec=float(cooldown_sec),
        rate_hz=1.0,
    )
    return {
        "speak": "好的，我会持续盯着看，发现就提醒你。",
        "render": (
            f"已启动视觉监视器: {watcher_id}\n"
            f"触发条件: {trigger}\n"
            f"冷却秒数: {float(cooldown_sec)}\n"
            "source: runtime.RUNNER.add_vision_watcher\n"
            "evidence: 手机清晰可见 + 靠近头部/耳朵 + 手持通话姿势"
        ),
        "ui": chosen_ui,
    }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run(cooldown_sec=12))
    assert isinstance(result, dict) and "speak" in result and "render" in result and "ui" in result
    assert "source:" in result["render"] or "evidence:" in result["render"]
    print("OK")
