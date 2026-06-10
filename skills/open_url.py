"""在 agent 的持久化浏览器里打开一个 URL,可选保存截图。"""

from datetime import datetime
from pathlib import Path

import runtime

SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "logs" / "screenshots"

RUN_SPEC = {
    "name": "open_url",
    "description": (
        "在 agent 的持久化浏览器里打开一个 URL,返回页面标题,可选保存截图。"
        "适用于 '打开 hacker news'、'去 github.com'、'访问 <url>' 之类的请求。"
        "用户想 '看看页面长什么样' 时,设 screenshot=true。"
    ),
    "args_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": (
                    "要打开的 URL。缺 http(s):// 前缀时自动补 https://。"
                    "常见站点没给完整 URL 时(如 '打开 hacker news'),"
                    "用对应的官方域名(news.ycombinator.com)。"
                ),
            },
            "screenshot": {
                "type": "boolean",
                "description": "为 true 时把页面截图保存到 logs/screenshots/。",
                "default": False,
            },
        },
        "required": ["url"],
    },
}


async def run(url: str, screenshot: bool = False, **kwargs):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    title = ""
    shot_path = None
    async with runtime.new_page() as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        title = (await page.title() or "").strip()
        if screenshot:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            shot_path = SCREENSHOTS_DIR / f"{ts}.png"
            await page.screenshot(path=str(shot_path), full_page=False)

    speak_parts = [f"已打开 {url}。"]
    if title:
        speak_parts.append(f"页面标题: {title}。")
    speak = " ".join(speak_parts)

    render_lines = [f"URL: {url}", f"标题: {title or '(无标题)'}"]
    if shot_path:
        render_lines.append(f"截图: {shot_path}")

    return {"speak": speak, "render": "\n".join(render_lines)}


if __name__ == "__main__":
    # 浏览器技能的烟雾测试约定: 只校验形状,不调用 run() —— 合成阶段没有运行中的 Chromium。
    import inspect
    assert isinstance(RUN_SPEC, dict)
    assert RUN_SPEC.get("name") == "open_url"
    assert "args_schema" in RUN_SPEC
    assert inspect.iscoroutinefunction(run)
    print("OK")
