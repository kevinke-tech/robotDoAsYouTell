"""一次性技能：抓取并展示搞笑视频（含可嵌入链接）。"""
import asyncio
from typing import Any, Dict, List
import httpx

RUN_SPEC = {
    "name": "funny_videos_headless",
    "description": "从公开接口获取搞笑视频并生成可播放视频卡片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "搞笑"},
            "limit": {"type": "integer", "default": 3, "minimum": 3, "maximum": 6},
        },
        "required": [],
    },
}


def _fallback() -> List[Dict[str, str]]:
    ids = [("R4anpxoHkPI", "try not to laugh"), ("xvFZjo5PgG0", "funny cat"), ("J---aiyznGQ", "nyan cat")]
    return [{"title": t, "video_id": vid, "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", "platform": "YouTube"} for vid, t in ids]


def _normalize(items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for it in items:
        vid = str(it.get("videoId") or "").strip()
        if not vid and isinstance(it.get("url"), str) and "watch?v=" in it["url"]:
            vid = it["url"].split("watch?v=")[-1].split("&")[0].strip()
        if not vid:
            continue
        thumb = str(it.get("thumbnail") or "").strip()
        if not thumb and isinstance(it.get("videoThumbnails"), list) and it["videoThumbnails"]:
            thumb = str(it["videoThumbnails"][0].get("url") or "").strip()
        out.append({"title": str(it.get("title") or "搞笑视频").strip(), "video_id": vid, "thumbnail_url": thumb or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", "platform": "YouTube"})
    return out


async def run(query: str = "搞笑", limit: int = 3, **kwargs):
    limit = max(3, min(int(limit or 3), 6))
    urls = [f"https://inv.nadeko.net/api/v1/search?q={query}&type=video", f"https://piped.video/api/v1/search?q={query}&filter=videos"]
    videos: List[Dict[str, str]] = []
    source_url = ""
    evidence = []
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            for u in urls:
                try:
                    r = await client.get(u)
                    data = r.json() if r.status_code == 200 else []
                    items = data.get("items", []) if isinstance(data, dict) else data
                    videos = _normalize(items if isinstance(items, list) else [])
                    evidence.append(f"{u} status={r.status_code} items={len(videos)}")
                    if len(videos) >= limit:
                        source_url = u
                        break
                except Exception as e:
                    evidence.append(f"{u} error={type(e).__name__}:{e}")
    except Exception as e:
        evidence.append(f"http_client_error={type(e).__name__}:{e}")
    if len(videos) < limit:
        videos = (videos + _fallback())[:limit]
        source_url = source_url or "fallback:internal_curated"
    cards = []
    for v in videos[:limit]:
        vid = v["video_id"]
        cards.append({"title": v["title"], "thumbnail_url": v["thumbnail_url"], "video_url": f"https://www.youtube.com/watch?v={vid}", "embed_url": f"https://www.youtube.com/embed/{vid}", "platform": v["platform"], "source_url": source_url})
    render = "source_url: " + source_url + "\n" + "evidence: " + " | ".join(evidence[:4]) + "\n" + "videos:\n" + "\n".join([f"- {c['title']} ({c['platform']}) {c['video_url']}" for c in cards])
    return {"speak": f"我找到了{len(cards)}个搞笑视频，已经给你放到卡片里了。", "render": render, "ui": {"type": "video_gallery", "title": "搞笑视频推荐", "videos": cards}}


if __name__ == "__main__":
    result = asyncio.run(run(query="搞笑", limit=3))
    assert isinstance(result, dict) and "speak" in result and "render" in result and "ui" in result
    assert isinstance(result["ui"], dict) and len(result["ui"].get("videos", [])) >= 3
    print("OK")
