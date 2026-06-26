"""中文一次性技能：多源检索女性人像/时尚摄影并返回图片网格。"""
import os
import asyncio
import httpx
from evidence_utils import build_render_evidence_block, attach_evidence_fields

RUN_SPEC = {"name": "cn_women_portrait_grid_multisource", "description": "搜索女性人像/时尚摄影图片并展示网格。", "args_schema": {"type": "object", "properties": {"query": {"type": "string", "default": "美女 人像 摄影 时尚 艺术"}, "limit": {"type": "integer", "default": 9, "minimum": 3, "maximum": 12}}, "required": []}}

async def _from_unsplash(query: str, limit: int):
    key = str(os.getenv("UNSPLASH_ACCESS_KEY") or "").strip()
    url = "https://api.unsplash.com/search/photos" if key else "https://unsplash.com/napi/search/photos"
    params = {"query": query, "per_page": limit, "page": 1}
    headers = {"Accept-Language": "zh-CN,zh;q=0.9", "User-Agent": "vox-agent/1.0"}
    if key:
        params["client_id"] = key
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(url, params=params, headers=headers)
            data = r.json() if r.status_code == 200 else {}
    except Exception as e:
        return [], {"source": "unsplash", "source_url": url, "error": f"{type(e).__name__}: {e}"}
    out = []
    for x in (data.get("results") or [])[:limit]:
        img = ((x.get("urls") or {}).get("small") or "").strip()
        page = str(x.get("links", {}).get("html") or "").strip()
        title = str((x.get("alt_description") or x.get("description") or "Unsplash 人像作品")[:28])
        if img and page:
            out.append({"title": title, "image_url": img, "action_url": page, "subtitle": "Unsplash"})
    return out, {"source": "unsplash", "source_url": url, "evidence": {"count": len(out), "query": query, "http_ok": bool(out)}}

async def _from_wikimedia(query: str, limit: int):
    url = "https://commons.wikimedia.org/w/api.php"
    params = {"action": "query", "generator": "search", "gsrsearch": f"{query} portrait fashion", "gsrlimit": limit, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 640, "format": "json"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(url, params=params)
            data = r.json() if r.status_code == 200 else {}
    except Exception as e:
        return [], {"source": "wikimedia_commons", "source_url": url, "error": f"{type(e).__name__}: {e}"}
    out = []
    for p in (data.get("query", {}).get("pages", {}) or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        img, page = str(ii.get("thumburl") or "").strip(), str(ii.get("descriptionurl") or "").strip()
        if img and page:
            out.append({"title": str(p.get("title") or "Wikimedia 图片")[:28], "image_url": img, "action_url": page, "subtitle": "Wikimedia Commons"})
    return out[:limit], {"source": "wikimedia_commons", "source_url": url, "evidence": {"count": len(out), "query": query, "http_ok": bool(out)}}

async def run(query: str = "美女 人像 摄影 时尚 艺术", limit: int = 9, **kwargs):
    n, refs = max(3, min(int(limit or 9), 12)), []
    mock_items = kwargs.get("_mock_items")
    if isinstance(mock_items, list) and mock_items:
        cards, chosen = mock_items[:n], {"source": "mock", "source_url": "local://smoke", "evidence": {"count": len(mock_items), "query": query}}
    else:
        cards = []
        for fn in (_from_unsplash, _from_wikimedia):
            items, meta = await fn(query, n)
            refs.append(meta)
            if items:
                cards, chosen = items, meta
                break
        if not cards:
            block = build_render_evidence_block(source="image_search_fallback", evidence="all_sources_failed", references=refs)
            return {"speak": "暂时没拿到图片结果，我稍后可以再试一次。", "render": f"未获取到可用图片。\n{block}", "ui": {"type": "info_card", "title": "图片获取失败", "message": "当前数据源不可用，请稍后重试。", "references": refs}}
    block = build_render_evidence_block(source=chosen.get("source", "unknown"), source_url=chosen.get("source_url", ""), evidence=chosen.get("evidence"), references=refs)
    ui = attach_evidence_fields({"type": "card_grid", "title": "女性人像与时尚摄影", "cards": cards}, source=chosen.get("source", "unknown"), source_url=chosen.get("source_url", ""), evidence=chosen.get("evidence"), references=refs)
    return {"speak": f"我找到了 {len(cards)} 张风格不错的人像图，给你看。", "render": f"已为你整理图片网格（共 {len(cards)} 张）。\n{block}", "ui": ui}

if __name__ == "__main__":
    mock = [{"title": "示例图", "image_url": "https://example.com/a.jpg", "action_url": "https://example.com", "subtitle": "mock"}]
    r = asyncio.run(run(_mock_items=mock, limit=3))
    assert isinstance(r, dict) and "speak" in r and "render" in r and isinstance(r.get("ui"), dict)
    print("OK")
