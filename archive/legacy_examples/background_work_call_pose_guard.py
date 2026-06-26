"""后台监视打电话姿势, 命中时语音提醒。"""
import runtime

RUN_SPEC = {
    "name": "background_work_call_pose_guard",
    "description": "持续监视画面, 检测手机贴耳或打电话姿势并提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 20},
            "rate_hz": {"type": "number", "default": 1.0},
        },
    },
}


async def run(cooldown_sec: float = 20, rate_hz: float = 1.0, **kwargs):
    trigger = "画面中的人出现手机贴近耳朵, 或明显做出打电话姿势(手持手机靠近耳部/脸颊)"
    say_on_match = "上班不要打电话，谢谢！"
    ui_on_match = {
        "type": "info_card",
        "title": "已检测到打电话姿势",
        "message": "上班不要打电话，谢谢！",
    }
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器。",
            "render": (
                "[错误] 后台运行器未就绪\n"
                "source: runtime.RUNNER\n"
                f"evidence: trigger={trigger}"
            ),
            "ui": {
                "type": "info_card",
                "title": "监视器未启动",
                "message": "后台运行器未就绪，请稍后再试。",
            },
        }
    try:
        watcher_id = await runtime.RUNNER.add_vision_watcher(
            trigger=trigger,
            say_on_match=say_on_match,
            ui_on_match=ui_on_match,
            cooldown_sec=float(cooldown_sec),
            rate_hz=float(rate_hz),
        )
        return {
            "speak": "好的，我会持续看着，发现打电话就提醒。",
            "render": (
                f"已启动视觉监视器: {watcher_id}\n"
                f"触发条件: {trigger}\n"
                f"触发播报: {say_on_match}\n"
                "source: runtime vision watcher\n"
                "evidence: phone_near_ear_or_call_pose"
            ),
            "ui": {
                "type": "info_card",
                "title": "打电话姿势监视已启动",
                "message": "检测到手机贴耳或打电话姿势时，会播报提醒。",
            },
        }
    except Exception as exc:
        return {
            "speak": "监视器启动失败了，我先记下原因。",
            "render": f"[失败] 启动视觉监视器异常: {exc}\nsource: runtime.add_vision_watcher",
            "ui": {"type": "info_card", "title": "启动失败", "message": str(exc)},
        }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run(cooldown_sec=10, rate_hz=1.0))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
