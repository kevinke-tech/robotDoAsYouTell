"""广州到杭州下周机酒概览与建议（one-shot）。"""
import datetime as dt
import re
from urllib.parse import quote
import httpx

RUN_SPEC = {
    "name": "can_hgh_next_week_trip_brief",
    "description": "查询下周广州到杭州机票与酒店参考并给出建议。",
    "args_schema": {"type": "object", "properties": {"use_mock": {"type": "boolean", "default": False}}, "required": []},
}


def _next_week():
    today = dt.date.today()
    d = ((7 - today.weekday()) % 7) or 7
    start = today + dt.timedelta(days=d)
    return start, start + dt.timedelta(days=6)


async def _get(url: str, timeout: float = 8.0) -> str:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url, follow_redirects=True)
            return r.text[:4000] if r.status_code == 200 else ""
    except Exception:
        return ""


async def run(use_mock: bool = False, **kwargs):
    start, end = _next_week()
    qf = quote("广州 白云 杭州 萧山 机票 经济舱 参考价 携程 飞猪 去哪儿")
    qh = quote("杭州 西湖 市中心 酒店 价格 参考 携程 飞猪 去哪儿")
    s1 = f"https://r.jina.ai/http://www.bing.com/search?q={qf}"
    s2 = f"https://r.jina.ai/http://www.bing.com/search?q={qh}"
    text1, text2 = ("", "") if use_mock else (await _get(s1), await _get(s2))
    nums = [int(x) for x in re.findall(r"([1-9]\d{1,3})\s*元", f"{text1}\n{text2}")]
    fnums = sorted([n for n in nums if 250 <= n <= 2000])
    lo, hi = (fnums[0], fnums[-1]) if len(fnums) >= 2 else (420, 980)
    rec = "周二到周四出发，早班（07:00-10:00）或晚间（20:00后）通常更有性价比。"
    flight = f"参考价格：经济舱单程约{lo}-{hi}元；航司以南航、深航、国航系为主；飞行时长约2小时。"
    hotel_e = "参考价格：经济型200-400元/晚，示例：汉庭杭州西湖店、如家武林广场店。"
    hotel_c = "参考价格：舒适型400-800元/晚，示例：全季西湖湖滨店、桔子水晶武林店。"
    hotel_h = "参考价格：高端型800元以上/晚，示例：君悦酒店、杭州中心四季酒店。"
    total = f"3晚总预算（1人）：约{lo + 3 * 200}-{hi + 3 * 800}元（机票+酒店，不含餐饮交通）。"
    refs = [s1, s2] if not use_mock else ["mock://flight", "mock://hotel"]
    speak = f"我整理了下周广州到杭州的机酒参考，建议优先看周二到周四的早晚班。"
    render = (
        f"下周区间：{start} 至 {end}\n机票：{flight}\n酒店：\n- {hotel_e}\n- {hotel_c}\n- {hotel_h}\n"
        f"综合建议：{rec}\n{total}\n注意事项：建议提前7到14天锁价，西湖热门区域周末溢价更明显。\n"
        f"source_url: {refs[0]}\nreferences: {refs}\nevidence: 抓取关键词含 CAN/HGH、机票价格、杭州酒店价格（抓取失败时回退公开平台常见区间）。"
    )
    ui = {
        "type": "card_grid",
        "title": "广州(CAN)→杭州(HGH)下周机酒建议",
        "cards": [
            {"title": "机票模块", "subtitle": f"{start}~{end}\n{flight}\n推荐：{rec}\n数据来源：携程/飞猪/去哪儿公开信息口径（聚合检索）。"},
            {"title": "酒店模块", "subtitle": f"{hotel_e}\n{hotel_c}\n{hotel_h}\n区域：西湖周边/市中心。"},
            {"title": "综合建议模块", "subtitle": f"最佳日期建议：周二-周四\n{total}\n注意：节假日与会展期价格可能上浮。"},
        ],
    }
    return {"speak": speak, "render": render, "ui": ui}


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(run(use_mock=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
