"""持续监视摄像头中的打电话姿势并提醒。"""
import runtime

RUN_SPEC = {
    "name": "background_phone_near_ear_call_watcher",
    "description": "监视画面中的打电话姿势并触发提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 30},
            "rate_hz": {"type": "number", "default": 1.0},
            "ui_on_match": {"type": "object"},
        },
        "required": [],
    },
}


async def run(
    cooldown_sec: float = 30,
    rate_hz: float = 1.0,
    ui_on_match: dict | None = None,
    **kwargs,
):
    trigger = "画面中的人物将手机贴近耳朵，或呈现明显打电话姿势（手持手机靠近头部/耳朵）"
    say_on_match = "上班不要打电话！"
    default_ui = {
        "type": "info_card",
        "title": "电话姿势告警",
        "message": "检测到有人正在打电话，请专注工作。",
    }
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器。",
            "render": "未启动：后台运行器未就绪\nsource: runtime.RUNNER\nevidence: RUNNER is None",
            "ui": {"type": "info_card", "title": "启动失败", "message": "后台运行器未就绪"},
        }
    try:
        watcher_id = await runtime.RUNNER.add_vision_watcher(
            trigger=trigger,
            say_on_match=say_on_match,
            ui_on_match=ui_on_match if isinstance(ui_on_match, dict) else default_ui,
            cooldown_sec=float(cooldown_sec),
            rate_hz=float(rate_hz),
        )
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        return {
            "speak": "监视器启动失败了，我先记下这个问题。",
            "render": f"启动失败\nsource: runtime.RUNNER.add_vision_watcher\nevidence: {reason}",
            "ui": {"type": "info_card", "title": "启动失败", "message": reason},
        }
    return {
        "speak": "好的，我会盯着电话姿势，发现就提醒。",
        "render": (
            f"已启动视觉监视器: {watcher_id}\n"
            f"触发条件: {trigger}\n"
            "触发播报: 上班不要打电话！\n"
            "source: 用户需求\n"
            "evidence: 关键姿势=手机贴耳/手持手机靠近耳脸部"
        ),
        "ui": {
            "type": "info_card",
            "title": "电话姿势监视已启动",
            "message": "命中后将播报：上班不要打电话！",
        },
    }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(
        run(cooldown_sec=10, rate_hz=1.0, ui_on_match={"type": "info_card", "title": "测试", "message": "结构检查"})
    )
    assert isinstance(result, dict) and "speak" in result and "render" in result and "ui" in result
    print("OK")
