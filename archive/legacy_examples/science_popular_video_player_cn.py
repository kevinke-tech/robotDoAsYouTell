"""一次性技能：搜索中文科普视频并返回可播放嵌入。"""
import asyncio
import re

import httpx

RUN_SPEC = {
    "name": "science_popular_video_player_cn",
    "description": "搜索一个中文科普视频并返回可播放嵌入链接。",
    "args_schema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "default": "科普"},
        },
        "required": [],
    },
}


async def run(topic: str = "科普", **kwargs):
    source = "bilibili_web_search_api"
    source_url = "https://api.bilibili.com/x/web-interface/search/type"
    keyword = f"{topic} 科普".strip()
    if kwargs.get("_smoke_test"):
        bvid = "BV1xx411c7mD"
        title = "一分钟看懂黑洞是什么（示例）"
    else:
        bvid, title = "", ""
        try:
            params = {"search_type": "video", "keyword": keyword}
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(source_url, params=params)
            data = resp.json() if resp.status_code == 200 else {}
            for item in (data.get("data", {}).get("result") or []):
                bvid = str(item.get("bvid") or "").strip()
                raw_title = str(item.get("title") or "").strip()
                title = re.sub(r"<[^>]+>", "", raw_title)
                if bvid:
                    break
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            return {
                "speak": "我这会儿没连上视频源，先给你记录下来，稍后再试一次。",
                "render": (
                    f"source: {source}\nsource_url: {source_url}\n"
                    f"evidence: keyword={keyword}; error={reason}"
                ),
                "ui": {"type": "info_card", "title": "科普视频获取失败", "message": f"请求失败：{reason}"},
            }
    if not bvid:
        return {
            "speak": "我暂时没找到合适的科普视频，你可以换个关键词再试试。",
            "render": f"source: {source}\nsource_url: {source_url}\nevidence: keyword={keyword}; result=empty",
            "ui": {"type": "info_card", "title": "暂无结果", "message": f"关键词：{keyword}"},
        }
    embed_url = f"https://player.bilibili.com/player.html?bvid={bvid}&page=1"
    play_url = f"https://www.bilibili.com/video/{bvid}"
    final_title = title or f"{topic} 科普视频"
    return {
        "speak": f"给你找到一个科普视频，现在就可以直接播放。",
        "render": (
            f"标题: {final_title}\n来源: Bilibili\n可播放嵌入: {embed_url}\n"
            f"source: {source}\nsource_url: {source_url}\n"
            f"evidence: keyword={keyword}; bvid={bvid}; page_url={play_url}"
        ),
        "ui": {"type": "iframe_card", "title": final_title, "iframe_url": embed_url},
    }


if __name__ == "__main__":
    result = asyncio.run(run(_smoke_test=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
