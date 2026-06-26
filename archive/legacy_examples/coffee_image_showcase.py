"""一次性技能：联网检索并展示高质量咖啡图片。"""
import httpx

RUN_SPEC = {
    "name": "coffee_image_showcase",
    "description": "搜索并展示一张高质量咖啡图片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "coffee"},
            "mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


async def run(query: str = "coffee", mock: bool = False, **kwargs):
    api_url = "https://commons.wikimedia.org/w/api.php"
    if mock:
        image_url = "https://upload.wikimedia.org/wikipedia/commons/4/45/A_small_cup_of_coffee.JPG"
        return {
            "speak": "我帮你找了一张清晰的咖啡图。",
            "render": (
                "source: Wikimedia Commons (mock)\n"
                f"source_url: {api_url}\n"
                "evidence: mock=true, image_selected=1"
            ),
            "ui": {
                "type": "image_card",
                "title": "高质量咖啡图片",
                "image_url": image_url,
                "caption": "示例咖啡图（冒烟测试）",
            },
        }
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": "5",
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "iiurlwidth": "1400",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(api_url, params=params)
            data = resp.json() if resp.status_code == 200 else {}
    except Exception as e:
        msg = f"网络请求失败：{e}"
        return {
            "speak": "我现在连网不太稳定，暂时没拿到咖啡图片。",
            "render": f"source_url: {api_url}\nevidence: {msg}",
            "ui": {"type": "info_card", "title": "咖啡图片获取失败", "message": msg},
        }
    pages = (data.get("query") or {}).get("pages") or {}
    pick = None
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        if str(info.get("mime") or "").startswith("image/") and (info.get("thumburl") or info.get("url")):
            pick = (page, info)
            break
    if not pick:
        return {
            "speak": "我暂时没找到清晰的咖啡图片，你稍后再试试。",
            "render": f"source_url: {api_url}\nevidence: no_valid_image_in_response",
            "ui": {"type": "info_card", "title": "未找到图片", "message": "未检索到可展示的咖啡图片"},
        }
    page, info = pick
    image_url = str(info.get("thumburl") or info.get("url") or "").strip()
    title = str(page.get("title") or "Coffee").replace("File:", "")
    w, h = info.get("width"), info.get("height")
    return {
        "speak": "找到啦，这张咖啡图片很清晰。",
        "render": (
            "source: Wikimedia Commons API\n"
            f"source_url: {api_url}\n"
            f"evidence: query={query}, title={title}, width={w}, height={h}"
        ),
        "ui": {"type": "image_card", "title": "高质量咖啡图片", "image_url": image_url, "caption": title},
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(mock=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
