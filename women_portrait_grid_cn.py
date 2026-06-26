"""从多源检索人像图片并返回网格卡片。"""
import asyncio
import re
import httpx

RUN_SPEC = {
    "name": "women_portrait_grid_cn",
    "description": "搜索并展示美女人像图片网格。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "beautiful woman portrait"},
            "limit": {"type": "integer", "default": 8, "minimum": 1, "maximum": 12},
            "offline_test": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}

FALLBACK = [
    {"title": "示例图 1", "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/99/Adriana_Lima_2012.jpg/512px-Adriana_Lima_2012.jpg", "subtitle": "source: wikimedia_fallback"},
    {"title": "示例图 2", "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0f/Audrey_Hepburn_1954.jpg/512px-Audrey_Hepburn_1954.jpg", "subtitle": "source: wikimedia_fallback"},
]


async def _wikimedia(client, query, limit):
    url = "https://commons.wikimedia.org/w/api.php"
    p = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": str(limit), "prop": "imageinfo|pageimages", "pithumbsize": "600", "iiprop": "url"}
    try:
        r = await client.get(url, params=p, timeout=8.0)
        pages = (r.json() if r.status_code == 200 else {}).get("query", {}).get("pages", {})
        return [{"title": v.get("title", "Wikimedia"), "image_url": v.get("thumbnail", {}).get("source", ""), "subtitle": "source: Wikimedia Commons"} for v in pages.values() if v.get("thumbnail", {}).get("source")]
    except Exception as e:
        return [{"title": "Wikimedia 检索失败", "image_url": "", "subtitle": f"error: {e}"}]


async def _pexels(client, query, limit):
    url = f"https://www.pexels.com/zh-cn/search/{query.replace(' ', '%20')}/"
    try:
        r = await client.get(url, timeout=8.0)
        imgs = list(dict.fromkeys(re.findall(r"https://images\\.pexels\\.com/photos/[^\"'\\s>]+", r.text)))[:limit]
        return [{"title": f"Pexels 图 {i+1}", "image_url": u, "subtitle": "source: Pexels(网页抓取)"} for i, u in enumerate(imgs)]
    except Exception as e:
        return [{"title": "Pexels 检索失败", "image_url": "", "subtitle": f"error: {e}"}]


async def run(query: str = "beautiful woman portrait", limit: int = 8, offline_test: bool = False, **kwargs):
    cards, evidence = [], []
    if not offline_test:
        try:
            async with httpx.AsyncClient(follow_redirects=True) as c:
                w, p = await _wikimedia(c, query, limit), await _pexels(c, query, limit)
            cards = [x for x in (w + p) if x.get("image_url")]
            evidence = ["source_url: https://commons.wikimedia.org/w/api.php", "source_url: https://www.pexels.com/zh-cn/search/"]
        except Exception as e:
            evidence.append(f"evidence: 聚合异常 {e}")
    if not cards:
        cards = FALLBACK[:]
        evidence.append("source: fallback_static_images")
    cards = cards[:limit]
    speak = f"我找到了 {len(cards)} 张人像图片，已经整理成网格给你看。"
    render = "结果: 美女人像图片检索\n" + "\n".join(evidence) + f"\nreferences: query={query}; count={len(cards)}"
    return {
        "speak": speak,
        "render": render,
        "ui": {"type": "card_grid", "title": "美女人像图片", "cards": cards},
    }


if __name__ == "__main__":
    out = asyncio.run(run(offline_test=True))
    assert isinstance(out, dict) and "speak" in out and "render" in out and out.get("ui", {}).get("type") == "card_grid"
    print("OK")
