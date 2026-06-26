"""一次性技能：检索并展示搞笑视频卡片列表。"""
import asyncio
import re
from html import unescape

import httpx

RUN_SPEC = {
    "name": "funny_video_cards",
    "description": "搜索并展示可点击的搞笑视频卡片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "default": "搞笑视频"},
            "limit": {"type": "integer", "default": 5, "minimum": 5, "maximum": 10},
            "use_mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", unescape(text or ""))).strip()


async def run(keyword: str = "搞笑视频", limit: int = 5, use_mock: bool = False, **kwargs):
    limit = max(5, min(int(limit or 5), 10))
    api_url = "https://api.bilibili.com/x/web-interface/search/type"
    if use_mock:
        items = [{"title": f"示例搞笑视频{i}", "thumbnail": "https://i0.hdslb.com/bfs/archive/mock.jpg", "platform": "Bilibili", "url": f"https://www.bilibili.com/video/BV1mock{i}", "description": "这是用于冒烟测试的示例描述。"} for i in range(1, 6)]
        return {"speak": "我给你找了几条搞笑视频，点开就能看。", "render": f"source: mock\nsource_url: {api_url}\nevidence: smoke_test=true, count=5", "ui": {"type": "video_card_list", "title": "搞笑视频推荐", "layout": "grid", "items": items}}
    items, seen, evidence = [], set(), []
    keywords = [keyword, "funny clips", "comedy"]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            for kw in keywords:
                try:
                    r = await client.get(api_url, params={"search_type": "video", "keyword": kw, "page": 1})
                    data = r.json() if r.status_code == 200 else {}
                    rows = ((data.get("data") or {}).get("result")) or []
                    evidence.append(f"{kw}:{len(rows)}")
                    for row in rows:
                        url = str(row.get("arcurl") or "").strip()
                        if not url or url in seen:
                            continue
                        pic = str(row.get("pic") or "").strip()
                        pic = f"https:{pic}" if pic.startswith("//") else pic
                        items.append({"title": _clean(str(row.get("title") or "")), "thumbnail": pic, "platform": "Bilibili", "url": url, "description": _clean(str(row.get("description") or ""))[:80]})
                        seen.add(url)
                        if len(items) >= limit:
                            break
                    if len(items) >= limit:
                        break
                except Exception as e:  # noqa: BLE001
                    evidence.append(f"{kw}:error={e}")
    except Exception as e:  # noqa: BLE001
        evidence.append(f"client_error={e}")
    if not items:
        return {"speak": "我现在没拉到搞笑视频，稍后再试一次吧。", "render": f"source: Bilibili Search API\nsource_url: {api_url}\nevidence: {'; '.join(evidence) or 'no_data'}", "ui": {"type": "info_card", "title": "搞笑视频获取失败", "message": "暂时未获取到可用视频，请稍后重试。", "source_url": api_url}}
    items = items[:limit]
    lines = [f"{i+1}. {v['title']} ({v['platform']})\n{v['url']}" for i, v in enumerate(items)]
    return {"speak": f"我找到了{len(items)}条搞笑视频，已经帮你排好卡片了。", "render": f"source: Bilibili Search API\nsource_url: {api_url}\nevidence: keywords={keywords}, counts={'; '.join(evidence)}\n\n" + "\n".join(lines), "ui": {"type": "video_card_list", "title": "搞笑视频推荐", "layout": "grid", "items": items, "source": "Bilibili Search API", "source_url": api_url}}


if __name__ == "__main__":
    result = asyncio.run(run(use_mock=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert isinstance(result.get("ui"), dict) and len(result["ui"].get("items", [])) >= 5
    print("OK")
