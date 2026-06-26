"""ONE-SHOT: 获取并展示一张真实城市夜景大图。"""
import asyncio

import httpx

RUN_SPEC = {
    "name": "city_night_view_image_card",
    "description": "搜索并展示一张高质量城市夜景照片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "city night view"},
        },
        "required": [],
    },
}


async def run(query: str = "city night view", mock_item: dict | None = None, **kwargs):
    endpoint = "https://commons.wikimedia.org/w/api.php"
    if mock_item:
        title = str(mock_item.get("title") or "城市夜景")
        image_url = str(mock_item.get("image_url") or "")
        source_url = str(mock_item.get("source_url") or "")
    else:
        title, image_url, source_url = "", "", ""
        params = {
            "action": "query",
            "format": "json",
            "origin": "*",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrlimit": "8",
            "gsrsearch": f"{query} skyline night",
            "prop": "imageinfo",
            "iiprop": "url|size",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(endpoint, params=params)
                data = resp.json() if resp.status_code == 200 else {}
            pages = (data.get("query") or {}).get("pages") or {}
            for page in pages.values():
                info = ((page.get("imageinfo") or [{}])[0]) if isinstance(page, dict) else {}
                if int(info.get("width") or 0) >= 1200 and str(info.get("url") or "").startswith("http"):
                    title = str(page.get("title") or "").replace("File:", "").strip() or "城市夜景"
                    image_url = str(info.get("url") or "").strip()
                    source_url = str(info.get("descriptionurl") or "").strip()
                    break
        except Exception as e:
            return {
                "speak": "我现在连不上图片来源，稍后再试一次吧。",
                "render": f"图片获取失败\nsource: Wikimedia Commons API\nsource_url: {endpoint}\nevidence: {type(e).__name__}: {e}",
                "ui": {"type": "info_card", "title": "城市夜景图片获取失败", "message": "网络请求失败，已返回错误证据。"},
            }
    if not image_url:
        return {
            "speak": "我暂时没找到合适的城市夜景图。",
            "render": f"未检索到可用结果\nsource: Wikimedia Commons API\nsource_url: {endpoint}\nevidence: query={query}",
            "ui": {"type": "info_card", "title": "未找到图片", "message": "请稍后重试或换一个关键词。"},
        }
    return {
        "speak": "我找到一张城市夜景图，已经放到大图卡片里了。",
        "render": f"已找到城市夜景图片\nsource: Wikimedia Commons API\nsource_url: {source_url or endpoint}\nevidence: query={query}; title={title}\nreferences: {image_url}",
        "ui": {
            "type": "image_card",
            "title": title,
            "image_url": image_url,
            "caption": f"来源: {source_url or 'Wikimedia Commons'}",
        },
    }


if __name__ == "__main__":
    sample = {"title": "Mock City Night", "image_url": "https://example.com/night.jpg", "source_url": "https://example.com"}
    out = asyncio.run(run(mock_item=sample))
    assert isinstance(out, dict) and "speak" in out and "render" in out and isinstance(out.get("ui"), dict)
    print("OK")
