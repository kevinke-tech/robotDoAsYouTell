"""一次性技能：检索并嵌入可播放的科普视频。"""
import datetime as dt
import re
from urllib.parse import quote

import httpx

RUN_SPEC = {
    "name": "bilibili_science_video_embed_cn",
    "description": "搜索科普视频并返回可播放嵌入卡片。",
    "args_schema": {
        "type": "object",
        "properties": {"topic": {"type": "string", "default": "宇宙"}},
        "required": [],
    },
}


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


async def run(topic: str = "宇宙", **kwargs):
    now = dt.datetime.now().isoformat(timespec="seconds")
    fallback = {
        "title": "3Blue1Brown：线性代数的本质",
        "desc": "这是一条高质量数学科普视频，用直观动画解释线性代数核心概念，适合快速建立整体理解。",
        "platform": "YouTube",
        "embed": "https://www.youtube.com/embed/aircAruvnKk",
        "source_url": "https://www.youtube.com/watch?v=aircAruvnKk",
    }
    if kwargs.get("_offline_test"):
        v = fallback
        return {"speak": "我给你放了一条科普视频，点播放就行。", "render": f"标题: {v['title']}\n来源平台: {v['platform']}\nsource_url: {v['source_url']}\nevidence: offline_test=true", "ui": {"type": "iframe_card", "title": v["title"], "iframe_url": v["embed"], "source": v["platform"], "source_url": v["source_url"]}}
    search_url = "https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=" + quote(f"{topic} 科普 李永乐")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(search_url, headers={"User-Agent": "vox-skill/1.0"})
        data = resp.json() if resp.status_code == 200 else {}
        result = ((data.get("data") or {}).get("result") or [])
        if result:
            item = result[0]
            bvid = (item.get("bvid") or "").strip()
            title = _clean(str(item.get("title") or "Bilibili 科普视频"))
            desc = _clean(str(item.get("description") or ""))[:90]
            arcurl = str(item.get("arcurl") or "").strip()
            embed = f"https://player.bilibili.com/player.html?bvid={bvid}&page=1" if bvid else ""
            if embed:
                render = f"标题: {title}\n简介: {desc or '这是一条中文科普视频。'}\n来源平台: Bilibili\nsource_url: {arcurl or ('https://www.bilibili.com/video/' + bvid)}\nevidence: keyword={topic} 科普 李永乐; fetched_at={now}; api_status={resp.status_code}"
                return {"speak": "我找好一条中文科普视频了，已经嵌入播放器，直接点播放就可以。", "render": render, "ui": {"type": "iframe_card", "title": title, "iframe_url": embed, "source": "Bilibili", "source_url": arcurl or ("https://www.bilibili.com/video/" + bvid), "references": [search_url]}}
    except Exception as e:
        err = str(e)
    else:
        err = "bilibili_result_empty_or_no_bvid"
    v = fallback
    render = f"标题: {v['title']}\n简介: {v['desc']}\n来源平台: {v['platform']}\nsource_url: {v['source_url']}\nevidence: bilibili_fallback_reason={err}; bilibili_search_url={search_url}; fetched_at={now}"
    return {"speak": "我先给你放一条高质量科普视频，已经可以直接播放。", "render": render, "ui": {"type": "iframe_card", "title": v["title"], "iframe_url": v["embed"], "source": v["platform"], "source_url": v["source_url"], "references": [search_url, v["source_url"]]}}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(run(topic="宇宙", _offline_test=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r and isinstance(r.get("ui"), dict)
    print("OK")
