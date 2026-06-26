"""Programmatically generated background vision watcher skill."""
from __future__ import annotations
import runtime

RUN_SPEC = {
    "name": "dynamic_vision_watcher_74ef2d",
    "description": "动态创建：启动一个视觉触发实例。",
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {"type": "string", "default": "the requested condition is clearly visible in the camera frame"},
            "say_on_match": {"type": "string", "default": "已检测到触发条件"},
            "cooldown_sec": {"type": "number", "default": 30},
            "rate_hz": {"type": "number", "default": 1.0},
        },
        "required": [],
    },
}

async def run(trigger: str = "the requested condition is clearly visible in the camera frame", say_on_match: str = "已检测到触发条件", cooldown_sec: float = 30, rate_hz: float = 1.0, **kwargs):
    if runtime.RUNNER is None:
        return {"speak": "现在还不能启动视觉监视。", "render": "[错误] RUNNER 未就绪"}
    id_ = await runtime.RUNNER.add_vision_watcher(
        trigger=str(trigger),
        say_on_match=str(say_on_match),
        cooldown_sec=float(cooldown_sec),
        rate_hz=float(rate_hz),
    )
    return {
        "speak": "好的，我已经开始盯着看了。",
        "render": f"已创建视觉实例: {id_}\ntrigger: {trigger}\nsay_on_match: {say_on_match}\ncooldown_sec: {cooldown_sec}\nrate_hz: {rate_hz}",
    }

if __name__ == "__main__":
    import inspect
    assert isinstance(RUN_SPEC, dict) and RUN_SPEC.get("name")
    assert inspect.iscoroutinefunction(run)
    print("OK")
