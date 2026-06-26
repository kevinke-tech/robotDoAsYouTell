"""中文图片检索技能：聚合百度与必应图片，返回卡片网格。"""
import asyncio
import re
from urllib.parse import quote_plus

import httpx

RUN_SPEC = {
    "name": "beautiful_women_image_grid_cn",
    "description": "搜索并展示写真、时尚、美妆风格图片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "beautiful women fashion photography"},
            "limit": {"type": "integer", "default": 8, "minimum": 1, "maximum": 12},
            "mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


async def _fetch_bing(client: httpx.AsyncClient, query: str, limit: int):
    out, src = [], f"https://cn.bing.com/images/search?q={quote_plus(query)}"
    try:
        text = (await client.get(src, timeout=8.0)).text
        for u in re.findall(r'"murl":"(.*?)"', text):
            img = u.encode("utf-8").decode("unicode_escape").replace("\\/", "/")
            if img.startswith("http"):
                out.append({"title": "必应图片", "image_url": img, "source": "Bing", "source_url": src})
            if len(out) >= limit:
                break
    except Exception:
        pass
    return out, src


async def _fetch_baidu(client: httpx.AsyncClient, query: str, limit: int):
    out, src = [], f"https://image.baidu.com/search/acjson?tn=resultjson_com&ipn=rj&rn={limit*2}&word={quote_plus(query)}"
    try:
        data = (await client.get(src, timeout=8.0)).json()
        for it in data.get("data") or []:
            img = it.get("thumbURL") or it.get("middleURL") or it.get("hoverURL")
            if isinstance(img, str) and img.startswith("http"):
                title = re.sub("<.*?>", "", str(it.get("fromPageTitle") or "百度图片")).strip() or "百度图片"
                out.append({"title": title[:32], "image_url": img, "source": "Baidu", "source_url": src})
            if len(out) >= limit:
                break
    except Exception:
        pass
    return out, src


async def run(query: str = "beautiful women fashion photography", limit: int = 8, mock: bool = False, **kwargs):
    limit = max(1, min(int(limit or 8), 12))
    if mock:
        return {"speak": "我已经整理好图片网格。", "render": "source: mock\nevidence: smoke_test", "ui": {"type": "card_grid", "title": "冒烟测试", "cards": [{"title": "示例图", "image_url": "https://example.com/a.jpg", "subtitle": "source: mock", "action_url": "https://example.com"}]}}
    try:
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}, timeout=10.0) as client:
            baidu, baidu_src = await _fetch_baidu(client, query, limit)
            bing, bing_src = await _fetch_bing(client, query, limit)
        seen, items = set(), []
        for it in baidu + bing:
            if it["image_url"] not in seen:
                seen.add(it["image_url"]); items.append(it)
            if len(items) >= limit:
                break
        if not items:
            return {"speak": "我这次没抓到可用图片，你可以换个关键词再试。", "render": f"source: Baidu,Bing\nreferences: {baidu_src} | {bing_src}\nevidence: empty_result", "ui": {"type": "info_card", "title": "图片获取失败", "message": "双源检索都未返回可用直链图片。"}}
        cards = [{"title": it["title"], "image_url": it["image_url"], "subtitle": f"source: {it['source']}", "action_url": it["source_url"]} for it in items]
        refs = " | ".join(sorted({it["source_url"] for it in items}))
        return {"speak": f"找到了{len(cards)}张风格图片，已经给你排成网格。", "render": f"source: Baidu,Bing\nreferences: {refs}\nevidence: count={len(cards)}, query={query}", "ui": {"type": "card_grid", "title": f"图片结果：{query}", "cards": cards}}
    except Exception as e:
        return {"speak": "网络检索出了点问题，我先返回失败信息给你。", "render": f"source: Baidu,Bing\nevidence: exception={type(e).__name__}", "ui": {"type": "info_card", "title": "检索异常", "message": f"失败原因: {type(e).__name__}"}}


if __name__ == "__main__":
    r = asyncio.run(run(query="美女写真", limit=2, mock=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
