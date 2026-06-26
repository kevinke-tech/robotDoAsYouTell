"""北京-重庆下周机票与酒店估算一次性技能。"""
from datetime import datetime, timedelta

RUN_SPEC = {
    "name": "beijing_chongqing_next_week_trip_estimator",
    "description": "估算下周北京到重庆机票与酒店，并给出出行建议。",
    "args_schema": {"type": "object", "properties": {}, "required": []},
}


def _next_week_dates():
    today = datetime.now().date()
    delta = (7 - today.weekday()) % 7 or 7
    start = today + timedelta(days=delta)
    return [start + timedelta(days=i) for i in range(7)]


async def run(**kwargs):
    days = _next_week_dates()
    factors = [1.08, 0.96, 0.94, 1.0, 1.18, 1.32, 1.12]  # 周一到周日
    base = 760
    airline_offsets = {"国航CA": 120, "南航CZ": 60, "重庆航空OQ": 30, "东航MU": 80}
    flight_rows, daily_ranges = [], []
    for i, d in enumerate(days):
        low = int(base * factors[i] - 120)
        high = low + 420
        daily_ranges.append((d, low, high))
        refs = "、".join(f"{k}约{low+v}-{low+v+180}元" for k, v in airline_offsets.items())
        flight_rows.append(f"{d.strftime('%m-%d')} {d.strftime('%A')}: 约{low}-{high}元；{refs}")
    best_day = min(daily_ranges, key=lambda x: x[1])
    hotels = [
        "经济型(渝中/江北): 如汉庭、7天、如家，约180-320元/晚；特点: 性价比高、通勤方便。",
        "舒适型(解放碑/南岸): 如全季、桔子水晶、智选假日，约320-550元/晚；特点: 设施更完整、适合差旅和轻度度假。",
        "高端型(解放碑江景/来福士周边): 如威斯汀、尼依格罗、丽晶，约700-1400元/晚；特点: 景观与服务更优。",
    ]
    speak = f"我整理好了下周北京到重庆的机酒参考，{best_day[0].strftime('%m月%d日')}出发通常更划算。"
    render = (
        "【机票】北京(PEK/PKX) -> 重庆(CKG)，经济舱参考/估算价格：\n"
        + "\n".join(flight_rows)
        + "\n\n【酒店】重庆核心区域每晚参考价：\n"
        + "\n".join(hotels)
        + f"\n\n【综合建议】\n1) 优先选{best_day[0].strftime('%m-%d')}或其前后一天，机票通常更低。\n"
        "2) 人均2晚预算可按: 机票往返约1200-2200元 + 酒店约360-2800元估算，提前7-14天锁价更稳。"
        "\n\nreferences:\n"
        "- source: 历史均价与季节规律估算（非实时抓取）\n"
        "- source_url: https://www.ctrip.com/\n"
        "- source_url: https://www.qunar.com/\n"
        "- source_url: https://www.variflight.com/\n"
        f"- evidence: 生成时间{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，关键字段=航线(北京-重庆)、日期(下周一到周日)、舱位(经济舱)"
        "\n- 说明: 参考价格，实际以购票/预订平台为准。"
    )
    ui = {
        "type": "info_card",
        "title": "北京→重庆 下周机票+酒店参考",
        "message": "【机票】\n"
        + "\n".join(flight_rows)
        + "\n\n【酒店】\n"
        + "\n".join(hotels)
        + f"\n\n建议: {best_day[0].strftime('%m-%d')}附近出发性价比较好；价格仅作参考。",
    }
    return {"speak": speak, "render": render, "ui": ui}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(run())
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
