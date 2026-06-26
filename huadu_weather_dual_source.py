"""广州市花都区今天天气查询（双数据源兜底）。"""
import asyncio
import json
import re
from datetime import datetime

import httpx

RUN_SPEC = {
    "name": "huadu_weather_dual_source",
    "description": "查询广州市花都区实时与今日天气并返回卡片。",
    "args_schema": {
        "type": "object",
        "properties": {"district": {"type": "string", "default": "广州市花都区"}},
        "required": [],
    },
}


def _norm_loc(district: str):
    text = (district or "").replace(" ", "")
    ok = "花都" in text or "huadu" in text.lower()
    return {"name": "广州市花都区", "code": "101280105", "lat": 23.392, "lon": 113.211, "ok": ok}


async def _from_weather_com(client: httpx.AsyncClient, code: str):
    h = {"Referer": f"http://www.weather.com.cn/weather1d/{code}.shtml", "User-Agent": "Mozilla/5.0"}
    sk = await client.get(f"http://d1.weather.com.cn/sk_2d/{code}.html", headers=h)
    d1 = await client.get(f"http://d1.weather.com.cn/weather1d/{code}.shtml", headers=h)
    j1 = json.loads(re.search(r"\{.*\}", sk.text).group(0)) if sk.status_code == 200 and re.search(r"\{.*\}", sk.text) else {}
    j2 = json.loads(re.search(r"\{.*\}", d1.text).group(0)) if d1.status_code == 200 and re.search(r"\{.*\}", d1.text) else {}
    if not j1 and not j2:
        return None
    return {"source": "中国天气网", "source_url": f"http://www.weather.com.cn/weather1d/{code}.shtml", "weather": j1.get("weather") or j2.get("weather"), "temp": j1.get("temp"), "high": j2.get("temp"), "low": j2.get("tempn"), "humidity": j1.get("SD"), "wind": f"{j1.get('WD','')}{j1.get('WS','')}".strip(), "evidence": {"obs_time": j1.get("time"), "city": j1.get("cityname") or j2.get("cityname")}}


async def _from_wttr(client: httpx.AsyncClient, lat: float, lon: float):
    u = f"https://wttr.in/{lat},{lon}?format=j1"
    r = await client.get(u)
    d = r.json() if r.status_code == 200 else {}
    c, w = (d.get("current_condition") or [{}])[0], (d.get("weather") or [{}])[0]
    if not c and not w:
        return None
    return {"source": "wttr.in", "source_url": u, "weather": ((c.get("weatherDesc") or [{}])[0].get("value") or ""), "temp": c.get("temp_C"), "high": w.get("maxtempC"), "low": w.get("mintempC"), "humidity": c.get("humidity"), "wind": f"{c.get('winddir16Point','')}{c.get('windspeedKmph','')}km/h".strip(), "evidence": {"obs_time": c.get("localObsDateTime"), "coord": f"{lat},{lon}"}}


async def run(district: str = "广州市花都区", **kwargs):
    try:
        if kwargs.get("mock_data"):
            data = kwargs["mock_data"]
        else:
            loc = _norm_loc(district)
            async with httpx.AsyncClient(timeout=6.0) as client:
                data = None
                for fn, args in ((_from_weather_com, (loc["code"],)), (_from_wttr, (loc["lat"], loc["lon"]))):
                    try:
                        data = await fn(client, *args)
                        if data:
                            break
                    except Exception:
                        continue
            if not data:
                return {"speak": "花都区天气暂时没查到，稍后我再试一次。", "render": "source: 中国天气网/wttr.in\nreferences: code=101280105, coord=23.392,113.211\nevidence: 两条数据路径均失败", "ui": {"type": "info_card", "title": "花都区天气获取失败", "message": "已尝试中国天气网与 wttr.in，当前不可用。"}}
        s = f"花都区今天{data.get('weather') or '天气未知'}，现在约{data.get('temp') or '--'}度。"
        r = (f"地点: 广州市花都区\n天气: {data.get('weather') or '--'}\n当前气温: {data.get('temp') or '--'}°C\n"
             f"最高/最低: {data.get('high') or '--'}°C / {data.get('low') or '--'}°C\n湿度: {data.get('humidity') or '--'}\n"
             f"风力风向: {data.get('wind') or '--'}\nsource: {data.get('source')}\nsource_url: {data.get('source_url')}\n"
             f"evidence: {json.dumps(data.get('evidence', {}), ensure_ascii=False)}\nupdated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        card = f"{data.get('weather') or '--'}  {data.get('temp') or '--'}°C\n高低温 {data.get('high') or '--'}/{data.get('low') or '--'}°C\n湿度 {data.get('humidity') or '--'}  风 {data.get('wind') or '--'}"
        return {"speak": s, "render": r, "ui": {"type": "info_card", "title": "广州市花都区今天天气", "message": card, "source_url": data.get("source_url"), "references": ["中国天气网: code=101280105", "wttr.in: coord=23.392,113.211"]}}
    except Exception as e:
        return {"speak": "天气查询遇到一点问题，但我已经记录原因。", "render": f"source: 中国天气网/wttr.in\nevidence: {type(e).__name__}: {e}", "ui": {"type": "info_card", "title": "天气查询异常", "message": "已自动降级返回，可稍后重试。"}}


if __name__ == "__main__":
    mock = {"source": "mock", "source_url": "mock://local", "weather": "多云", "temp": "30", "high": "33", "low": "26", "humidity": "70%", "wind": "东北风2级", "evidence": {"obs_time": "14:00"}}
    out = asyncio.run(run(mock_data=mock))
    assert isinstance(out, dict) and "speak" in out and "render" in out
    print("OK")
