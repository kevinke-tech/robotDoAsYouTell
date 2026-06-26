"""后台监视手机贴耳或接打电话姿势。"""
import runtime

RUN_SPEC = {
    "name": "background_phone_near_ear_work_call_watcher",
    "description": "持续监视摄像头，发现手机贴耳或电话姿势时提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 30},
            "ui_on_match": {"type": "object"},
        },
        "required": [],
    },
}


async def run(cooldown_sec: float = 30, ui_on_match: dict | None = None, **kwargs):
    trigger = (
        "画面中的人物将手机贴近耳朵，或做出明显的接打电话姿势，"
        "例如手持手机靠近头部耳朵区域。"
    )
    say_on_match = "上班不要打电话！"
    default_ui = {
        "type": "info_card",
        "title": "电话姿势提醒",
        "message": "检测到手机贴耳或接打电话姿势：上班不要打电话！",
    }
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器。",
            "render": (
                "[错误] 后台运行器未就绪\n"
                "evidence:\n"
                "- source: runtime.RUNNER\n"
                f"- trigger: {trigger}\n"
                f"- say_on_match: {say_on_match}"
            ),
            "ui": {"type": "info_card", "title": "启动失败", "message": "后台运行器未就绪。"},
        }
    watcher_id = await runtime.RUNNER.add_vision_watcher(
        trigger=trigger,
        say_on_match=say_on_match,
        ui_on_match=ui_on_match if isinstance(ui_on_match, dict) else default_ui,
        cooldown_sec=float(cooldown_sec),
        rate_hz=1.0,
    )
    return {
        "speak": "好的，我会持续看着，发现就提醒。",
        "render": (
            f"已启动视觉监视器: {watcher_id}\n"
            f"触发条件: {trigger}\n"
            "evidence:\n"
            "- source: runtime.RUNNER.add_vision_watcher\n"
            f"- watcher_id: {watcher_id}\n"
            f"- say_on_match: {say_on_match}"
        ),
        "ui": {"type": "info_card", "title": "监视已启动", "message": "检测到电话姿势会立即提醒。"},
    }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run(cooldown_sec=10))
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    print("OK")
