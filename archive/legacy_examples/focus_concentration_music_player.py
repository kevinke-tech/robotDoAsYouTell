"""ONE-SHOT: 搜索并返回可播放的专注音乐。"""
import json
from typing import Any, Dict, Optional

import httpx

RUN_SPEC = {
    "name": "focus_concentration_music_player",
    "description": "搜索可播放的专注音乐并返回内嵌播放器。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "lofi beats focus"},
        },
        "required": [],
    },
}


async def _fetch_track(query: str, timeout: float = 8.0) -> Dict[str, Any]:
    url = "https://itunes.apple.com/search"
    params = {"term": query, "media": "music", "entity": "song", "limit": 1}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params)
    data = resp.json() if resp.status_code == 200 else {}
    item = (data.get("results") or [{}])[0]
    return {
        "source": "iTunes Search API",
        "source_url": str(resp.url),
        "status_code": resp.status_code,
        "track": item,
    }


async def run(query: str = "lofi beats focus", mock_track: Optional[Dict[str, Any]] = None, **kwargs):
    evidence: Dict[str, Any] = {"query": query}
    try:
        if mock_track is not None:
            result = {"source": "mock", "source_url": "mock://local-test", "status_code": 200, "track": mock_track}
        else:
            result = await _fetch_track(query=query)
        track = result.get("track") or {}
        audio_url = str(track.get("previewUrl") or "").strip()
        title = str(track.get("trackName") or "专注背景音乐").strip()
        artist = str(track.get("artistName") or "未知艺术家").strip()
        evidence.update(result)
        if not audio_url:
            raise ValueError("未获取到可播放音频 URL")
        return {
            "speak": "我帮你找了一首适合专注的音乐，点播放就可以开始。",
            "render": f"source: {result['source']}\nsource_url: {result['source_url']}\nevidence: {json.dumps({'title': title, 'artist': artist, 'audio_url': audio_url}, ensure_ascii=False)}",
            "ui": {"type": "music_player", "audio_url": audio_url, "title": f"{title} - {artist}", "source_url": result["source_url"]},
        }
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"
        return {
            "speak": "我现在没找到可播放的专注音乐，稍后再试一次吧。",
            "render": f"source: iTunes Search API\nsource_url: https://itunes.apple.com/search\nevidence: {json.dumps({'query': query, 'error': reason, 'raw': evidence}, ensure_ascii=False)}",
            "ui": {"type": "info_card", "title": "专注音乐获取失败", "message": f"原因：{reason}\n我已保留检索证据，建议稍后重试。"},
        }


if __name__ == "__main__":
    import asyncio

    mock = {"previewUrl": "https://example.com/focus.mp3", "trackName": "Deep Focus Loop", "artistName": "Focus Lab"}
    out = asyncio.run(run(query="focus music", mock_track=mock))
    assert isinstance(out, dict) and "speak" in out and "render" in out and out.get("ui", {}).get("type") == "music_player"
    print("OK")
