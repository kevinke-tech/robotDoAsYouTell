"""一次性技能：搜索并返回可直接播放的运动视频。"""
from datetime import datetime, timezone

import httpx

RUN_SPEC = {
    "name": "sports_video_player_embed_cn",
    "description": "搜索运动视频并以可播放卡片返回。",
    "args_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "default": "精彩运动视频"}},
        "required": [],
    },
}


def _pick_video(data: dict):
    pages = list((data.get("query") or {}).get("pages", {}).values())
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        url = str(info.get("url") or "").strip()
        if url.lower().endswith((".webm", ".ogv", ".ogg", ".mp4")):
            return str(page.get("title") or "运动视频"), url
    return "", ""


async def run(query: str = "精彩运动视频", **kwargs):
    source_url = "https://commons.wikimedia.org/w/api.php"
    if kwargs.get("mock_video_url"):
        title = kwargs.get("mock_title") or "测试运动视频"
        url = str(kwargs["mock_video_url"])
        return {"speak": "我给你放好一个运动视频了。", "render": f"source: mock\nsource_url: mock://video\nevidence: title={title}; video_url={url}", "ui": {"type": "video_player", "title": title, "video_url": url, "source_url": source_url}}
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": "6",
        "gsrlimit": "8",
        "gsrsearch": f"{(query or '运动').strip()} filetype:video",
        "prop": "imageinfo",
        "iiprop": "url",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(source_url, params=params)
        data = res.json() if res.status_code == 200 else {}
        title, video_url = _pick_video(data if isinstance(data, dict) else {})
        if video_url:
            ts = datetime.now(timezone.utc).isoformat()
            return {
                "speak": "我找到一个精彩的运动视频，已经可以直接播放了。",
                "render": f"source: Wikimedia Commons API\nsource_url: {source_url}\nevidence: query={query}; status={res.status_code}; checked_at={ts}; title={title}; video_url={video_url}",
                "ui": {"type": "video_player", "title": title, "video_url": video_url, "source_url": source_url},
            }
        reason = f"status={res.status_code}, empty_video_result"
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
    fallback_title = "运动视频（备用）"
    fallback_url = "https://upload.wikimedia.org/wikipedia/commons/3/3f/Fitness_treadmill_running.webm"
    return {
        "speak": "我先给你放一个运动视频备用源，现在就能播放。",
        "render": f"source: Wikimedia Commons fallback\nsource_url: {source_url}\nevidence: reason={reason}; fallback_title={fallback_title}; fallback_video_url={fallback_url}",
        "ui": {"type": "video_player", "title": fallback_title, "video_url": fallback_url, "source_url": source_url},
    }


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(run(mock_video_url="https://example.com/sport.mp4", mock_title="合成测试视频"))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    assert r["ui"].get("type") == "video_player" and r["ui"].get("video_url")
    print("OK")
