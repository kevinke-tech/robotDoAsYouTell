"""广州花都天气查询：双数据源与证据化输出。"""
import asyncio
import json
import re
from datetime import datetime

import httpx

RUN_SPEC = {
    "name": "huadu_weather_cn_dual_source",
    "description": "查询广州市花都区实时天气并返回卡片。",
    "args_schema": {
        "type": "object",
        "properties": {"location": {"type": "string", "default": "广州市花都区"}},
        "required": [],
    },
}


def _norm_location(text: str) -> str:
    t = (text or "").strip().replace(" ", "")
    return "广州市花都区" if t in {"花都", "花都区", "广州花都", "广州市花都区"} else "广州市花都区"


def _wcode_to_text(code: int) -> str:
    return {0: "晴", 1: "多云", 2: "多云", 3: "阴", 45: "雾", 51: "小雨", 61: "雨", 80: "阵雨", 95: "雷雨"}.get(code, "未知")


def _wind_cn(deg: float) -> str:
    arr = ["北风", "东北风", "东风", "东南风", "南风", "西南风", "西风", "西北风"]
    return arr[int(((deg % 360) + 22.5) // 45) % 8]


async def _fetch_weather_com(code: str):
    refs = [f"http://d1.weather.com.cn/sk_2d/{code}.html", f"http://www.weather.com.cn/data/cityinfo/{code}.html"]
    headers = {"Referer": "http://www.weather.com.cn/", "User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(timeout=4.0, headers=headers) as c:
        sk = await c.get(refs[0]); city = await c.get(refs[1])
    m = re.search(r"\{.*\}", sk.text, re.S); now = json.loads(m.group(0)) if m else {}
    info = (city.json() or {}).get("weatherinfo", {}) if city.status_code == 200 else {}
    return {
        "source": "中国天气网",
        "source_url": refs[0],
        "references": refs,
        "weather": now.get("weather") or info.get("weather") or "",
        "temp": now.get("temp") or "",
        "temp_max": info.get("temp1", "").replace("℃", ""),
        "temp_min": info.get("temp2", "").replace("℃", ""),
        "humidity": now.get("sd") or "",
        "wind_dir": now.get("wd") or "",
        "wind_speed": now.get("ws") or "",
        "obs_time": now.get("time") or "",
        "evidence": {"raw_sk_status": sk.status_code, "raw_city_status": city.status_code},
    }


async def _fetch_open_meteo(lat: float, lon: float):
    url = "https://api.open-meteo.com/v1/forecast"
    q = {"latitude": lat, "longitude": lon, "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m", "daily": "temperature_2m_max,temperature_2m_min", "timezone": "Asia/Shanghai"}
    async with httpx.AsyncClient(timeout=4.0) as c:
        r = await c.get(url, params=q)
    d = r.json() if r.status_code == 200 else {}
    cur, daily = d.get("current", {}), d.get("daily", {})
    return {
        "source": "Open-Meteo(坐标兜底)",
        "source_url": str(r.url),
        "references": [str(r.url)],
        "weather": _wcode_to_text(int(cur.get("weather_code", -1))),
        "temp": str(cur.get("temperature_2m", "")),
        "temp_max": str((daily.get("temperature_2m_max") or [""])[0]),
        "temp_min": str((daily.get("temperature_2m_min") or [""])[0]),
        "humidity": f'{cur.get("relative_humidity_2m", "")}%',
        "wind_dir": _wind_cn(float(cur.get("wind_direction_10m", 0))),
        "wind_speed": f'{cur.get("wind_speed_10m", "")} km/h',
        "obs_time": str(cur.get("time", "")),
        "evidence": {"status": r.status_code, "coords": [lat, lon]},
    }


async def run(location: str = "广州市花都区", mock_data=None, **kwargs):
    loc, code, coords = _norm_location(location), "101280105", (23.3924, 113.2112)
    if mock_data:
        w = mock_data
    else:
        errs, w = [], None
        for fn in (lambda: _fetch_weather_com(code), lambda: _fetch_open_meteo(*coords)):
            try:
                w = await fn()
                if w.get("weather") and w.get("temp") != "":
                    break
            except Exception as e:
                errs.append(str(e))
        if not w:
            return {"speak": "我这会儿没查到花都天气，稍后再试一次。", "render": f"location: {loc}\nsource: 多源尝试失败\nevidence: {errs or ['no_data']}", "ui": {"type": "info_card", "title": "天气查询失败", "message": "暂时无法获取天气数据，请稍后重试。"}}
    msg = f"{loc}现在{w.get('weather','未知')}，{w.get('temp','?')}度，最高{w.get('temp_max','?')}度，最低{w.get('temp_min','?')}度。"
    msg += f" 湿度{w.get('humidity','?')}，{w.get('wind_dir','?')}{w.get('wind_speed','?')}。"
    render = f"location: {loc}\nsource: {w.get('source','')}\nsource_url: {w.get('source_url','')}\nweather: {w.get('weather','')}\ntemp: {w.get('temp','')}\ntemp_max: {w.get('temp_max','')}\ntemp_min: {w.get('temp_min','')}\nhumidity: {w.get('humidity','')}\nwind: {w.get('wind_dir','')} {w.get('wind_speed','')}\nobs_time: {w.get('obs_time','')}\nreferences: {w.get('references',[])}\nevidence: {w.get('evidence',{})}\nconclusion: 以上结论基于来源字段与关键观测字段。"
    return {"speak": "我查到花都区今天的天气了。", "render": render, "ui": {"type": "info_card", "title": f"{loc}天气", "message": msg, "source_url": w.get("source_url", "")}}


if __name__ == "__main__":
    fake = {"source": "mock", "source_url": "mock://local", "references": ["mock://local"], "weather": "多云", "temp": "31", "temp_max": "34", "temp_min": "27", "humidity": "70%", "wind_dir": "东南风", "wind_speed": "3级", "obs_time": datetime.now().strftime("%H:%M"), "evidence": {"mock": True}}
    r = asyncio.run(run(location="花都", mock_data=fake))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
