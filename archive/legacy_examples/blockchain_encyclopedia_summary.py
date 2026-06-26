"""查询区块链百科并生成简明总结。"""
import asyncio
import re
from urllib.parse import quote

import httpx

RUN_SPEC = {
    "name": "blockchain_encyclopedia_summary",
    "description": "检索区块链百科并返回200字内中文总结。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "区块链"},
            "mock_extract": {"type": "string"},
        },
        "required": [],
    },
}


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\[[^\]]*\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


async def run(query: str = "区块链", mock_extract: str = "", **kwargs):
    source, source_url, title, extract, errors = "维基百科中文版", "", "", "", []
    if mock_extract:
        extract = _clean(mock_extract)
        source, source_url, title = "本地模拟数据", "mock://local", query
    else:
        timeout = httpx.Timeout(8.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                wurl = f"https://zh.wikipedia.org/api/rest_v1/page/summary/{quote(query)}"
                wr = await client.get(wurl)
                if wr.status_code == 200:
                    wd = wr.json()
                    extract = _clean(str(wd.get("extract") or ""))
                    title = str(wd.get("title") or query)
                    source_url = str((wd.get("content_urls") or {}).get("desktop", {}).get("page") or wurl)
                else:
                    errors.append(f"wiki_status={wr.status_code}")
            except Exception as e:
                errors.append(f"wiki_error={type(e).__name__}")
            if not extract:
                source = "百度百科"
                try:
                    burl = f"https://baike.baidu.com/item/{quote(query)}"
                    br = await client.get(burl)
                    source_url = burl
                    m = re.search(r'<meta name="description" content="([^"]+)"', br.text)
                    extract = _clean(m.group(1) if m else "")
                    title = query
                    if br.status_code != 200:
                        errors.append(f"baike_status={br.status_code}")
                except Exception as e:
                    errors.append(f"baike_error={type(e).__name__}")
    summary = (extract[:200]).rstrip("，。；;,. ")
    if not summary:
        reason = "；".join(errors) if errors else "未抓取到有效摘要"
        return {
            "speak": "我这次没查到可靠的百科摘要，你稍后再试一下。",
            "render": f"source: 未命中\nsource_url: N/A\nevidence: query={query}; reason={reason}",
            "ui": {"type": "info_card", "title": "区块链百科查询失败", "message": f"原因：{reason}", "source": "N/A", "source_url": "N/A"},
        }
    return {
        "speak": "我查到了区块链的百科信息，给你一句话总结。",
        "render": f"总结: {summary}\nsource: {source}\nsource_url: {source_url}\nevidence: query={query}; title={title}; extract_len={len(extract)}",
        "ui": {"type": "info_card", "title": "区块链百科简明总结", "message": summary, "source": source, "source_url": source_url},
    }


if __name__ == "__main__":
    r = asyncio.run(run(query="区块链", mock_extract="区块链是以分布式账本、密码学和共识机制为基础的数据结构与系统，可实现去中心化记录与可追溯协作。"))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
