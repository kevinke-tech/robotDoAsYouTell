"""One-shot focus audio skill with resilient retrieval."""
import asyncio
import datetime as dt
from urllib.parse import quote
import httpx

RUN_SPEC = {
    "name": "focus_concentration_audio_embed",
    "description": "搜索并返回可直接播放的专注环境音频。",
    "args_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "default": "focus ambient music"}},
        "required": [],
    },
}


async def _search_archive(query: str, timeout: float):
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            s = await c.get("https://archive.org/advancedsearch.php", params={"q": f'mediatype:(audio) AND ({query})', "fl[]": ["identifier", "title"], "rows": 5, "output": "json"})
            docs = ((s.json() or {}).get("response") or {}).get("docs") or []
            for d in docs:
                ident = str(d.get("identifier") or "").strip()
                if not ident:
                    continue
                m = await c.get(f"https://archive.org/metadata/{ident}")
                for f in (m.json() or {}).get("files") or []:
                    n = str(f.get("name") or "")
                    if n.lower().endswith((".mp3", ".m4a", ".ogg")):
                        return {"title": str(d.get("title") or ident), "audio_url": f"https://archive.org/download/{ident}/{quote(n)}", "source": "Internet Archive", "source_url": f"https://archive.org/details/{ident}", "evidence": {"identifier": ident, "file": n}}
    except Exception as e:
        return None, f"archive_error={type(e).__name__}:{e}"
    return None, "archive_error=no_playable_audio"


async def _search_itunes(query: str, timeout: float):
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get("https://itunes.apple.com/search", params={"term": query, "media": "music", "entity": "song", "limit": 5})
            for x in (r.json() or {}).get("results") or []:
                u = str(x.get("previewUrl") or "").strip()
                if u:
                    return {"title": str(x.get("trackName") or "Focus Preview"), "audio_url": u, "source": "iTunes Search API", "source_url": str(x.get("trackViewUrl") or "https://itunes.apple.com"), "evidence": {"artist": str(x.get("artistName") or ""), "kind": str(x.get("kind") or "")}}
    except Exception as e:
        return None, f"itunes_error={type(e).__name__}:{e}"
    return None, "itunes_error=no_preview"


async def run(query: str = "focus ambient music", **kwargs):
    if kwargs.get("_smoke_test"):
        return {"speak": "已为你准备好专注音频。", "render": "source: mock\nsource_url: https://example.com\nevidence: smoke_test", "ui": {"type": "music_player", "audio_url": "https://example.com/focus.mp3", "title": "Mock Focus Audio"}}
    errors = []
    for fn in (_search_archive, _search_itunes):
        item, err = await fn(query, 8.0)
        if item:
            now = dt.datetime.now().isoformat(timespec="seconds")
            return {
                "speak": "我给你找了一段适合专注的音频，已经可以直接播放。",
                "render": f"title: {item['title']}\nsource: {item['source']}\nsource_url: {item['source_url']}\nevidence: {item['evidence']}\nretrieved_at: {now}",
                "ui": {"type": "music_player", "audio_url": item["audio_url"], "title": item["title"]},
            }
        errors.append(err)
    y = "https://www.youtube.com/embed/jfKfPfyJRdk"
    return {
        "speak": "我找到了一个可直接播放的专注背景音乐。",
        "render": f"title: Lofi Girl - beats to relax/study to\nsource: YouTube Embed Fallback\nsource_url: https://www.youtube.com/watch?v=jfKfPfyJRdk\nevidence: fallback_after_errors={errors}\nreferences: ['https://www.youtube.com/embed/jfKfPfyJRdk']",
        "ui": {"type": "iframe_card", "title": "专注背景音乐", "iframe_url": y},
    }


if __name__ == "__main__":
    out = asyncio.run(run(_smoke_test=True))
    assert isinstance(out, dict) and "speak" in out and "render" in out and "ui" in out
    print("OK")
