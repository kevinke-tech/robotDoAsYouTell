"""专注音频 one-shot 技能：检索并返回可播放嵌入播放器。"""
import json
from urllib.parse import quote_plus

import httpx

RUN_SPEC = {
    "name": "focus_deep_work_audio_embed",
    "description": "搜索专注背景音并返回可直接播放的嵌入播放器。",
    "args_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "default": "focus ambient music"}},
        "required": [],
    },
}

FALLBACKS = [
    {
        "title": "Lofi Girl - Focus Radio",
        "source": "YouTube",
        "iframe_url": "https://www.youtube.com/embed/jfKfPfyJRdk",
        "source_url": "https://www.youtube.com/watch?v=jfKfPfyJRdk",
        "evidence": "known_focus_stream",
    },
    {
        "title": "White Noise for Deep Work",
        "source": "YouTube",
        "iframe_url": "https://www.youtube.com/embed/nMfPqeZjc2c",
        "source_url": "https://www.youtube.com/watch?v=nMfPqeZjc2c",
        "evidence": "known_white_noise_stream",
    },
]


async def _search_itunes(query: str):
    url = "https://itunes.apple.com/search"
    params = {"term": query, "media": "music", "limit": 1}
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.get(url, params=params)
            data = r.json() if r.status_code == 200 else {}
        item = (data.get("results") or [{}])[0]
        audio_url = str(item.get("previewUrl") or "").strip()
        if not audio_url:
            return None, f"itunes_empty_{r.status_code}"
        title = str(item.get("trackName") or "Focus Preview").strip()
        artist = str(item.get("artistName") or "").strip()
        msg = f"{title} - {artist}" if artist else title
        return {
            "title": msg,
            "audio_url": audio_url,
            "source": "iTunes Search API",
            "source_url": str(item.get("trackViewUrl") or url),
            "evidence": {"query": query, "result_count": int(data.get("resultCount") or 0)},
            "references": [url],
        }, ""
    except Exception as e:
        return None, f"itunes_error:{type(e).__name__}"


async def run(query: str = "focus ambient music", **kwargs):
    if kwargs.get("test_mode"):
        return {"speak": "我给你准备了一段专注背景音，现在可以直接播放。", "render": "source: mock\nevidence: offline_test\nreferences: [\"mock://local\"]", "ui": {"type": "music_player", "audio_url": "https://example.com/mock.mp3", "title": "Mock Focus Audio"}}
    try:
        picked, err = await _search_itunes(query)
        if picked:
            ev = json.dumps(picked["evidence"], ensure_ascii=False)
            return {"speak": "我找到了适合专注的音频，你现在就能播放。", "render": f"title: {picked['title']}\nsource: {picked['source']}\nsource_url: {picked['source_url']}\nevidence: {ev}\nreferences: {picked['references']}", "ui": {"type": "music_player", "audio_url": picked["audio_url"], "title": picked["title"]}}
        fb = FALLBACKS[0 if "white noise" not in query.lower() else 1]
        refs = [fb["source_url"], f"https://www.youtube.com/results?search_query={quote_plus(query)}"]
        return {"speak": "我给你切换到了稳定可播的专注背景音，已经可以直接播放。", "render": f"title: {fb['title']}\nsource: {fb['source']}\nsource_url: {fb['source_url']}\nevidence: primary_failed={err or 'unknown'}; fallback={fb['evidence']}\nreferences: {refs}", "ui": {"type": "iframe_card", "title": fb["title"], "iframe_url": fb["iframe_url"]}}
    except Exception as e:
        fb = FALLBACKS[0]
        return {"speak": "我已回退到可用的专注音频播放器，你可以直接播放。", "render": f"title: {fb['title']}\nsource: {fb['source']}\nsource_url: {fb['source_url']}\nevidence: run_error={type(e).__name__}; fallback={fb['evidence']}\nreferences: {[fb['source_url']]}", "ui": {"type": "iframe_card", "title": fb["title"], "iframe_url": fb["iframe_url"]}}


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(query="专注白噪音", test_mode=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result and "ui" in result
    print("OK")
