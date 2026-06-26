"""一次性技能：播放轻松愉快的背景音乐并返回可播放播放器。"""

RUN_SPEC = {
    "name": "lofi_relaxing_music_player",
    "description": "播放一首轻松愉快的背景音乐，并返回可播放的音乐播放器。",
    "args_schema": {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "default": "lofi hip hop"},
        },
        "required": [],
    },
}

_TRACKS = [
    {
        "title": "Lofi hip hop radio - beats to relax/study to",
        "video_url": "https://www.youtube.com/embed/jfKfPfyJRdk",
        "source": "YouTube - Lofi Girl",
        "source_url": "https://www.youtube.com/watch?v=jfKfPfyJRdk",
    },
    {
        "title": "Chillhop Radio - jazzy & lofi hip hop beats",
        "video_url": "https://www.youtube.com/embed/5yx6BWlEVcY",
        "source": "YouTube - Chillhop Music",
        "source_url": "https://www.youtube.com/watch?v=5yx6BWlEVcY",
    },
]


async def run(keyword: str = "lofi hip hop", **kwargs):
    query = (keyword or "").lower()
    chosen = _TRACKS[1] if "chill" in query else _TRACKS[0]
    title = chosen["title"]
    source = chosen["source"]
    source_url = chosen["source_url"]
    video_url = chosen["video_url"]
    return {
        "speak": "我给你准备了一首轻松的背景音乐，点播放就可以开始听。",
        "render": (
            f"已为你准备背景音乐：{title}\n"
            f"source: {source}\n"
            f"source_url: {source_url}\n"
            f"evidence: keyword={keyword or 'lofi hip hop'}; "
            f"selected_video={video_url}"
        ),
        "ui": {
            "type": "video_player",
            "title": "轻松愉快背景音乐",
            "video_url": video_url,
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(keyword="relaxing music"))
    assert isinstance(result, dict)
    assert "speak" in result and "render" in result
    assert isinstance(result.get("ui"), dict) and result["ui"].get("type") == "video_player"
    print("OK")
