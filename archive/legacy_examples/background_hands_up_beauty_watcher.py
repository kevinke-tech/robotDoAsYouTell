"""后台监视双手举起动作, 触发后播报并返回美女图片卡片信息。"""
try:
    import runtime
except ModuleNotFoundError:
    class _RuntimeFallback:
        RUNNER = None
    runtime = _RuntimeFallback()

import httpx

IMAGE_SOURCE_URL = "https://source.unsplash.com/featured/?beautiful,woman"

RUN_SPEC = {
    "name": "background_hands_up_beauty_watcher",
    "description": "持续监视双手明显举起动作, 触发后播报“好的，美女来了！”。",
    "args_schema": {
        "type": "object",
        "properties": {
            "cooldown_sec": {"type": "number", "default": 30},
            "rate_hz": {"type": "number", "default": 1.0},
            "resolve_image": {"type": "boolean", "default": True},
        },
    },
}


async def run(cooldown_sec: float = 30, rate_hz: float = 1.0, resolve_image: bool = True, **kwargs):
    trigger = "画面中的人物双手明显举起，双臂抬至肩部或以上位置"
    say_on_match = "好的，美女来了！"
    image_url, evidence = IMAGE_SOURCE_URL, []
    if resolve_image:
        try:
            async with httpx.AsyncClient(timeout=2.0, follow_redirects=False) as client:
                resp = await client.get(IMAGE_SOURCE_URL)
            if resp.status_code in (301, 302, 303, 307, 308):
                image_url = resp.headers.get("location", IMAGE_SOURCE_URL)
                evidence.append(f"unsplash_redirect={resp.status_code}")
            else:
                evidence.append(f"unsplash_status={resp.status_code}")
        except Exception as e:
            evidence.append(f"unsplash_error={type(e).__name__}: {e}")
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法启动监视器。",
            "render": "[错误] 后台运行器未就绪\nsource: runtime.RUNNER\n"
                      f"source_url: {IMAGE_SOURCE_URL}\nevidence: {', '.join(evidence) or 'RUNNER is None'}",
            "ui": {"type": "info_card", "title": "启动失败", "message": "后台运行器未就绪，暂时无法开始监视。"},
        }
    try:
        watcher_id = await runtime.RUNNER.add_vision_watcher(
            trigger=trigger, say_on_match=say_on_match, cooldown_sec=float(cooldown_sec), rate_hz=float(rate_hz)
        )
    except Exception as e:
        return {
            "speak": "监视器启动失败了，我再试试。",
            "render": f"[错误] 启动视觉监视器失败: {e}\nsource: runtime.RUNNER.add_vision_watcher\n"
                      f"source_url: {IMAGE_SOURCE_URL}\nevidence: {', '.join(evidence) or 'none'}",
            "ui": {"type": "info_card", "title": "启动失败", "message": "视觉监视器调用失败，请稍后重试。"},
        }
    return {
        "speak": "好的，我会持续盯着看，检测到双手举起就播报。",
        "render": f"已启动视觉监视器: {watcher_id}\n触发条件: {trigger}\n触发播报: {say_on_match}\n"
                  f"source: Unsplash featured + runtime watcher\nsource_url: {IMAGE_SOURCE_URL}\n"
                  f"evidence: {', '.join(evidence) or 'image_source_url_used'}",
        "ui": {"type": "image_card", "title": "美女图片（触发后播报）", "image_url": image_url, "caption": "来源：Unsplash"},
    }


if __name__ == "__main__":
    import asyncio
    runtime.RUNNER = None
    r = asyncio.run(run(cooldown_sec=10, rate_hz=1.0, resolve_image=False))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
