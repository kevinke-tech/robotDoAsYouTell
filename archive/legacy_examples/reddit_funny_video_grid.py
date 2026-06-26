"""抓取热门搞笑视频并以卡片网格返回。"""
import json
from datetime import datetime, timezone
import httpx

RUN_SPEC = {
    "name": "reddit_funny_video_grid",
    "description": "搜索并展示热门搞笑视频卡片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "funny videos"},
            "limit": {"type": "integer", "default": 8, "minimum": 5, "maximum": 12},
        },
        "required": [],
    },
}


async def run(query: str = "funny videos", limit: int = 8, mock_items=None, **kwargs):
    source_url = f"https://www.reddit.com/r/funny/hot.json?limit={max(limit * 3, 20)}"
    cards, evidence = [], {"query": query, "fetched_at": datetime.now(timezone.utc).isoformat()}
    try:
        if isinstance(mock_items, list):
            cards = mock_items[: max(5, limit)]
        else:
            headers = {"User-Agent": "vox-skill/1.0"}
            async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
                resp = await client.get(source_url)
            data = resp.json() if resp.status_code == 200 else {}
            posts = ((data.get("data") or {}).get("children") or [])
            for p in posts:
                d = p.get("data") or {}
                title = str(d.get("title") or "").strip()
                if not title:
                    continue
                url = str(d.get("url_overridden_by_dest") or d.get("url") or "").strip()
                if not url:
                    continue
                thumb = str(d.get("thumbnail") or "").strip()
                if not thumb.startswith("http"):
                    images = (((d.get("preview") or {}).get("images")) or [])
                    thumb = (((images[0] or {}).get("source") or {}).get("url") or "") if images else ""
                    thumb = thumb.replace("&amp;", "&")
                platform = "YouTube" if ("youtube.com" in url or "youtu.be" in url) else "Reddit"
                desc = (str(d.get("selftext") or "").strip()[:60] or "这条看起来很有梗，点开就能看。")
                cards.append({"title": title[:80], "image_url": thumb, "platform": platform, "url": url, "description": desc, "emoji": "😂"})
                if len(cards) >= max(5, limit):
                    break
            evidence["reddit_status"] = resp.status_code if "resp" in locals() else None
            evidence["reddit_items_seen"] = len(posts) if "posts" in locals() else 0
    except Exception as e:
        evidence["error"] = f"{type(e).__name__}: {e}"
    if not cards:
        return {
            "speak": "我暂时没找到搞笑视频，但我已经记录了失败原因。",
            "render": f"source_url: {source_url}\nevidence: {json.dumps(evidence, ensure_ascii=False)}\n结果: 空",
            "ui": {"type": "info_card", "title": "搞笑视频获取失败", "message": "暂时没拿到可展示内容，请稍后重试。", "source_url": source_url},
        }
    return {
        "speak": f"我找到了 {len(cards)} 条搞笑视频，已经给你排成卡片了。",
        "render": f"source: Reddit r/funny 热门帖\nsource_url: {source_url}\nevidence: {json.dumps(evidence, ensure_ascii=False)}\nreferences: " + ", ".join(c["url"] for c in cards[:5]),
        "ui": {"type": "video_card_grid", "title": "搞笑视频精选 😂", "layout": "grid", "cards": cards},
    }


if __name__ == "__main__":
    import asyncio

    sample = [{"title": f"搞笑视频 {i+1}", "image_url": "https://example.com/t.jpg", "platform": "YouTube", "url": f"https://youtu.be/demo{i+1}", "description": "轻松一下，笑一笑。", "emoji": "🤣"} for i in range(5)]
    result = asyncio.run(run(mock_items=sample, limit=5))
    assert isinstance(result, dict) and "speak" in result and "render" in result and "ui" in result
    assert len((result["ui"] or {}).get("cards", [])) >= 5
    print("OK")
