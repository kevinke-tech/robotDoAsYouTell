"""广州花都区实时天气（多源）一次性技能。"""
import asyncio
import datetime as dt
import httpx
from evidence_utils import build_render_evidence_block, attach_evidence_fields

RUN_SPEC = {"name": "guangzhou_huadu_weather_now_cn_oneshot", "description": "查询广州花都区实时天气并返回中文卡片。", "args_schema": {"type": "object", "properties": {}, "required": []}}

_WM = {0: "晴", 1: "晴", 2: "少云", 3: "多云", 45: "有雾", 48: "有雾", 51: "小毛毛雨", 53: "毛毛雨", 55: "浓毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨", 71: "小雪", 80: "阵雨", 95: "雷雨"}

def _wd(d):
    n = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    return n[int((float(d) % 360 + 22.5) // 45) % 8]

async def _wttr(c):
    u = "https://wttr.in/Guangzhou+Huadu?format=j1"
    try:
        r = await c.get(u, timeout=8.0); j = r.json() if r.status_code == 200 else {}
        cc = (j.get("current_condition") or [{}])[0]; d = (j.get("weather") or [{}])[0]
        if not cc: return {"ok": False, "source_url": u, "error": f"http_{r.status_code}"}
        return {"ok": True, "source": "wttr.in", "source_url": u, "cond": (((cc.get("weatherDesc") or [{}])[0]).get("value") or "未知"),
                "temp": cc.get("temp_C"), "feels": cc.get("FeelsLikeC"), "hum": cc.get("humidity"), "wind": cc.get("windspeedKmph"),
                "wdir": cc.get("winddir16Point"), "max": d.get("maxtempC"), "min": d.get("mintempC"), "obs": cc.get("localObsDateTime")}
    except Exception as e:
        return {"ok": False, "source": "wttr.in", "source_url": u, "error": f"{type(e).__name__}: {e}"}

async def _om(c):
    gu, lat, lon, note = "https://geocoding-api.open-meteo.com/v1/search?name=%E8%8A%B1%E9%83%BD%E5%8C%BA&count=1&language=zh&format=json", 23.39, 113.22, "固定坐标兜底"
    try:
        g = await c.get(gu, timeout=8.0); gj = g.json() if g.status_code == 200 else {}
        rr = gj.get("results") or []; 
        if rr: lat, lon, note = rr[0].get("latitude", lat), rr[0].get("longitude", lon), "地名归一化成功"
    except Exception:
        pass
    fu = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,wind_direction_10m,weather_code&daily=temperature_2m_max,temperature_2m_min&timezone=Asia%2FShanghai"
    try:
        r = await c.get(fu, timeout=8.0); j = r.json() if r.status_code == 200 else {}
        cur, d = j.get("current") or {}, j.get("daily") or {}
        if not cur: return {"ok": False, "source_url": fu, "error": f"http_{r.status_code}"}
        return {"ok": True, "source": "open-meteo", "source_url": fu, "cond": _WM.get(int(cur.get("weather_code", -1)), "未知"),
                "temp": cur.get("temperature_2m"), "feels": cur.get("apparent_temperature"), "hum": cur.get("relative_humidity_2m"),
                "wind": cur.get("wind_speed_10m"), "wdir": _wd(cur.get("wind_direction_10m", 0)), "max": (d.get("temperature_2m_max") or [None])[0],
                "min": (d.get("temperature_2m_min") or [None])[0], "obs": cur.get("time"), "loc_path": note}
    except Exception as e:
        return {"ok": False, "source": "open-meteo", "source_url": fu, "error": f"{type(e).__name__}: {e}", "loc_path": note}

async def run(**kwargs):
    if kwargs.get("_smoke"):
        return {"speak": "广州花都区天气卡片已就绪。", "render": "source: smoke\nreferences: []", "ui": {"type": "info_card", "title": "花都天气", "message": "结构检查通过"}}
    async with httpx.AsyncClient(headers={"Accept-Language": "zh-CN,zh;q=0.9"}) as c:
        a, b = await asyncio.gather(_wttr(c), _om(c))
    refs = [x for x in (a, b) if x.get("ok")]; fail = [x for x in (a, b) if not x.get("ok")]
    if not refs:
        ev = build_render_evidence_block(source="wttr.in/open-meteo", evidence={"errors": [f.get("error", "unknown") for f in fail]}, references=fail)
        return {"speak": "抱歉，我暂时没拿到花都实时天气。", "render": f"查询失败，请稍后重试。\n{ev}", "ui": {"type": "info_card", "title": "花都天气获取失败", "message": "两条数据源都不可用，请稍后再试。"}}
    p = refs[0]; t = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"花都现在{p.get('cond','未知')}，{p.get('temp','?')}度，体感{p.get('feels','?')}度，湿度{p.get('hum','?')}%，风向{p.get('wdir','?')}，风速{p.get('wind','?')}。"
    line = f"当前: {p.get('cond','未知')} | 温度: {p.get('temp','?')}°C | 体感: {p.get('feels','?')}°C | 湿度: {p.get('hum','?')}% | 风: {p.get('wdir','?')} {p.get('wind','?')} km/h | 今日: {p.get('min','?')}~{p.get('max','?')}°C"
    ev = build_render_evidence_block(source=p.get("source",""), source_url=p.get("source_url",""), evidence={"obs_time": p.get("obs"), "loc_path": p.get("loc_path","direct")}, references=refs + fail)
    ui = attach_evidence_fields({"type": "info_card", "title": "广州花都区实时天气", "message": f"{line}\n更新时间: {t}"}, source=p.get("source",""), source_url=p.get("source_url",""), references=refs + fail)
    return {"speak": "我查到花都区最新天气了。" + msg, "render": f"{line}\n更新时间: {t}\n{ev}", "ui": ui}

if __name__ == "__main__":
    r = asyncio.run(run(_smoke=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
