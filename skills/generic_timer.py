"""设定一个一次性的语音提醒,延时后触发。"""

import runtime

RUN_SPEC = {
    "name": "generic_timer",
    "description": (
        "设定一个一次性的语音提醒,在指定延时后触发。适用于 'N 分钟后提醒我 X'、"
        "'10 秒后告诉我 Y'、'1 小时后叫我做 Z' 之类的请求。参数: "
        "delay_seconds(延时秒数)、message(到时要说的话)。"
    ),
    "args_schema": {
        "type": "object",
        "properties": {
            "delay_seconds": {
                "type": "number",
                "description": "延时秒数。",
            },
            "message": {
                "type": "string",
                "description": "到时要说的话。",
            },
        },
        "required": ["delay_seconds", "message"],
    },
}


def _human_delay_zh(seconds: float) -> str:
    if seconds >= 3600:
        h = seconds / 3600
        return f"{h:.0f} 小时"
    if seconds >= 60:
        m = seconds / 60
        return f"{m:.0f} 分钟"
    return f"{int(round(seconds))} 秒"


async def run(delay_seconds: float, message: str, **kwargs):
    if runtime.RUNNER is None:
        return {"speak": "现在还没法定时。", "render": "[错误] 后台运行器未就绪"}
    id_ = await runtime.RUNNER.add_timer(float(delay_seconds), message)
    return {
        "speak": f"好的,{_human_delay_zh(float(delay_seconds))}后提醒你。",
        "render": f"已设定提醒: {id_},{delay_seconds} 秒后触发 — {message!r}",
    }


if __name__ == "__main__":
    import asyncio
    # runtime.RUNNER is None during smoke test — exercise the no-runner branch.
    r = asyncio.run(run(10, "测试"))
    assert isinstance(r, dict) and "speak" in r
    print("OK")
