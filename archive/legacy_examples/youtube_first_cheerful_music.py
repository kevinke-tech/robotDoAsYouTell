"""搜索 YouTube 并播放第一条视频结果。"""
from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin

import runtime

RUN_SPEC = {
    "name": "youtube_first_cheerful_music",
    "description": "在 YouTube 搜索 cheerful instrumental music，并打开第一条结果开始播放。",
    "args_schema": {"type": "object", "properties": {}, "required": []},
}


async def run(**kwargs):
    query = "cheerful instrumental music"
    search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    async with runtime.new_page() as page:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=45_000)
        first = page.locator("a#video-title[href*='/watch?v=']").first
        await first.wait_for(state="visible", timeout=45_000)
        href = (await first.get_attribute("href")) or ""
        title = ((await first.inner_text()) or "").strip()
        video_url = urljoin("https://www.youtube.com", href)
        await first.click(timeout=10_000)
        await page.wait_for_load_state("domcontentloaded", timeout=45_000)
        play_btn = page.locator("button.ytp-play-button").first
        if await play_btn.count():
            label = ((await play_btn.get_attribute("aria-label")) or "").lower()
            if "play" in label:
                await play_btn.click(timeout=5_000)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    safe_title = title or "未读取到标题"
    return {
        "speak": "我已经打开第一条音乐视频并开始播放了。",
        "render": (
            "已在 YouTube 打开首条搜索结果并尝试开始播放。\n"
            f"关键词：{query}\n"
            f"搜索页：{search_url}\n"
            f"视频标题：{safe_title}\n"
            f"视频链接：{video_url}\n"
            f"执行时间：{now}"
        ),
        "ui": {
            "type": "video_player",
            "title": "YouTube 音乐播放",
            "video_url": video_url,
            "subtitle": safe_title,
            "source": "YouTube",
        },
    }


if __name__ == "__main__":
    # 浏览器类 skill 的冒烟测试约定: 只检查结构，不调用 run。
    import inspect

    assert isinstance(RUN_SPEC, dict) and RUN_SPEC.get("name")
    assert inspect.iscoroutinefunction(run)
    print("OK")
