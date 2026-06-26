"""一次性技能：检索并展示真实城市夜景照片。"""
from datetime import datetime, timezone
import html

import httpx

RUN_SPEC = {
    "name": "city_night_photo_html_card",
    "description": "搜索并展示一张高质量城市夜景图片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "city night skyline"},
            "mock_image_url": {"type": "string", "default": ""},
        },
        "required": [],
    },
}


async def run(query: str = "city night skyline", mock_image_url: str = "", **kwargs):
    source = "Wikimedia Commons API"
    source_url = "https://commons.wikimedia.org/w/api.php"
    fetched_at = datetime.now(timezone.utc).isoformat()
    if mock_image_url:
        html_block = (
            "<div><img src='"
            + html.escape(mock_image_url, quote=True)
            + "' alt='城市夜景' style='width:100%;max-width:960px;border-radius:12px;'/></div>"
        )
        return {
            "speak": "我给你展示一张城市夜景图。",
            "render": f"source: mock\nsource_url: local_test\nevidence: smoke_test=true; fetched_at={fetched_at}",
            "ui": {"type": "html_card", "title": "城市夜景", "html": html_block},
        }
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": "6",
        "gsrlimit": "8",
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(source_url, params=params)
            data = resp.json() if resp.status_code == 200 else {}
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        return {
            "speak": "我暂时没拉到夜景图片，稍后我再试一次。",
            "render": f"source: {source}\nsource_url: {source_url}\nevidence: network_error={reason}; fetched_at={fetched_at}",
            "ui": {"type": "info_card", "title": "城市夜景加载失败", "message": f"获取失败：{reason}"},
        }
    pages = ((data.get("query") or {}).get("pages") or {}).values()
    image_url = next(
        (info[0].get("url") for p in pages if (info := p.get("imageinfo")) and info[0].get("url")),
        "",
    )
    if not image_url:
        return {
            "speak": "我这次没有找到合适的城市夜景图。",
            "render": f"source: {source}\nsource_url: {source_url}\nevidence: empty_result=true; query={query}; fetched_at={fetched_at}",
            "ui": {"type": "info_card", "title": "未找到图片", "message": "请稍后重试，或换一个关键词。"},
        }
    html_block = (
        "<div><img src='"
        + html.escape(image_url, quote=True)
        + "' alt='城市夜景照片' style='width:100%;max-width:960px;border-radius:12px;'/></div>"
    )
    return {
        "speak": "我找到一张灯光很漂亮的城市夜景，已经展示给你了。",
        "render": f"source: {source}\nsource_url: {source_url}\nevidence: query={query}; fetched_at={fetched_at}\nimage_url: {image_url}",
        "ui": {"type": "html_card", "title": "城市夜景实拍", "html": html_block},
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(mock_image_url="https://example.com/city-night.jpg"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert "<img" in str((result.get("ui") or {}).get("html", ""))
    print("OK")
