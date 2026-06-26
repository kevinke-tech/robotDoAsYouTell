"""10 秒后提醒去吃饭。"""
import runtime
import skill_manifest

RUN_SPEC = {
    "name": "lunch_timer",
    "description": '安排一次提醒：10 秒后播报“该去吃饭了！”。',
    "args_schema": {"type": "object", "properties": {}, "required": []},
}


async def run(**kwargs):
    delay_seconds = 10.0
    message = "该去吃饭了！"
    if runtime.RUNNER is None:
        return {
            "speak": "现在还没法定时提醒。",
            "render": "[错误] 后台运行器未就绪，无法安排 10 秒后提醒。",
            "ui": {
                "type": "info_card",
                "title": "定时提醒失败",
                "message": "后台运行器未就绪，请稍后再试。",
            },
        }
    timer_id = await runtime.RUNNER.add_timer(delay_seconds, message)
    return {
        "speak": "好，十秒后我会提醒你该去吃饭了。",
        "render": (
            f"已安排定时提醒：{timer_id}\n"
            f"触发时间：{delay_seconds:.0f} 秒后\n"
            f"提醒内容：{message}"
        ),
        "ui": {
            "type": "info_card",
            "title": "定时提醒已创建",
            "message": f"{delay_seconds:.0f} 秒后提醒：{message}",
        },
    }


if __name__ == "__main__":
    import asyncio
    import runtime

    runtime.RUNNER = None
    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result and "ui" in result
    print("OK")
