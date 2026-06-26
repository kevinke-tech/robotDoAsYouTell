"""查询广州市花都区实时天气并返回信息卡。"""
import httpx

RUN_SPEC = {
    "name": "huadu_weather_live_card",
    "description": "查询今天广州市花都区的实时天气。",
    "args_schema": {
        "type": "object",
        "properties": {"location": {"type": "string", "default": "广州市花都区"}},
        "required": [],
    },
}


def _norm_loc(location: str) -> str:
    s = (location or "").strip()
    return "广州市花都区" if not s or "花都" in s else s


async def _from_qq(client: httpx.AsyncClient):
    url = "https://wis.qq.com/weather/common"
    p = {"source": "pc", "weather_type": "observe|forecast_24h", "province": "广东省", "city": "广州市", "county": "花都区"}
    r = await client.get(url, params=p, headers={"Referer": "https://tianqi.qq.com/", "User-Agent": "Mozilla/5.0"})
    d = (r.json() or {}).get("data") or {}
    o, f = d.get("observe") or {}, ((d.get("forecast_24h") or {}).get("0") or {})
    if not o.get("degree"):
        raise ValueError("QQ天气返回空数据")
    return {"status": o.get("weather") or o.get("weather_short") or "未知", "temp": o.get("degree"), "max": f.get("max_degree"), "min": f.get("min_degree"), "humidity": o.get("humidity"), "wind_dir": o.get("wind_direction_name") or o.get("wind_direction"), "wind_speed": o.get("wind_power"), "update": o.get("update_time"), "source": "腾讯天气", "source_url": str(r.url)}


async def _from_open_meteo(client: httpx.AsyncClient, location: str):
    g = await client.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": location, "count": 1, "language": "zh", "format": "json"})
    rs = (g.json() or {}).get("results") or []
    lat, lon = (rs[0]["latitude"], rs[0]["longitude"]) if rs else (23.38, 113.22)
    p = {"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weather_code", "daily": "temperature_2m_max,temperature_2m_min", "timezone": "Asia/Shanghai", "forecast_days": 1}
    r = await client.get("https://api.open-meteo.com/v1/forecast", params=p)
    d, c = r.json() or {}, (r.json() or {}).get("current") or {}
    if "temperature_2m" not in c:
        raise ValueError("Open-Meteo返回空数据")
    dm = (d.get("daily") or {})
    return {"status": f"代码{c.get('weather_code', 'NA')}", "temp": c.get("temperature_2m"), "max": (dm.get("temperature_2m_max") or [None])[0], "min": (dm.get("temperature_2m_min") or [None])[0], "humidity": c.get("relative_humidity_2m"), "wind_dir": c.get("wind_direction_10m"), "wind_speed": c.get("wind_speed_10m"), "update": c.get("time"), "source": "Open-Meteo", "source_url": str(r.url), "evidence": f"geocode_results={len(rs)};coords={lat},{lon}"}


async def run(location: str = "广州市花都区", **kwargs):
    if kwargs.get("_smoke"):
        return {"speak": "花都区天气技能可用。", "render": "source: mock\nevidence: smoke_test", "ui": {"type": "info_card", "title": "冒烟测试", "message": "结构检查通过"}}
    loc = _norm_loc(location)
    tried = []
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            for fn in (_from_qq, lambda c: _from_open_meteo(c, loc)):
                try:
                    w = await fn(client)
                    txt = f"{loc}现在{w['status']}，{w['temp']}度，今天{w['min']}到{w['max']}度。湿度{w['humidity']}%，风{w['wind_dir']} {w['wind_speed']}级。"
                    render = f"地点: {loc}\n天气: {w['status']}\n当前温度: {w['temp']}°C\n最高/最低: {w['max']}°C / {w['min']}°C\n湿度: {w['humidity']}%\n风向风速: {w['wind_dir']} {w['wind_speed']}级\nsource: {w.get('source')}\nsource_url: {w.get('source_url')}\nevidence: update={w.get('update')} {w.get('evidence','')}\nreferences: {tried + [w.get('source')]}"
                    return {"speak": txt, "render": render, "ui": {"type": "info_card", "title": "花都区实时天气", "message": txt, "source_url": w.get("source_url")}}
                except Exception as e:
                    tried.append(f"{getattr(fn, '__name__', 'fallback')}失败:{e}")
    except Exception as e:
        tried.append(f"网络调用异常:{e}")
    msg = "我暂时没查到花都区天气，稍后再试。"
    return {"speak": msg, "render": f"地点: {loc}\nsource: 腾讯天气/Open-Meteo\nevidence: {'; '.join(tried) or '无'}", "ui": {"type": "info_card", "title": "天气获取失败", "message": msg}}


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(run(_smoke=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
