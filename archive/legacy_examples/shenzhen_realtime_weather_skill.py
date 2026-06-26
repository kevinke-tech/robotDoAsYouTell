"""深圳实时天气 one-shot 技能（wttr.in）。"""
import httpx

RUN_SPEC = {
    "name": "shenzhen_realtime_weather_skill",
    "description": "查询深圳当前实时天气并返回中文卡片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "default": "深圳"},
            "location_query": {"type": "string", "default": "Shenzhen"},
        },
        "required": [],
    },
}


def _extract_weather(data: dict) -> dict:
    cc = (data.get("current_condition") or [{}])[0]
    descs = cc.get("weatherDesc") or [{}]
    return {
        "temp_c": str(cc.get("temp_C") or ""),
        "feels_c": str(cc.get("FeelsLikeC") or ""),
        "desc": str((descs[0] or {}).get("value") or "未知"),
        "humidity": str(cc.get("humidity") or ""),
        "wind_kmph": str(cc.get("windspeedKmph") or ""),
        "wind_dir": str(cc.get("winddir16Point") or ""),
        "obs_time": str(cc.get("observation_time") or ""),
    }


async def run(city: str = "深圳", location_query: str = "Shenzhen", **kwargs):
    source_url = f"https://wttr.in/{location_query}?format=j1"
    try:
        data = kwargs.get("_mock_data")
        if data is None:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(source_url)
                data = resp.json() if resp.status_code == 200 else {}
        w = _extract_weather(data if isinstance(data, dict) else {})
        if not w["temp_c"]:
            raise ValueError("缺少关键字段 temp_C")
        msg = (
            f"城市：{city}\n当前温度：{w['temp_c']}°C（体感 {w['feels_c']}°C）\n"
            f"天气：{w['desc']}\n湿度：{w['humidity']}%\n"
            f"风速：{w['wind_kmph']} km/h（{w['wind_dir']}）"
        )
        return {
            "speak": f"{city}现在{w['desc']}，气温{w['temp_c']}度，体感{w['feels_c']}度。",
            "render": f"{msg}\n\nsource: wttr.in\nsource_url: {source_url}\nevidence: observation_time={w['obs_time']}, temp_C={w['temp_c']}, humidity={w['humidity']}, windspeedKmph={w['wind_kmph']}",
            "ui": {
                "type": "info_card",
                "title": f"{city}实时天气",
                "message": msg,
                "source_url": source_url,
            },
        }
    except Exception as e:
        reason = str(e) or "未知错误"
        return {
            "speak": f"我暂时没查到{city}的实时天气，请稍后再试。",
            "render": f"查询失败：{reason}\nsource: wttr.in\nsource_url: {source_url}\nevidence: 请求失败或返回字段不完整",
            "ui": {"type": "info_card", "title": f"{city}天气查询失败", "message": f"原因：{reason}"},
        }


if __name__ == "__main__":
    import asyncio

    mock = {"current_condition": [{"temp_C": "30", "FeelsLikeC": "35", "weatherDesc": [{"value": "多云"}], "humidity": "78", "windspeedKmph": "12", "winddir16Point": "SE", "observation_time": "11:00 AM"}]}
    r = asyncio.run(run(_mock_data=mock))
    assert isinstance(r, dict) and "speak" in r and "render" in r
    print("OK")
