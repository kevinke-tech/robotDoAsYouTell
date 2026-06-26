"""One-shot skill: search horror ambient track and return playable iframe UI."""
from datetime import datetime, timezone
import httpx

RUN_SPEC = {
    "name": "horror_ambient_youtube_iframe",
    "description": "搜索惊悚氛围音乐并返回可直接播放的 YouTube 嵌入卡片。",
    "args_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "default": "horror ambient music"}},
        "required": [],
    },
}

_SEARCH_APIS = [
    "https://invidious.fdn.fr/api/v1/search",
    "https://inv.nadeko.net/api/v1/search",
    "https://yewtu.be/api/v1/search",
]

def _score(item: dict) -> tuple[float, int]:
    length = int(item.get("lengthSeconds") or 0)
    views = int(item.get("viewCount") or 0)
    return ((length / 3600.0) + min(views, 200000000) / 200000000.0, views)

async def run(query: str = "horror ambient music", **kwargs):
    q = (query or "horror ambient music").strip()
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    items, source_url = kwargs.get("mock_results"), "mock://invidious/search"
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        if items is None:
            items = []
            for api in _SEARCH_APIS:
                try:
                    r = await client.get(api, params={"q": q, "type": "video"})
                    data = r.json() if r.status_code == 200 else []
                    items = [x for x in data if isinstance(x, dict) and x.get("videoId")]
                    if items:
                        source_url = f"{api}?q={q}&type=video"
                        break
                except Exception:
                    continue
    if not items:
        return {
            "speak": "我这次没搜到可播放的惊悚氛围音乐，请稍后再试。",
            "render": f"来源: {_SEARCH_APIS[0]} 等公开搜索接口\n时间: {checked_at}\n关键字段: 空结果",
            "ui": {"type": "info_card", "title": "未找到可播放内容", "message": "暂时没有可用结果"},
        }
    best = max(items, key=_score)
    vid = str(best.get("videoId") or "").strip()
    title = str(best.get("title") or "Horror Ambient Music").strip()
    views = int(best.get("viewCount") or 0)
    length = int(best.get("lengthSeconds") or 0)
    embed = f"https://www.youtube.com/embed/{vid}?autoplay=1&mute=1&rel=0"
    desc = "长时惊悚氛围音乐，适合背景播放。"
    return {
        "speak": "我给你找到一首惊悚氛围音乐，已经可以直接播放了。",
        "render": f"来源: {source_url}\n时间: {checked_at}\n关键字段: title={title}, videoId={vid}, lengthSeconds={length}, viewCount={views}",
        "ui": {
            "type": "youtube_iframe_card",
            "title": "惊悚氛围音乐",
            "video_title": title,
            "description": desc,
            "iframe_url": embed,
            "video_url": embed,
            "iframe_html": f'<iframe src="{embed}" title="{title}" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>',
            "source_url": f"https://www.youtube.com/watch?v={vid}",
        },
    }

if __name__ == "__main__":
    import asyncio
    sample = [{"videoId": "dQw4w9WgXcQ", "title": "Scary Ambient Background Music 3 Hours", "lengthSeconds": 10800, "viewCount": 1234567}]
    out = asyncio.run(run(query="scary background music", mock_results=sample))
    assert isinstance(out, dict) and "speak" in out and "render" in out and out.get("ui", {}).get("iframe_url")
    print("OK")
