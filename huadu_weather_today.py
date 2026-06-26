"""查询广州市花都区今日天气（多数据源）。"""
import asyncio
from datetime import datetime
import httpx

RUN_SPEC = {
    "name": "huadu_weather_today",
    "description": "查询广州花都区今天的天气并返回证据。",
    "args_schema": {
        "type": "object",
        "properties": {
            "location": {"type": "string", "default": "广州市花都区"},
            "use_mock": {"type": "boolean", "default": False},
        },
        "required": [],
    },
}

WMO = {0: "晴", 1: "基本晴", 2: "多云", 3: "阴", 45: "有雾", 51: "毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨", 71: "小雪", 95: "雷雨"}

def _wind_dir(deg):
    arr = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    return arr[int(((deg or 0) + 22.5) // 45) % 8]

async def run(location: str = "广州市花都区", use_mock: bool = False, **kwargs):
    src_om = "https://api.open-meteo.com/v1/forecast"
    src_wttr = "https://wttr.in"
    geo_src = "https://geocoding-api.open-meteo.com/v1/search"
    lat, lon, norm = 23.39, 113.22, location
    om = wt = {}
    if use_mock:
        om = {"current": {"temperature_2m": 30, "relative_humidity_2m": 70, "wind_speed_10m": 12, "wind_direction_10m": 135, "weather_code": 2}, "daily": {"temperature_2m_max": [33], "temperature_2m_min": [27]}}
        wt = {"current_condition": [{"weatherDesc": [{"value": "多云"}]}], "weather": [{"maxtempC": "32", "mintempC": "26"}]}
    else:
        try:
            async with httpx.AsyncClient(timeout=6.0) as c:
                try:
                    g = await c.get(geo_src, params={"name": location, "count": 1, "language": "zh", "format": "json"})
                    rr = (g.json() or {}).get("results") or []
                    if rr:
                        lat, lon = float(rr[0].get("latitude", lat)), float(rr[0].get("longitude", lon))
                        norm = rr[0].get("name") or norm
                except Exception:
                    pass
                try:
                    r1 = await c.get(src_om, params={"latitude": lat, "longitude": lon, "timezone": "Asia/Shanghai", "forecast_days": 1, "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weather_code", "daily": "temperature_2m_max,temperature_2m_min"})
                    om = r1.json() if r1.status_code == 200 else {}
                except Exception:
                    om = {}
                try:
                    r2 = await c.get(f"{src_wttr}/{location}", params={"format": "j1"})
                    wt = r2.json() if r2.status_code == 200 else {}
                except Exception:
                    wt = {}
        except Exception:
            om, wt = {}, {}
    cur = om.get("current") or {}
    daily = om.get("daily") or {}
    wcur = (wt.get("current_condition") or [{}])[0]
    wday = (wt.get("weather") or [{}])[0]
    cond = WMO.get(cur.get("weather_code"), (((wcur.get("weatherDesc") or [{}])[0]).get("value") or "未知"))
    t = cur.get("temperature_2m") if cur.get("temperature_2m") is not None else wcur.get("temp_C")
    tmax = (daily.get("temperature_2m_max") or [wday.get("maxtempC")])[0]
    tmin = (daily.get("temperature_2m_min") or [wday.get("mintempC")])[0]
    hum = cur.get("relative_humidity_2m") if cur.get("relative_humidity_2m") is not None else wcur.get("humidity")
    ws = cur.get("wind_speed_10m") if cur.get("wind_speed_10m") is not None else wcur.get("windspeedKmph")
    wd = _wind_dir(cur.get("wind_direction_10m")) if cur.get("wind_direction_10m") is not None else (wcur.get("winddir16Point") or "未知")
    if t is None and tmax is None and tmin is None:
        return {"speak": "我暂时没查到花都区天气，稍后再试试。", "render": f"查询失败\nsource_url: {src_om}, {src_wttr}\nevidence: geocode_fallback=({lat},{lon}), time={datetime.now().isoformat(timespec='minutes')}", "ui": {"type": "info_card", "title": "花都区天气查询失败", "message": "两个数据源均未返回可用天气字段。", "references": [src_om, src_wttr]}}
    overview = f"今天{cond}，当前约{t}度，最高{tmax}度，最低{tmin}度。"
    render = (
        f"地点: 广州·花都区（归一化: {norm}, 坐标: {lat:.2f},{lon:.2f}）\n"
        f"天气: {cond}\n当前温度: {t}°C\n最高/最低: {tmax}°C / {tmin}°C\n湿度: {hum}%\n风: {wd}风 {ws} km/h\n"
        f"今日概述: {overview}\nsource_url: {src_om}; {src_wttr}; {geo_src}\n"
        f"evidence: now={cur or wcur}, daily_maxmin={daily.get('temperature_2m_max')},{daily.get('temperature_2m_min')}, fetch_time={datetime.now().isoformat(timespec='minutes')}"
    )
    return {"speak": f"花都区今天{cond}，气温大概在{tmin}到{tmax}度。", "render": render, "ui": {"type": "info_card", "title": "广州花都区今日天气", "message": f"{overview} 湿度{hum}%，{wd}风{ws}公里每小时。", "references": [src_om, src_wttr, geo_src]}}

if __name__ == "__main__":
    x = asyncio.run(run(use_mock=True))
    assert isinstance(x, dict) and "speak" in x and "render" in x and "ui" in x
    print("OK")
