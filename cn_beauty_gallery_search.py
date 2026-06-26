"""中文一次性技能：检索并展示人像/时尚风格图片画廊。"""
import re

from evidence_utils import attach_evidence_fields, build_render_evidence_block
from web_search import search_web

RUN_SPEC = {
    "name": "cn_beauty_gallery_search",
    "description": "从公开图片源检索多张人像时尚图片并展示画廊。",
    "args_schema": {
        "type": "object",
        "properties": {"count": {"type": "integer", "minimum": 4, "maximum": 10, "default": 6}},
        "required": [],
    },
}


async def run(count: int = 6, **kwargs):
    n = max(4, min(int(count or 6), 10))
    refs, cards, errs = [], [], []
    try:
        u = await search_web("site:unsplash.com/photos portrait fashion woman", max_results=n)
        for i, h in enumerate((u.get("hits") or [])[:n], 1):
            url = str(h.get("url") or "").strip()
            if "/photos/" not in url:
                continue
            cards.append({"title": h.get("title") or f"Unsplash 图{i}", "image_url": f"https://source.unsplash.com/900x1200/?portrait,fashion,woman&sig={i}", "action_url": url, "subtitle": f"来源: Unsplash | {url}"})
            refs.append({"source": "unsplash", "source_url": url, "title": h.get("title") or ""})
    except Exception as e:
        errs.append(f"unsplash_error={type(e).__name__}")
    try:
        p = await search_web("site:pexels.com/photo fashion portrait woman", max_results=n)
        for h in (p.get("hits") or []):
            url = str(h.get("url") or "").strip()
            m = re.search(r"/photo/[^/]*-(\d+)/?", url)
            if not m:
                continue
            pid = m.group(1)
            cards.append({"title": h.get("title") or f"Pexels #{pid}", "image_url": f"https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg?auto=compress&cs=tinysrgb&w=900", "action_url": url, "subtitle": f"来源: Pexels | {url}"})
            refs.append({"source": "pexels", "source_url": url, "title": h.get("title") or ""})
            if len(cards) >= n:
                break
    except Exception as e:
        errs.append(f"pexels_error={type(e).__name__}")
    cards = cards[:n]
    if not cards:
        ev = {"deploy_region": "CN", "primary_locale": "zh-CN", "fallback_paths": ["unsplash_search", "pexels_search"], "errors": errs or ["no_results"]}
        return {"speak": "我这次没抓到可用图片，稍后再试我会继续给你找。", "render": "本次未获取到图片。\n" + build_render_evidence_block(source="unsplash+pexels", evidence=ev), "ui": attach_evidence_fields({"type": "info_card", "title": "图片画廊暂不可用", "message": "未检索到可展示图片，请稍后重试。"}, source="unsplash+pexels", evidence=ev)}
    ev = {"deploy_region": "CN", "primary_locale": "zh-CN", "count": len(cards), "fallback_paths": ["unsplash_search", "pexels_search"], "errors": errs}
    render = "为你找到一组人像/时尚风格图片：\n" + build_render_evidence_block(source="unsplash+pexels", evidence=ev, references=refs[:n])
    ui = attach_evidence_fields({"type": "card_grid", "title": "高质量美女写真画廊", "cards": cards}, source="unsplash+pexels", references=refs[:n], evidence=ev)
    return {"speak": f"我找到了{len(cards)}张高质量人像图片，已经整理成画廊。", "render": render, "ui": ui}


if __name__ == "__main__":
    import asyncio

    out = asyncio.run(run(count=6))
    assert isinstance(out, dict) and "speak" in out and "render" in out and "ui" in out
    print("OK")
