"""查询广州花都区当前天气与未来简报（one-shot）。"""
import asyncio
import httpx
from evidence_utils import attach_evidence_fields, build_render_evidence_block

RUN_SPEC = {"name": "guangzhou_huadu_weather_brief_cn", "description": "查询广州花都当前天气和未来2-3天预报。", "args_schema": {"type": "object", "properties": {"location": {"type": "string", "default": "广州市花都区"}, "days": {"type": "integer", "minimum": 2, "maximum": 3, "default": 3}}, "required": []}}
WC = {0: "晴", 1: "多云", 2: "多云", 3: "阴", 45: "雾", 61: "小雨", 63: "中雨", 65: "大雨", 80: "阵雨"}

def _w(code): return WC.get(int(code or -1), "未知")

async def _open_meteo(days, location):
    refs, coords, labels = [], None, [location, "广州市花都区", "Huadu Guangzhou"]
    try:
        async with httpx.AsyncClient(timeout=6.0) as c:
            for q in labels:
                u = f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=3&language=zh&format=json"
                refs.append({"source_url": u, "stage": "geocode"}); r = await c.get(u); arr = (r.json() or {}).get("results") or []
                hit = next((x for x in arr if str(x.get("country_code")) == "CN"), arr[0] if arr else None)
                if hit: coords = (hit.get("latitude"), hit.get("longitude")); break
            coords = coords if coords and all(coords) else (23.3895, 113.2209)
            fu = "https://api.open-meteo.com/v1/forecast"
            p = {"latitude": coords[0], "longitude": coords[1], "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m", "daily": "weather_code,temperature_2m_max,temperature_2m_min", "forecast_days": days + 1, "timezone": "Asia/Shanghai"}
            refs.append({"source_url": fu, "stage": "forecast"}); d = (await c.get(fu, params=p)).json() or {}
        cur, dy = d.get("current") or {}, d.get("daily") or {}
        out = [{"date": t, "weather": _w(c), "temp": f"{lo}~{hi}°C"} for t, c, hi, lo in zip((dy.get("time") or [])[1:days+1], (dy.get("weather_code") or [])[1:days+1], (dy.get("temperature_2m_max") or [])[1:days+1], (dy.get("temperature_2m_min") or [])[1:days+1])]
        return {"source": "open-meteo.com", "source_url": fu, "temp": f"{cur.get('temperature_2m','?')}°C", "weather": _w(cur.get("weather_code")), "humidity": f"{cur.get('relative_humidity_2m','?')}%", "wind": f"{cur.get('wind_speed_10m','?')} km/h", "forecast": out, "references": refs}
    except Exception as e:
        return {"error": f"open-meteo失败: {e}", "references": refs}

async def _wttr(days):
    u = "https://wttr.in/Guangzhou?format=j1"; refs = [{"source_url": u, "stage": "fallback"}]
    try:
        async with httpx.AsyncClient(timeout=6.0) as c: d = (await c.get(u)).json() or {}
        cc = (d.get("current_condition") or [{}])[0]
        out = [{"date": x.get("date", "?"), "weather": ((x.get("hourly") or [{}])[0].get("weatherDesc") or [{"value": "未知"}])[0].get("value"), "temp": f"{x.get('mintempC','?')}~{x.get('maxtempC','?')}°C"} for x in (d.get("weather") or [])[1:days+1]]
        return {"source": "wttr.in", "source_url": u, "temp": f"{cc.get('temp_C','?')}°C", "weather": ((cc.get("weatherDesc") or [{"value": "未知"}])[0].get("value")), "humidity": f"{cc.get('humidity','?')}%", "wind": f"{cc.get('windspeedKmph','?')} km/h", "forecast": out, "references": refs}
    except Exception as e:
        return {"error": f"wttr失败: {e}", "references": refs}

async def run(location="广州市花都区", days=3, **kwargs):
    try:
        d = kwargs.get("_mock_data") or await _open_meteo(int(days), location)
        if not kwargs.get("_mock_data") and d.get("error"): d = await _wttr(int(days))
        if d.get("error"):
            rs = d.get("references") or []
            return {"speak": "我暂时没拿到花都天气，稍后再试。", "render": "天气查询失败。\n" + build_render_evidence_block(source="weather_api", evidence=d.get("error"), references=rs), "ui": attach_evidence_fields({"type": "info_card", "title": "花都天气获取失败", "message": str(d.get("error"))}, source="weather_api", evidence=d.get("error"), references=rs)}
        lines = [f"{x['date']} {x['weather']} {x['temp']}" for x in d.get("forecast") or []]
        msg = f"现在{d['temp']}，{d['weather']}，湿度{d['humidity']}，风速{d['wind']}。未来预报：" + "；".join(lines)
        ev = build_render_evidence_block(source=d["source"], source_url=d["source_url"], evidence={"location": location, "current": {"temp": d["temp"], "weather": d["weather"], "humidity": d["humidity"], "wind": d["wind"]}}, references=d.get("references"))
        return {"speak": f"花都区当前{d['temp']}，{d['weather']}。", "render": f"广州市花都区天气\n{msg}\n{ev}", "ui": attach_evidence_fields({"type": "info_card", "title": "花都区天气", "message": msg}, source=d["source"], source_url=d["source_url"], evidence={"current_temp": d["temp"], "forecast_days": len(lines)}, references=d.get("references"))}
    except Exception as e:
        return {"speak": "天气服务暂时不可用。", "render": "技能降级返回。\n" + build_render_evidence_block(source="skill_runtime", evidence=str(e)), "ui": {"type": "info_card", "title": "花都天气", "message": f"查询失败：{e}", "source": "skill_runtime", "evidence": str(e)}}

if __name__ == "__main__":
    mock = {"source": "mock", "source_url": "https://mock.local/weather", "temp": "30°C", "weather": "多云", "humidity": "70%", "wind": "10 km/h", "forecast": [{"date": "2026-06-19", "weather": "阵雨", "temp": "27~33°C"}, {"date": "2026-06-20", "weather": "多云", "temp": "28~34°C"}], "references": [{"source_url": "https://mock.local/weather"}]}
    r = asyncio.run(run(_mock_data=mock))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
