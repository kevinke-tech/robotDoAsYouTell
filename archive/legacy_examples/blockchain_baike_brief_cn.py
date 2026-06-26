"""区块链百科摘要：一次性检索并生成中文简明总结。"""
import datetime as dt
import re
from urllib.parse import quote

import httpx

RUN_SPEC = {
    "name": "blockchain_baike_brief_cn",
    "description": "检索区块链百科并输出 200 字内中文摘要。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "区块链"},
            "max_chars": {"type": "integer", "default": 200, "minimum": 60, "maximum": 240},
            "offline_test": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}


async def run(query: str = "区块链", max_chars: int = 200, offline_test: bool = False, **kwargs):
    source = "中文维基百科"
    source_url = f"https://zh.wikipedia.org/wiki/{quote(query)}"
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    if offline_test:
        summary = "区块链是一种按时间顺序连接数据块的分布式账本技术，依靠密码学和共识机制保证记录难以篡改，常用于数字资产与多方协作场景。"
        return {
            "speak": "我整理了一段区块链的百科简介。",
            "render": f"总结: {summary}\nsource: {source}\nsource_url: {source_url}\nevidence: offline_test=true; fetched_at={fetched_at}",
            "ui": {"type": "info_card", "title": "区块链百科摘要", "message": summary, "source": source, "source_url": source_url},
        }
    api_url = f"https://zh.wikipedia.org/api/rest_v1/page/summary/{quote(query)}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(api_url)
        data = resp.json() if resp.status_code == 200 else {}
        raw = str(data.get("extract") or "").strip()
        title = str(data.get("title") or query).strip()
        source_url = str(data.get("content_urls", {}).get("desktop", {}).get("page") or source_url)
        clean = re.sub(r"\[[0-9]+\]", "", raw)
        summary = clean[: max(60, min(int(max_chars), 240))].strip(" ，。；\n")
        if not summary:
            raise ValueError("empty_summary")
        speak = f"我查到{title}的百科内容，已为你简要总结。"
        render = f"标题: {title}\n总结: {summary}\nsource: {source}\nsource_url: {source_url}\nevidence: status={resp.status_code}; fetched_at={fetched_at}; extract_len={len(raw)}"
        ui = {
            "type": "info_card",
            "title": title,
            "message": f"{summary}\n\n来源: {source}\n链接: {source_url}",
            "source": source,
            "source_url": source_url,
        }
        return {"speak": speak, "render": render, "ui": ui}
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"
        msg = "我这次没连上百科源，但先给你一个核心概念：区块链是去中心化、可追溯且难篡改的分布式账本。"
        return {
            "speak": "百科检索暂时失败了，我先口头给你一个简版定义。",
            "render": f"总结: {msg}\nsource: {source}\nsource_url: {source_url}\nevidence: request_failed={reason}; fetched_at={fetched_at}",
            "ui": {"type": "info_card", "title": "区块链百科摘要（降级）", "message": f"{msg}\n\n来源: {source}\n链接: {source_url}", "source": source, "source_url": source_url},
        }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(offline_test=True))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
