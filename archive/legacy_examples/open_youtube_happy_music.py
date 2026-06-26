"""一次性技能：打开 YouTube 愉快背景音乐搜索页。"""
from datetime import datetime, timezone
import webbrowser

RUN_SPEC = {
    "name": "open_youtube_happy_music",
    "description": "在系统默认浏览器中打开 YouTube 的 happy upbeat background music 搜索页。",
    "args_schema": {
        "type": "object",
        "properties": {
            "task_input": {"type": "string", "default": ""},
        },
        "required": [],
    },
}

YOUTUBE_URL = "https://www.youtube.com/results?search_query=happy+upbeat+background+music"


async def run(task_input: str = "", **kwargs):
    opened = webbrowser.open(YOUTUBE_URL)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    speak = "我已经为你打开 YouTube 的愉快轻松背景音乐搜索页了。"
    render = (
        "已按你的请求执行：在系统默认浏览器打开 YouTube 搜索页，"
        "用于选择并播放愉快轻松的背景音乐。\n\n"
        "信息来源与关键依据：\n"
        f"- source: YouTube Search\n"
        f"- source_url: {YOUTUBE_URL}\n"
        f"- timestamp: {ts}\n"
        f"- key_fields: search_query=happy+upbeat+background+music, webbrowser_open_result={opened}"
    )
    return {
        "speak": speak,
        "render": render,
        "ui": {
            "type": "info_card",
            "title": "已打开 YouTube 音乐搜索",
            "message": "点击或切换到已打开的浏览器页面，选择一首喜欢的愉快音乐播放。",
            "source_url": YOUTUBE_URL,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(task_input="打开愉快背景音乐"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
