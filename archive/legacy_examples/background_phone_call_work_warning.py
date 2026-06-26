"""后台监视摄像头中的打电话姿势并提醒。"""
import asyncio

import runtime

RUN_SPEC = {
    "name": "background_phone_call_work_warning",
    "description": "检测手机贴耳或近脸通话姿势并提醒上班不要打电话。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 20},
            "ui_on_match": {"type": "object"},
        },
    },
}


async def run(cooldown_sec: float = 20, ui_on_match: dict | None = None, **kwargs):
    trigger = (
        "画面中人物明显把手机贴在耳边，或手持手机靠近嘴边并呈现通话姿势"
    )
    say_on_match = "上班不要打电话！"
    match_ui = (
        ui_on_match
        if isinstance(ui_on_match, dict)
        else {
            "type": "info_card",
            "title": "检测到通话姿势",
            "message": "已识别到手机贴耳或近脸通话动作，提醒：上班不要打电话！",
        }
    )
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器。",
            "render": (
                "[错误] 后台运行器未就绪\n"
                "source: runtime.RUNNER\n"
                f"evidence: trigger={trigger}; say_on_match={say_on_match}"
            ),
            "ui": {"type": "info_card", "title": "启动失败", "message": "后台运行器未就绪"},
        }
    watcher_id = await runtime.RUNNER.add_vision_watcher(
        trigger=trigger,
        say_on_match=say_on_match,
        ui_on_match=match_ui,
        cooldown_sec=float(cooldown_sec),
        rate_hz=1.0,
    )
    return {
        "speak": "好的，我会盯着看，发现打电话姿势就提醒。",
        "render": (
            f"已启动视觉监视器: {watcher_id}\n"
            f"触发条件: {trigger}\n"
            "提醒语: 上班不要打电话！\n"
            "source: runtime vision watcher\n"
            "evidence: 检测要点=手机贴耳/手持近脸通话姿势; rate_hz=1.0"
        ),
        "ui": {
            "type": "info_card",
            "title": "通话姿势监视已开启",
            "message": "检测到手机贴耳或近脸通话动作时，将播报：上班不要打电话！",
        },
    }


if __name__ == "__main__":
    runtime.RUNNER = None
    result = asyncio.run(run(cooldown_sec=10))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
