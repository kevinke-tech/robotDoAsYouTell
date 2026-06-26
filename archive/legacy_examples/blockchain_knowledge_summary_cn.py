"""区块链百科信息检索与中文摘要。"""
import re
from typing import Dict

import httpx

RUN_SPEC = {
    "name": "blockchain_knowledge_summary_cn",
    "description": "检索区块链百科并生成简明中文总结。",
    "args_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "default": "区块链"}},
        "required": [],
    },
}


def _short(text: str, limit: int = 200) -> str:
    t = re.sub(r"\s+", " ", (text or "")).strip()
    return t if len(t) <= limit else t[: limit - 1] + "…"


async def run(query: str = "区块链", mock_summary: str = "", **kwargs) -> Dict[str, object]:
    q = (query or "区块链").strip()
    if mock_summary:
        msg = _short(mock_summary)
        return {
            "speak": f"我整理好了关于{q}的简明介绍。",
            "render": f"source: mock\nsource_url: local_test\nevidence: synthetic\n总结: {msg}",
            "ui": {"type": "info_card", "title": f"{q}百科总结", "message": msg, "source_name": "mock", "source_url": "local_test"},
        }
    wiki_url = f"https://zh.wikipedia.org/api/rest_v1/page/summary/{q}"
    baike_url = f"https://baike.baidu.com/item/{q}"
    source, source_url, evidence, summary = "", "", "", ""
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.get(wiki_url, headers={"accept": "application/json"})
            if r.status_code == 200:
                data = r.json()
                summary = _short(str(data.get("extract") or ""))
                if summary:
                    source, source_url = "中文维基百科", str(data.get("content_urls", {}).get("desktop", {}).get("page") or wiki_url)
                    evidence = f"title={data.get('title','')}; lang=zh; status=200"
            if not summary:
                r2 = await client.get(baike_url, headers={"user-agent": "Mozilla/5.0"})
                if r2.status_code == 200:
                    m = re.search(r'<meta name="description" content="([^"]+)"', r2.text)
                    summary = _short(m.group(1) if m else "")
                    if summary:
                        source, source_url, evidence = "百度百科", baike_url, "field=meta_description; status=200"
    except Exception as e:
        evidence = f"error={type(e).__name__}:{str(e)[:80]}"
    if not summary:
        fail = f"我暂时没查到{q}的百科内容，请稍后再试。"
        return {
            "speak": fail,
            "render": f"source: 未获取到有效来源\nsource_url: {wiki_url}\nevidence: {evidence or 'empty_response'}\n结论: 检索失败",
            "ui": {"type": "info_card", "title": f"{q}百科总结", "message": fail, "source_name": "未知", "source_url": wiki_url},
        }
    return {
        "speak": f"我整理好了关于{q}的简明介绍。",
        "render": f"source: {source}\nsource_url: {source_url}\nevidence: {evidence}\n总结: {summary}",
        "ui": {"type": "info_card", "title": f"{q}百科总结", "message": summary, "source_name": source, "source_url": source_url},
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(query="区块链", mock_summary="区块链是以分布式账本、密码学和共识机制为基础的数据记录技术，强调去中心化、可追溯和难篡改，常用于数字资产、供应链溯源与协同存证等场景。"))
    assert isinstance(result, dict) and "speak" in result and "render" in result
    print("OK")
