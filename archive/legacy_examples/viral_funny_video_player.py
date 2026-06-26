"""One-shot skill: find a funny viral clip and return a playable video UI."""
from datetime import datetime, timezone
from urllib.parse import quote, quote_plus
import httpx

RUN_SPEC = {
    "name": "viral_funny_video_player",
    "description": "Search a family-friendly funny viral video and return a playable card.",
    "args_schema": {"type": "object", "properties": {"query": {"type": "string", "default": "funny animal viral"}}, "required": []},
}

def _is_video(name: str) -> bool:
    return (name or "").lower().endswith((".mp4", ".webm"))

async def run(query: str = "funny animal viral", **kwargs):
    q = (query or "funny animal viral").strip()
    search_url = "https://archive.org/advancedsearch.php?q=" + f"{quote_plus(q)}+AND+mediatype%3Amovies&fl[]=identifier&fl[]=title&rows=12&output=json"
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    docs, files_map = kwargs.get("mock_docs"), kwargs.get("mock_files") or {}
    async with httpx.AsyncClient(timeout=18.0, follow_redirects=True) as client:
        if docs is None:
            try:
                r = await client.get(search_url)
                docs = (r.json() if r.status_code == 200 else {}).get("response", {}).get("docs", [])
            except Exception:
                docs = []
        for d in docs or []:
            ident, title = str(d.get("identifier") or "").strip(), str(d.get("title") or "Funny viral clip").strip()
            if not ident:
                continue
            meta_url, files = f"https://archive.org/metadata/{ident}", files_map.get(ident)
            if files is None:
                try:
                    m = await client.get(meta_url)
                    files = (m.json() if m.status_code == 200 else {}).get("files", [])
                except Exception:
                    files = []
            for f in files:
                name = str(f.get("name") or "").strip()
                if _is_video(name):
                    video_url = f"https://archive.org/download/{ident}/{quote(name)}"
                    return {
                        "speak": "I found a lighthearted viral video. You can play it right here.",
                        "render": f"Source: Internet Archive API\nsearch_url: {search_url}\nmetadata_url: {meta_url}\nchecked_at: {checked_at}\nkey_fields: identifier={ident}, title={title}, file={name}",
                        "ui": {"type": "video_player", "title": "Funny Viral Video", "video_title": title, "video_url": video_url, "source": "Internet Archive", "source_url": f"https://archive.org/details/{ident}"},
                    }
    return {
        "speak": "I could not find a playable funny clip right now. Please try again shortly.",
        "render": f"Source: {search_url}\nchecked_at: {checked_at}\nkey_fields: no direct .mp4/.webm found",
        "ui": {"type": "info_card", "title": "Video Not Found", "message": "No playable direct video URL found."},
    }

if __name__ == "__main__":
    import asyncio
    sample_docs = [{"identifier": "test_funny_clip", "title": "Funny Cat Compilation"}]
    sample_files = {"test_funny_clip": [{"name": "funny-cat.mp4"}]}
    out = asyncio.run(run(query="funny animal viral", mock_docs=sample_docs, mock_files=sample_files))
    assert isinstance(out, dict) and "speak" in out and "render" in out
    print("OK")
