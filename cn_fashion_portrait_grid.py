"""一次性技能：聚合可在中国大陆访问的时尚人像图片并返回卡片网格。"""
import asyncio
import html
import re
import urllib.parse
import httpx

RUN_SPEC = {
    "name": "cn_fashion_portrait_grid",
    "description": "搜索并展示6张时尚写真风格人像图片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "时尚写真 美女 人像摄影"},
            "count": {"type": "integer", "default": 6, "minimum": 1, "maximum": 6},
            "mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}

def _extract_urls(text: str):
    t = html.unescape(text or "")
    pats = [r'"murl":"(https?://[^"]+)"', r'"turl":"(https?://[^"]+)"', r'"img":"(https?://[^"]+)"', r'<img[^>]+src="(https?://[^"]+)"']
    urls = []
    for p in pats:
        urls.extend(re.findall(p, t, flags=re.I))
    return [u.replace("\\/", "/") for u in urls if re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", u, re.I)]

async def run(query: str = "时尚写真 美女 人像摄影", count: int = 6, mock: bool = False, **kwargs):
    try:
        count = max(1, min(int(count), 6))
        if mock:
            cards = [{"title": f"示例图片{i+1}", "image_url": f"https://example.com/{i+1}.jpg", "subtitle": "mock"} for i in range(count)]
            return {"speak": f"我整理了{count}张时尚人像图。", "render": "source: mock\nevidence: 离线结构测试数据", "ui": {"type": "card_grid", "title": "时尚人像图片", "cards": cards}}
        q = urllib.parse.quote_plus((query or "").strip() or "时尚写真 美女 人像摄影")
        sources = [
            ("Bing CN", f"https://cn.bing.com/images/search?q={q}&form=HDRSC3"),
            ("360图片", f"https://image.so.com/i?q={q}&src=srp"),
        ]
        urls, refs, fails = [], [], []
        headers = {"User-Agent": "Mozilla/5.0 VoxSkill/1.0"}
        async with httpx.AsyncClient(timeout=8.0, headers=headers, follow_redirects=True) as client:
            for name, url in sources:
                try:
                    r = await client.get(url)
                    found = _extract_urls(r.text)[: count * 2]
                    refs.append({"source": name, "source_url": url, "status": r.status_code, "found": len(found)})
                    urls.extend([(u, name) for u in found])
                except Exception as e:
                    fails.append(f"{name}:{e.__class__.__name__}")
                    refs.append({"source": name, "source_url": url, "status": "error", "evidence": str(e)})
        picked, seen = [], set()
        for u, s in urls:
            if u in seen:
                continue
            seen.add(u); picked.append((u, s))
            if len(picked) >= count:
                break
        if not picked:
            return {"speak": "我这次没找到合适的图片，稍后再试一次。", "render": f"source: Bing CN, 360图片\nreferences: {refs}\nevidence: 抓取结果为空; failures={fails}", "ui": {"type": "info_card", "title": "图片获取失败", "message": "暂时没有拿到可展示的图片，请稍后重试。"}}
        cards = [{"title": f"时尚人像 {i+1}", "image_url": u, "subtitle": f"来源: {s}"} for i, (u, s) in enumerate(picked)]
        return {"speak": f"我找到了{len(cards)}张时尚写真风格的人像图片。", "render": f"source: Bing CN, 360图片\nreferences: {refs}\nevidence: query={query}; returned={len(cards)}; failures={fails or 'none'}", "ui": {"type": "card_grid", "title": "时尚写真人像精选", "cards": cards}}
    except Exception as e:
        return {"speak": "处理图片时出了点问题，我先给你返回失败信息。", "render": f"source: internal\nsource_url: N/A\nevidence: {e.__class__.__name__}: {e}", "ui": {"type": "info_card", "title": "技能降级返回", "message": f"失败原因: {e.__class__.__name__}"}}

if __name__ == "__main__":
    r = asyncio.run(run(mock=True, count=6))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
