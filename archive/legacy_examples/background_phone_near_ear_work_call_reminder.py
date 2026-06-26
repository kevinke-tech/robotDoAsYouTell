"""后台监视手机贴耳通话姿势并触发提醒。"""
import asyncio
import runtime

RUN_SPEC = {
    "name": "background_phone_near_ear_work_call_reminder",
    "description": "持续监视画面中的贴耳通话姿势并语音提醒。",
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {"type": "string", "default": "人物手持手机且手机明显贴近耳朵/脸部侧面，呈接打电话状态"},
            "cooldown_sec": {"type": "number", "default": 20},
            "rate_hz": {"type": "number", "default": 1.0},
        },
        "required": [],
        "additionalProperties": True,
    },
}


async def run(
    trigger: str = "人物手持手机且手机明显贴近耳朵/脸部侧面，呈接打电话状态",
    cooldown_sec: float = 20,
    rate_hz: float = 1.0,
    **kwargs,
):
    say_on_match = "上班不要打电话，谢谢！"
    ui_on_match = {
        "type": "info_card",
        "title": "检测到通话姿势",
        "message": "检测到人物手持手机并贴近耳侧，已触发提醒：上班不要打电话，谢谢！",
    }
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器，稍后再试。",
            "render": "[错误] 后台运行器未就绪\nsource: runtime.RUNNER\nevidence: RUNNER=None",
            "ui": {"type": "info_card", "title": "启动失败", "message": "后台运行器未就绪，暂时无法开启监视。"},
        }
    try:
        watcher_id = await runtime.RUNNER.add_vision_watcher(
            trigger=trigger,
            say_on_match=say_on_match,
            ui_on_match=ui_on_match,
            cooldown_sec=float(cooldown_sec),
            rate_hz=float(rate_hz),
        )
    except Exception as e:
        return {
            "speak": "监视器启动失败了，我先记下错误。",
            "render": f"[错误] 启动视觉监视器失败: {e}\nsource: runtime.RUNNER.add_vision_watcher\nevidence: trigger={trigger}",
            "ui": {"type": "info_card", "title": "启动失败", "message": f"视觉监视器启动失败：{e}"},
        }
    return {
        "speak": "好的，我会持续盯着，发现打电话姿势就提醒。",
        "render": (
            f"已启动视觉监视器: {watcher_id}\n"
            f"source: runtime.RUNNER.add_vision_watcher\n"
            f"evidence: trigger={trigger}; say_on_match={say_on_match}; cooldown_sec={float(cooldown_sec)}; rate_hz={float(rate_hz)}"
        ),
        "ui": {"type": "info_card", "title": "监视已开启", "message": "检测到贴耳通话姿势时将自动提醒。"},
    }


if __name__ == "__main__":
    runtime.RUNNER = None
    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result and "ui" in result
    print("OK")
