"""中文一次性技能：联网搜索并展示健康向时尚美女图片网格。"""
import asyncio
import html
import re

import httpx

from evidence_utils import attach_evidence_fields, build_render_evidence_block
from web_fetch import fetch_page
from web_search import search_web

RUN_SPEC = {"name": "cn_beauty_image_grid_live", "description": "搜索并展示健康向时尚/模特图片网格。", "args_schema": {"type": "object", "properties": {"query": {"type": "string", "default": "时尚女模特 艺术人像 高清"}, "limit": {"type": "integer", "default": 6, "minimum": 6, "maximum": 12}}, "required": []}}
_BAD = ("裸", "内衣", "比基尼", "泳装", "sexy", "adult")


def _ok(u: str, t: str) -> bool:
    s = (u + " " + t).lower()
    return u.startswith("http") and not any(k in s for k in _BAD)


async def _src_360(q: str, n: int):
    out, meta = [], {"source": "360_images", "source_url": "https://image.so.com/j", "ok": False}
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get("https://image.so.com/j", params={"q": q, "sn": "0", "pn": str(max(n * 2, 20))})
            for i in (r.json().get("list") or []):
                u, t = str(i.get("img") or "").strip(), str(i.get("title") or "时尚人像").strip()
                if _ok(u, t):
                    out.append({"title": t[:24], "image_url": u, "subtitle": "来源: 360图搜", "action_url": u})
        meta["ok"] = bool(out)
    except Exception as e:
        meta["error"] = f"{type(e).__name__}: {e}"
    return out[: n * 2], meta


async def _src_bing(q: str, n: int):
    out, meta = [], {"source": "bing_images", "source_url": "https://www.bing.com/images/async", "ok": False}
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as c:
            r = await c.get("https://www.bing.com/images/async", params={"q": q, "first": "0", "count": str(max(n * 2, 16)), "adlt": "off"}, headers={"User-Agent": "Mozilla/5.0"})
            for i, raw in enumerate(re.findall(r'murl&quot;:&quot;([^"]+?)&quot;', r.text or ""), start=1):
                u = html.unescape(raw).replace("\\/", "/")
                if _ok(u, ""):
                    out.append({"title": f"时尚人像 {i}", "image_url": u, "subtitle": "来源: Bing图片", "action_url": u})
        meta["ok"] = bool(out)
    except Exception as e:
        meta["error"] = f"{type(e).__name__}: {e}"
    return out[: n * 2], meta


async def _src_fallback(q: str, n: int):
    out, meta = [], {"source": "web_search+web_fetch", "source_url": "internal_backbone", "ok": False}
    try:
        hits = (await search_web(f"{q} site:weibo.com OR site:xiaohongshu.com 图片")).get("hits") or []
        for h in hits[:4]:
            fr = await fetch_page(str(h.get("url") or ""), timeout_ms=5000, max_bytes=180000)
            for u in re.findall(r'https?://[^\s"\']+\.(?:jpg|jpeg|png|webp)', fr.text or "", re.I):
                if _ok(u, str(h.get("title") or "")):
                    out.append({"title": str(h.get("title") or "图片")[:24], "image_url": u, "subtitle": "来源: 网页提取", "action_url": u})
        meta["ok"] = bool(out)
    except Exception as e:
        meta["error"] = f"{type(e).__name__}: {e}"
    return out[: n * 2], meta


async def run(query: str = "时尚女模特 艺术人像 高清", limit: int = 6, **kwargs):
    n = max(6, min(int(limit or 6), 12))
    if kwargs.get("_mock"):
        mock = [{"title": f"示例图{i}", "image_url": f"https://example.com/{i}.jpg", "subtitle": "mock", "action_url": f"https://example.com/{i}.jpg"} for i in range(1, n + 1)]
        return {"speak": "我准备好了图片卡片。", "render": "source: mock\nevidence: smoke_test", "ui": {"type": "card_grid", "title": "时尚美女图片", "cards": mock}}
    refs, cards, seen = [], [], set()
    for fn in (_src_360, _src_bing, _src_fallback):
        got, meta = await fn(query, n); refs.append(meta)
        for c in got:
            if c["image_url"] not in seen:
                seen.add(c["image_url"]); cards.append(c)
            if len(cards) >= n: break
        if len(cards) >= n: break
    render = build_render_evidence_block(source="360_images|bing_images|web_backbone", source_url="https://image.so.com/j", evidence={"query": query, "returned": len(cards), "required": n}, references=refs)
    if len(cards) < 6:
        return {"speak": "我这次只拿到少量可用图片，你可以稍后再试。", "render": "图片数量不足，未达6张。\n" + render, "ui": attach_evidence_fields({"type": "info_card", "title": "图片获取不完整", "message": "当前可用图片不足 6 张，请稍后重试或换关键词。"}, source="cn_image_sources", evidence={"count": len(cards)}, references=refs)}
    return {"speak": f"我找到了{len(cards)}张时尚风格图片，已经排好给你看。", "render": "已为你生成图片网格。\n" + render, "ui": attach_evidence_fields({"type": "card_grid", "title": "时尚/模特/艺术风格图片", "cards": cards[:n]}, source="cn_image_sources", source_url="https://image.so.com/j", evidence={"query": query, "count": len(cards[:n])}, references=refs)}


if __name__ == "__main__":
    r = asyncio.run(run(_mock=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
