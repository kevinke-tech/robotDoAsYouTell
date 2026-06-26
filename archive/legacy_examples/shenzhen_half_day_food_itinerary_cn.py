"""深圳周末半天游玩+餐饮安排建议（one-shot）。"""

RUN_SPEC = {
    "name": "shenzhen_half_day_food_itinerary_cn",
    "description": "给出深圳周末上午/下午半天游玩与餐饮建议。",
    "args_schema": {
        "type": "object",
        "properties": {
            "day_part": {"type": "string", "enum": ["morning", "afternoon", "both"], "default": "both"}
        },
        "required": [],
    },
}


def _plan_data():
    return {
        "morning": {
            "title": "上午轻松版",
            "timeline": ["09:00 莲花山公园晨步", "10:30 深圳博物馆看特展", "12:10 市民中心周边午餐"],
            "spots": [("🌳 莲花山公园", "城市绿地视野开阔，适合慢走拍照", "约1小时", "福田区"),
                      ("🏛️ 深圳博物馆", "城市发展与文化展陈集中，路线紧凑", "约1.2小时", "福田区"),
                      ("🏙️ 市民中心广场", "中轴景观与现代建筑打卡", "约0.5小时", "福田区")],
            "foods": [("🍜 润园四季椰子鸡", "粤式椰子鸡", "人均80-110元", "福田区会展中心片区"),
                      ("🥟 点都德", "广式点心", "人均70-100元", "福田区皇庭广场周边")],
        },
        "afternoon": {
            "title": "下午海风版",
            "timeline": ["14:00 深圳湾公园海边步道", "15:20 人才公园观景", "17:00 欢乐海岸晚餐"],
            "spots": [("🌊 深圳湾公园", "滨海步道平缓，适合看海放松", "约1小时", "南山区"),
                      ("🌇 人才公园", "湖景与湾区天际线同框，傍晚更出片", "约1小时", "南山区"),
                      ("🎨 欢乐海岸街区", "商业+艺术装置，散步休闲方便", "约0.8小时", "南山区")],
            "foods": [("🍣 西贝海鲜工坊", "海鲜与创意粤菜", "人均120-180元", "南山区欢乐海岸"),
                      ("🍛 探鱼", "川味烤鱼", "人均90-130元", "南山区欢乐海岸")],
        },
    }


async def run(day_part: str = "both", **kwargs):
    plans = _plan_data()
    selected = ["morning", "afternoon"] if day_part not in plans else [day_part]
    blocks, summary = [], []
    for key in selected:
        p = plans[key]
        summary.append(f"{p['title']}：{p['timeline'][0]} -> {p['timeline'][-1]}")
        timeline = "".join(f"<li>{t}</li>" for t in p["timeline"])
        spots = "".join(f"<div>• {n}｜{d}｜{a}<br>{i}</div>" for n, i, d, a in p["spots"])
        foods = "".join(f"<div>• {n}｜{c}｜{pp}｜{loc}</div>" for n, c, pp, loc in p["foods"])
        blocks.append(f"<section><h3>🗺️ {p['title']}</h3><p><b>时间轴</b></p><ol>{timeline}</ol>"
                      f"<p><b>景点卡片</b></p>{spots}<p><b>餐厅卡片</b></p>{foods}</section>")
    source = "source: 深圳文旅公开信息与商圈常识整理（离线模板）"
    evidence = "evidence: 福田线集中在莲花山-博物馆-市民中心；南山线集中在深圳湾-人才公园-欢乐海岸"
    references = "references: https://www.sz.gov.cn/ ; https://www.visitshenzhen.com/"
    render = "深圳周末半天游玩+餐饮建议\n" + "\n".join(summary) + f"\n{source}\n{evidence}\n{references}"
    ui = {
        "type": "html_card",
        "title": "深圳半天行程卡",
        "srcdoc": "<div style='font-family:sans-serif;line-height:1.5'>" + "".join(blocks) + "</div>",
    }
    return {"speak": "我给你整理好了深圳周末半天游和吃饭安排，直接照着走就行。", "render": render, "ui": ui}


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run(day_part="both"))
    assert isinstance(result, dict) and "speak" in result and "render" in result and result.get("ui", {}).get("type")
    print("OK")
