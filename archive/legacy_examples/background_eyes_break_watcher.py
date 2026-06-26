"""后台视觉监视：检测到人眼清晰可见时提醒护眼。"""
import runtime

RUN_SPEC = {
    "name": "background_eyes_break_watcher",
    "description": "启动护眼视觉监视器，检测到人眼可见时播报提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {
                "type": "string",
                "default": "画面中人脸上双眼或至少一只眼睛清晰可见",
            },
            "say_on_match": {
                "type": "string",
                "default": "Please remember to protect your eyes — take a break, look away from the screen, and rest your eyes for a moment.",
            },
            "cooldown_sec": {"type": "number", "default": 30},
            "rate_hz": {"type": "number", "default": 1.0},
        },
    },
}


async def run(
    trigger: str = "画面中人脸上双眼或至少一只眼睛清晰可见",
    say_on_match: str = "Please remember to protect your eyes — take a break, look away from the screen, and rest your eyes for a moment.",
    cooldown_sec: float = 30,
    rate_hz: float = 1.0,
    **kwargs,
):
    del kwargs
    if runtime.RUNNER is None:
        return {
            "speak": "现在还不能启动护眼监视器。",
            "render": "[错误] 后台运行器未就绪\nsource: runtime.RUNNER\nevidence: RUNNER is None",
            "ui": {"type": "info_card", "title": "护眼监视器未启动", "message": "后台运行器未就绪，请稍后重试。"},
        }
    try:
        watcher_id = await runtime.RUNNER.add_vision_watcher(
            trigger=trigger,
            say_on_match=say_on_match,
            cooldown_sec=float(cooldown_sec),
            rate_hz=float(rate_hz),
        )
        return {
            "speak": "好的，我会持续看画面，检测到眼睛清晰可见就提醒你休息。",
            "render": (
                f"已启动护眼视觉监视器: {watcher_id}\n"
                f"触发条件: {trigger}\n"
                f"提醒语: {say_on_match}\n"
                "source: runtime.RUNNER.add_vision_watcher\n"
                f"evidence: cooldown_sec={float(cooldown_sec)}, rate_hz={float(rate_hz)}"
            ),
            "ui": {
                "type": "info_card",
                "title": "护眼监视已开启",
                "message": f"已开始逐帧监看；满足条件后将播报指定提醒。监视器ID: {watcher_id}",
            },
        }
    except Exception as exc:
        return {
            "speak": "护眼监视器启动失败了，我可以再试一次。",
            "render": f"[失败] 启动监视器异常: {exc}\nsource: runtime.RUNNER.add_vision_watcher\nevidence: exception_caught",
            "ui": {"type": "info_card", "title": "护眼监视启动失败", "message": f"原因: {exc}"},
        }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    print("OK")
