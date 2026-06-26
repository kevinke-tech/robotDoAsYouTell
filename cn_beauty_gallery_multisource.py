"""美女写真/时尚人像图片画廊（双源检索，CN 优先）。"""
import json
from typing import Any

import httpx
from evidence_utils import attach_evidence_fields, build_render_evidence_block

RUN_SPEC = {
    "name": "cn_beauty_gallery_multisource",
    "description": "搜索并渲染一组美女写真与时尚人像图片画廊。",
    "args_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "default": "美女 写真 时尚 人像"}, "limit": {"type": "integer", "default": 8, "minimum": 3, "maximum": 12}, "use_mock": {"type": "boolean", "default": False}},
        "required": [],
    },
}


async def _fetch(client: httpx.AsyncClient, url: str, params: dict[str, Any], parser):
    try:
        r = await client.get(url, params=params)
        return parser(r.json() if r.status_code == 200 else {})
    except Exception:
        return []


async def run(query: str = "美女 写真 时尚 人像", limit: int = 8, use_mock: bool = False, **kwargs):
    n = max(3, min(int(limit or 8), 12))
    if use_mock:
        cards = [{"title": f"示例图 {i+1}", "image_url": "https://example.com/mock.jpg", "action_url": "https://example.com", "subtitle": "来源: mock"} for i in range(n)]
        return {"speak": "我整理了一组示例人像图。", "render": "source: mock\nreferences: [{\"provider\":\"mock\"}]", "ui": {"type": "card_grid", "title": "美女写真画廊（示例）", "cards": cards}}

    async def parse_baidu(data: dict[str, Any]):
        out = []
        for d in data.get("data") or []:
            u = str(d.get("thumbURL") or d.get("middleURL") or "").strip()
            if u:
                out.append({"title": str(d.get("fromPageTitleEnc") or "百度图片"), "image_url": u, "action_url": str(d.get("fromURLHost") or "https://image.baidu.com"), "subtitle": "来源: 百度图片"})
            if len(out) >= n:
                break
        return out

    async def parse_wiki(data: dict[str, Any]):
        out = []
        for p in (data.get("query") or {}).get("pages", {}).values():
            ii = ((p.get("imageinfo") or [{}])[0] or {})
            u = str(ii.get("thumburl") or ii.get("url") or "").strip()
            if u:
                out.append({"title": str(p.get("title") or "Wikimedia"), "image_url": u, "action_url": str(ii.get("descriptionurl") or "https://commons.wikimedia.org"), "subtitle": "来源: Wikimedia Commons"})
            if len(out) >= n:
                break
        return out

    refs = [{"provider": "baidu_images", "source_url": "https://image.baidu.com/search/acjson"}, {"provider": "wikimedia_commons", "source_url": "https://commons.wikimedia.org/w/api.php"}]
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN,zh;q=0.9"}) as client:
            cards = await _fetch(client, "https://image.baidu.com/search/acjson", {"tn": "resultjson_com", "ipn": "rj", "word": query, "rn": n, "pn": 0}, parse_baidu)
            if not cards:
                cards = await _fetch(client, "https://commons.wikimedia.org/w/api.php", {"action": "query", "format": "json", "generator": "search", "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": n, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 640}, parse_wiki)
    except Exception as e:
        cards = []
        refs.append({"error": f"{type(e).__name__}: {e}"})

    if not cards:
        ev = build_render_evidence_block(source="baidu_images|wikimedia_commons", source_url="https://image.baidu.com/search/acjson", evidence={"query": query, "count": 0}, references=refs)
        ui = attach_evidence_fields({"type": "info_card", "title": "图片获取失败", "message": "暂时没拿到可用图片，稍后我再试。"}, source="baidu_images|wikimedia_commons", references=refs)
        return {"speak": "我这次没取到图片，你稍后再让我试试。", "render": ev, "ui": ui}

    ev = build_render_evidence_block(source="baidu_images->wikimedia_commons_fallback", source_url="https://image.baidu.com/search/acjson", evidence={"query": query, "count": len(cards)}, references=refs)
    ui = attach_evidence_fields({"type": "card_grid", "title": "美女写真与时尚人像", "cards": cards}, source="baidu_images", references=refs)
    return {"speak": f"我找到了{len(cards)}张风格不错的人像图。", "render": ev, "ui": ui}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(run(use_mock=True, limit=4))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r and r["ui"].get("type") in {"card_grid", "info_card"}
    print("OK")
