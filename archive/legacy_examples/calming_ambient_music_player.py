"""一次性技能：搜索并播放舒缓的环境音乐视频。"""
import asyncio
import re
from urllib.parse import quote_plus

import httpx

RUN_SPEC = {
    "name": "calming_ambient_music_player",
    "description": "搜索并嵌入可播放的舒缓音乐视频。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "calming ambient music"},
            "use_mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


def _extract_first_video(html: str):
    ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
    titles = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"\}\]', html)
    if not ids:
        return "", ""
    return ids[0], (titles[0] if titles else "Calming Ambient Music")


async def run(query: str = "calming ambient music", use_mock: bool = False, **kwargs):
    source = "YouTube Search"
    search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    video_id, title, evidence = "", "", []
    if use_mock:
        video_id, title = "jfKfPfyJRdk", "lofi hip hop radio - beats to relax/study to"
        evidence.append("mock_mode=true")
    else:
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get("https://www.youtube.com/results", params={"search_query": query})
                evidence.append(f"http_status={resp.status_code}")
                if resp.status_code == 200:
                    video_id, title = _extract_first_video(resp.text)
                    evidence.append(f"parsed_video_id={video_id or 'none'}")
        except Exception as e:
            evidence.append(f"error={type(e).__name__}:{str(e)[:80]}")
    if not video_id:
        video_id, title = "5qap5aO4i9A", "lofi hip hop radio - beats to relax/study to"
        evidence.append("fallback_video=true")
    video_url = f"https://www.youtube.com/embed/{video_id}?autoplay=1&rel=0"
    speak = f"我帮你找了一段舒缓音乐，现在就可以直接播放。"
    render = (
        f"已为你准备舒缓音乐。\n"
        f"source: {source}\n"
        f"source_url: {search_url}\n"
        f"selected_title: {title}\n"
        f"selected_video_id: {video_id}\n"
        f"references: {video_url}\n"
        f"evidence: {'; '.join(evidence) if evidence else 'none'}"
    )
    return {
        "speak": speak,
        "render": render,
        "ui": {"type": "video_player", "video_url": video_url, "title": title},
    }


if __name__ == "__main__":
    result = asyncio.run(run(use_mock=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert isinstance(result.get("ui"), dict) and result["ui"].get("video_url")
    print("OK")
