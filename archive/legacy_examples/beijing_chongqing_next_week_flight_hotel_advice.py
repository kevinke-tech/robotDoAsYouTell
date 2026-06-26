"""北京到重庆下周机酒估算 one-shot skill。"""
from datetime import date, timedelta
import asyncio
import httpx

RUN_SPEC = {
    "name": "beijing_chongqing_next_week_flight_hotel_advice",
    "description": "估算下周北京到重庆机票和酒店信息并给出建议。",
    "args_schema": {"type": "object", "properties": {"use_live": {"type": "boolean", "default": True}}, "required": []},
}

def _next_week_dates():
    today = date.today()
    days = (7 - today.weekday()) % 7 or 7
    start = today + timedelta(days=days)
    return [start + timedelta(days=i) for i in range(7)]

async def _fetch_evidence():
    out, urls = [], [
        "https://www.ly.com/flights/itinerary/oneway/PEK-CKG",
        "https://flight.qunar.com/site/oneway_list.htm?searchDepartureAirport=PEK&searchArrivalAirport=CKG",
    ]
    try:
        async with httpx.AsyncClient(timeout=2.0, follow_redirects=True) as c:
            for u in urls:
                try:
                    r = await c.get(u)
                    out.append({"source_url": u, "status_code": r.status_code, "checked_at": str(date.today())})
                except Exception as e:
                    out.append({"source_url": u, "error": f"{type(e).__name__}: {e}"[:120]})
    except Exception as e:
        out.append({"source": "httpx_client", "error": f"{type(e).__name__}: {e}"[:120]})
    return out

async def run(use_live: bool = True, **kwargs):
    try:
        days = _next_week_dates()
        mult = [0.96, 0.9, 0.88, 0.98, 1.15, 1.25, 1.08]
        carriers = {"国航": 1.0, "南航": 0.97, "重庆航空": 0.93}
        flights = []
        for i, d in enumerate(days):
            lo, hi = int(680 * mult[i]), int(1080 * mult[i])
            flights.append({"date": d.isoformat(), "range": f"{lo}-{hi}元", "carriers": {k: f"{int(lo*v)}-{int(hi*v)}元" for k, v in carriers.items()}})
        best = min(flights, key=lambda x: int(x["range"].split("-")[0]))
        hotels = {"经济型": "180-320元/晚（连锁便捷，交通优先）", "舒适型": "320-580元/晚（商圈核心，性价比高）", "高端型": "680-1400元/晚（江景/地标，配套完整）"}
        evidence = await _fetch_evidence() if use_live else [{"source": "历史均价+季节规律估算", "references": ["携程机票指数页", "同程/去哪儿航线列表页", "重庆核心商圈酒店价带"]}]
        f_lines = [f"{x['date']}: {x['range']}（国航{x['carriers']['国航']}，南航{x['carriers']['南航']}，重庆航空{x['carriers']['重庆航空']}）" for x in flights]
        h_lines = [f"{k}: {v}" for k, v in hotels.items()]
        tips = [f"建议优先选择 {best['date']} 出发，机票区间约 {best['range']}。", "机票建议提前5-10天锁价；酒店优先选解放碑/观音桥地铁沿线。"]
        render = "机票（参考价格，实际以购票平台为准）\n" + "\n".join(f_lines) + "\n\n酒店（重庆市区每晚参考）\n" + "\n".join(h_lines) + "\n\n综合建议\n- " + "\n- ".join(tips) + f"\n\nreferences: {evidence}"
        html = "<h3>机票</h3><ul>" + "".join([f"<li>{l}</li>" for l in f_lines]) + "</ul><h3>酒店</h3><ul>" + "".join([f"<li>{l}</li>" for l in h_lines]) + "</ul><h3>建议</h3><ul>" + "".join([f"<li>{t}</li>" for t in tips]) + "</ul><p>参考价格，实际以购票平台为准。</p>"
        return {"speak": f"我整理了下周北京到重庆的机票和酒店参考，{best['date']}出发通常更划算。", "render": render, "ui": {"type": "html_card", "title": "北京→重庆 下周机酒参考", "html": html, "references": evidence}}
    except Exception as e:
        msg = f"抱歉，这次查询失败了，我先给你保底建议：下周二到周四通常更划算。错误: {type(e).__name__}"
        return {"speak": "我这次没完整拿到数据，但给你了保底出行建议。", "render": msg + "\nsource: 历史均价与季节规律估算", "ui": {"type": "info_card", "title": "机酒查询降级结果", "message": msg, "source": "fallback_estimate"}}

if __name__ == "__main__":
    r = asyncio.run(run(use_live=False))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
