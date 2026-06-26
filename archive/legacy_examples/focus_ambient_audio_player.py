"""一次性专注音乐技能：检索可播放音频并返回播放器。"""
import httpx

RUN_SPEC = {
    "name": "focus_ambient_audio_player",
    "description": "搜索并播放适合专注的环境音乐或白噪音。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "focus ambient study music"},
        },
        "required": [],
    },
}


async def run(query: str = "focus ambient study music", mock_track=None, **kwargs):
    api_url = "https://itunes.apple.com/search"
    term = (query or "focus ambient study music").strip()
    picked, error = None, ""
    if isinstance(mock_track, dict):
        picked = mock_track
    else:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(api_url, params={"term": term, "media": "music", "entity": "song", "limit": 8})
                data = resp.json() if resp.status_code == 200 else {}
                items = data.get("results", []) if isinstance(data, dict) else []
                tags = ("lofi", "lo-fi", "focus", "study", "ambient", "binaural", "noise", "meditation", "chill")
                for item in items:
                    text = f"{item.get('trackName', '')} {item.get('primaryGenreName', '')}".lower()
                    if item.get("previewUrl") and any(t in text for t in tags):
                        picked = item
                        break
                if not picked and items:
                    picked = items[0]
        except Exception as exc:
            error = str(exc)
    if not picked or not picked.get("previewUrl"):
        reason = error or "未找到可播放的音频预览链接"
        return {
            "speak": "我暂时没找到可播放的专注音乐，稍后我再帮你试一次。",
            "render": f"source: iTunes Search API\nsource_url: {api_url}\nevidence: query={term}; error={reason}",
            "ui": {"type": "info_card", "title": "专注音频获取失败", "message": f"原因：{reason}", "source_url": api_url},
        }
    title = str(picked.get("trackName") or "Focus Audio")
    artist = str(picked.get("artistName") or "Unknown Artist")
    genre = str(picked.get("primaryGenreName") or "Unknown Genre")
    audio_url = str(picked.get("previewUrl"))
    track_url = str(picked.get("trackViewUrl") or api_url)
    return {
        "speak": f"给你找到一首适合专注的音频，现在就可以直接播放。",
        "render": (
            f"source: iTunes Search API\nsource_url: {api_url}\n"
            f"references: {track_url}\n"
            f"evidence: query={term}; title={title}; artist={artist}; genre={genre}; preview_url={audio_url}"
        ),
        "ui": {"type": "music_player", "audio_url": audio_url, "title": f"{title} - {artist}", "source_url": track_url},
    }


if __name__ == "__main__":
    import asyncio

    mock = {
        "trackName": "Deep Focus Lofi",
        "artistName": "Study Waves",
        "primaryGenreName": "Ambient",
        "previewUrl": "https://example.com/focus-preview.mp3",
        "trackViewUrl": "https://example.com/focus-track",
    }
    result = asyncio.run(run(mock_track=mock))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    assert isinstance(result.get("ui"), dict) and result["ui"].get("type") == "music_player"
    assert result["ui"].get("audio_url")
    print("OK")
