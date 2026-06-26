"""One-shot skill: 搜索并展示搞笑视频卡片。"""
import asyncio
from urllib.parse import quote_plus

import httpx

RUN_SPEC = {
    "name": "youtube_funny_video_cards",
    "description": "搜索 YouTube 搞笑视频并返回可点击卡片。",
    "args_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "default": "搞笑视频 funny"}},
        "required": [],
    },
}


async def run(query: str = "搞笑视频 funny", **kwargs):
    queries = [query, "funny moments"]
    instances = ["https://invidious.privacyredirect.com", "https://yewtu.be"]
    refs, videos, err = [], [], ""
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as c:
            for q in queries:
                for base in instances:
                    url = f"{base}/api/v1/search?q={quote_plus(q)}&type=video"
                    try:
                        r = await c.get(url)
                        refs.append({"source": "invidious", "source_url": url, "status": r.status_code})
                        if r.status_code != 200:
                            continue
                        for it in (r.json() or []):
                            vid = str(it.get("videoId") or "").strip()
                            if not vid or any(v["id"] == vid for v in videos):
                                continue
                            thumbs = it.get("videoThumbnails") or []
                            thumb = next((t.get("url") for t in thumbs if t.get("quality") == "medium"), "") or (thumbs[0].get("url") if thumbs else "")
                            videos.append({"id": vid, "title": str(it.get("title") or "未命名视频"), "thumb": thumb, "platform": "YouTube"})
                            if len(videos) >= 8:
                                break
                    except Exception as e:
                        refs.append({"source": "invidious", "source_url": url, "evidence": f"error:{type(e).__name__}"})
                    if len(videos) >= 8:
                        break
                if len(videos) >= 8:
                    break
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    picked = videos[:5]
    if len(picked) < 5:
        reason = err or "可用检索结果不足 5 条"
        return {
            "speak": "我这次没拿到足够的搞笑视频，稍后再试我就能继续找。",
            "render": f"source: invidious api\nreferences: {refs}\nevidence: {reason}",
            "ui": {"type": "info_card", "title": "搞笑视频获取失败", "message": f"原因: {reason}"},
        }
    items = []
    for v in picked:
        watch = f"https://www.youtube.com/watch?v={v['id']}"
        items.append({"title": v["title"], "thumbnail_url": v["thumb"], "video_url": watch, "embed_url": f"https://www.youtube.com/embed/{v['id']}", "platform": v["platform"]})
    return {
        "speak": "我帮你找了几条搞笑视频，点开就能看。",
        "render": f"source: invidious api / YouTube\nreferences: {refs}\nevidence: collected_videos={len(videos)}",
        "ui": {"type": "video_grid", "title": "搞笑视频 funny", "items": items},
    }


if __name__ == "__main__":
    r = asyncio.run(run(query="搞笑视频 funny"))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
