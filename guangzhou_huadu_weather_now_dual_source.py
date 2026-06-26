"""广州花都当前天气（主备双源）one-shot skill。"""
import asyncio
from typing import Optional

import httpx

RUN_SPEC = {
    "name": "guangzhou_huadu_weather_now_dual_source",
    "description": "查询广州花都区当前天气与今日高低温（主备双源）。",
    "args_schema": {
        "type": "object",
        "properties": {"city": {"type": "string", "default": "广州"}, "district": {"type": "string", "default": "花都区"}},
        "required": [],
    },
}


async def _from_wttr(city: str, district: str) -> tuple[Optional[dict], str]:
    url = f"https://wttr.in/{city}{district}"
    try:
        async with httpx.AsyncClient(timeout=6.0) as c:
            r = await c.get(url, params={"format": "j1", "lang": "zh"})
        d = r.json() if r.status_code == 200 else {}
        cc, w = (d.get("current_condition") or [{}])[0], (d.get("weather") or [{}])[0]
        if not cc:
            return None, f"wttr状态异常:{r.status_code}"
        cond = (((cc.get("lang_zh") or [{}])[0]).get("value") or ((cc.get("weatherDesc") or [{}])[0]).get("value") or "未知").strip()
        return {
            "temp": cc.get("temp_C"),
            "feel": cc.get("FeelsLikeC"),
            "cond": cond,
            "hum": cc.get("humidity"),
            "wind": cc.get("windspeedKmph"),
            "wind_dir": cc.get("winddir16Point"),
            "tmax": w.get("maxtempC"),
            "tmin": w.get("mintempC"),
            "time": cc.get("localObsDateTime") or cc.get("observation_time"),
            "source": "wttr.in",
            "source_url": "https://wttr.in",
            "references": ["current_condition.temp_C", "current_condition.FeelsLikeC", "weather.maxtempC", "weather.mintempC"],
        }, ""
    except Exception as e:
        return None, f"wttr异常:{type(e).__name__}:{e}"


def _wmo_cn(code: int) -> str:
    m = {0: "晴", 1: "大部晴", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇", 51: "小毛雨", 61: "小雨", 63: "中雨", 65: "大雨", 71: "小雪", 80: "阵雨", 95: "雷暴"}
    return m.get(code, f"天气代码{code}")


async def _from_open_meteo(city: str, district: str) -> tuple[Optional[dict], str]:
    g_url, w_url = "https://geocoding-api.open-meteo.com/v1/search", "https://api.open-meteo.com/v1/forecast"
    lat, lon, geo_note = 23.392, 113.220, "坐标兜底(花都区)"
    try:
        async with httpx.AsyncClient(timeout=6.0) as c:
            g = await c.get(g_url, params={"name": f"{city}{district}", "count": 1, "language": "zh", "format": "json"})
            gd = g.json() if g.status_code == 200 else {}
            r0 = (gd.get("results") or [{}])[0]
            if r0.get("latitude") and r0.get("longitude"):
                lat, lon, geo_note = r0["latitude"], r0["longitude"], f"地名归一化:{r0.get('name','')},{r0.get('admin1','')}"
            w = await c.get(w_url, params={"latitude": lat, "longitude": lon, "timezone": "Asia/Shanghai", "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weather_code", "daily": "temperature_2m_max,temperature_2m_min", "forecast_days": 1})
        d = w.json() if w.status_code == 200 else {}
        cur, daily = d.get("current") or {}, d.get("daily") or {}
        if not cur:
            return None, f"open-meteo状态异常:{w.status_code}"
        return {
            "temp": cur.get("temperature_2m"), "feel": cur.get("apparent_temperature"), "cond": _wmo_cn(int(cur.get("weather_code", -1))),
            "hum": cur.get("relative_humidity_2m"), "wind": cur.get("wind_speed_10m"), "wind_dir": cur.get("wind_direction_10m"),
            "tmax": (daily.get("temperature_2m_max") or [None])[0], "tmin": (daily.get("temperature_2m_min") or [None])[0], "time": cur.get("time"),
            "source": f"open-meteo({geo_note})", "source_url": w_url,
            "references": ["current.temperature_2m", "current.apparent_temperature", "daily.temperature_2m_max", "daily.temperature_2m_min"],
        }, ""
    except Exception as e:
        return None, f"open-meteo异常:{type(e).__name__}:{e}"


async def run(city: str = "广州", district: str = "花都区", **kwargs):
    wx = kwargs.get("_mock")
    if not isinstance(wx, dict):
        wx, e1 = await _from_wttr(city, district)
        if not wx:
            wx, e2 = await _from_open_meteo(city, district)
    if not isinstance(wx, dict):
        return {"speak": "我暂时没查到花都区实时天气，你稍后再试。", "render": f"source: wttr.in/open-meteo\nsource_url: https://wttr.in | https://api.open-meteo.com\nevidence: {e1}; {e2}", "ui": {"type": "info_card", "title": "花都天气获取失败", "message": f"主备源都失败：{e1}; {e2}"}}
    msg = f"{city}{district}现在{wx['cond']}，{wx['temp']}度，体感{wx['feel']}度。"
    render = f"source: {wx['source']}\nsource_url: {wx['source_url']}\n当前温度: {wx['temp']}°C\n体感温度: {wx['feel']}°C\n天气状况: {wx['cond']}\n湿度: {wx['hum']}%\n风速风向: {wx['wind']} km/h, {wx['wind_dir']}\n今日最高/最低: {wx['tmax']}°C / {wx['tmin']}°C\n观测时间: {wx['time']}\nreferences: {wx['references']}"
    return {"speak": msg, "render": render, "ui": {"type": "info_card", "title": f"{city}{district}当前天气", "message": f"{wx['cond']} | {wx['temp']}°C(体感{wx['feel']}°C)\n湿度{wx['hum']}% | 风{wx['wind']} km/h {wx['wind_dir']}\n今日 {wx['tmin']}~{wx['tmax']}°C", "source_url": wx["source_url"]}}


if __name__ == "__main__":
    fake = {"temp": 30, "feel": 34, "cond": "多云", "hum": 76, "wind": 12, "wind_dir": "东北", "tmax": 33, "tmin": 27, "time": "2026-06-18T16:00", "source": "mock", "source_url": "local", "references": ["mock"]}
    r = asyncio.run(run(_mock=fake))
    assert isinstance(r, dict) and "speak" in r and "render" in r and isinstance(r.get("ui"), dict)
    print("OK")
