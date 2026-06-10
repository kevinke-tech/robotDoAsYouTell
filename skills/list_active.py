"""列出当前所有运行中的后台技能(定时器和视觉监视器)。"""

import runtime

RUN_SPEC = {
    "name": "list_active",
    "description": (
        "列出当前所有运行中的后台技能(定时器和视觉监视器)。"
        "用户问 '你在看什么'、'有哪些提醒'、'当前在运行什么' 等时调用。"
    ),
    "args_schema": {"type": "object", "properties": {}, "required": []},
}


_KIND_ZH = {"timer": "定时器", "vision": "视觉监视器"}


async def run(**kwargs):
    if runtime.RUNNER is None:
        return {"speak": "现在没有运行中的任务。", "render": "(后台运行器未就绪)"}
    items = runtime.RUNNER.list()
    if not items:
        return {"speak": "现在没有运行中的任务。", "render": "(无运行中的后台技能)"}

    spoken = []
    rendered = []
    for it in items:
        kind = it.get("kind", "?")
        kind_zh = _KIND_ZH.get(kind, kind)
        label = it.get("label", "?")
        id_ = it.get("id", "?")
        spoken.append(f"一个{kind_zh}: {label}")
        rendered.append(f"  - {id_} [{kind_zh}] {label}")

    speak_text = "当前运行中: " + ";".join(spoken) + "。"
    render_text = f"{len(items)} 个运行中:\n" + "\n".join(rendered)
    return {"speak": speak_text, "render": render_text}


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(run())
    assert isinstance(r, dict) and "speak" in r
    print("OK")
