"""一次性技能：抓取搞笑短视频并渲染可点击网格卡片。"""
import datetime as dt
import html

import httpx

RUN_SPEC = {
    "name": "comedy_video_grid",
    "description": "从公开来源抓取搞笑短视频并展示卡片网格。",
    "args_schema": {"type": "object", "properties": {"subreddit": {"type": "string", "default": "videos"}, "limit": {"type": "integer", "default": 4, "minimum": 3, "maximum": 5}}, "required": []},
}


def _thumb(d: dict) -> str:
    p = (((d.get("preview") or {}).get("images") or [{}])[0].get("source") or {}).get("url")
    t = str(p or d.get("thumbnail") or "").replace("&amp;", "&").strip()
    return t if t.startswith("http") else "https://www.redditstatic.com/icon.png"


def _platform(url: str, domain: str) -> str:
    s = f"{domain} {url}".lower()
    return "YouTube" if "youtu" in s else ("Reddit" if "reddit" in s else domain or "Web")


async def run(subreddit: str = "videos", limit: int = 4, **kwargs):
    n = max(3, min(5, int(limit or 4)))
    sub = "".join(c for c in (subreddit or "videos") if c.isalnum() or c == "_") or "videos"
    api = f"https://www.reddit.com/r/{sub}/hot.json?limit=30"
    posts = kwargs.get("mock_posts")
    if posts is None:
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as c:
                r = await c.get(api, headers={"User-Agent": "vox-skill/1.0"})
                posts = ((r.json() if r.status_code == 200 else {}).get("data") or {}).get("children") or []
        except Exception:
            posts = []
    items = []
    for child in posts:
        d = child.get("data", child) if isinstance(child, dict) else {}
        url = str(d.get("url_overridden_by_dest") or d.get("url") or "").strip()
        title = str(d.get("title") or "").strip()
        if not (title and url.startswith("http")):
            continue
        items.append({"title": title, "thumbnail": _thumb(d), "watch_url": url, "platform": _platform(url, str(d.get("domain") or ""))})
        if len(items) >= n:
            break
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if len(items) < 3:
        return {"speak": "我这次没抓到足够的搞笑视频，稍后再试一次吧。", "render": f"source: Reddit\nsource_url: {api}\nevidence: fetched_items={len(items)}\nfetched_at: {ts}", "ui": {"type": "info_card", "title": "获取失败", "message": "未拿到至少 3 条可播放链接。"}}
    cards = "".join(f"<a href='{html.escape(i['watch_url'])}' target='_blank' style='text-decoration:none;color:#111'><div style='border:1px solid #eee;border-radius:12px;overflow:hidden;background:#fff'><img src='{html.escape(i['thumbnail'])}' style='width:100%;height:120px;object-fit:cover'/><div style='padding:8px'><div style='font-size:13px;line-height:1.35;height:36px;overflow:hidden'>{html.escape(i['title'])}</div><div style='font-size:12px;color:#666;margin-top:6px'>来源: {html.escape(i['platform'])}</div></div></div></a>" for i in items)
    grid = f"<div style='font-family:Arial,\"Microsoft YaHei\",sans-serif'><div style='font-size:15px;font-weight:600;margin:2px 0 10px'>搞笑短视频精选</div><div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px'>{cards}</div></div>"
    ev = "; ".join(f"{k+1}.{i['platform']}|{i['watch_url']}" for k, i in enumerate(items))
    return {"speak": "我给你找了几条正在流行的搞笑短视频，点卡片就能看。", "render": f"source: Reddit hot feed\nsource_url: {api}\nevidence: {ev}\nfetched_at: {ts}", "ui": {"type": "html_card", "title": "搞笑短视频网格", "html": grid, "source_url": f"https://www.reddit.com/r/{sub}/"}}


if __name__ == "__main__":
    import asyncio
    mock = [{"data": {"title": "猫咪搞笑翻车合集", "url_overridden_by_dest": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg", "domain": "youtube.com"}}, {"data": {"title": "办公室爆笑瞬间", "url": "https://v.redd.it/abc123", "thumbnail": "https://b.thumbs.redditmedia.com/a.jpg", "domain": "v.redd.it"}}, {"data": {"title": "宠物迷惑行为大赏", "url": "https://www.reddit.com/r/videos/comments/x1/demo/", "thumbnail": "https://b.thumbs.redditmedia.com/b.jpg", "domain": "reddit.com"}}]
    out = asyncio.run(run(limit=3, mock_posts=mock))
    assert isinstance(out, dict) and "speak" in out and "render" in out and out.get("ui", {}).get("type")
    print("OK")
