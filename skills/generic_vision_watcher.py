"""持续盯着摄像头,看到指定状态就说出指定的话。"""

import runtime

RUN_SPEC = {
    "name": "generic_vision_watcher",
    "description": (
        "开启一个持续运行的摄像头监视器,看到指定的视觉条件就播报一句话。"
        "适用于 '看到 X 就告诉我'、'如果我做了 Y 就提醒我'、'画面里出现 Z 时通知我' 之类的请求。"
        "参数: trigger(对要观察的视觉条件的精确自然语言描述)、"
        "say_on_match(匹配时要说的话)、cooldown_sec(两次触发之间的最小间隔秒数,默认 30,"
        "慢事件加大,快事件减小)。"
    ),
    "args_schema": {
        "type": "object",
        "properties": {
            "trigger": {
                "type": "string",
                "description": (
                    "要观察的视觉条件,精确描述。"
                    "示例: 'a person raises their hand at or above shoulder height'。"
                    "注意触发判定模型用英文系统提示,所以 trigger 建议用英文写。"
                ),
            },
            "say_on_match": {
                "type": "string",
                "description": "匹配时播报的话(中文)。",
            },
            "cooldown_sec": {
                "type": "number",
                "description": "两次触发之间的最小间隔秒数。",
                "default": 30,
            },
        },
        "required": ["trigger", "say_on_match"],
    },
}


async def run(trigger: str, say_on_match: str, cooldown_sec: float = 30, **kwargs):
    if runtime.RUNNER is None:
        return {"speak": "现在还没法启动监视器。", "render": "[错误] 后台运行器未就绪"}
    id_ = await runtime.RUNNER.add_vision_watcher(
        trigger=trigger,
        say_on_match=say_on_match,
        cooldown_sec=float(cooldown_sec),
        rate_hz=1.0,
    )
    return {
        "speak": "好的,我盯着看,看到了就告诉你。",
        "render": (
            f"视觉监视器已启动: {id_}\n"
            f"  触发条件: {trigger}\n"
            f"  匹配时播报: {say_on_match}\n"
            f"  冷却: {cooldown_sec} 秒,采样率: 1 Hz"
        ),
    }


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(run("a hand is raised", "你举手了!"))
    assert isinstance(r, dict) and "speak" in r
    print("OK")
