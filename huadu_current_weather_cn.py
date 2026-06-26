"""查询中国广州市花都区当前天气（主备双源）。"""
import httpx
from evidence_utils import build_render_evidence_block, attach_evidence_fields

RUN_SPEC = {
    "name": "huadu_current_weather_cn",
    "description": "查询广州市花都区当前天气与今日日间预报。",
    "args_schema": {
        "type": "object",
        "properties": {"location": {"type": "string", "default": "广州市花都区"}, "mock": {"type": "boolean", "default": False}},
        "required": [],
    },
}


def _fmt(city, t, d, h, w, hi, lo):
    return f"{city}现在{d}，{t}°C，湿度{h}%，风{w} km/h。今天最高{hi}°C，最低{lo}°C。"


async def run(location: str = "广州市花都区", mock: bool = False, **kwargs):
    city = (location or "广州市花都区").strip()
    if mock:
        msg = _fmt(city, "28", "多云", "78", "12 东南", "31", "26")
        return {"speak": "花都区现在多云，体感还行。", "render": "source: mock\nsource_url: local://mock\nevidence: {\"mode\":\"smoke\"}\n" + msg, "ui": {"type": "info_card", "title": "花都区当前天气", "message": msg, "source_url": "local://mock"}}
    refs, url_a = [], f"https://wttr.in/{city}?format=j1&lang=zh"
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            ra = await c.get(url_a)
            da = ra.json() if ra.status_code == 200 else {}
        cur, today = (da.get("current_condition") or [{}])[0], (da.get("weather") or [{}])[0]
        t, d = str(cur.get("temp_C", "")), str((cur.get("lang_zh") or [{}])[0].get("value") or cur.get("weatherDesc", [{}])[0].get("value", ""))
        h, ws, wd = str(cur.get("humidity", "")), str(cur.get("windspeedKmph", "")), str(cur.get("winddir16Point", ""))
        hi, lo = str(today.get("maxtempC", "")), str(today.get("mintempC", ""))
        if t and d:
            msg = _fmt(city, t, d, h or "-", (ws + " " + wd).strip(), hi or "-", lo or "-")
            ev = {"path": "primary_wttr", "city": city, "key_fields": {"temp_C": t, "desc": d, "humidity": h, "wind_kmph": ws, "wind_dir": wd, "maxC": hi, "minC": lo}}
            render = build_render_evidence_block(source="wttr.in", source_url=url_a, evidence=ev, references=refs, extra_lines=[msg])
            ui = attach_evidence_fields({"type": "info_card", "title": "花都区当前天气", "message": msg, "source_url": url_a}, source="wttr.in", source_url=url_a, evidence=ev, references=refs)
            return {"speak": f"花都区现在{d}，{t}度。", "render": render, "ui": ui}
        refs.append({"source": "wttr.in", "source_url": url_a, "status": "empty_fields"})
    except Exception as e:
        refs.append({"source": "wttr.in", "source_url": url_a, "error": f"{type(e).__name__}: {e}"})
    geo_url = "https://geocoding-api.open-meteo.com/v1/search?name=Huadu,Guangzhou&country=CN&language=zh&count=1"
    lat, lon, geo_way = 23.39, 113.22, "fallback_coords"
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            rg = await c.get(geo_url)
            g = rg.json() if rg.status_code == 200 else {}
        r0 = (g.get("results") or [{}])[0]
        if r0.get("latitude") and r0.get("longitude"):
            lat, lon, geo_way = float(r0["latitude"]), float(r0["longitude"]), "geo_normalized"
    except Exception as e:
        refs.append({"source": "open-meteo-geocoding", "source_url": geo_url, "error": f"{type(e).__name__}: {e}"})
    url_b = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weather_code&daily=temperature_2m_max,temperature_2m_min&timezone=Asia%2FShanghai"
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            rb = await c.get(url_b)
            db = rb.json() if rb.status_code == 200 else {}
        cur, day = db.get("current", {}), db.get("daily", {})
        t, h, ws, wd = cur.get("temperature_2m"), cur.get("relative_humidity_2m"), cur.get("wind_speed_10m"), cur.get("wind_direction_10m")
        hi, lo, code = (day.get("temperature_2m_max") or [None])[0], (day.get("temperature_2m_min") or [None])[0], int(cur.get("weather_code", -1))
        desc = {0: "晴", 1: "大部晴", 2: "多云", 3: "阴", 45: "雾", 51: "小雨", 61: "雨", 63: "中雨", 65: "大雨", 80: "阵雨", 95: "雷雨"}.get(code, f"天气码{code}")
        if t is not None:
            msg = _fmt(city, str(t), desc, str(h or "-"), f"{ws or '-'} {wd or '-'}°", str(hi or "-"), str(lo or "-"))
            ev = {"path": "backup_open_meteo", "geo": geo_way, "lat": lat, "lon": lon, "key_fields": {"temperature_2m": t, "humidity": h, "wind_speed_10m": ws, "wind_direction_10m": wd, "weather_code": code, "maxC": hi, "minC": lo}}
            render = build_render_evidence_block(source="open-meteo", source_url=url_b, evidence=ev, references=refs, extra_lines=[msg])
            ui = attach_evidence_fields({"type": "info_card", "title": "花都区当前天气", "message": msg, "source_url": url_b}, source="open-meteo", source_url=url_b, evidence=ev, references=refs)
            return {"speak": f"花都区现在{desc}，{t}度。", "render": render, "ui": ui}
    except Exception as e:
        refs.append({"source": "open-meteo", "source_url": url_b, "error": f"{type(e).__name__}: {e}"})
    msg = "天气服务暂时不可用，我已经尝试主备数据源。"
    render = build_render_evidence_block(source="weather_fallback", source_url=url_a, evidence={"reason": "all_sources_failed", "location": city}, references=refs, extra_lines=[msg])
    return {"speak": "抱歉，我暂时没查到花都区天气。", "render": render, "ui": {"type": "info_card", "title": "天气查询失败", "message": msg, "source_url": url_a, "references": refs}}


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(run(mock=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
