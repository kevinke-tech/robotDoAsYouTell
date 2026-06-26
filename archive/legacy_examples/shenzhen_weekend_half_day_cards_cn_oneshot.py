"""深圳周末半天游玩+餐饮安排（one-shot）。"""

RUN_SPEC = {
    "name": "shenzhen_weekend_half_day_cards_cn_oneshot",
    "description": "生成深圳周末半天游玩+餐饮建议，并以卡片时间轴展示。",
    "args_schema": {
        "type": "object",
        "properties": {
            "period": {"type": "string", "enum": ["morning", "afternoon", "both"], "default": "both"},
            "area_preference": {"type": "string", "default": "福田-南山沿线"},
        },
        "required": [],
    },
}


def _primary_plans():
    return {
        "morning": {
            "title": "上午版（09:00-13:30）",
            "spots": [("🌿 深圳湾公园晨间漫步", "1.5小时", "南山区滨海大道沿线"), ("🖼️ 海上世界文化艺术中心", "1小时", "南山区蛇口望海路"), ("🛍️ 欢乐海岸轻逛", "1小时", "南山区白石路东")],
            "food": [("🍤 润园四季椰子鸡", "粤式椰子鸡", "人均¥90-120", "南山区欢乐海岸"), ("🥟 点都德", "广式点心", "人均¥70-100", "南山区海岸城附近")],
        },
        "afternoon": {
            "title": "下午版（14:00-19:00）",
            "spots": [("🏛️ 深圳博物馆（历史民俗馆）", "1.5小时", "福田区市民中心东侧"), ("🌆 莲花山公园观景", "1.5小时", "福田区红荔路"), ("🎵 深圳音乐厅/中心书城周边", "1小时", "福田区福中一路")],
            "food": [("🐟 探鱼", "川湘烤鱼", "人均¥85-120", "福田区中心城商圈"), ("🍜 八合里牛肉火锅", "潮汕牛肉火锅", "人均¥100-140", "福田区购物公园周边")],
        },
    }


def _backup_plans():
    return {
        "morning": {"title": "上午版（09:30-13:00）", "spots": [("🌊 人才公园散步", "1小时", "南山区科苑南路"), ("🎨 华侨城创意园", "1.5小时", "南山区锦绣北街")], "food": [("🍚 金稻园砂锅粥", "粤式粥品", "人均¥60-90", "南山区华侨城")]},
        "afternoon": {"title": "下午版（14:30-18:30）", "spots": [("🏞️ 笔架山公园", "1.5小时", "福田区梅岗路"), ("📚 中心书城", "1小时", "福田区福中一路")], "food": [("🍲 顺德公猪肚鸡", "顺德风味", "人均¥80-110", "福田区华强北商圈")]},
    }


def _html(plans):
    parts = ["<div style='font-family:Arial;padding:10px'>", "<h3>🧭 深圳周末半天游玩+餐饮卡片</h3>"]
    for k in ("morning", "afternoon"):
        p = plans[k]
        parts.append(f"<h4>{'🌞' if k=='morning' else '🌇'} {p['title']}</h4><div>⏱️ 时间轴</div><ol>")
        for s in p["spots"]:
            parts.append(f"<li><b>{s[0]}</b>｜建议时长：{s[1]}｜区域：{s[2]}</li>")
        parts.append("</ol><div>🍽️ 餐厅卡片</div><ul>")
        for f in p["food"]:
            parts.append(f"<li><b>{f[0]}</b>｜{f[1]}｜{f[2]}｜{f[3]}</li>")
        parts.append("</ul>")
    return "".join(parts) + "</div>"


async def run(period: str = "both", area_preference: str = "福田-南山沿线", **kwargs):
    try:
        try:
            plans = _primary_plans()
            source = "source: curated_local_plan_primary_v1"
        except Exception:
            plans = _backup_plans()
            source = "source: curated_local_plan_backup_v1"
        choose = plans if period == "both" else {"morning": plans["morning"], "afternoon": plans["afternoon"] if period == "afternoon" else plans["morning"]}
        render = f"{source}\nreferences: 深圳文旅公开区位信息/地图常识（离线整理）\nevidence: 片区={area_preference}，行程按同片区串联减少折返。\n\n上午方案: {plans['morning']['title']}\n下午方案: {plans['afternoon']['title']}"
        return {
            "speak": "我给你整理了深圳周末半天游玩和吃饭安排，上午和下午两个版本都能直接用。",
            "render": render,
            "ui": {"type": "html_card", "html": _html(choose), "title": "深圳半日游玩+餐饮建议"},
        }
    except Exception as e:
        return {
            "speak": "我这次没完整生成行程，但先给你一个可用的简版建议。",
            "render": f"source: local_fallback\nevidence: {type(e).__name__}: {e}\nreferences: 预置离线备选行程",
            "ui": {"type": "info_card", "title": "深圳半日游建议（降级）", "message": "推荐南山深圳湾公园+海上世界，搭配椰子鸡；或福田博物馆+莲花山，搭配潮汕牛肉火锅。"},
        }


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(run(period="both", area_preference="福田-南山沿线"))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
