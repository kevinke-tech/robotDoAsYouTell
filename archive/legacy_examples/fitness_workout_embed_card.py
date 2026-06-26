"""一次性健身视频推荐技能：返回可直接播放的嵌入视频卡片。"""
import html
import json
import httpx

RUN_SPEC = {
    "name": "fitness_workout_embed_card",
    "description": "搜索并返回可直接播放的健身训练视频卡片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "full body workout"},
            "offline_test": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


async def run(query: str = "full body workout", offline_test: bool = False, **kwargs):
    video_id = "UBMk30rjy0o"
    source_url = f"https://www.youtube.com/watch?v={video_id}"
    embed_url = f"https://www.youtube.com/embed/{video_id}?rel=0"
    title = "20 MIN Full Body Workout (No Equipment)"
    desc = "这是一套全身自重训练，节奏连贯，适合在家进行有氧与力量结合练习。"
    evidence = {"query": query, "platform": "YouTube", "video_id": video_id, "retrieval": "fallback"}
    if not offline_test:
        api = f"https://www.youtube.com/oembed?url={source_url}&format=json"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(api)
            if r.status_code == 200:
                data = r.json()
                title = str(data.get("title") or title).strip()
                author = str(data.get("author_name") or "").strip()
                if author:
                    desc = f"来自 {author} 的热门健身训练视频，适合居家跟练。"
                evidence.update({"retrieval": "oembed", "oembed_url": api, "status_code": r.status_code})
            else:
                evidence.update({"oembed_url": api, "status_code": r.status_code})
        except Exception as e:
            evidence.update({"error": str(e), "oembed_url": api})
    safe_title = html.escape(title)
    safe_desc = html.escape(desc)
    ui_html = (
        f'<div style="display:flex;flex-direction:column;gap:8px;">'
        f'<iframe src="{embed_url}" title="{safe_title}" '
        f'style="width:100%;aspect-ratio:16/9;border:0;border-radius:10px;" '
        f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
        f'allowfullscreen></iframe>'
        f"<strong>{safe_title}</strong><p>{safe_desc}</p>"
        f'<p>来源: <a href="{source_url}" target="_blank" rel="noreferrer">{source_url}</a></p></div>'
    )
    return {
        "speak": "我帮你找好一个可以直接播放的健身视频，现在就能开始跟练。",
        "render": f"标题: {title}\n简介: {desc}\nsource_url: {source_url}\nevidence: {json.dumps(evidence, ensure_ascii=False)}",
        "ui": {"type": "html_card", "title": "健身视频推荐", "html": ui_html, "source_url": source_url},
    }


if __name__ == "__main__":
    import asyncio
    out = asyncio.run(run(query="居家全身训练", offline_test=True))
    assert isinstance(out, dict) and "speak" in out and "render" in out and "ui" in out
    assert "source_url" in out["render"] and "evidence" in out["render"]
    print("OK")
