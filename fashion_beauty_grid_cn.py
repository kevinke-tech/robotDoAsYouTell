"""Vox one-shot: 展示精选时尚美女写真图集。"""
import asyncio
import urllib.parse

import httpx

RUN_SPEC = {
    "name": "fashion_beauty_grid_cn",
    "description": "搜索并展示时尚美女图片卡片网格。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "beautiful woman portrait"},
            "limit": {"type": "integer", "default": 6, "minimum": 1, "maximum": 9},
        },
        "required": [],
    },
}


async def _fetch_wikimedia(query: str, limit: int) -> tuple[list[dict], str]:
    url = "https://commons.wikimedia.org/w/api.php"
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": query, "gsrnamespace": "6", "gsrlimit": str(limit), "prop": "imageinfo", "iiprop": "url"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
        data = r.json() if r.status_code == 200 else {}
        pages = (data.get("query") or {}).get("pages") or {}
        items = []
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            image_url = info.get("thumburl") or info.get("url") or ""
            if image_url:
                items.append({"title": str(page.get("title") or "Wikimedia 图片"), "image_url": image_url, "source": "Wikimedia Commons", "source_url": info.get("descriptionurl") or image_url})
        return items[:limit], "ok"
    except Exception as e:
        return [], f"wikimedia_error:{type(e).__name__}"


def _fallback_unsplash(query: str, need: int) -> list[dict]:
    q = urllib.parse.quote_plus(query)
    return [
        {"title": f"Unsplash 推荐图 {i+1}", "image_url": f"https://source.unsplash.com/1200x1600/?{q}&sig={i}", "source": "Unsplash Source", "source_url": "https://source.unsplash.com/"}
        for i in range(max(0, need))
    ]


async def run(query: str = "beautiful woman portrait", limit: int = 6, **kwargs):
    limit = max(1, min(int(limit or 6), 9))
    mock = kwargs.get("_mock_data")
    if mock is not None:
        items, status = list(mock)[:limit], "mock"
    else:
        items, status = await _fetch_wikimedia(query, limit)
        if len(items) < limit:
            items.extend(_fallback_unsplash(query or "fashion beauty", limit - len(items)))
    if not items:
        return {"speak": "我这次没取到可展示的图片。", "render": f"source: Wikimedia Commons API + Unsplash Source\nevidence: status={status}, query={query}, count=0", "ui": {"type": "info_card", "title": "图片获取失败", "message": "暂时没有获取到可用图片，请稍后重试。"}}
    cards = [{"title": x.get("title") or "美女写真", "image_url": x.get("image_url") or "", "subtitle": f"来源: {x.get('source')}", "action_url": x.get("source_url") or x.get("image_url") or ""} for x in items if x.get("image_url")]
    refs = ", ".join(sorted({c["action_url"] for c in cards[:3]}))
    return {
        "speak": f"我为你找到了{len(cards)}张时尚美女图片，已经整理成卡片。",
        "render": f"source: Wikimedia Commons API; fallback: Unsplash Source\nevidence: query={query}, status={status}, count={len(cards)}\nreferences: {refs}",
        "ui": {"type": "card_grid", "title": "精选美女写真 / Fashion Beauty", "cards": cards},
    }


if __name__ == "__main__":
    sample = [{"title": "测试图A", "image_url": "https://img.example/a.jpg", "source": "mock", "source_url": "https://example.com/a"}, {"title": "测试图B", "image_url": "https://img.example/b.jpg", "source": "mock", "source_url": "https://example.com/b"}]
    out = asyncio.run(run(limit=2, _mock_data=sample))
    assert isinstance(out, dict) and "speak" in out and "render" in out and isinstance(out.get("ui"), dict)
    print("OK")
