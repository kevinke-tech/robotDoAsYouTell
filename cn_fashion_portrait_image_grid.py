"""中文一次性技能：多源抓取时尚写真风格图片并网格展示。"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import quote_plus

import httpx
from evidence_utils import build_render_evidence_block

RUN_SPEC = {
    "name": "cn_fashion_portrait_image_grid",
    "description": "展示健康风格的时尚写真图片网格。",
    "args_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "default": "时尚 写真 女生 高清"}, "limit": {"type": "integer", "default": 8, "minimum": 4, "maximum": 12}},
        "required": [],
    },
}

_BAD = ("性感", "泳装", "内衣", "裸", "成人", "sexy", "lingerie", "nude")

def _pick(text: str, limit: int) -> list[dict]:
    out, seen = [], set()
    for u, t in re.findall(r'"(?:murl|objURL|thumbURL|hoverURL)"\s*:\s*"(https?:[^"]+)".{0,260}?"(?:t|fromPageTitleEnc|title)"\s*:\s*"([^"]{1,80})"', text, re.I | re.S):
        uu, tt = u.replace("\\/", "/").strip(), re.sub(r"\s+", " ", t).strip()
        if not uu or uu in seen or any(k in (uu + tt).lower() for k in _BAD):
            continue
        seen.add(uu); out.append({"title": tt or "时尚人像", "image_url": uu, "action_url": uu, "subtitle": "可点击查看大图"})
        if len(out) >= limit:
            break
    return out

async def _fetch(url: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN,zh;q=0.9"})
            return r.status_code == 200, r.text or ""
    except Exception:
        return False, ""

async def run(query: str = "时尚 写真 女生 高清", limit: int = 8, **kwargs):
    mock = kwargs.get("_mock_items")
    if isinstance(mock, list) and mock:
        cards = mock[: max(4, min(int(limit or 8), 12))]
        return {"speak": "我给你整理了一组时尚风格图片。", "render": "source: mock\nevidence: smoke_test", "ui": {"type": "card_grid", "title": "时尚写真图片", "cards": cards}}
    n = max(4, min(int(limit or 8), 12)); q = quote_plus(str(query or "").strip() or "时尚 写真 女生 高清")
    sources = [("bing", f"https://cn.bing.com/images/async?q={q}&first=0&count=35&adlt=strict"), ("baidu", f"https://image.baidu.com/search/index?tn=baiduimage&word={q}")]
    cards, refs = [], []
    for name, url in sources:
        ok, html = await _fetch(url); refs.append({"source": name, "source_url": url, "ok": ok})
        if ok and len(cards) < n:
            cards.extend(_pick(html, n - len(cards)))
    if not cards:
        block = build_render_evidence_block(source="bing+baidu", source_url=sources[0][1], evidence={"query": query, "count": 0}, references=refs, extra_lines=["结论: 暂时没有抓到可展示的图片，请稍后重试。"])
        return {"speak": "我这次没抓到可展示的图片，稍后再试一次吧。", "render": block, "ui": {"type": "info_card", "title": "图片获取失败", "message": "未获取到可用图片，已自动尝试 Bing 与百度。", "references": refs}}
    block = build_render_evidence_block(source="bing+baidu", source_url=sources[0][1], evidence={"query": query, "count": len(cards)}, references=refs, extra_lines=["结论: 已筛选为健康、适合普通浏览的时尚写真图片。"])
    return {"speak": f"我找到{len(cards)}张时尚写真图片，点卡片就能看大图。", "render": block, "ui": {"type": "card_grid", "title": "时尚写真图片网格", "cards": cards, "references": refs}}

if __name__ == "__main__":
    demo = [{"title": "示例图", "image_url": "https://example.com/a.jpg", "action_url": "https://example.com/a.jpg", "subtitle": "可点击查看大图"}]
    r = asyncio.run(run(query="测试", limit=4, _mock_items=demo))
    assert isinstance(r, dict) and "speak" in r and "render" in r and isinstance(r.get("ui"), dict)
    print("OK")
