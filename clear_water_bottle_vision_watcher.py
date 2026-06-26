"""持续监控画面，检测清晰可见的矿泉水瓶并触发提醒。"""
import asyncio

import runtime

RUN_SPEC = {
    "name": "clear_water_bottle_vision_watcher",
    "description": "监控摄像头，检测清晰可见矿泉水瓶后播报“好喝！”。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 30},
            "rate_hz": {"type": "number", "default": 1.0},
        },
        "required": [],
    },
}


async def run(cooldown_sec: float = 30, rate_hz: float = 1.0, **kwargs):
    trigger = (
        "画面中清晰可见一个矿泉水瓶（塑料透明或半透明饮用水瓶），"
        "明显可见即可，部分遮挡也算；但不能只是模糊背景轮廓。"
    )
    say_on_match = "好喝！"
    ui_on_match = {
        "type": "info_card",
        "title": "已发现矿泉水瓶",
        "message": "检测到画面中有清晰可见的矿泉水瓶，我要喝水！",
    }
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器。",
            "render": (
                "[错误] 后台运行器未就绪\n"
                "source: runtime.RUNNER\n"
                f"evidence: trigger={trigger}"
            ),
            "ui": {"type": "info_card", "title": "启动失败", "message": "后台运行器未就绪"},
        }
    try:
        watcher_id = await runtime.RUNNER.add_vision_watcher(
            trigger=trigger,
            say_on_match=say_on_match,
            ui_on_match=ui_on_match,
            cooldown_sec=float(cooldown_sec),
            rate_hz=float(rate_hz),
        )
    except Exception as exc:
        return {
            "speak": "监控启动失败了，我再试试。",
            "render": (
                "[失败] 启动视觉监视器异常\n"
                "source: runtime.RUNNER.add_vision_watcher\n"
                f"evidence: error={type(exc).__name__}: {exc}"
            ),
            "ui": {"type": "info_card", "title": "启动失败", "message": f"{type(exc).__name__}: {exc}"},
        }
    return {
        "speak": "好的，我会持续盯着看，看到矿泉水瓶就提醒你。",
        "render": (
            f"已启动视觉监视器: {watcher_id}\n"
            f"trigger: {trigger}\n"
            f"source: runtime.RUNNER.add_vision_watcher\n"
            f"evidence: say_on_match={say_on_match}, cooldown_sec={float(cooldown_sec)}, rate_hz={float(rate_hz)}"
        ),
        "ui": {
            "type": "info_card",
            "title": "矿泉水瓶监控已开启",
            "message": "当画面中清晰可见矿泉水瓶时，将播报“好喝！”。",
        },
    }


if __name__ == "__main__":
    runtime.RUNNER = None
    result = asyncio.run(run(cooldown_sec=10, rate_hz=1.0))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
