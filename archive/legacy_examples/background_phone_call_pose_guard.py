"""持续监视画面中的打电话姿势并触发提醒。"""
import runtime

RUN_SPEC = {
    "name": "background_phone_call_pose_guard",
    "description": "监视人物将手机贴近耳朵或脸侧的打电话姿势并提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {"type": "string", "default": "画面中有人将手机贴近耳朵或手持手机靠近耳/脸部，明显处于打电话状态"},
            "say_on_match": {"type": "string", "default": "上班不要打电话！"},
            "cooldown_sec": {"type": "number", "default": 20},
            "rate_hz": {"type": "number", "default": 1.0},
            "ui_on_match": {"type": "object"},
        },
        "required": [],
    },
}


async def run(
    trigger: str = "画面中有人将手机贴近耳朵或手持手机靠近耳/脸部，明显处于打电话状态",
    say_on_match: str = "上班不要打电话！",
    cooldown_sec: float = 20,
    rate_hz: float = 1.0,
    ui_on_match: dict | None = None,
    **kwargs,
):
    if runtime.RUNNER is None:
        return {
            "speak": "现在还启动不了监视器，请稍后再试。",
            "render": "[错误] 后台运行器未就绪\nsource: runtime.RUNNER\nevidence: RUNNER is None",
            "ui": {"type": "info_card", "title": "监视器未启动", "message": "后台运行器未就绪，请稍后重试。"},
        }
    hit_ui = ui_on_match if isinstance(ui_on_match, dict) else {
        "type": "info_card",
        "title": "电话姿势告警",
        "message": "检测到有人疑似接打电话：上班不要打电话！",
    }
    try:
        watcher_id = await runtime.RUNNER.add_vision_watcher(
            trigger=trigger,
            say_on_match=say_on_match,
            ui_on_match=hit_ui,
            cooldown_sec=float(cooldown_sec),
            rate_hz=float(rate_hz),
        )
        return {
            "speak": "好，我会持续盯着，看到打电话姿势就提醒。",
            "render": (
                f"已启动视觉监视器: {watcher_id}\n"
                f"source: runtime.RUNNER.add_vision_watcher\n"
                f"evidence: trigger={trigger}; say_on_match={say_on_match}; cooldown_sec={float(cooldown_sec)}; rate_hz={float(rate_hz)}"
            ),
            "ui": {"type": "info_card", "title": "电话姿势监视中", "message": "检测到手机贴耳/靠脸打电话姿势时，将播报“上班不要打电话！”。"},
        }
    except Exception as e:
        return {
            "speak": "监视器启动失败了，我先记下原因。",
            "render": f"[错误] 启动视觉监视器失败\nsource: runtime.RUNNER.add_vision_watcher\nevidence: {type(e).__name__}: {e}",
            "ui": {"type": "info_card", "title": "启动失败", "message": f"{type(e).__name__}: {e}"},
        }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
