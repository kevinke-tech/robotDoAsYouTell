"""一次性技能：搜索并嵌入可播放的运动视频。"""
from urllib.parse import quote_plus

import httpx

RUN_SPEC = {
    "name": "sports_video_embed_oneshot",
    "description": "搜索运动视频并返回可播放嵌入卡片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "健身训练"},
            "mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


async def run(query: str = "健身训练", mock: bool = False, **kwargs):
    safe_query = (query or "健身训练").strip()
    if mock:
        return {
            "speak": "我给你找了一个运动视频，现在就能直接播放。",
            "render": "source: mock\nsource_url: mock://sports\nreferences: mock_video_id",
            "ui": {
                "type": "video_player",
                "title": "运动视频（测试）",
                "video_url": "https://www.youtube.com/embed?listType=search&list=fitness+workout",
            },
        }
    api = "https://api.dailymotion.com/videos"
    params = {"search": safe_query, "limit": 1, "fields": "id,title,url,thumbnail_360_url"}
    timeout = 8.0
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(api, params=params)
        data = resp.json() if resp.status_code == 200 else {}
        items = data.get("list") if isinstance(data, dict) else []
        if items:
            item = items[0] if isinstance(items[0], dict) else {}
            video_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "精彩运动视频").strip()
            page_url = str(item.get("url") or "").strip()
            if video_id:
                embed_url = f"https://www.dailymotion.com/embed/video/{video_id}"
                return {
                    "speak": f"我找到一个{safe_query}视频，已经给你放好了。",
                    "render": (
                        f"source: dailymotion_api\nsource_url: {api}\n"
                        f"references: video_id={video_id}, title={title}, page_url={page_url}"
                    ),
                    "ui": {"type": "video_player", "title": title, "video_url": embed_url},
                }
        reason = f"HTTP {resp.status_code} 或返回为空"
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
    yt_embed = f"https://www.youtube.com/embed?listType=search&list={quote_plus(safe_query)}"
    return {
        "speak": "我这次没拿到稳定的视频源，先给你一个可直接播放的运动搜索视频。",
        "render": (
            "source: youtube_embed_fallback\n"
            f"source_url: {yt_embed}\nevidence: dailymotion_error={reason}"
        ),
        "ui": {"type": "iframe_card", "title": f"{safe_query}视频", "iframe_url": yt_embed},
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(query="篮球训练", mock=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
