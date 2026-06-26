"""持续监控贴耳打电话姿势，命中时提醒。"""
import runtime

RUN_SPEC = {
    "name": "phone_call_vision_watcher",
    "description": "监控清晰可见的贴耳通话姿势，命中后提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 20},
            "rate_hz": {"type": "number", "default": 1.0},
        },
        "required": [],
    },
}


async def run(cooldown_sec: float = 20, rate_hz: float = 1.0, **kwargs):
    trigger = "画面中清晰可见用户手持手机贴近耳边、呈通话姿势（如贴耳讲话或持续贴耳聆听）即触发。"
    say_on_match = "上班不要打电话！"
    ui_on_match = {"type": "info_card", "title": "检测到打电话", "message": "已识别到贴耳通话姿势，已触发提醒：上班不要打电话！"}
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监控。",
            "render": "[错误] 后台运行器未就绪\nsource: runtime.RUNNER\nevidence: RUNNER is None",
            "ui": {"type": "info_card", "title": "启动失败", "message": "后台运行器未就绪，暂时无法开始监控。"},
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
            "speak": "好，我会盯着看，发现就提醒。",
            "render": (
                f"已启动视觉监视器: {watcher_id}\ntrigger: {trigger}\n"
                f"source: runtime.RUNNER.add_vision_watcher\nevidence: say_on_match={say_on_match}, cooldown_sec={float(cooldown_sec)}, rate_hz={float(rate_hz)}"
            ),
            "ui": {"type": "info_card", "title": "电话姿势监控已启动", "message": "检测到手机贴耳通话姿势时，将播报：上班不要打电话！"},
        }
    except Exception as exc:
        return {
            "speak": "监控启动失败了，我先记下原因。",
            "render": f"[失败] 启动视觉监视器异常\nsource: runtime.RUNNER.add_vision_watcher\nevidence: {type(exc).__name__}: {exc}",
            "ui": {"type": "info_card", "title": "启动失败", "message": f"{type(exc).__name__}: {exc}"},
        }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    out = asyncio.run(run(cooldown_sec=10, rate_hz=1.0))
    assert isinstance(out, dict) and "speak" in out and "render" in out
    print("OK")
