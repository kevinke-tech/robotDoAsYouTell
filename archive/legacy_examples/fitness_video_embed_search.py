"""One-shot skill: 搜索并内嵌可播放健身视频。"""
import asyncio
import html
import json
import re
import urllib.parse
import urllib.request

RUN_SPEC = {
    "name": "fitness_video_embed_search",
    "description": "搜索一个可直接播放的健身视频并返回内嵌播放器。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "full body workout no equipment"},
            "offline_test": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


def _pack(video_id: str, title: str, desc: str, source_url: str, source: str, evidence: str):
    embed = f"https://www.youtube.com/embed/{video_id}"
    safe_title, safe_desc, safe_src = html.escape(title), html.escape(desc), html.escape(source_url)
    card = (
        "<div style='font-family:sans-serif;line-height:1.45'>"
        f"<h3 style='margin:0 0 8px'>{safe_title}</h3>"
        f"<p style='margin:0 0 10px'>{safe_desc}</p>"
        "<iframe width='100%' height='315' "
        f"src='{embed}' title='{safe_title}' frameborder='0' allow='accelerometer; autoplay; encrypted-media; picture-in-picture' allowfullscreen></iframe>"
        f"<p style='margin:8px 0 0'>来源: <a href='{safe_src}' target='_blank'>{safe_src}</a></p></div>"
    )
    return {
        "speak": "我给你找了一个可以直接播放的健身视频。",
        "render": f"video_title: {title}\ndescription: {desc}\nsource: {source}\nsource_url: {source_url}\nevidence: {evidence}\nreferences: [{source_url}]",
        "ui": {"type": "html_card", "title": "健身训练视频", "html": card, "source_url": source_url},
    }


async def run(query: str = "full body workout no equipment", offline_test: bool = False, **kwargs):
    fallback_id, title = "UBMk30rjy0o", "20 MIN FULL BODY WORKOUT // No Equipment | Pamela Reif"
    desc = "这是一个热门全身训练视频，适合居家跟练，能同时锻炼心肺与核心肌群。"
    if offline_test:
        return _pack(fallback_id, title, desc, f"https://www.youtube.com/watch?v={fallback_id}", "YouTube fallback", "offline_test=true")
    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    video_id, evidence = fallback_id, "fallback_used=true"
    try:
        req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read().decode("utf-8", "ignore")
        ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', text)
        if ids:
            video_id, evidence = ids[0], f"search_hit=true,candidates={len(set(ids))}"
    except Exception as e:
        evidence = f"search_error={type(e).__name__},fallback_used=true"
    source_url = f"https://www.youtube.com/watch?v={video_id}"
    oembed_url = "https://www.youtube.com/oembed?url=" + urllib.parse.quote(source_url, safe="") + "&format=json"
    try:
        with urllib.request.urlopen(oembed_url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        title = str(data.get("title") or title).strip()
    except Exception as e:
        evidence += f",oembed_error={type(e).__name__}"
    return _pack(video_id, title, desc, source_url, "YouTube Search HTML + oEmbed", evidence)

if __name__ == "__main__":
    r = asyncio.run(run(query="mock fitness", offline_test=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    assert "<iframe" in r["ui"].get("html", "") and "source_url" in r["ui"]
    print("OK")
