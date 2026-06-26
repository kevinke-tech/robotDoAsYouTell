"""中文一次性技能：展示优雅时尚人像图片网格。"""
import asyncio
import httpx
from evidence_utils import attach_evidence_fields, build_render_evidence_block

RUN_SPEC = {
    "name": "cn_elegant_portrait_grid_skill",
    "description": "从公开图片源获取优雅人像并展示网格卡片。",
    "args_schema": {
        "type": "object",
        "properties": {"count": {"type": "integer", "default": 8, "minimum": 4, "maximum": 12}, "test_mode": {"type": "boolean", "default": False}},
        "required": [],
    },
}

async def _wikimedia_cards(count: int) -> tuple[list[dict], dict]:
    url = "https://commons.wikimedia.org/w/api.php"
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": "woman portrait fashion photography", "gsrnamespace": "6", "gsrlimit": str(max(8, count * 2)), "prop": "imageinfo", "iiprop": "url", "iiurlwidth": "480"}
    refs, cards = [url], []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            data = r.json() if r.status_code == 200 else {}
    except Exception as e:
        return [], {"source": "wikimedia_commons", "source_url": url, "error": f"{type(e).__name__}: {e}", "references": refs}
    for p in (data.get("query", {}).get("pages", {}) or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        img = str(ii.get("thumburl") or ii.get("url") or "").strip()
        if img.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and img:
            cards.append({"title": str(p.get("title") or "人像摄影"), "image_url": img, "action_url": str(ii.get("descriptionurl") or ii.get("url") or img), "subtitle": "公开来源图片"})
        if len(cards) >= count:
            break
    return cards, {"source": "wikimedia_commons", "source_url": url, "count": len(cards), "references": refs}

def _unsplash_cards(start_sig: int, count: int) -> tuple[list[dict], dict]:
    cards, refs = [], ["https://source.unsplash.com/featured/600x800/?woman,portrait,fashion"]
    for i in range(count):
        sig = start_sig + i
        img = f"https://source.unsplash.com/featured/600x800/?woman,portrait,fashion&sig={sig}"
        cards.append({"title": f"时尚人像 {sig}", "image_url": img, "action_url": img, "subtitle": "Unsplash 动态图源"})
    return cards, {"source": "unsplash_source_fallback", "source_url": refs[0], "count": len(cards), "references": refs}

async def run(count: int = 8, test_mode: bool = False, **kwargs):
    n = max(4, min(int(count or 8), 12))
    if test_mode:
        ui = {"type": "card_grid", "title": "优雅人像图集", "cards": [{"title": "测试图", "image_url": "https://example.com/a.jpg", "action_url": "https://example.com/a.jpg", "subtitle": "mock"}]}
        return {"speak": "我整理好图片卡片了。", "render": "source: mock\nevidence: smoke_test", "ui": attach_evidence_fields(ui, source="mock", evidence={"mode": "test"})}
    try:
        cards, ev = await _wikimedia_cards(n)
        if len(cards) < n:
            extra, ev2 = _unsplash_cards(len(cards) + 1, n - len(cards))
            cards.extend(extra)
            ev["references"] = (ev.get("references") or []) + (ev2.get("references") or [])
            ev["fallback_added"] = len(extra)
        if not cards:
            cards, ev = _unsplash_cards(1, n)
        ui = attach_evidence_fields({"type": "card_grid", "title": "优雅时尚人像图片", "cards": cards[:n]}, source=ev.get("source", "mixed"), source_url=ev.get("source_url", ""), evidence=ev, references=ev.get("references"))
        render = "已为你整理一组时尚、优雅的人像摄影图片。\n" + build_render_evidence_block(source=ev.get("source", "mixed"), source_url=ev.get("source_url", ""), evidence=ev, references=ev.get("references"), extra_lines=[f"items: {len(cards[:n])}"])
        return {"speak": "我给你挑好一组高质量人像图了，可以直接看卡片。", "render": render, "ui": ui}
    except Exception as e:
        msg = f"暂时没拉到图片，我先给你保底图源。原因：{type(e).__name__}"
        fb, ev = _unsplash_cards(1, n)
        ui = attach_evidence_fields({"type": "card_grid", "title": "人像图片（降级结果）", "cards": fb}, source=ev["source"], source_url=ev["source_url"], evidence={"error": f"{type(e).__name__}: {e}"}, references=ev["references"])
        return {"speak": "网络有点波动，我先给你一组可用的人像图。", "render": msg + "\n" + build_render_evidence_block(source=ev["source"], source_url=ev["source_url"], evidence={"error": f"{type(e).__name__}: {e}"}), "ui": ui}

if __name__ == "__main__":
    r = asyncio.run(run(test_mode=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
