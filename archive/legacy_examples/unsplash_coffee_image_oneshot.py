"""一次性技能：获取并展示 Unsplash 咖啡图片。"""
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

RUN_SPEC = {
    "name": "unsplash_coffee_image_oneshot",
    "description": "搜索并展示一张高质量咖啡图片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "coffee"},
            "use_mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


async def _fetch_image(query: str) -> dict:
    source_url = f"https://source.unsplash.com/featured/?{quote(query)}"
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(source_url, headers={"User-Agent": "vox-skill/1.0"})
        final_url = str(resp.url)
        ok = resp.status_code == 200 and final_url.startswith("http")
        return {"ok": ok, "source_url": source_url, "image_url": final_url, "status": resp.status_code, "time": now}
    except Exception as exc:
        return {"ok": False, "source_url": source_url, "image_url": "", "status": "error", "time": now, "error": str(exc)}


async def run(query: str = "coffee", use_mock: bool = False, **kwargs):
    data = {
        "ok": True,
        "source_url": "https://source.unsplash.com/featured/?coffee",
        "image_url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085",
        "status": 200,
        "time": "mock",
    } if use_mock else await _fetch_image(query or "coffee")
    title = f"高质量咖啡图片：{query or 'coffee'}"
    if data.get("ok"):
        return {
            "speak": "我帮你找到一张咖啡图片，已经放到界面里了。",
            "render": (
                f"图片标题: {title}\n"
                f"source: Unsplash Source\nsource_url: {data['source_url']}\n"
                f"evidence: status={data['status']}, fetched_at={data['time']}\n"
                f"image_url: {data['image_url']}"
            ),
            "ui": {
                "type": "image_card",
                "title": title,
                "image_url": data["image_url"],
                "caption": f"来源链接: {data['source_url']}",
            },
        }
    err = data.get("error", "未拿到可用图片")
    return {
        "speak": "我这次没拿到咖啡图片，不过我把失败原因放在卡片里了。",
        "render": (
            f"图片标题: {title}\nsource: Unsplash Source\nsource_url: {data['source_url']}\n"
            f"evidence: status={data['status']}, fetched_at={data['time']}, error={err}"
        ),
        "ui": {"type": "info_card", "title": "咖啡图片获取失败", "message": f"原因: {err}"},
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(query="coffee", use_mock=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
