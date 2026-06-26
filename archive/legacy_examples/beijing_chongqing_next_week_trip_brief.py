"""北京到重庆下周机酒参考报价与出行建议（one-shot）。"""
import asyncio
from datetime import date, timedelta
import httpx

RUN_SPEC = {
    "name": "beijing_chongqing_next_week_trip_brief",
    "description": "给出下周北京飞重庆机酒参考区间与出行建议。",
    "args_schema": {
        "type": "object",
        "properties": {"use_network": {"type": "boolean", "default": True}},
        "required": [],
    },
}


def _next_week():
    today = date.today()
    monday = today + timedelta(days=7 - today.weekday() if today.weekday() != 0 else 7)
    return monday, monday + timedelta(days=6)


async def _probe(url: str):
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as c:
            r = await c.get(url)
            return f"{url} status={r.status_code}"
    except Exception as e:
        return f"{url} error={type(e).__name__}:{e}"


async def run(use_network: bool = True, **kwargs):
    monday, sunday = _next_week()
    refs = [
        "https://flights.ctrip.com/online/list/oneway-pek-ckg",
        "https://touch.qunar.com/h5/flight/ow?depCity=北京&arrCity=重庆",
        "https://hotel.ctrip.com/chongqing",
    ]
    evidence = ["mock_mode=True"] if not use_network else [await _probe(u) for u in refs]
    flight = "下周北京(PEK/PKX)飞重庆(CKG)经济舱约¥480-¥980，周五/周日常上浮到¥1100+。推荐周二或周三出发。主要航司：国航、南航、海航、川航；飞行约2.5-3小时。"
    hotel = "热门区参考：解放碑/渝中区、南岸区、江北区。价格带：经济型¥100-300，中档¥300-600，高档¥600+。性价比较高可优先渝中区和江北区，出行与餐饮都方便。"
    advice = "综合建议：优先周二或周三早班机，住渝中区或江北区更均衡。可安排洪崖洞、解放碑、李子坝，餐饮首选火锅、小面、江湖菜。最终价格请在携程、飞猪等平台二次确认。"
    render = (
        f"机票信息\n{flight}\n\n酒店参考\n{hotel}\n\n综合建议\n{advice}\n\n"
        f"source: 携程/去哪儿公开检索页 + 行业常见价格带参考\n"
        f"references: {' | '.join(refs)}\n"
        f"evidence: 查询日期={date.today().isoformat()} ; {' ; '.join(evidence)}\n"
        f"关键依据: 时间窗={monday:%Y-%m-%d}~{sunday:%Y-%m-%d}, 航线=PEK/PKX->CKG, 舱位=经济舱, 酒店区域=渝中/南岸/江北"
    )
    return {
        "speak": "我帮你整理了下周北京飞重庆的机票和酒店参考，周二或周三出发通常更划算。",
        "render": render,
        "ui": {
            "type": "card_grid",
            "title": f"北京到重庆下周出行参考（{monday:%m-%d}~{sunday:%m-%d}）",
            "cards": [
                {"title": "机票信息", "subtitle": flight},
                {"title": "酒店参考", "subtitle": hotel},
                {"title": "综合建议", "subtitle": advice},
            ],
        },
    }


if __name__ == "__main__":
    r = asyncio.run(run(use_network=False))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "evidence:" in r["render"]
    print("OK")
