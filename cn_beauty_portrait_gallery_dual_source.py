"""中文美女人像图片画廊（双数据源）。"""
import asyncio
from urllib.parse import quote
import httpx

RUN_SPEC = {
    "name": "cn_beauty_portrait_gallery_dual_source",
    "description": "搜索并展示高质量美女写真/时尚/人像图片画廊。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "beautiful woman portrait"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 12, "default": 8},
            "use_mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


async def run(query: str = "beautiful woman portrait", limit: int = 8, use_mock: bool = False, **kwargs):
    if use_mock:
        cards = [{"title": "示例图片", "image_url": "https://example.com/a.jpg", "action_url": "https://example.com", "subtitle": "来源: mock"}]
        return {"speak": "我整理好一组示例图片。", "render": "source: mock\nevidence: smoke_test=true", "ui": {"type": "card_grid", "title": "美女图片画廊", "cards": cards}}
    limit = max(1, min(int(limit or 8), 12))
    q = str(query or "beautiful woman portrait").strip()
    unsplash_url = f"https://unsplash.com/napi/search/photos?query={quote(q)}&per_page={limit}&page=1"
    wiki_url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={quote(q)}&gsrnamespace=6&gsrlimit={limit}&prop=imageinfo&iiprop=url&format=json&origin=*"
    cards, refs, errs = [], [], []
    try:
        async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "vox-skill/1.0"}) as c:
            try:
                r = await c.get(unsplash_url)
                data = r.json() if r.status_code == 200 else {}
                for it in (data.get("results") or []):
                    img = ((it.get("urls") or {}).get("small") or (it.get("urls") or {}).get("regular") or "").strip()
                    page = ((it.get("links") or {}).get("html") or "").strip()
                    if img and page and len(cards) < limit:
                        cards.append({"title": (it.get("alt_description") or "人像摄影").strip()[:36], "image_url": img, "action_url": page, "subtitle": "来源: Unsplash"})
                        refs.append(page)
            except Exception as e:
                errs.append(f"unsplash:{type(e).__name__}")
            if len(cards) < limit:
                try:
                    r2 = await c.get(wiki_url)
                    data2 = r2.json() if r2.status_code == 200 else {}
                    for p in (data2.get("query", {}).get("pages", {}) or {}).values():
                        ii = (p.get("imageinfo") or [{}])[0]
                        img = str(ii.get("url") or "").strip()
                        page = f"https://commons.wikimedia.org/wiki/{quote(str(p.get('title') or ''))}"
                        if img and len(cards) < limit:
                            cards.append({"title": str(p.get("title") or "时尚人像")[:36], "image_url": img, "action_url": page, "subtitle": "来源: Wikimedia Commons"})
                            refs.append(page)
                except Exception as e:
                    errs.append(f"wikimedia:{type(e).__name__}")
    except Exception as e:
        errs.append(f"client:{type(e).__name__}")
    if not cards:
        reason = "; ".join(errs) if errs else "empty_result"
        return {
            "speak": "这次没搜到可用图片，我已记录原因，你可以换个关键词再试。",
            "render": f"source_url: {unsplash_url}\nsource_url: {wiki_url}\nevidence: query={q}; failure={reason}",
            "ui": {"type": "info_card", "title": "图片搜索失败", "message": f"关键词: {q}\n原因: {reason}"},
        }
    return {
        "speak": f"我找到了{len(cards)}张高质量人像图片，已经整理成画廊。",
        "render": f"source_url: {unsplash_url}\nsource_url: {wiki_url}\nevidence: query={q}; total={len(cards)}; errors={','.join(errs) if errs else 'none'}\nreferences: {' | '.join(refs[:3])}",
        "ui": {"type": "card_grid", "title": f"美女图片画廊：{q}", "cards": cards},
    }


if __name__ == "__main__":
    out = asyncio.run(run(use_mock=True))
    assert isinstance(out, dict) and "speak" in out and "render" in out
    print("OK")
