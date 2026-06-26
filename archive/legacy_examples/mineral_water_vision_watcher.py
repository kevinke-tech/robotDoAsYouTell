"""持续监视画面中的矿泉水瓶，出现就提醒活动。"""
import runtime

RUN_SPEC = {
    "name": "mineral_water_vision_watcher",
    "description": "持续监视画面中的矿泉水瓶，出现时语音提醒活动。参数：cooldown_sec。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 30},
        },
        "required": [],
    },
}

_TRIGGER = "画面中任意位置清晰可见矿泉水瓶（桌上、手持或其他位置均算触发）"
_ALERT = "矿泉水出现啦！该站起来走走了，活动一下筋骨！"


async def run(cooldown_sec: float = 30, **kwargs):
    if runtime.RUNNER is None:
        return {
            "speak": "现在还启动不了监视器。",
            "render": "[错误] 后台运行器未就绪，暂时不能监视矿泉水瓶。",
            "ui": {
                "type": "info_card",
                "title": "矿泉水瓶监视器",
                "message": "后台运行器未就绪，请稍后重试。",
            },
        }

    watcher_id = await runtime.RUNNER.add_vision_watcher(
        trigger=_TRIGGER,
        say_on_match=_ALERT,
        cooldown_sec=float(cooldown_sec),
        rate_hz=1.0,
    )
    return {
        "speak": "好，我会盯着看，看到矿泉水瓶就提醒你活动。",
        "render": (
            f"已启动矿泉水瓶视觉监视器：{watcher_id}\n"
            f"触发条件：{_TRIGGER}\n"
            f"提醒文案：{_ALERT}"
        ),
        "ui": {
            "type": "info_card",
            "title": "矿泉水瓶监视中",
            "message": "检测到矿泉水瓶时会自动播报活动提醒。",
        },
    }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run(cooldown_sec=12))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
