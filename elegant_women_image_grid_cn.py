"""一次性技能：搜索并展示优雅时尚女性图片网格。"""
import asyncio
import re
import httpx
from web_search import search_web
from evidence_utils import build_render_evidence_block, attach_evidence_fields

RUN_SPEC = {
    "name": "elegant_women_image_grid_cn",
    "description": "搜索多张优雅时尚女性图片并以网格展示。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "优雅 时尚 女性 人像"},
            "count": {"type": "integer", "default": 8, "minimum": 4, "maximum": 12},
            "mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}

def _derive(url: str) -> list[str]:
    out, u = [], str(url or "").strip()
    m = re.search(r"unsplash\.com/photos/([A-Za-z0-9_-]+)", u)
    if m:
        out.append(f"https://images.unsplash.com/{m.group(1)}?auto=format&fit=crop&w=900&q=80")
    m = re.search(r"pexels\.com/photo/.*-(\d+)/?$", u)
    if m:
        pid = m.group(1)
        out.append(f"https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg?auto=compress&cs=tinysrgb&w=900")
    if re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", u, re.I):
        out.append(u)
    return out

async def _ok_image(client: httpx.AsyncClient, url: str) -> bool:
    try:
        r = await client.get(url, timeout=6.0, follow_redirects=True)
        return r.status_code == 200 and str(r.headers.get("content-type", "")).startswith("image/")
    except Exception:
        return False

async def run(query: str = "优雅 时尚 女性 人像", count: int = 8, mock: bool = False, **kwargs):
    n = max(4, min(int(count or 8), 12))
    if mock:
        cards = [{"title": f"示例图{i+1}", "image_url": f"https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=80{i}&q=80"} for i in range(min(4, n))]
        return {"speak": "我整理好了示例图片网格。", "render": "source: mock\nreferences: [\"unsplash_mock\"]", "ui": {"type": "card_grid", "title": "优雅时尚女性图片", "cards": cards}}
    refs, candidates = [], []
    for q in [f"site:unsplash.com/photos {query}", f"site:pexels.com/photo {query}"]:
        try:
            rs = await search_web(q, max_results=8)
            refs.append({"query": q, "provider": rs.get("provider", "none"), "hits": len(rs.get("hits") or [])})
            for h in (rs.get("hits") or []):
                for img in _derive(h.get("url", "")):
                    if img not in candidates:
                        candidates.append(img)
        except Exception as e:
            refs.append({"query": q, "error": f"{type(e).__name__}: {e}"})
    cards = []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            for u in candidates:
                if len(cards) >= n:
                    break
                if await _ok_image(client, u):
                    cards.append({"title": f"优雅人像 {len(cards)+1}", "image_url": u, "action_url": u, "subtitle": "公开可访问图片"})
    except Exception as e:
        refs.append({"validate_error": f"{type(e).__name__}: {e}"})
    if not cards:
        ev = build_render_evidence_block(source="search_web(unsplash+pexels)", evidence="未找到可直接加载图片", references=refs)
        ui = attach_evidence_fields({"type": "info_card", "title": "图片暂未取到", "message": "我没找到可直接加载的公开图片，建议稍后重试。"}, source="search_web", evidence="empty_cards", references=refs)
        return {"speak": "这次没拿到可用图片，我稍后可以再试一次。", "render": ev, "ui": ui}
    ev = build_render_evidence_block(source="search_web + direct image validation", evidence={"count": len(cards)}, references=refs)
    ui = attach_evidence_fields({"type": "card_grid", "title": "优雅时尚女性图片", "cards": cards}, source="unsplash/pexels", evidence={"validated_cards": len(cards)}, references=refs)
    return {"speak": f"我找到了{len(cards)}张优雅时尚女性图片。", "render": ev, "ui": ui}

if __name__ == "__main__":
    r = asyncio.run(run(mock=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r and isinstance(r.get("ui"), dict)
    print("OK")
