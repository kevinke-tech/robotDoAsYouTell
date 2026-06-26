"""ONE-SHOT: 获取并展示一张 Unsplash 咖啡图片。"""
import time
import httpx

RUN_SPEC = {
    "name": "unsplash_coffee_image_card",
    "description": "搜索并展示一张高质量咖啡图片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "coffee"},
            "test_mode": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


async def run(query: str = "coffee", test_mode: bool = False, **kwargs):
    source = "Unsplash Source API"
    source_url = "https://source.unsplash.com/1600x900/?coffee"
    page_url = f"https://unsplash.com/s/photos/{(query or 'coffee').strip() or 'coffee'}"
    ts = int(time.time())
    image_url = f"https://source.unsplash.com/1600x900/?{(query or 'coffee').strip() or 'coffee'}&sig={ts}"
    title = "高质量咖啡图片"
    if test_mode:
        return {
            "speak": "我找到一张咖啡图片，已经展示给你。",
            "render": f"source: {source}\nsource_url: {source_url}\nevidence: test_mode mock",
            "ui": {"type": "image_card", "title": title, "image_url": image_url, "caption": f"来源链接: {page_url}"},
        }
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(image_url)
        final_url = str(resp.url) if resp.status_code == 200 else ""
        if not final_url:
            raise RuntimeError(f"status={resp.status_code}")
        return {
            "speak": "我给你找了一张高质量的咖啡图片。",
            "render": (
                f"source: {source}\nsource_url: {source_url}\n"
                f"references: {page_url}\nevidence: status=200, final_image_url={final_url}"
            ),
            "ui": {
                "type": "image_card",
                "title": title,
                "image_url": final_url,
                "caption": f"来源链接: {page_url}",
                "source_url": page_url,
            },
        }
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"
        return {
            "speak": "我暂时没拉到咖啡图片，但我保留了来源信息。",
            "render": (
                f"source: {source}\nsource_url: {source_url}\nreferences: {page_url}\n"
                f"evidence: request_failed={reason}"
            ),
            "ui": {"type": "info_card", "title": "咖啡图片获取失败", "message": f"失败原因: {reason}\n来源: {page_url}"},
        }


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(run(query="coffee", test_mode=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
