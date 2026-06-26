"""启动后台视觉监视：眼睛清晰可见时提醒护眼。"""
import runtime

RUN_SPEC = {
    "name": "eyes_visible_protection_watcher",
    "description": "监视人脸眼睛可见状态并播报护眼提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 30},
            "rate_hz": {"type": "number", "default": 1.0},
        },
    },
}


async def run(cooldown_sec: float = 30, rate_hz: float = 1.0, **kwargs):
    trigger = (
        "A person's eyes are clearly visible in the camera frame: both eyes, "
        "or at least one eye, are distinctly visible on a human face."
    )
    say_on_match = (
        "Please remember to protect your eyes — take a break, look away from the "
        "screen, and rest your eyes for a moment."
    )
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动护眼监视器。",
            "render": "[错误] 后台运行器未就绪\nsource: runtime.RUNNER\nevidence: state=None",
            "ui": {"type": "info_card", "title": "启动失败", "message": "后台运行器未就绪，暂时无法开始监视。"},
        }
    watcher_id = await runtime.RUNNER.add_vision_watcher(
        trigger=trigger, say_on_match=say_on_match, cooldown_sec=float(cooldown_sec), rate_hz=float(rate_hz)
    )
    return {
        "speak": "好的，我会持续看摄像头，检测到眼睛清晰可见就提醒你护眼。",
        "render": (
            f"已启动视觉监视器: {watcher_id}\n"
            f"触发条件: {trigger}\n"
            f"提醒话术: {say_on_match}\n"
            f"source: runtime.RUNNER.add_vision_watcher\n"
            f"evidence: cooldown_sec={float(cooldown_sec)}, rate_hz={float(rate_hz)}"
        ),
        "ui": {"type": "info_card", "title": "护眼监视已开启", "message": "检测到人脸眼睛清晰可见时，将自动播报你指定的英文护眼提醒。"},
    }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    r = asyncio.run(run(cooldown_sec=10, rate_hz=1.0))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
