"""深圳周末半天游玩+餐饮 one-shot 技能。"""

RUN_SPEC = {
    "name": "shenzhen_weekend_half_day_plan",
    "description": "生成深圳周末半天游玩与餐饮安排建议。",
    "args_schema": {
        "type": "object",
        "properties": {
            "period": {"type": "string", "enum": ["morning", "afternoon", "both"], "default": "both"}
        },
        "required": [],
    },
}

PLANS = {
    "morning": {
        "title": "上午版（09:00-13:30）",
        "spots": [("🌿 莲花山公园", "1h", "福田区"), ("📸 市民中心广场", "45m", "福田区"), ("🛍️ COCO Park", "1h", "福田区")],
        "foods": [("🍜 润园四季椰子鸡", "粤式椰子鸡，人均约90元", "福田CBD"), ("🥟 点都德", "广式点心，人均约80元", "会展中心周边")],
        "traffic": "步行+地铁 2/3 号线串联，点间约 10-20 分钟。",
    },
    "afternoon": {
        "title": "下午版（14:00-19:00）",
        "spots": [("🎨 华侨城创意文化园", "1.5h", "南山区"), ("🌊 深圳湾公园", "1h", "南山区"), ("🌇 海上世界文化艺术中心外圈", "1h", "蛇口")],
        "foods": [("🍲 八合里牛肉火锅", "潮汕火锅，人均约110元", "南山后海"), ("🍣 Sushi Express", "日式简餐，人均约70元", "海上世界")],
        "traffic": "地铁 1/2/11 号线可达，打车 15-25 分钟可覆盖全段。",
    },
}


async def run(period: str = "both", **kwargs):
    keys = ["morning", "afternoon"] if period not in PLANS else [period]
    sections, html_sections = [], []
    for key in keys:
        p = PLANS[key]
        spot_text = "；".join([f"{n}（{d}，{a}）" for n, d, a in p["spots"]])
        food_text = "；".join([f"{n}（{f}，{a}）" for n, f, a in p["foods"]])
        sections += [f"{p['title']}", f"景点/活动: {spot_text}", f"餐厅推荐: {food_text}", f"交通: {p['traffic']}"]
        timeline = "".join([f"<li>{n} · {d} · {a}</li>" for n, d, a in p["spots"]])
        foods = "".join([f"<li>{n}<br>{f}<br>📍{a}</li>" for n, f, a in p["foods"]])
        html_sections.append(
            f"<section style='border:1px solid #e5e7eb;border-radius:12px;padding:12px;margin:10px 0;'>"
            f"<h3>{p['title']}</h3><div>🚇 {p['traffic']}</div><h4>🕒 时间轴</h4><ol>{timeline}</ol>"
            f"<h4>🍽️ 餐厅卡片</h4><ul>{foods}</ul></section>"
        )
    render = (
        "source: 深圳地铁线路与核心商圈公开信息（离线整理模板）\n"
        "evidence: 福田/南山/蛇口点位邻近地铁站，单段通勤通常 10-25 分钟，适合半天紧凑动线。\n"
        "references: 深圳地铁公开线路图、商圈公开营业信息\n\n"
        + "\n".join(sections)
    )
    speak = "我给你整理好了深圳周末半天游方案，路线紧凑，景点和吃饭都搭配好了。"
    return {
        "speak": speak,
        "render": render,
        "ui": {
            "type": "html_card",
            "title": "深圳周末半天游玩+餐饮安排",
            "html": "<div style='font-family:sans-serif;line-height:1.6;'>" + "".join(html_sections) + "</div>",
        },
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run(period="both"))
    assert isinstance(result, dict) and "speak" in result and "render" in result and "ui" in result
    assert "source:" in result["render"] and "evidence:" in result["render"]
    print("OK")
