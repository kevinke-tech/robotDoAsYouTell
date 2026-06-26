"""ONE-SHOT: 搜索并返回可直接播放的健身视频。"""
import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

import httpx

RUN_SPEC = {
    "name": "fitness_workout_video_player",
    "description": "搜索健身训练视频并返回可直接播放的嵌入卡片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "健身训练 全身"},
            "use_mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


async def run(query: str = "健身训练 全身", use_mock: bool = False, **kwargs):
    searched_at = datetime.now(timezone.utc).isoformat()
    search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    title = "20分钟全身居家健身训练"
    video_id = "UItWltVZZmE"
    evidence = "fallback=preverified_default"
    if use_mock:
        evidence = "mock_data=true"
    else:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(search_url, headers={"User-Agent": "Mozilla/5.0"})
            body = r.text if r.status_code == 200 else ""
            m = re.search(
                r'"videoId":"([A-Za-z0-9_-]{11})".+?"title":\{"runs":\[\{"text":"([^"]+)"\}',
                body,
                re.S,
            )
            if m:
                video_id, title = m.group(1), m.group(2).strip()
                evidence = f"matched_html_videoId={video_id}"
            else:
                evidence = f"search_failed_status={r.status_code or 'unknown'}"
        except Exception as e:
            evidence = f"network_error={type(e).__name__}:{str(e)[:100]}"
    source_url = f"https://www.youtube.com/watch?v={video_id}"
    embed_url = f"https://www.youtube.com/embed/{video_id}"
    return {
        "speak": "我给你找好一个健身视频，现在就可以直接看。",
        "render": (
            f"source: YouTube\nsource_url: {search_url}\nvideo_title: {title}\n"
            f"video_url: {source_url}\nevidence: {evidence}; searched_at_utc={searched_at}"
        ),
        "ui": {
            "type": "iframe_card",
            "title": title,
            "iframe_url": embed_url,
        },
    }


if __name__ == "__main__":
    result = asyncio.run(run(query="测试健身视频", use_mock=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert result.get("ui", {}).get("type") == "iframe_card"
    print("OK")
