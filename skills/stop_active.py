"""按 id 或标签子串停掉一个运行中的后台技能。"""

import runtime

RUN_SPEC = {
    "name": "stop_active",
    "description": (
        "停掉一个运行中的后台技能。用户可能说 '停掉笔的监视器'、'取消那个提醒'、"
        "'算了不用了'、'别再看了'。identifier 参数可以传精确 id"
        "(如 'timer_abc12345')或标签/触发条件的子串做模糊匹配。多个匹配时停第一个。"
        "用户说 '全部停掉' 时传 identifier='*'。"
    ),
    "args_schema": {
        "type": "object",
        "properties": {
            "identifier": {
                "type": "string",
                "description": "精确 id、标签子串、或 '*' 表示全部。",
            }
        },
        "required": ["identifier"],
    },
}


async def run(identifier: str, **kwargs):
    if runtime.RUNNER is None:
        return {"speak": "没有可以停的任务。", "render": "(后台运行器未就绪)"}

    ident = (identifier or "").strip()
    if ident == "*":
        n = await runtime.RUNNER.stop_all()
        if n == 0:
            return {"speak": "没有运行中的任务。", "render": "(已停 0 个)"}
        return {"speak": f"已停掉 {n} 个。", "render": f"已停 {n} 个后台技能"}

    items = runtime.RUNNER.list()
    target = None
    # 先按精确 id 匹配
    for it in items:
        if it["id"] == ident:
            target = it["id"]
            break
    # 再按标签子串匹配
    if not target:
        ident_low = ident.lower()
        for it in items:
            if ident_low in (it.get("label", "") or "").lower():
                target = it["id"]
                break

    if not target:
        return {
            "speak": "没找到对应的任务。",
            "render": f"未匹配到 {identifier!r};当前运行中: {[i['id'] for i in items]}",
        }
    ok = await runtime.RUNNER.stop(target)
    if ok:
        return {"speak": "已停掉了。", "render": f"已停 {target}"}
    return {"speak": "停不掉。", "render": f"停止 {target} 失败"}


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(run("*"))
    assert isinstance(r, dict) and "speak" in r
    print("OK")
