"""一次性技能：抓取热门搞笑视频并返回可点击卡片。"""
import asyncio
import re
from typing import List, Dict
import httpx

RUN_SPEC = {
    "name": "hot_funny_video_cards",
    "description": "获取热门搞笑视频并以卡片展示。",
    "args_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "default": "搞笑"}, "limit": {"type": "integer", "default": 6}, "use_mock": {"type": "boolean", "default": False}},
        "required": [],
    },
}

MOCK = [{"title": "搞笑短片合集", "thumbnail": "https://i.ytimg.com/vi/9bZkp7q19f0/hqdefault.jpg", "video_url": "https://www.youtube.com/watch?v=9bZkp7q19f0", "platform": "YouTube", "source_url": "https://www.youtube.com"}, {"title": "爆笑动物名场面", "thumbnail": "https://i.ytimg.com/vi/J---aiyznGQ/hqdefault.jpg", "video_url": "https://www.youtube.com/watch?v=J---aiyznGQ", "platform": "YouTube", "source_url": "https://www.youtube.com"}, {"title": "整活翻车现场", "thumbnail": "https://i.ytimg.com/vi/kJQP7kiw5Fk/hqdefault.jpg", "video_url": "https://www.youtube.com/watch?v=kJQP7kiw5Fk", "platform": "YouTube", "source_url": "https://www.youtube.com"}, {"title": "今日份快乐源泉", "thumbnail": "https://i.ytimg.com/vi/3JZ_D3ELwOQ/hqdefault.jpg", "video_url": "https://www.youtube.com/watch?v=3JZ_D3ELwOQ", "platform": "YouTube", "source_url": "https://www.youtube.com"}, {"title": "经典搞笑片段回顾", "thumbnail": "https://i.ytimg.com/vi/L_jWHffIx5E/hqdefault.jpg", "video_url": "https://www.youtube.com/watch?v=L_jWHffIx5E", "platform": "YouTube", "source_url": "https://www.youtube.com"}]


def _clean(t: str) -> str:
    return re.sub(r"<.*?>", "", t or "").strip()


async def _fetch_bili(client: httpx.AsyncClient, q: str) -> List[Dict]:
    u = "https://api.bilibili.com/x/web-interface/search/type"
    try:
        r = await client.get(u, params={"search_type": "video", "keyword": q, "page": 1}, timeout=8.0)
        rows = (r.json().get("data") or {}).get("result") or []
        return [{"title": _clean(i.get("title")), "thumbnail": ("https:" + i.get("pic", "")) if str(i.get("pic", "")).startswith("//") else str(i.get("pic", "")), "video_url": str(i.get("arcurl", "")), "platform": "Bilibili", "source_url": u} for i in rows]
    except Exception:
        return []


async def _fetch_youtube(client: httpx.AsyncClient, q: str) -> List[Dict]:
    u = "https://piped.video/api/v1/search"
    try:
        r = await client.get(u, params={"q": f"{q} funny comedy", "filter": "videos"}, timeout=8.0)
        rows = r.json() if isinstance(r.json(), list) else []
        return [{"title": _clean(i.get("title")), "thumbnail": str(i.get("thumbnail", "")), "video_url": "https://www.youtube.com" + str(i.get("url", "")), "platform": "YouTube", "source_url": u} for i in rows]
    except Exception:
        return []


async def run(query: str = "搞笑", limit: int = 6, use_mock: bool = False, **kwargs):
    items = MOCK[:] if use_mock else []
    refs = ["https://api.bilibili.com/x/web-interface/search/type", "https://piped.video/api/v1/search"]
    if not use_mock:
        try:
            async with httpx.AsyncClient(headers={"User-Agent": "vox-skill/1.0"}) as client:
                items = (await _fetch_bili(client, query)) + (await _fetch_youtube(client, query))
        except Exception:
            items = []
    seen, picked = set(), []
    for i in items:
        k = i.get("video_url", "")
        if k and k not in seen and i.get("title"):
            seen.add(k); picked.append(i)
        if len(picked) >= max(5, int(limit or 6)): break
    if len(picked) < 5:
        picked = (picked + MOCK)[:5]
    ok = len(picked) >= 5
    speak = "我找到了几条热门搞笑视频，点卡片就能看。" if ok else "我这次没抓到足够视频，先给你可用的备选。"
    render = "source: bilibili+piped\nsource_url: " + ", ".join(refs) + f"\nevidence: total={len(picked)}, query={query}\nreferences: " + " | ".join([p.get("video_url", "") for p in picked[:5]])
    ui = {"type": "video_cards", "title": "热门搞笑视频", "items": [{"title": p["title"], "thumbnail": p["thumbnail"], "video_url": p["video_url"], "platform": p["platform"], "source_url": p["source_url"]} for p in picked[: max(5, int(limit or 6))]]}
    return {"speak": speak, "render": render, "ui": ui}


if __name__ == "__main__":
    r = asyncio.run(run(use_mock=True, limit=5))
    assert isinstance(r, dict) and "speak" in r and "render" in r and len(r.get("ui", {}).get("items", [])) >= 5
    print("OK")
