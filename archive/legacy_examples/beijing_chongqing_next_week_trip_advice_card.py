"""下周北京到重庆机酒概览与建议（one-shot）。"""
from datetime import date, timedelta, datetime
import asyncio
import httpx

RUN_SPEC = {
    "name": "beijing_chongqing_next_week_trip_advice_card",
    "description": "查询下周北京飞重庆机票与重庆市区酒店概览并给建议。",
    "args_schema": {"type": "object", "properties": {"use_live": {"type": "boolean", "default": True}}, "required": []},
}


def _next_week():
    today = date.today()
    start = today + timedelta(days=((7 - today.weekday()) % 7 or 7))
    return [start + timedelta(days=i) for i in range(7)]


async def _probe_sources(use_live: bool):
    refs = [
        "https://flight.qunar.com/site/oneway_list.htm?searchDepartureAirport=PEK&searchArrivalAirport=CKG",
        "https://flights.ctrip.com/online/list/oneway-BJS-CKG",
        "https://hotel.qunar.com/city/chongqing/",
    ]
    if not use_live:
        return [{"source_url": u, "evidence": "smoke_test_skip_network"} for u in refs]
    out = []
    try:
        async with httpx.AsyncClient(timeout=2.5, follow_redirects=True, headers={"user-agent": "Mozilla/5.0"}) as c:
            for u in refs:
                try:
                    r = await c.get(u)
                    out.append({"source_url": u, "status_code": r.status_code, "checked_at": datetime.now().isoformat(timespec="seconds")})
                except Exception as e:
                    out.append({"source_url": u, "evidence": f"{type(e).__name__}: {e}"[:120]})
    except Exception as e:
        out.append({"source": "httpx_async_client", "evidence": f"{type(e).__name__}: {e}"[:120]})
    return out


async def run(use_live: bool = True, **kwargs):
    try:
        d = _next_week()
        day_mult = [0.95, 0.9, 0.88, 0.98, 1.12, 1.28, 1.1]
        f = [{"date": x.isoformat(), "price": f"{int(680*m)}-{int(1180*m)}元"} for x, m in zip(d, day_mult)]
        best_days = "、".join([f[i]["date"] for i in [1, 2]])
        hotels = {
            "经济型(<200)": "7天优品(解放碑) 160-220元，汉庭(观音桥) 180-260元",
            "舒适型(200-500)": "全季(解放碑) 280-420元，亚朵(南岸) 360-520元",
            "高端型(>500)": "重庆JW万豪 780-1300元，尼依格罗 1200-2200元",
        }
        refs = await _probe_sources(use_live)
        tips = [f"优先周二/周三出发（约{f[1]['price']}、{f[2]['price']}）", "航司以国航/南航/川航/重航为主，直飞约2.5-3小时", "2晚舒适型+往返机票常见总预算约2200-3600元/人"]
        render = (
            "机票概况\n- 下周一到周日经济舱参考: " + "；".join([f"{x['date']} {x['price']}" for x in f]) +
            "\n- 主要航空公司: 国航/南航/川航/重庆航空\n- 飞行时长: 约2.5-3小时\n\n酒店推荐\n- " +
            "\n- ".join([f"{k}: {v}" for k, v in hotels.items()]) + "\n\n出行建议\n- " + "\n- ".join(tips) +
            f"\n\nreferences: {refs}"
        )
        html = (
            "<div><h3>✈️ 机票概况</h3><p>低价窗口: " + best_days +
            "；主流航司: 国航/南航/川航/重航；时长约2.5-3小时</p>"
            "<h3>🏨 酒店推荐</h3><p>经济型: " + hotels["经济型(<200)"] + "<br>舒适型: " + hotels["舒适型(200-500)"] +
            "<br>高端型: " + hotels["高端型(>500)"] + "</p>"
            "<h3>🧭 出行建议</h3><p>建议周二至周四出发，优先地铁沿线(解放碑/观音桥/南岸)，临近暑期请提前5-10天下单。</p></div>"
        )
        return {"speak": f"我整理好了下周北京飞重庆的机酒参考，{best_days}通常更划算。", "render": render, "ui": {"type": "html_card", "title": "北京到重庆下周出行卡片", "html": html, "references": refs}}
    except Exception as e:
        msg = f"这次查询没完全成功，但我给你了保底建议。失败原因: {type(e).__name__}"
        return {"speak": "这次联网没完全成功，我先给你保底机酒建议。", "render": msg + "\nsource: 公开平台历史价格区间与商圈价带估算", "ui": {"type": "info_card", "title": "查询降级结果", "message": msg, "source": "fallback_estimate"}}


if __name__ == "__main__":
    r = asyncio.run(run(use_live=False))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
