"""一次性技能：搜索并返回可直接播放的健身/运动训练视频。"""
from datetime import datetime, timezone

import httpx

RUN_SPEC = {
    "name": "workout_video_player_cn",
    "description": "搜索可播放的健身训练视频并在 UI 中展示。",
    "args_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "default": "健身 训练 运动"}},
        "required": [],
    },
}


async def run(query: str = "健身 训练 运动", **kwargs):
    source_url = "https://commons.wikimedia.org/w/api.php"
    mock_video = kwargs.get("mock_video")
    if isinstance(mock_video, dict) and mock_video.get("video_url"):
        video = mock_video
    else:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrlimit": "5",
            "gsrsearch": f"{query} filetype:video",
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": "640",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(source_url, params=params)
                data = res.json() if res.status_code == 200 else {}
            pages = list((data.get("query") or {}).get("pages", {}).values())
            first = next((p for p in pages if (p.get("imageinfo") or [{}])[0].get("url")), {})
            info = (first.get("imageinfo") or [{}])[0]
            video = {
                "title": str(first.get("title") or "训练视频"),
                "video_url": str(info.get("url") or ""),
                "thumbnail_url": str(info.get("thumburl") or ""),
            }
        except Exception as e:
            msg = f"我这次没连上视频源，你可以稍后再试。错误是：{type(e).__name__}"
            return {
                "speak": "我暂时没拿到可播放视频，请稍后再试。",
                "render": f"source: Wikimedia Commons API\nsource_url: {source_url}\nevidence: network_error={type(e).__name__}\nresult: 无可播放视频\nreason: {msg}",
                "ui": {"type": "info_card", "title": "视频获取失败", "message": msg, "source_url": source_url},
            }
    if not video.get("video_url"):
        return {
            "speak": "我暂时没找到可播放的训练视频。",
            "render": f"source: Wikimedia Commons API\nsource_url: {source_url}\nevidence: empty_result_for_query={query}\nresult: 无可播放视频",
            "ui": {"type": "info_card", "title": "未找到视频", "message": f"关键词“{query}”暂无可播放结果", "source_url": source_url},
        }
    checked_at = datetime.now(timezone.utc).isoformat()
    title = video.get("title") or "训练视频"
    video_url = video["video_url"]
    thumb = video.get("thumbnail_url") or ""
    return {
        "speak": "我给你找了一条可以直接播放的训练视频，现在就能看。",
        "render": f"source: Wikimedia Commons API\nsource_url: {source_url}\nevidence: query={query}; checked_at={checked_at}; title={title}; video_url={video_url}; thumbnail_url={thumb}",
        "ui": {"type": "video_player", "title": title, "video_url": video_url, "thumbnail_url": thumb, "action_url": video_url, "source_url": source_url},
    }


if __name__ == "__main__":
    import asyncio

    fake = {"title": "Mock Workout Clip", "video_url": "https://example.com/workout.mp4", "thumbnail_url": "https://example.com/workout.jpg"}
    result = asyncio.run(run(query="健身", mock_video=fake))
    assert isinstance(result, dict) and "speak" in result and "render" in result and "ui" in result
    assert result["ui"].get("type") == "video_player" and result["ui"].get("video_url")
    print("OK")
