"""中文图片画廊技能：聚合公开图片直链并输出卡片网格。"""
from __future__ import annotations

from evidence_utils import attach_evidence_fields, build_render_evidence_block
from web_fetch import fetch_page
from web_search import search_web

RUN_SPEC = {
    "name": "cn_beauty_gallery_card",
    "description": "搜索并展示美女写真/时尚人像图片画廊。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "美女 写真 时尚 人像 摄影"},
            "max_images": {"type": "integer", "minimum": 3, "maximum": 12, "default": 6},
        },
        "required": [],
    },
}


async def run(query: str = "美女 写真 时尚 人像 摄影", max_images: int = 6, mock: bool = False, **kwargs):
    if mock:
        return {"speak": "我整理好图片画廊了。", "render": "source: mock\nreferences: []", "ui": {"type": "card_grid", "title": "图片画廊（演示）", "cards": [{"title": "演示图", "image_url": "https://example.com/demo.jpg", "subtitle": "来源: mock"}]}}
    try:
        n = max(3, min(int(max_images or 6), 12))
        plans = [("unsplash_cdn", f"site:images.unsplash.com {query}"), ("pexels_cdn", f"site:images.pexels.com {query}")]
        picks, refs = [], []
        for source, q in plans:
            try:
                sr = await search_web(q, max_results=max(4, n))
            except Exception as e:
                refs.append({"source": source, "error": f"search_failed:{type(e).__name__}"})
                continue
            for h in (sr.get("hits") or []):
                u = str(h.get("url") or "").strip()
                if (".jpg" not in u and ".jpeg" not in u and ".png" not in u) or u in {x["image_url"] for x in picks}:
                    continue
                ok = False
                try:
                    fr = await fetch_page(u, timeout_ms=4500, max_bytes=4096)
                    ok = bool(fr.ok or (fr.status and fr.status < 400))
                    refs.append({"source": source, "source_url": u, "status": fr.status, "final_url": fr.final_url})
                except Exception as e:
                    refs.append({"source": source, "source_url": u, "error": f"fetch_failed:{type(e).__name__}"})
                if ok:
                    picks.append({"title": f"人像图 {len(picks)+1}", "image_url": u, "action_url": u, "subtitle": f"来源: {source}"})
                if len(picks) >= n:
                    break
            if len(picks) >= n:
                break
        if not picks:
            ev = build_render_evidence_block(source="unsplash_cdn|pexels_cdn", evidence={"query": query, "count": 0}, references=refs[:8])
            ui = attach_evidence_fields({"type": "info_card", "title": "图片获取失败", "message": "暂时没有拿到可用图片，请稍后重试。"}, source="multi_source_search", references=refs[:8])
            return {"speak": "这次没拿到可用图片，我稍后可以再试一次。", "render": ev, "ui": ui}
        ev = build_render_evidence_block(source="unsplash_cdn+pexels_cdn", evidence={"query": query, "picked": len(picks)}, references=refs[:12], extra_lines=["result: 已生成图片画廊"])
        ui = attach_evidence_fields({"type": "card_grid", "title": "高质量美女图片画廊", "cards": picks}, source="multi_source_search", references=refs[:12])
        return {"speak": f"我找到了 {len(picks)} 张图片，已经整理成画廊。", "render": ev, "ui": ui}
    except Exception as e:
        msg = f"技能异常已降级: {type(e).__name__}"
        return {"speak": "图片画廊暂时不可用，我已经记录了失败原因。", "render": build_render_evidence_block(source="cn_beauty_gallery_card", evidence=msg, references=[]), "ui": {"type": "info_card", "title": "图片画廊异常", "message": msg}}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(run(query="测试", max_images=3, mock=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
