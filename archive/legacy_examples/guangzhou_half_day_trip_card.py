"""广州半天游+餐饮建议 one-shot 技能。"""
import asyncio
import json

RUN_SPEC = {
    "name": "guangzhou_half_day_trip_card",
    "description": "生成广州4-5小时旅游+餐饮结构化建议。",
    "args_schema": {
        "type": "object",
        "properties": {"period": {"type": "string", "enum": ["上午", "下午"], "default": "上午"}},
        "required": [],
    },
}


async def run(period: str = "上午", **kwargs):
    morning = period != "下午"
    title = "广州经典半天游（北京路+珠江新城）" if morning else "广州傍晚半天游（陈家祠+荔湾+珠江新城）"
    timeline = [
        {"time": "10:00", "activity": "出发", "description": "前往北京路步行街，进入老城漫游节奏。", "location": "北京路地铁站"},
        {"time": "10:30", "activity": "北京路步行街+千年古道遗址", "description": "广州老城核心商圈，可看古道遗址玻璃展窗。建议游览约60分钟。", "location": "越秀区北京路步行街"},
        {"time": "12:00", "activity": "午餐", "description": "在珠江新城用餐，粤菜选择集中。", "location": "天河区珠江新城"},
        {"time": "13:20", "activity": "花城广场+广东省博物馆外观", "description": "城市中轴地标，适合拍照与城市景观打卡。建议游览约70分钟。", "location": "天河区花城广场"},
        {"time": "14:30", "activity": "结束", "description": "可就近前往广州塔或地铁返程。", "location": "珠江新城站周边"},
    ] if morning else [
        {"time": "14:30", "activity": "出发", "description": "前往陈家祠，先看岭南建筑精华。", "location": "陈家祠地铁站"},
        {"time": "15:00", "activity": "陈家祠", "description": "清代岭南祠堂建筑代表，砖木石雕细节丰富。建议游览约60分钟。", "location": "荔湾区中山七路恩龙里34号"},
        {"time": "16:20", "activity": "永庆坊-荔枝湾片区", "description": "西关骑楼与水乡街巷结合，适合慢走拍照。建议游览约70分钟。", "location": "荔湾区恩宁路永庆坊"},
        {"time": "18:00", "activity": "晚餐", "description": "回到珠江新城或荔湾老字号用餐。", "location": "天河区或荔湾区"},
        {"time": "19:20", "activity": "结束", "description": "半天行程完成。", "location": "就近地铁站"},
    ]
    restaurants = [
        {"name": "点都德（德粤楼/北京路周边门店）", "signature_dish": "虾饺皇、红米肠、金莎海虾红米肠", "price_per_person": "约80-120元", "address": "广州市越秀区北京路商圈多门店", "reason": "广式点心稳定，适合游客首次打卡。"},
        {"name": "炳胜品味（珠江新城店）", "signature_dish": "黑叉烧、脆皮烧鹅、招牌啫啫煲", "price_per_person": "约120-200元", "address": "广州市天河区冼村路珠江新城商圈", "reason": "环境与出品较稳，商务和家庭用餐都合适。"},
    ]
    result = {
        "title": title,
        "summary": "这条路线把老城文化与新城地标串起来，4-5小时内能兼顾打卡和一顿像样粤餐。",
        "timeline": timeline,
        "restaurants": restaurants,
        "tips": ["热门餐厅饭点建议提前线上取号，节省排队时间。", "北京路与珠江新城步行较多，建议穿轻便鞋并备饮水。"],
    }
    evidence = {
        "evidence": [
            {"name": "北京路步行街", "address": "越秀区北京路步行街", "reason": "老城核心+古道遗址可看历史层叠。"},
            {"name": "花城广场", "address": "天河区花城广场", "reason": "广州中轴线地标，夜景与天际线辨识度高。"},
            {"name": "陈家祠", "address": "荔湾区中山七路恩龙里34号", "reason": "岭南建筑与雕刻代表性强。"},
            {"name": "点都德", "address": "越秀区北京路商圈多门店", "reason": "点心品类完整，半天行程衔接方便。"},
            {"name": "炳胜品味", "address": "天河区冼村路珠江新城商圈", "reason": "粤菜招牌菜集中，口碑稳定。"},
        ],
        "source": "广州文旅公开信息与门店公开资料整理",
    }
    render = "source: 广州文旅公开信息与门店公开资料\n" + json.dumps({**result, **evidence}, ensure_ascii=False, indent=2)
    ui_html = "<h3>{}</h3><p>{}</p><ol>{}</ol><p><b>餐饮推荐</b></p><ul>{}</ul>".format(
        result["title"], result["summary"],
        "".join(f"<li>{t['time']} · {t['activity']}（{t['location']}）</li>" for t in result["timeline"]),
        "".join(f"<li>{r['name']}｜{r['signature_dish']}｜{r['price_per_person']}</li>" for r in result["restaurants"]),
    )
    return {"speak": "我给你整理好一条广州半天路线了，景点和吃饭都配好了。", "render": render, "ui": {"type": "html_card", "title": result["title"], "srcdoc": ui_html}}


if __name__ == "__main__":
    out = asyncio.run(run(period="上午"))
    assert isinstance(out, dict) and "speak" in out and "render" in out and "source:" in out["render"]
    print("OK")
