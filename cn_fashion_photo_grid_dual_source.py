"""时尚/写真人像图片检索：双源抓取并以卡片网格返回。"""
import asyncio
from datetime import datetime, timezone
import html
import re
import httpx

RUN_SPEC = {
    "name": "cn_fashion_photo_grid_dual_source",
    "description": "从中国可访问图源检索时尚写真人像图片并展示网格卡片。",
    "args_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "default": "时尚 写真 人像 美女"}, "count": {"type": "integer", "default": 6, "minimum": 1, "maximum": 6}},
        "required": [],
    },
}

def _norm_query(query: str) -> str:
    q = (query or "").strip()
    return q if q else "时尚 写真 人像 美女"

async def _fetch_baidu(client: httpx.AsyncClient, q: str):
    url = "https://image.baidu.com/search/acjson"
    params = {"tn": "resultjson_com", "ipn": "rj", "word": q, "queryWord": q, "pn": 0, "rn": 30}
    try:
        r = await client.get(url, params=params)
        data = r.json() if r.status_code == 200 else {}
        rows = data.get("data") if isinstance(data, dict) else []
        items = [{"title": str(x.get("fromPageTitleEnc") or x.get("fromPageTitle") or "百度图片"), "image_url": str(x.get("thumbURL") or x.get("middleURL") or ""), "source": "Baidu"} for x in rows if isinstance(x, dict)]
        return items, {"source": "Baidu", "source_url": str(r.url), "status": r.status_code, "hits": len(items)}
    except Exception as e:
        return [], {"source": "Baidu", "source_url": url, "error": str(e)}

async def _fetch_bing(client: httpx.AsyncClient, q: str):
    url = "https://cn.bing.com/images/search"
    try:
        r = await client.get(url, params={"q": q, "form": "HDRSC2", "first": 1})
        text = r.text if r.status_code == 200 else ""
        urls = [html.unescape(x).replace("\\/", "/") for x in re.findall(r'murl&quot;:&quot;(.*?)&quot;', text)]
        items = [{"title": "必应图片", "image_url": u, "source": "Bing"} for u in urls if u.startswith("http")]
        return items, {"source": "Bing", "source_url": str(r.url), "status": r.status_code, "hits": len(items)}
    except Exception as e:
        return [], {"source": "Bing", "source_url": url, "error": str(e)}

async def run(query: str = "时尚 写真 人像 美女", count: int = 6, **kwargs):
    q, want = _norm_query(query), max(1, min(int(count or 6), 6))
    if kwargs.get("_smoke_test"):
        rows = [{"title": "时尚人像 1", "image_url": "https://example.com/a.jpg", "source": "mock"}, {"title": "时尚人像 2", "image_url": "https://example.com/b.jpg", "source": "mock"}]
        refs = [{"source": "mock", "source_url": "https://example.com/mock", "hits": len(rows)}]
    else:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0), headers={"User-Agent": "Mozilla/5.0"}) as client:
                a, ra = await _fetch_baidu(client, q)
                b, rb = await _fetch_bing(client, q)
            rows, refs = a + b, [ra, rb]
        except Exception as e:
            rows, refs = [], [{"source": "runtime", "evidence": str(e)}]
    cards, seen = [], set()
    for x in rows:
        u = str(x.get("image_url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        cards.append({"title": str(x.get("title") or "时尚人像"), "image_url": u, "action_url": u, "subtitle": f"来源: {x.get('source', 'unknown')}"})
        if len(cards) >= want:
            break
    ts = datetime.now(timezone.utc).isoformat()
    if not cards:
        return {"speak": "我这次没抓到可展示的图片，你稍后再试试。", "render": f"query: {q}\nsource: Baidu,Bing\nreferences: {refs}\nevidence: empty_cards\nretrieved_at: {ts}", "ui": {"type": "info_card", "title": "图片获取失败", "message": "未获取到可用缩略图，请稍后重试。", "source_url": "https://image.baidu.com/ / https://cn.bing.com/images"}}
    return {"speak": f"我找到了{len(cards)}张时尚写真人像图片。", "render": f"query: {q}\nsource: Baidu,Bing\nreferences: {refs}\nevidence: first_card={cards[0]['image_url']}\nretrieved_at: {ts}", "ui": {"type": "card_grid", "title": "时尚写真人像图片", "cards": cards}}

if __name__ == "__main__":
    result = asyncio.run(run(query="测试", count=2, _smoke_test=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result and isinstance(result.get("ui"), dict)
    assert result["ui"].get("type") in {"card_grid", "info_card"}
    print("OK")
