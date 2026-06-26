"""花都区实时天气 one-shot skill（双源，含证据）。"""
import asyncio
from datetime import datetime
from urllib.parse import quote

import httpx
from evidence_utils import attach_evidence_fields, build_render_evidence_block

RUN_SPEC = {
    "name": "guangzhou_huadu_weather_now_multisource",
    "description": "查询广州市花都区今日实时天气并返回证据卡片。",
    "args_schema": {"type": "object", "properties": {"mock": {"type": "boolean", "default": False}}, "required": []},
}


def _w(code):
    return {0: "晴", 1: "晴", 2: "少云", 3: "多云", 45: "雾", 48: "雾", 51: "小雨", 53: "小雨", 55: "中雨", 61: "小雨", 63: "中雨", 65: "大雨", 80: "阵雨", 81: "阵雨", 82: "强阵雨", 95: "雷雨"}.get(code, "未知")


def _fmt(v, u=""):
    return f"{v}{u}" if v not in (None, "") else "--"


async def _get_json(client, url):
    try:
        r = await client.get(url, timeout=8.0)
        return (r.json() if r.status_code == 200 else {}), (None if r.status_code == 200 else f"http_{r.status_code}")
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"


async def run(mock: bool = False, **kwargs):
    if mock:
        return {"speak": "花都区现在多云，26度。", "render": "source: mock\nreferences: [{\"source\":\"mock\"}]", "ui": {"type": "info_card", "title": "花都区实时天气", "message": "天气: 多云\n当前: 26C\n最高/最低: 30C/24C"}}
    refs, c = [], {}
    wttr = f"https://wttr.in/{quote('广州市花都区')}?format=j1"
    geo = "https://geocoding-api.open-meteo.com/v1/search?name=%E8%8A%B1%E9%83%BD%E5%8C%BA&count=5&language=zh&format=json"
    async with httpx.AsyncClient() as client:
        wj, we = await _get_json(client, wttr); refs.append({"source": "wttr.in", "url": wttr, "ok": not we, "error": we})
        gj, ge = await _get_json(client, geo); refs.append({"source": "open-meteo-geocoding", "url": geo, "ok": not ge, "error": ge})
        lat, lon = 23.392, 113.221
        for it in (gj.get("results") or []):
            if "花都" in str(it.get("name", "")) or "Guangzhou" in str(it.get("admin1", "")):
                lat, lon = it.get("latitude", lat), it.get("longitude", lon); break
        om = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,wind_direction_10m,weather_code&daily=temperature_2m_max,temperature_2m_min&timezone=Asia%2FShanghai"
        oj, oe = await _get_json(client, om); refs.append({"source": "open-meteo-forecast", "url": om, "ok": not oe, "error": oe}); c = oj.get("current") or {}
    wc = (wj.get("current_condition") or [{}])[0]; wd = (wj.get("weather") or [{}])[0]; d = oj.get("daily") or {}
    s = ((wc.get("weatherDesc") or [{}])[0].get("value")) or _w(c.get("weather_code"))
    t, hi, lo = wc.get("temp_C") or c.get("temperature_2m"), wd.get("maxtempC") or (d.get("temperature_2m_max") or [None])[0], wd.get("mintempC") or (d.get("temperature_2m_min") or [None])[0]
    h, ws, wd16, fl = wc.get("humidity") or c.get("relative_humidity_2m"), wc.get("windspeedKmph") or c.get("wind_speed_10m"), wc.get("winddir16Point") or _fmt(c.get("wind_direction_10m"), "°"), wc.get("FeelsLikeC") or c.get("apparent_temperature")
    if not any([s, t, hi, lo, h, ws, fl]):
        ev = build_render_evidence_block(source="wttr.in + open-meteo", evidence={"reason": "all_sources_failed"}, references=refs)
        return {"speak": "抱歉，天气服务暂时不可用，请稍后再试。", "render": f"未获取到花都区天气数据。\n{ev}", "ui": attach_evidence_fields({"type": "info_card", "title": "花都区实时天气", "message": "获取失败，请稍后重试。"}, source="wttr.in + open-meteo", evidence={"reason": "all_sources_failed"}, references=refs)}
    msg = f"天气: {_fmt(s)}\n当前: {_fmt(t,'C')}\n最高/最低: {_fmt(hi,'C')}/{_fmt(lo,'C')}\n湿度: {_fmt(h,'%')}\n风: {_fmt(ws,'km/h')} {_fmt(wd16)}\n体感: {_fmt(fl,'C')}"
    speak = f"花都区现在{_fmt(s)}，气温{_fmt(t,'度')}，最高{_fmt(hi,'度')}，最低{_fmt(lo,'度')}。"
    ev = build_render_evidence_block(source="wttr.in + open-meteo", evidence={"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "key_fields": {"status": s, "temp_c": t, "max_c": hi, "min_c": lo, "humidity": h, "wind_kmh": ws, "wind_dir": wd16, "feels_like_c": fl}}, references=refs)
    return {"speak": speak, "render": f"{msg}\n\n{ev}", "ui": attach_evidence_fields({"type": "info_card", "title": "广州市花都区实时天气", "message": msg}, source="wttr.in + open-meteo", references=refs)}


if __name__ == "__main__":
    r = asyncio.run(run(mock=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r and isinstance(r.get("ui"), dict)
    print("OK")
