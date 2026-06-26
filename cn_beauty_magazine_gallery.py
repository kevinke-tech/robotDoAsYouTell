"""中文美女写真画廊：双源抓取并返回可视化网格。"""
import asyncio
from typing import Any, Dict, List

import httpx

RUN_SPEC = {
    "name": "cn_beauty_magazine_gallery",
    "description": "搜索并展示高质量美女人像/时尚风格照片画廊。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "美女 人像 时尚 杂志"},
            "count": {"type": "integer", "minimum": 4, "maximum": 12, "default": 8},
            "mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


async def _from_wikimedia(client: httpx.AsyncClient, query: str, count: int) -> List[Dict[str, str]]:
    u = "https://commons.wikimedia.org/w/api.php"
    p = {"action": "query", "format": "json", "generator": "search", "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": count, "prop": "imageinfo", "iiprop": "url"}
    r = await client.get(u, params=p, timeout=8.0)
    pages = ((r.json() if r.status_code == 200 else {}).get("query") or {}).get("pages") or {}
    out = []
    for v in pages.values():
        img = ((v.get("imageinfo") or [{}])[0]).get("url", "")
        if img.startswith("http"):
            out.append({"title": (v.get("title") or "Wikimedia").replace("File:", ""), "image_url": img, "action_url": f"https://commons.wikimedia.org/wiki/{v.get('title','')}", "subtitle": "来源: Wikimedia Commons"})
    return out[:count]


async def _from_openverse(client: httpx.AsyncClient, query: str, count: int) -> List[Dict[str, str]]:
    u = "https://api.openverse.org/v1/images/"
    r = await client.get(u, params={"q": query, "page_size": count}, timeout=8.0)
    rows = (r.json() if r.status_code == 200 else {}).get("results") or []
    return [{"title": x.get("title") or "Openverse", "image_url": x.get("url") or x.get("thumbnail") or "", "action_url": x.get("foreign_landing_url") or "https://openverse.org", "subtitle": f"来源: {x.get('source') or 'Openverse'}"} for x in rows if (x.get("url") or x.get("thumbnail"))][:count]


async def run(query: str = "美女 人像 时尚 杂志", count: int = 8, mock: bool = False, **kwargs: Any) -> Dict[str, Any]:
    count = max(4, min(int(count or 8), 12))
    if mock:
        cards = [{"title": f"示例写真 {i+1}", "image_url": f"https://picsum.photos/seed/beauty{i}/900/1200", "action_url": "https://picsum.photos", "subtitle": "来源: mock"} for i in range(count)]
        return {"speak": "我给你准备了一组写真画廊。", "render": "source: mock\nevidence: offline smoke test\nreferences: [https://picsum.photos]", "ui": {"type": "card_grid", "title": "美女写真画廊（测试）", "cards": cards}}
    cards, refs, evidence = [], [], []
    async with httpx.AsyncClient() as client:
        for fn, name, src in [(_from_wikimedia, "Wikimedia", "https://commons.wikimedia.org"), (_from_openverse, "Openverse", "https://api.openverse.org/v1/images/")]:
            try:
                got = await fn(client, query, count)
                cards.extend(got)
                evidence.append(f"{name}: ok, count={len(got)}")
            except Exception as e:
                evidence.append(f"{name}: failed, reason={type(e).__name__}")
            refs.append(src)
    uniq, seen = [], set()
    for c in cards:
        if c["image_url"] not in seen:
            seen.add(c["image_url"])
            uniq.append(c)
    cards = uniq[:count]
    if not cards:
        return {"speak": "我这次没抓到可展示的写真图，你稍后再试。", "render": f"source: Wikimedia/Openverse\nsource_url: {', '.join(refs)}\nevidence: {'; '.join(evidence)}\nreferences: {refs}", "ui": {"type": "info_card", "title": "写真获取失败", "message": "已尝试双数据源，但暂未获取到可用图片。"}}
    return {"speak": f"我找到了{len(cards)}张风格不错的写真图，已经整理成画廊。", "render": f"source: Wikimedia/Openverse\nsource_url: {', '.join(refs)}\nevidence: {'; '.join(evidence)}\nreferences: {refs}", "ui": {"type": "card_grid", "title": "高质量美女写真画廊", "cards": cards}}


if __name__ == "__main__":
    r = asyncio.run(run(mock=True, count=6))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r and r["ui"].get("type") in {"card_grid", "info_card"}
    print("OK")
