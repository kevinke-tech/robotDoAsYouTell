"""中文美女人像图片网格：双来源检索并返回 card_grid。"""
import asyncio
import httpx

RUN_SPEC = {
    "name": "cn_beauty_gallery_dual_source",
    "description": "搜索并展示美女人像/时尚图片卡片网格。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "时尚美女 人像摄影"},
            "count": {"type": "integer", "minimum": 1, "maximum": 12, "default": 6},
            "mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}

WIKI_API = "https://commons.wikimedia.org/w/api.php"
UNSPLASH_SEARCH = "https://unsplash.com/s/photos/"


async def _wiki_cards(client: httpx.AsyncClient, query: str, count: int):
    p = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
         "gsrsearch": query, "gsrlimit": count * 2, "prop": "imageinfo", "iiprop": "url"}
    r = await client.get(WIKI_API, params=p, timeout=8.0)
    pages = (r.json().get("query") or {}).get("pages") or {}
    cards = []
    for v in pages.values():
        info = (v.get("imageinfo") or [{}])[0]
        u = str(info.get("url") or "").strip()
        if u:
            cards.append({"title": str(v.get("title", "")).replace("File:", ""), "image_url": u,
                          "action_url": f"https://commons.wikimedia.org/wiki/{v.get('title','')}",
                          "subtitle": "Wikimedia Commons"})
        if len(cards) >= count:
            break
    return cards


def _unsplash_cards(query: str, count: int):
    q = query.replace(" ", ",")
    base = UNSPLASH_SEARCH + httpx.QueryParams({"query": query}).get("query", query)
    return [{"title": f"Unsplash {i+1}",
             "image_url": f"https://source.unsplash.com/1200x1600/?{q}&sig={i+1}",
             "action_url": base, "subtitle": "Unsplash Source"} for i in range(count)]


async def run(query: str = "时尚美女 人像摄影", count: int = 6, mock: bool = False, **kwargs):
    n = max(1, min(int(count), 12))
    if mock:
        cards = _unsplash_cards("fashion portrait woman", n)
    else:
        cards, err = [], ""
        try:
            async with httpx.AsyncClient() as c:
                cards = await _wiki_cards(c, query, n)
        except Exception as e:
            err = f"Wikimedia失败: {e.__class__.__name__}"
        if len(cards) < n:
            cards += _unsplash_cards(query, n - len(cards))
        if not cards:
            reason = err or "双来源均未返回可用图片"
            return {"speak": "我这次没拉到可用图片，你稍后再试。",
                    "render": f"source: Wikimedia+Unsplash\nsource_url: {WIKI_API} | {UNSPLASH_SEARCH}\nevidence: {reason}",
                    "ui": {"type": "info_card", "title": "图片获取失败", "message": reason}}
    refs = [WIKI_API, UNSPLASH_SEARCH]
    return {"speak": f"我找到了 {len(cards)} 张高质量人像图片。",
            "render": f"source: Wikimedia Commons + Unsplash\nreferences: {refs}\nevidence: query={query}, count={len(cards)}",
            "ui": {"type": "card_grid", "title": "美女人像图片集", "cards": cards}}


if __name__ == "__main__":
    r = asyncio.run(run(query="时尚美女", count=4, mock=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r and (r.get("ui") or {}).get("type") == "card_grid"
    print("OK")
