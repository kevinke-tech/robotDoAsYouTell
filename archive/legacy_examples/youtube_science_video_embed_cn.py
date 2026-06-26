"""一次性技能：检索可嵌入播放的 YouTube 科普视频。"""
import re
from urllib.parse import quote_plus

import httpx

RUN_SPEC = {
    "name": "youtube_science_video_embed_cn",
    "description": "搜索科普视频并返回可直接嵌入播放的卡片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "default": "宇宙"},
            "mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}

FALLBACK = {
    "title": "What Actually Happens If You Are in Space Without A Suit?",
    "channel": "Kurzgesagt – In a Nutshell",
    "description": "解释真空环境、缺氧和体温变化等核心生理影响，内容扎实且易懂。",
    "video_id": "mN9tVfWaw0Q",
    "source_url": "https://www.youtube.com/watch?v=mN9tVfWaw0Q",
}


def _extract_video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\\.be/|/embed/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


async def run(topic: str = "宇宙", mock: bool = False, **kwargs):
    data = dict(FALLBACK)
    source = "fallback_catalog"
    source_url = data["source_url"]
    evidence = {"topic": topic, "reason": "api_unavailable_or_mock"}
    if not mock:
        api = f"https://piped.video/api/v1/search?q={quote_plus(topic + ' 科普 youtube')}&filter=videos"
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(api)
                items = resp.json() if resp.status_code == 200 else []
            for item in items if isinstance(items, list) else []:
                vid = _extract_video_id(str(item.get("url") or ""))
                if vid:
                    data = {
                        "title": str(item.get("title") or "未命名视频").strip(),
                        "channel": str(item.get("uploaderName") or "未知频道").strip(),
                        "description": str(item.get("shortDescription") or "暂无简介").strip()[:240],
                        "video_id": vid,
                        "source_url": f"https://www.youtube.com/watch?v={vid}",
                    }
                    source, source_url = "piped_search_api", api
                    evidence = {"topic": topic, "api_status": resp.status_code, "video_id": vid}
                    break
        except Exception as e:
            evidence = {"topic": topic, "error": f"{type(e).__name__}: {e}"[:180]}
    embed = f"https://www.youtube.com/embed/{data['video_id']}"
    return {
        "speak": f"我帮你找了一条{topic}相关的科普视频，现在可以直接播放。",
        "render": (
            f"标题: {data['title']}\n来源频道: {data['channel']}\n视频简介: {data['description']}\n"
            f"source: {source}\nsource_url: {source_url}\nreferences: {data['source_url']}\nevidence: {evidence}\n"
            f"embed_url: {embed}"
        ),
        "ui": {
            "type": "iframe_card",
            "title": data["title"],
            "iframe_url": embed,
            "source_url": data["source_url"],
            "channel": data["channel"],
        },
    }


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(run(topic="宇宙", mock=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
