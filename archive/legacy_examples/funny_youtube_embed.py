"""一次性技能：抓取 YouTube 搞笑视频并返回可嵌入播放器。"""
import datetime as dt
import re
from urllib.parse import quote_plus

import httpx

RUN_SPEC = {
    "name": "funny_youtube_embed",
    "description": "搜索可内嵌播放的 YouTube 搞笑视频并返回播放器 UI。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "funny fails compilation"},
        },
        "required": [],
    },
}


def _pick_video(html: str):
    pat = re.compile(
        r'"videoRenderer":\{"videoId":"(?P<id>[\w-]{11})".{0,1600}?'
        r'"title":\{"runs":\[\{"text":"(?P<title>[^"]+)".{0,1200}?'
        r'"ownerText":\{"runs":\[\{"text":"(?P<channel>[^"]+)"',
        re.S,
    )
    m = pat.search(html)
    if not m:
        return None
    return {"id": m.group("id"), "title": m.group("title"), "channel": m.group("channel")}


async def run(query: str = "funny fails compilation", **kwargs):
    q = (query or "funny fails compilation").strip()
    search_url = f"https://www.youtube.com/results?search_query={quote_plus(q)}"
    html = kwargs.get("mock_html") or ""
    if not html:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as c:
            r = await c.get(search_url, headers={"User-Agent": "Mozilla/5.0"})
            html = r.text if r.status_code == 200 else ""
    video = _pick_video(html)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if not video:
        return {
            "speak": "我这次没找到可播放的搞笑视频，稍后再试一次吧。",
            "render": f"来源URL: {search_url}\n抓取时间: {now}\n关键字段: videoId=空",
            "ui": {"type": "info_card", "title": "视频获取失败", "message": "未提取到可嵌入视频"},
        }
    vid = video["id"]
    title = video["title"]
    channel = video["channel"]
    embed = f"https://www.youtube.com/embed/{vid}"
    watch = f"https://www.youtube.com/watch?v={vid}"
    return {
        "speak": "我给你找了一个搞笑视频，已经可以直接播放。",
        "render": (
            f"来源URL: {search_url}\n抓取时间: {now}\n关键字段: videoId={vid}\n"
            f"title: {title}\nchannel: {channel}\nembed_url: {embed}\nwatch_url: {watch}"
        ),
        "ui": {
            "type": "iframe_card",
            "title": "YouTube 搞笑视频",
            "iframe_url": embed,
            "source_url": watch,
        },
    }


if __name__ == "__main__":
    import asyncio

    fake_html = (
        '{"videoRenderer":{"videoId":"dQw4w9WgXcQ","title":{"runs":[{"text":"Funny Fails 2026"}]},'
        '"ownerText":{"runs":[{"text":"Comedy Hub"}]}}}'
    )
    out = asyncio.run(run(query="funny fails compilation", mock_html=fake_html))
    assert isinstance(out, dict) and "speak" in out and "render" in out
    assert out.get("ui", {}).get("iframe_url", "").endswith("dQw4w9WgXcQ")
    print("OK")
