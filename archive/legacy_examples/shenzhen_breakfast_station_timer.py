"""后台安排一次提醒，询问深圳地铁站附近早餐需求。"""
import runtime

RUN_SPEC = {
    "name": "shenzhen_breakfast_station_timer",
    "description": "安排一次提醒并询问要查深圳哪个地铁站附近的早餐。",
    "args_schema": {
        "type": "object",
        "properties": {
            "delay_seconds": {"type": "number", "default": 1},
            "message": {
                "type": "string",
                "default": "你想查深圳哪个地铁站附近的早餐店？",
            },
        },
        "additionalProperties": True,
    },
}


async def run(delay_seconds: float = 1, message: str = "你想查深圳哪个地铁站附近的早餐店？", **kwargs):
    prompt = str(message or "你想查深圳哪个地铁站附近的早餐店？")
    delay = float(delay_seconds) if delay_seconds is not None else 1.0
    if delay < 0:
        delay = 0.0
    if runtime.RUNNER is None:
        return {
            "speak": "你想查深圳哪个地铁站附近的早餐店？",
            "render": "后台运行器未就绪，暂未安排提醒。\n"
            "evidence: runner_ready=false; planned_delay_seconds="
            f"{delay}; planned_message={prompt}",
            "ui": {"type": "awaiting_slot", "slot": "station_name", "question": "你想查深圳哪个地铁站附近的早餐店？"},
        }
    try:
        timer_id = await runtime.RUNNER.add_timer(delay, prompt)
        return {
            "speak": "好呀，你想查深圳哪个地铁站附近的早餐店？",
            "render": f"已安排一次后台提醒：{timer_id}，将在 {delay} 秒后触发。\n"
            f"evidence: source=runtime.RUNNER.add_timer; timer_id={timer_id}; message={prompt}",
            "ui": {"type": "awaiting_slot", "slot": "station_name", "question": "你想查深圳哪个地铁站附近的早餐店？"},
        }
    except Exception as exc:
        return {
            "speak": "我先问你一句，你想查深圳哪个地铁站附近的早餐店？",
            "render": "安排后台提醒失败，但你现在就可以告诉我站点名。\n"
            f"evidence: source=runtime.RUNNER.add_timer; error={type(exc).__name__}: {exc}",
            "ui": {"type": "awaiting_slot", "slot": "station_name", "question": "你想查深圳哪个地铁站附近的早餐店？"},
        }


if __name__ == "__main__":
    import asyncio

    runtime.RUNNER = None
    result = asyncio.run(run())
    assert isinstance(result, dict) and "speak" in result and "render" in result and "ui" in result
    print("OK")
