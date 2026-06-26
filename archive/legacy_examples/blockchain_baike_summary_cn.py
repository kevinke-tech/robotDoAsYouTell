"""一次性技能：检索区块链百科并生成中文摘要。"""
import html
import re

import httpx

RUN_SPEC = {
    "name": "blockchain_baike_summary_cn",
    "description": "查询区块链百科并返回200字内中文总结与来源证据。",
    "args_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "default": "区块链"},
            "mock_summary": {"type": "string", "default": ""},
        },
        "required": [],
    },
}


def _compact(text: str, max_len: int = 200) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= max_len else cleaned[: max_len - 1] + "…"


async def _fetch_wikipedia(query: str, timeout: float):
    url = "https://zh.wikipedia.org/w/api.php"
    params = {"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "format": "json", "titles": query}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, params=params)
        if r.status_code != 200:
            return None, f"维基请求失败: HTTP {r.status_code}"
        pages = (r.json().get("query") or {}).get("pages") or {}
        for page in pages.values():
            text = str(page.get("extract") or "").strip()
            if text:
                return {"source": "维基百科中文版", "source_url": f"https://zh.wikipedia.org/wiki/{query}", "title": str(page.get("title") or query), "text": text}, ""
        return None, "维基返回为空"
    except Exception as e:
        return None, f"维基异常: {e}"


async def _fetch_baidu_baike(query: str, timeout: float):
    url = f"https://baike.baidu.com/item/{query}"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return None, f"百度百科请求失败: HTTP {r.status_code}"
        m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', r.text, re.I)
        text = html.unescape((m.group(1) if m else "").strip())
        if text:
            return {"source": "百度百科", "source_url": str(r.url), "title": f"{query} - 百度百科", "text": text}, ""
        return None, "百度百科描述为空"
    except Exception as e:
        return None, f"百度百科异常: {e}"


async def run(query: str = "区块链", mock_summary: str = "", **kwargs):
    if mock_summary.strip():
        summary = _compact(mock_summary.strip(), 200)
        return {"speak": f"我整理好了{query}的简介。", "render": f"总结: {summary}\nsource: 本地冒烟测试\nsource_url: N/A\nevidence: mock_summary", "ui": {"type": "info_card", "title": f"{query}百科速览", "message": summary, "source": "本地冒烟测试", "source_url": "N/A"}}
    timeout, errors = 8.0, []
    data, err = await _fetch_wikipedia(query, timeout)
    if not data:
        errors.append(err)
        data, err = await _fetch_baidu_baike(query, timeout)
    if not data:
        errors.append(err)
        msg = f"我暂时没查到{query}的百科内容。"
        ev = " | ".join([e for e in errors if e]) or "无可用证据"
        return {"speak": msg, "render": f"查询词: {query}\nsource: 维基百科中文版 / 百度百科\nsource_url: https://zh.wikipedia.org/ , https://baike.baidu.com/\nevidence: {ev}", "ui": {"type": "info_card", "title": "百科查询失败", "message": msg, "source": "维基百科中文版/百度百科", "source_url": "https://zh.wikipedia.org/"}}
    sentences = [s.strip() for s in re.split(r"[。！？]", data["text"]) if s.strip()]
    summary = _compact("。".join(sentences[:2]) or data["text"], 200)
    speak = f"我查到{query}的百科信息了，给你一句话总结。"
    render = f"总结: {summary}\nsource: {data['source']}\nsource_url: {data['source_url']}\nevidence: title={data['title']} | snippet={_compact(data['text'], 80)}"
    ui = {"type": "info_card", "title": f"{query}百科速览", "message": summary, "source": data["source"], "source_url": data["source_url"]}
    return {"speak": speak, "render": render, "ui": ui}


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(mock_summary="区块链是按时间顺序连接数据块并通过密码学保障防篡改的分布式账本技术，常用于多方协作场景中的可信记录。"))
    assert isinstance(result, dict) and "speak" in result and "render" in result and isinstance(result.get("ui"), dict)
    print("OK")
