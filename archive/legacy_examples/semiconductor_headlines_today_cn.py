"""抓取近24小时芯片/半导体头条并返回中文卡片列表。"""
import asyncio
import datetime as dt
import email.utils
import re
import urllib.parse
import xml.etree.ElementTree as ET

import httpx

RUN_SPEC = {
    "name": "semiconductor_headlines_today_cn",
    "description": "抓取今日或近24小时芯片半导体头条并生成中文卡片。",
    "args_schema": {
        "type": "object",
        "properties": {"limit": {"type": "integer", "default": 6}, "mock": {"type": "boolean", "default": False}},
        "required": [],
    },
}


def _fmt_time(s: str) -> str:
    try:
        t = email.utils.parsedate_to_datetime(s).astimezone()
        return t.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s or "未知"


async def _translate_zh(client: httpx.AsyncClient, text: str) -> str:
    url = "https://translate.googleapis.com/translate_a/single"
    params = {"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text}
    try:
        r = await client.get(url, params=params, timeout=6.0)
        data = r.json() if r.status_code == 200 else []
        return "".join(seg[0] for seg in data[0]) if data and data[0] else text
    except Exception:
        return text


async def run(limit: int = 6, mock: bool = False, **kwargs):
    if mock:
        return {"speak": "我整理好了芯片新闻速览。", "render": "references: mock://local\n1. 示例新闻", "ui": {"type": "card_grid", "title": "芯片头条（测试）", "cards": [{"title": "示例标题", "subtitle": "来源: Mock\n时间: 2026-06-18 12:00\n摘要: 这是结构测试数据。", "action_url": "https://example.com"}]}}
    query = "芯片 OR 半导体 OR chip OR semiconductor when:1d"
    rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote_plus(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    cards, refs = [], []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(rss_url, timeout=8.0)
            root = ET.fromstring(r.text) if r.status_code == 200 else ET.Element("rss")
            now_utc = dt.datetime.now(dt.timezone.utc)
            for item in root.findall(".//item"):
                if len(cards) >= max(1, min(limit, 10)):
                    break
                raw_t = (item.findtext("title") or "").strip()
                src = (item.findtext("source") or "未知来源").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                desc = re.sub(r"<[^>]+>", "", (item.findtext("description") or "")).strip()
                try:
                    pub_dt = email.utils.parsedate_to_datetime(pub).astimezone(dt.timezone.utc)
                    if pub_dt < now_utc - dt.timedelta(hours=24):
                        continue
                except Exception:
                    pass
                title = raw_t
                if re.search(r"[A-Za-z]", raw_t) and not re.search(r"[\u4e00-\u9fff]", raw_t):
                    zh = await _translate_zh(client, raw_t)
                    title = f"{raw_t}（中文：{zh}）"
                summary = (desc[:90] + "…") if len(desc) > 90 else (desc or "该报道聚焦芯片/半导体产业动态，涉及公司动作、供应链或政策变化。")
                cards.append({"title": title, "subtitle": f"来源: {src}\n发布时间: {_fmt_time(pub)}\n要点: {summary}", "action_url": link})
                refs.append(f"- source: {src} | source_url: {link} | published_at: {_fmt_time(pub)}")
    except Exception as e:
        msg = f"抓取失败，原因: {e}"
        return {"speak": "我这次没拿到最新新闻，稍后再试更稳妥。", "render": f"source_url: {rss_url}\nevidence: {msg}", "ui": {"type": "info_card", "title": "芯片新闻抓取失败", "message": msg, "source_url": rss_url}}
    if not cards:
        return {"speak": "我暂时没筛到近24小时的芯片头条。", "render": f"source_url: {rss_url}\nevidence: 结果为空", "ui": {"type": "info_card", "title": "芯片新闻", "message": "未检索到符合条件的头条，请稍后再试。", "source_url": rss_url}}
    render = "近24小时芯片/半导体头条\n" + "\n".join(f"{i+1}. {c['title']}\n{c['subtitle']}\n原文: {c['action_url']}" for i, c in enumerate(cards)) + "\nreferences:\n" + "\n".join(refs)
    return {"speak": f"我整理了最近{len(cards)}条芯片头条，给你看重点。", "render": render, "ui": {"type": "card_grid", "title": "今日芯片/半导体头条", "cards": cards}}


if __name__ == "__main__":
    out = asyncio.run(run(mock=True, limit=3))
    assert isinstance(out, dict) and "speak" in out and "render" in out
    print("OK")
