"""后台监视画面中的手机贴耳通话姿态, 检测到就语音提醒。"""
from datetime import datetime, timezone

import runtime

RUN_SPEC = {
    "name": "phone_call_vision_watcher",
    "description": "监视人物是否把手机贴近耳侧通话, 命中后播报“上班不要打电话！”。参数: cooldown_sec。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 30},
        },
        "required": [],
    },
}

PHONE_CALL_TRIGGER = (
    "Watch the camera feed frame by frame. Trigger when the person in frame is clearly "
    "holding a mobile phone up to their ear or visibly talking on a phone call — i.e., "
    "a phone is pressed against or near the side of their face/ear, or they are clearly "
    "holding a phone in a phone-call posture."
)
ALERT_TEXT = "上班不要打电话！"


async def run(cooldown_sec: float = 30, **kwargs):
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动这个监视器。",
            "render": "状态: 启动失败\n信息来源: runtime.RUNNER\nsource_url: local://background_runner\n关键字段: RUNNER=None",
            "ui": {
                "type": "info_card",
                "title": "手机通话监视器",
                "message": "后台运行器未就绪, 暂时无法开始监视。",
            },
        }
    watcher_id = await runtime.RUNNER.add_vision_watcher(
        trigger=PHONE_CALL_TRIGGER,
        say_on_match=ALERT_TEXT,
        cooldown_sec=float(cooldown_sec),
        rate_hz=1.0,
    )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "speak": "好的, 我会盯着看, 发现有人拿手机贴耳通话就提醒。",
        "render": (
            f"已启动视觉监视器: {watcher_id}\n"
            f"触发后播报: {ALERT_TEXT}\n"
            f"信息来源: runtime.RUNNER.add_vision_watcher\n"
            f"source_url: local://camera_feed\n"
            f"关键字段: trigger=phone_call_posture, cooldown_sec={float(cooldown_sec)}, timestamp_utc={now}"
        ),
        "ui": {
            "type": "info_card",
            "title": "手机通话监视中",
            "message": f"已启动监视器 {watcher_id}。检测到手机贴耳通话姿态时会播报“{ALERT_TEXT}”。",
        },
    }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run(cooldown_sec=12))
    assert isinstance(result, dict)
    assert {"speak", "render", "ui"}.issubset(result)
    print("OK")
