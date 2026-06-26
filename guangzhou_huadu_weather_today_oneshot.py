"""广州花都区今日天气 one-shot skill。"""
import asyncio
import httpx

RUN_SPEC = {
    "name": "guangzhou_huadu_weather_today_oneshot",
    "description": "查询广州市花都区今日天气并返回中文卡片。",
    "args_schema": {
        "type": "object",
        "properties": {"location": {"type": "string", "default": "广州市花都区"}, "use_mock": {"type": "boolean", "default": False}},
        "required": [],
    },
}

def _norm_location(location: str) -> str:
    t = (location or "").strip().lower()
    return "广州市花都区" if (not t or "花都" in t or "huadu" in t) else location.strip()

def _wind_dir(deg):
    dirs = ["北", "东北", "东", "东南", "南", "西南", "西", "西北", "北"]
    return dirs[int((float(deg) % 360) / 45 + 0.5)]

async def _fetch_wttr(loc: str):
    url = f"https://wttr.in/{loc}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(url, params={"format": "j1", "lang": "zh"})
            d = r.json() if r.status_code == 200 else {}
        cur, day = (d.get("current_condition") or [{}])[0], (d.get("weather") or [{}])[0]
        cond = ((cur.get("lang_zh") or [{}])[0].get("value") or (cur.get("weatherDesc") or [{}])[0].get("value") or "").strip()
        if not cur:
            return None, {"source": "wttr.in", "source_url": url, "error": "empty_data"}
        data = {"condition": cond or "未知", "temp": cur.get("temp_C"), "temp_max": day.get("maxtempC"), "temp_min": day.get("mintempC"),
                "humidity": cur.get("humidity"), "wind_speed": cur.get("windspeedKmph"), "wind_dir": cur.get("winddir16Point"),
                "feels_like": cur.get("FeelsLikeC")}
        return data, {"source": "wttr.in", "source_url": "https://wttr.in/?format=j1", "evidence": {"location": loc, "obs": cur.get("observation_time"), "condition": data["condition"]}}
    except Exception as e:
        return None, {"source": "wttr.in", "source_url": url, "error": str(e)}

async def _fetch_open_meteo(loc: str):
    lat, lon, url = 23.392, 113.211, "https://api.open-meteo.com/v1/forecast"
    p = {"latitude": lat, "longitude": lon, "timezone": "Asia/Shanghai", "forecast_days": 1,
         "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,wind_direction_10m,weather_code",
         "daily": "temperature_2m_max,temperature_2m_min"}
    txt = {0: "晴", 1: "多云", 2: "多云", 3: "阴", 45: "雾", 51: "小雨", 61: "小雨", 63: "中雨", 65: "大雨", 80: "阵雨", 95: "雷雨"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(url, params=p)
            d = r.json() if r.status_code == 200 else {}
        cur, day = d.get("current", {}), d.get("daily", {})
        if not cur:
            return None, {"source": "open-meteo", "source_url": url, "error": "empty_data", "references": ["coords_fallback:23.392,113.211"]}
        data = {"condition": txt.get(cur.get("weather_code"), "未知"), "temp": cur.get("temperature_2m"),
                "temp_max": (day.get("temperature_2m_max") or [None])[0], "temp_min": (day.get("temperature_2m_min") or [None])[0],
                "humidity": cur.get("relative_humidity_2m"), "wind_speed": cur.get("wind_speed_10m"),
                "wind_dir": _wind_dir(cur.get("wind_direction_10m", 0)), "feels_like": cur.get("apparent_temperature")}
        return data, {"source": "open-meteo", "source_url": url, "evidence": {"location": loc, "lat": lat, "lon": lon, "time": cur.get("time")}, "references": ["coords_fallback:23.392,113.211"]}
    except Exception as e:
        return None, {"source": "open-meteo", "source_url": url, "error": str(e), "references": ["coords_fallback:23.392,113.211"]}

async def run(location: str = "广州市花都区", use_mock: bool = False, **kwargs):
    try:
        loc = _norm_location(location)
        data, meta = ({"condition": "多云", "temp": 29, "temp_max": 32, "temp_min": 26, "humidity": 78, "wind_speed": 12, "wind_dir": "东南", "feels_like": 33},
                      {"source": "mock", "source_url": "local://mock", "evidence": {"smoke_test": True}}) if use_mock else await _fetch_wttr(loc)
        if not data and not use_mock:
            data, meta = await _fetch_open_meteo(loc)
        if not data:
            return {"speak": "我现在没拿到花都天气数据，稍后我再帮你查。", "render": f"查询失败\nsource: {meta.get('source')}\nsource_url: {meta.get('source_url')}\nevidence: {meta}",
                    "ui": {"type": "info_card", "title": "花都区天气查询失败", "message": "暂时无法获取天气数据，请稍后重试。", "source_url": meta.get("source_url")}}
        c, t = str(data["condition"]), float(data["temp"])
        adv = "今天出门记得带伞。" if "雨" in c else ("天气偏热，注意补水防晒。" if t >= 32 else "体感舒适，外出可带件薄外套。")
        msg = f"{loc}现在{c}，{data['temp']}°C，最高/最低{data['temp_max']}/{data['temp_min']}°C，湿度{data['humidity']}%，{data['wind_dir']}风{data['wind_speed']}km/h，体感{data['feels_like']}°C。{adv}"
        render = f"{msg}\nsource: {meta.get('source')}\nsource_url: {meta.get('source_url')}\nevidence: {meta.get('evidence')}\nreferences: {meta.get('references')}"
        return {"speak": f"花都区现在{c}，{data['temp']}度。{adv}", "render": render,
                "ui": {"type": "info_card", "title": "广州市花都区今天天气", "message": msg, "source_url": meta.get("source_url"), "references": meta.get("references", [])}}
    except Exception as e:
        return {"speak": "天气服务暂时有点忙，请稍后再试。", "render": f"source: internal\nerror: {e}\nevidence: run_exception",
                "ui": {"type": "info_card", "title": "天气查询降级返回", "message": "服务暂时不可用，已记录错误信息。"}}

if __name__ == "__main__":
    r = asyncio.run(run(location="广州市花都区", use_mock=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
