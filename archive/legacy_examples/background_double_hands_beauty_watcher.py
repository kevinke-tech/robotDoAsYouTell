"""持续监视摄像头，双手举起时播报并展示美女图片。"""
import runtime

RUN_SPEC = {
    "name": "background_double_hands_beauty_watcher",
    "description": "监视人物双手抬至肩部或以上，触发后播报并展示美女图片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 30},
            "rate_hz": {"type": "number", "default": 1.0},
            "image_url": {
                "type": "string",
                "default": "https://source.unsplash.com/featured/?beautiful,woman",
            },
        },
    },
}


async def run(cooldown_sec: float = 30, rate_hz: float = 1.0, image_url: str = "", **kwargs):
    trigger = "画面中的人物双手明显举起，双臂抬至肩部或以上位置"
    say_text = "好的，美女来了！"
    final_image = image_url or "https://source.unsplash.com/featured/?beautiful,woman"
    base = {
        "speak": "好的，我会持续盯着看，发现双手举起就提醒你。",
        "render": (
            "已配置后台视觉监视。\n"
            f"触发条件: {trigger}\n"
            f"触发播报: {say_text}\n"
            "source: Unsplash Source\n"
            f"source_url: {final_image}"
        ),
        "ui": {
            "type": "image_card",
            "title": "触发后展示图片",
            "image_url": final_image,
            "caption": "检测到双手明显举起后，TTS 将播报：好的，美女来了！",
        },
    }
    if runtime.RUNNER is None:
        base["speak"] = "现在还没法启动监视器，不过配置已经准备好了。"
        base["render"] = "[错误] 后台运行器未就绪\n" + base["render"]
        return base
    try:
        watcher_id = await runtime.RUNNER.add_vision_watcher(
            trigger=trigger,
            say_on_match=say_text,
            cooldown_sec=float(cooldown_sec),
            rate_hz=float(rate_hz),
        )
        base["render"] = f"已启动视觉监视器: {watcher_id}\n" + base["render"]
        return base
    except Exception as exc:
        base["speak"] = "监视器启动失败了，我先把失败原因告诉你。"
        base["render"] = f"[错误] 启动失败: {exc}\n" + base["render"]
        return base


if __name__ == "__main__":
    import asyncio
    import runtime

    runtime.RUNNER = None
    result = asyncio.run(run(cooldown_sec=10, rate_hz=1.0))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
