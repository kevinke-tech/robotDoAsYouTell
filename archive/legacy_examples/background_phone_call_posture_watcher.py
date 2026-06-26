"""持续监视摄像头，检测打电话姿势后提醒。"""
import runtime

RUN_SPEC = {
    "name": "background_phone_call_posture_watcher",
    "description": "监视手机贴耳或打电话姿势，命中后语音提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {
                "type": "string",
                "default": "画面中的人物将手机贴近耳朵、或呈现明显的打电话姿势（手持手机靠近头部/耳朵）",
            },
            "say_on_match": {"type": "string", "default": "上班不要打电话！"},
            "ui_on_match": {"type": "object"},
            "cooldown_sec": {"type": "number", "default": 15},
        },
    },
}


async def run(
    trigger: str = "画面中的人物将手机贴近耳朵、或呈现明显的打电话姿势（手持手机靠近头部/耳朵）",
    say_on_match: str = "上班不要打电话！",
    ui_on_match: dict | None = None,
    cooldown_sec: float = 15,
    **kwargs,
):
    default_ui_on_match = {
        "type": "info_card",
        "title": "电话姿势告警",
        "message": "检测到手机贴耳或打电话姿势，上班不要打电话！",
    }
    effective_ui_on_match = ui_on_match if isinstance(ui_on_match, dict) else default_ui_on_match
    base_ui = {
        "type": "info_card",
        "title": "监视器已配置",
        "message": "持续监视手机贴耳/打电话姿势，命中后将立即语音提醒。",
    }
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器，稍后我再试。",
            "render": "未启动监视器\nsource: runtime.RUNNER\nevidence: 背景运行器未就绪，无法注册视觉监视任务",
            "ui": base_ui,
        }
    try:
        watcher_id = await runtime.RUNNER.add_vision_watcher(
            trigger=trigger,
            say_on_match=say_on_match,
            ui_on_match=effective_ui_on_match,
            cooldown_sec=float(cooldown_sec),
            rate_hz=1.0,
        )
        return {
            "speak": "好，我会持续盯着看，发现就马上提醒。",
            "render": (
                f"已启动视觉监视器: {watcher_id}\n"
                f"source: runtime.RUNNER.add_vision_watcher\n"
                f"evidence: trigger={trigger}; say_on_match={say_on_match}; cooldown_sec={float(cooldown_sec)}"
            ),
            "ui": base_ui,
        }
    except Exception as exc:
        return {
            "speak": "监视器启动失败了，我先记下原因。",
            "render": (
                "启动视觉监视器失败\n"
                "source: runtime.RUNNER.add_vision_watcher\n"
                f"evidence: {type(exc).__name__}: {exc}"
            ),
            "ui": {"type": "info_card", "title": "启动失败", "message": "视觉监视器未成功启动，请稍后重试。"},
        }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result and "ui" in result
    print("OK")
