"""检索搞笑视频并返回一次性播放器 UI。"""
import inspect
from urllib.parse import quote, quote_plus

import httpx

QUERY = "funny video"
RUN_SPEC = {
    "name": "funny_video_player",
    "description": "检索搞笑视频并返回可立即播放的一次性视频播放器。",
    "args_schema": {"type": "object", "properties": {}},
}


def _direct_media_name(name: str) -> bool:
    return (name or "").lower().endswith((".mp4", ".webm", ".m3u8"))


async def run(**kwargs):
    search_url = (
        "https://archive.org/advancedsearch.php?q="
        f"{quote_plus(QUERY)}+AND+mediatype%3Amovies&fl[]=identifier&fl[]=title&rows=10&output=json"
    )
    evidence = [f"query={QUERY}"]
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        try:
            docs = (await client.get(search_url)).json().get("response", {}).get("docs", [])
        except Exception as err:
            return {"speak": "我暂时连不上视频数据源。", "render": f"检索失败。\n来源：{search_url}\n证据：{err}"}
        evidence.append(f"hits={len(docs)}")
        for doc in docs:
            ident = (doc.get("identifier") or "").strip()
            title = (doc.get("title") or "搞笑视频").strip()
            if not ident:
                continue
            meta_url = f"https://archive.org/metadata/{ident}"
            try:
                files = (await client.get(meta_url)).json().get("files", [])
            except Exception:
                evidence.append(f"metadata_failed={ident}")
                continue
            for item in files:
                name = (item.get("name") or "").strip()
                if not _direct_media_name(name):
                    continue
                video_url = f"https://archive.org/download/{ident}/{quote(name)}"
                return {
                    "speak": "找到一个搞笑视频，马上给你播放。",
                    "render": f"已命中可直接播放的视频。\n来源：Internet Archive API\n检索URL：{search_url}\n元数据URL：{meta_url}\n关键字段：identifier={ident}，name={name}",
                    "ui": {
                        "type": "video_player",
                        "title": "搞笑视频即刻播放",
                        "video_title": title,
                        "video_url": video_url,
                        "autoplay": True,
                        "loop": False,
                        "source": "Internet Archive API",
                        "source_url": meta_url,
                        "query": QUERY,
                    },
                }
    return {
        "speak": "暂时没找到能直接播放的视频源。",
        "render": f"检索结束但未命中 mp4/webm/m3u8。\n来源：{search_url}\n证据：{' | '.join(evidence)}",
    }


if __name__ == "__main__":
    # 浏览器类 skill 的冒烟测试约定：只检查结构，不调用 run。
    assert isinstance(RUN_SPEC, dict) and RUN_SPEC.get("name") == "funny_video_player"
    assert inspect.iscoroutinefunction(run)
    print("OK")
