"""花都区今天天气：双来源查询并返回中文卡片。"""
import asyncio
import json

import httpx

RUN_SPEC = {
    "name": "huadu_weather_today_skill",
    "description": "查询广州花都区今天天气并返回卡片。",
    "args_schema": {
        "type": "object",
        "properties": {"district": {"type": "string", "default": "广州市花都区"}},
        "required": [],
    },
}


async def run(district: str = "广州市花都区", **kwargs):
    if kwargs.get("_mock"):
        return {
            "speak": "花都区现在多云，气温28度，最高31度，最低25度。",
            "render": "source: mock\nevidence: {'weather':'多云','temp':'28'}",
            "ui": {"type": "info_card", "title": "花都区天气", "message": "多云 28°C\n最高31°C 最低25°C"},
        }
    place = str(district or "广州市花都区").strip()
    code, coords = ("101280105", "23.3924,113.2202") if "花都" in place else ("101280101", "23.1291,113.2644")
    data, refs, errs = {"place": place}, [], []
    try:
        async with httpx.AsyncClient(timeout=6.0, headers={"User-Agent": "vox-agent/1.0"}) as c:
            sk = await c.get(f"https://www.weather.com.cn/data/sk/{code}.html")
            ci = await c.get(f"https://www.weather.com.cn/data/cityinfo/{code}.html")
        skd = sk.json().get("weatherinfo", {}) if sk.status_code == 200 else {}
        cid = ci.json().get("weatherinfo", {}) if ci.status_code == 200 else {}
        data.update(
            {
                "weather": cid.get("weather"),
                "temp": skd.get("temp"),
                "temp_max": str(cid.get("temp1", "")).replace("℃", ""),
                "temp_min": str(cid.get("temp2", "")).replace("℃", ""),
                "humidity": skd.get("SD"),
                "wind": (skd.get("WD", "") + skd.get("WS", "")).strip() or None,
                "aqi": skd.get("aqi"),
            }
        )
        refs.append({"source": "weather.com.cn", "source_url": f"https://www.weather.com.cn/weather/{code}.shtml", "time": skd.get("time")})
    except Exception as e:
        errs.append(f"weather.com.cn失败:{e}")
    if not data.get("weather") or not data.get("temp"):
        for q in [place, "花都区,广州", coords]:
            try:
                async with httpx.AsyncClient(timeout=6.0) as c:
                    r = await c.get(f"https://wttr.in/{q}", params={"format": "j1", "lang": "zh-CN"})
                if r.status_code != 200:
                    continue
                j = r.json()
                cur, day = (j.get("current_condition") or [{}])[0], (j.get("weather") or [{}])[0]
                data.update(
                    {
                        "weather": data.get("weather") or cur.get("weatherDesc", [{}])[0].get("value"),
                        "temp": data.get("temp") or cur.get("temp_C"),
                        "temp_max": data.get("temp_max") or day.get("maxtempC"),
                        "temp_min": data.get("temp_min") or day.get("mintempC"),
                        "humidity": data.get("humidity") or cur.get("humidity"),
                        "wind": data.get("wind") or f"{cur.get('winddir16Point', '')} {cur.get('windspeedKmph', '')}km/h".strip(),
                    }
                )
                refs.append({"source": "wttr.in", "source_url": f"https://wttr.in/{q}?format=j1", "query": q})
                if data.get("weather") and data.get("temp"):
                    break
            except Exception as e:
                errs.append(f"wttr.in[{q}]失败:{e}")
    ok = bool(data.get("weather") or data.get("temp"))
    speak = (
        f"{place}现在{data.get('weather','天气暂不明')}，气温{data.get('temp','未知')}度，最高{data.get('temp_max','未知')}度，最低{data.get('temp_min','未知')}度。"
        if ok
        else f"抱歉，我暂时没查到{place}天气。"
    )
    lines = [
        f"地点: {place}",
        f"天气: {data.get('weather','未知')}",
        f"当前气温: {data.get('temp','未知')}°C",
        f"最高/最低: {data.get('temp_max','未知')}°C / {data.get('temp_min','未知')}°C",
        f"湿度: {data.get('humidity','未知')}",
        f"风速风向: {data.get('wind','未知')}",
        f"空气质量: {data.get('aqi','暂无')}",
        f"references: {json.dumps(refs, ensure_ascii=False)}",
        f"evidence: {json.dumps({'key_fields': data, 'errors': errs}, ensure_ascii=False)}",
    ]
    return {
        "speak": speak,
        "render": "\n".join(lines),
        "ui": {
            "type": "info_card",
            "title": f"{place}今日天气",
            "message": f"{data.get('weather','未知')} {data.get('temp','未知')}°C\n最高{data.get('temp_max','未知')}°C 最低{data.get('temp_min','未知')}°C\n湿度{data.get('humidity','未知')} 风{data.get('wind','未知')} AQI {data.get('aqi','暂无')}",
            "source_url": refs[0]["source_url"] if refs else "https://www.weather.com.cn/",
        },
    }


if __name__ == "__main__":
    r = asyncio.run(run(_mock=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
