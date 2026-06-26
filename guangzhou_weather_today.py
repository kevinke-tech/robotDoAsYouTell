"""广州今天天气 one-shot 技能。"""
import httpx

RUN_SPEC = {
    "name": "guangzhou_weather_today",
    "description": "查询广州市今天的天气并返回中文卡片。",
    "args_schema": {
        "type": "object",
        "properties": {"city": {"type": "string", "default": "Guangzhou"}, "mock_data": {"type": "object"}},
        "required": [],
    },
}


def _s(v, d="--"):
    return d if v in (None, "", []) else str(v)


async def run(city: str = "Guangzhou", mock_data=None, **kwargs):
    source_url = f"https://wttr.in/{city}?format=j1"
    data, err = (mock_data if isinstance(mock_data, dict) else {}), ""
    if not data:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(source_url, headers={"User-Agent": "vox-weather-skill/1.0"})
                data = r.json() if r.status_code == 200 else {}
                if not data:
                    err = f"HTTP {r.status_code}"
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    cur = (data.get("current_condition") or [{}])[0] if isinstance(data, dict) else {}
    day = (data.get("weather") or [{}])[0] if isinstance(data, dict) else {}
    desc = _s(((cur.get("weatherDesc") or [{}])[0]).get("value"), "未知")
    temp, feels, hum = _s(cur.get("temp_C")), _s(cur.get("FeelsLikeC")), _s(cur.get("humidity"))
    wv, wd = _s(cur.get("windspeedKmph")), _s(cur.get("winddir16Point"))
    tmax, tmin = _s(day.get("maxtempC")), _s(day.get("mintempC"))
    obs = _s(cur.get("localObsDateTime"), _s(cur.get("observation_time")))
    city_cn = "广州市" if city.lower() == "guangzhou" else city
    if temp == "--":
        reason = err or "上游返回空数据或关键字段缺失"
        return {
            "speak": "我现在没查到广州天气，稍后再试一次吧。",
            "render": f"source: wttr.in\nsource_url: {source_url}\nevidence: {reason}",
            "ui": {"type": "info_card", "title": "广州天气获取失败", "message": f"失败原因：{reason}\n数据源：wttr.in"},
        }
    line = f"{city_cn}{desc}，当前{temp}°C，体感{feels}°C；最高{tmax}°C、最低{tmin}°C；湿度{hum}%；{wd}风 {wv} km/h。"
    return {
        "speak": f"{city_cn}现在{desc}，气温{temp}度，体感{feels}度。",
        "render": f"source: wttr.in\nsource_url: {source_url}\nevidence: weather={desc},temp_C={temp},feelsLike_C={feels},max_C={tmax},min_C={tmin},humidity={hum},wind={wd} {wv}km/h,obs_time={obs}\n{line}",
        "ui": {"type": "info_card", "title": f"{city_cn}今天天气", "message": line},
    }


if __name__ == "__main__":
    import asyncio

    sample = {"current_condition": [{"weatherDesc": [{"value": "多云"}], "temp_C": "30", "FeelsLikeC": "35", "humidity": "72", "windspeedKmph": "18", "winddir16Point": "SE", "localObsDateTime": "2026-06-18 14:00"}], "weather": [{"maxtempC": "33", "mintempC": "27"}]}
    x = asyncio.run(run(city="Guangzhou", mock_data=sample))
    assert isinstance(x, dict) and "speak" in x and "render" in x
    print("OK")
