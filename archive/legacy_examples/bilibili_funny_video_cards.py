"""一次性技能：搜索并展示 Bilibili 搞笑视频卡片。"""
import re
from html import unescape

import httpx

RUN_SPEC = {
    "name": "bilibili_funny_video_cards",
    "description": "搜索热门搞笑视频并返回可点击卡片列表。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "搞笑视频"},
            "limit": {"type": "integer", "default": 6, "minimum": 5, "maximum": 10},
            "mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", unescape(str(text or "")))).strip()


def _mk_item(v: dict) -> dict:
    pic = str(v.get("pic") or "")
    if pic.startswith("//"):
        pic = "https:" + pic
    bvid = str(v.get("bvid") or "")
    return {
        "title": _clean(v.get("title")),
        "thumbnail": pic,
        "url": f"https://www.bilibili.com/video/{bvid}" if bvid else str(v.get("arcurl") or ""),
        "description": _clean(v.get("description"))[:90],
        "platform": "Bilibili",
    }


async def run(query: str = "搞笑视频", limit: int = 6, mock: bool = False, **kwargs):
    api = "https://api.bilibili.com/x/web-interface/search/type"
    want = max(5, min(int(limit or 6), 10))
    err, items = "", []
    if mock:
        items = [{"title": f"搞笑片段示例 {i}", "thumbnail": "https://i0.hdslb.com/bfs/archive/mock.jpg", "url": f"https://www.bilibili.com/video/BV1mock{i}", "description": "这是用于冒烟测试的模拟视频。", "platform": "Bilibili"} for i in range(1, 6)]
    else:
        try:
            params = {"search_type": "video", "keyword": query, "order": "click", "page": 1}
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(api, params=params)
            data = resp.json() if resp.status_code == 200 else {}
            raw = (((data.get("data") or {}).get("result")) or [])[:want]
            items = [x for x in (_mk_item(v) for v in raw) if x["title"] and x["url"]]
        except Exception as e:
            err = str(e)
    if len(items) < 5:
        why = f"抓取结果不足 5 条（当前 {len(items)} 条）"
        if err:
            why += f"，错误: {err}"
        return {
            "speak": "我这次没拿到足够的视频，稍后我可以再试一次。",
            "render": f"source: Bilibili 搜索 API\nsource_url: {api}\nevidence: query={query}, count={len(items)}, reason={why}",
            "ui": {"type": "info_card", "title": "搞笑视频获取失败", "message": why, "source_url": api},
        }
    refs = [v["url"] for v in items[:5]]
    lines = [f"{i+1}. {v['title']} | {v['platform']} | {v['url']}" for i, v in enumerate(items[:want])]
    return {
        "speak": "我帮你找了几条热门搞笑视频，直接点卡片就能看。",
        "render": f"source: Bilibili 搜索 API\nsource_url: {api}\nevidence: query={query}, count={len(items)}\nreferences: " + ", ".join(refs) + "\n\n" + "\n".join(lines),
        "ui": {"type": "video_card_list", "title": "热门搞笑视频", "layout": "grid", "items": items[:want]},
    }


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run(mock=True, limit=5))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert isinstance(result.get("ui"), dict) and len(result["ui"].get("items", [])) >= 5
    print("OK")
