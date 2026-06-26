"""后台监视: 发现手机贴耳通话姿态时提醒。"""
import runtime

RUN_SPEC = {
    "name": "background_phone_to_ear_call_alert",
    "description": "持续监视摄像头，检测到手机贴耳通话姿态时语音提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 20},
            "rate_hz": {"type": "number", "default": 1.0},
        },
    },
}


async def run(cooldown_sec: float = 20, rate_hz: float = 1.0, **kwargs):
    trigger = (
        "person is visibly holding a mobile phone to their ear in a phone-call posture; "
        "hand holding phone pressed against or near side of face/ear"
    )
    say_on_match = "上班不要打电话！"
    ui_on_match = {
        "type": "info_card",
        "title": "检测到打电话",
        "message": "识别到你正在把手机贴近耳朵通话，请尽快结束通话并回到工作状态。",
    }
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器。",
            "render": (
                "[错误] 后台运行器未就绪\n"
                "evidence: runtime.RUNNER is None; trigger=phone_to_ear_call_posture"
            ),
            "ui": {
                "type": "info_card",
                "title": "监视器未启动",
                "message": "后台运行器尚未就绪，暂时不能开始摄像头监视。",
            },
        }
    watcher_id = await runtime.RUNNER.add_vision_watcher(
        trigger=trigger,
        say_on_match=say_on_match,
        ui_on_match=ui_on_match,
        cooldown_sec=float(cooldown_sec),
        rate_hz=float(rate_hz),
    )
    return {
        "speak": "好的，我会持续盯着看，发现打电话就提醒。",
        "render": (
            f"已启动视觉监视器: {watcher_id}\n"
            f"触发播报: {say_on_match}\n"
            f"source: runtime.RUNNER.add_vision_watcher\n"
            f"evidence: trigger={trigger}; cooldown_sec={float(cooldown_sec)}; rate_hz={float(rate_hz)}"
        ),
        "ui": {
            "type": "info_card",
            "title": "打电话姿态监视中",
            "message": "当检测到手机贴耳通话姿态时，将立即播报：上班不要打电话！",
        },
    }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run(cooldown_sec=10, rate_hz=1.0))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
