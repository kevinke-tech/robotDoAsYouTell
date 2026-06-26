"""广州市花都区天气：当前 + 未来三天（双源兜底）。"""
import json
import httpx
from evidence_utils import build_render_evidence_block, attach_evidence_fields

RUN_SPEC = {
    "name": "huadu_weather_now_3day_cn",
    "description": "查询广州花都区当前天气和未来2-3天预报。",
    "args_schema": {
        "type": "object",
        "properties": {"location": {"type": "string", "default": "广州市花都区"}, "mock": {"type": "boolean", "default": False}},
        "required": [],
    },
}

WCODE = {0: "晴", 1: "少云", 2: "多云", 3: "阴", 45: "雾", 51: "小毛雨", 61: "小雨", 63: "中雨", 65: "大雨", 80: "阵雨", 95: "雷雨"}

async def _wttr(city: str):
    u = f"https://wttr.in/{city}?format=j1"
    try:
        async with httpx.AsyncClient(timeout=6.0) as c:
            r = await c.get(u)
        if r.status_code != 200:
            return None, f"http_{r.status_code}", [u]
        d = r.json()
        cur = (d.get("current_condition") or [{}])[0]
        days = d.get("weather") or []
        f = [f"{x.get('date','')} {(x.get('hourly') or [{}])[0].get('weatherDesc',[{'value':'未知'}])[0].get('value','未知')} {x.get('maxtempC','?')}/{x.get('mintempC','?')}°C" for x in days[:3]]
        return {
            "now": f"{cur.get('temp_C','?')}°C，{(cur.get('weatherDesc') or [{'value':'未知'}])[0].get('value','未知')}，湿度{cur.get('humidity','?')}%，风速{cur.get('windspeedKmph','?')}km/h",
            "forecast": f,
            "source": "wttr.in",
            "urls": [u],
            "evidence": {"observation_time": cur.get("observation_time"), "nearest_area": d.get("nearest_area", [])[:1]},
        }, "", [u]
    except Exception as e:
        return None, f"{type(e).__name__}: {e}", [u]

async def _open_meteo():
    geo = "https://geocoding-api.open-meteo.com/v1/search?name=Huadu%20District,Guangzhou&count=1&language=zh&format=json"
    lat, lon, refs = 23.392, 113.298, [geo]
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            rg = await c.get(geo)
        g = rg.json() if rg.status_code == 200 else {}
        one = (g.get("results") or [{}])[0]
        lat, lon = float(one.get("latitude", lat)), float(one.get("longitude", lon))
    except Exception:
        pass
    u = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code&daily=weather_code,temperature_2m_max,temperature_2m_min&timezone=Asia%2FShanghai&forecast_days=3"
    refs.append(u)
    try:
        async with httpx.AsyncClient(timeout=6.0) as c:
            r = await c.get(u)
        if r.status_code != 200:
            return None, f"http_{r.status_code}", refs
        d = r.json()
        cur, daily = d.get("current", {}), d.get("daily", {})
        t, code, tmax, tmin = daily.get("time", []), daily.get("weather_code", []), daily.get("temperature_2m_max", []), daily.get("temperature_2m_min", [])
        f = [f"{t[i]} {WCODE.get(int(code[i]), '未知')} {tmax[i]}/{tmin[i]}°C" for i in range(min(3, len(t), len(code), len(tmax), len(tmin)))]
        return {
            "now": f"{cur.get('temperature_2m','?')}°C，{WCODE.get(int(cur.get('weather_code',-1)),'未知')}，湿度{cur.get('relative_humidity_2m','?')}%，风速{cur.get('wind_speed_10m','?')}km/h",
            "forecast": f,
            "source": "open-meteo",
            "urls": refs,
            "evidence": {"lat": lat, "lon": lon, "current_time": cur.get("time")},
        }, "", refs
    except Exception as e:
        return None, f"{type(e).__name__}: {e}", refs

async def run(location: str = "广州市花都区", mock: bool = False, **kwargs):
    if mock:
        return {"speak": "花都区当前26度，多云，未来三天有阵雨。", "render": "source: mock\nevidence: 离线冒烟测试", "ui": {"type": "info_card", "title": "花都天气(测试)", "message": "当前26°C，多云；未来三天：阵雨/多云/小雨", "source": "mock"}}
    w, we, wr = await _wttr("Huadu,Guangzhou")
    o, oe, orf = (None, "", [])
    if not w:
        o, oe, orf = await _open_meteo()
    r = w or o
    if not r:
        refs = wr + orf
        msg = f"暂时没查到花都区天气。wttr错误: {we or '未知'}；open-meteo错误: {oe or '未知'}"
        ev = build_render_evidence_block(source="wttr.in/open-meteo", evidence={"wttr_error": we, "open_meteo_error": oe}, references=refs)
        return {"speak": "天气服务暂时不可用，请稍后再试。", "render": f"{msg}\n{ev}", "ui": attach_evidence_fields({"type": "info_card", "title": "花都天气获取失败", "message": msg}, source="wttr.in/open-meteo", evidence={"wttr_error": we, "open_meteo_error": oe}, references=refs)}
    brief = f"{location} 当前：{r['now']}；未来三天：{'；'.join(r['forecast'])}"
    ev = build_render_evidence_block(source=r["source"], source_url=r["urls"][0], evidence=r["evidence"], references=r["urls"])
    return {"speak": f"已查到{location}天气。现在{r['now']}。", "render": f"{brief}\n{ev}", "ui": attach_evidence_fields({"type": "info_card", "title": "广州市花都区天气", "message": brief, "source_url": r["urls"][0]}, source=r["source"], evidence=r["evidence"], references=r["urls"])}

if __name__ == "__main__":
    import asyncio
    out = asyncio.run(run(mock=True))
    assert isinstance(out, dict) and "speak" in out and "render" in out
    print("OK")
