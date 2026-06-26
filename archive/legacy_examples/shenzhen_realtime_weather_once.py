"""深圳实时天气 one-shot 技能。"""
from datetime import datetime, timezone
import httpx

RUN_SPEC = {
    "name": "shenzhen_realtime_weather_once",
    "description": "查询深圳当前实时天气并返回中文卡片。",
    "args_schema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "default": "Shenzhen"},
            "mock_data": {"type": "object"},
        },
        "required": [],
    },
}


async def run(city: str = "Shenzhen", mock_data=None, **kwargs):
    source_url = f"https://wttr.in/{city}?format=j1&lang=zh-cn"
    queried_at = datetime.now(timezone.utc).isoformat()
    data, error = {}, ""
    if isinstance(mock_data, dict):
        data = mock_data
    else:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(source_url)
            data = resp.json() if resp.status_code == 200 else {}
            if not data:
                error = f"HTTP {resp.status_code}"
        except Exception as exc:
            error = str(exc)
    cur = ((data.get("current_condition") or [{}])[0]) if isinstance(data, dict) else {}
    desc = (((cur.get("weatherDesc") or [{}])[0]).get("value") or "").strip()
    temp = str(cur.get("temp_C") or "").strip()
    feels = str(cur.get("FeelsLikeC") or "").strip()
    hum = str(cur.get("humidity") or "").strip()
    wind = str(cur.get("windspeedKmph") or "").strip()
    wind_dir = str(cur.get("winddir16Point") or "").strip()
    ok = all([temp, feels, desc, hum, wind, wind_dir])
    if not ok:
        reason = f"数据不完整; error={error or '缺少关键字段'}"
        return {
            "speak": "我刚查天气时遇到一点问题，请稍后再试。",
            "render": f"source_url: {source_url}\nevidence: queried_at={queried_at}; reason={reason}",
            "ui": {"type": "info_card", "title": "深圳实时天气获取失败", "message": reason, "source_url": source_url},
        }
    message = (
        f"城市: 深圳\n天气: {desc}\n温度: {temp}°C\n体感温度: {feels}°C\n"
        f"湿度: {hum}%\n风速: {wind} km/h\n风向: {wind_dir}"
    )
    return {
        "speak": f"深圳现在{desc}，气温{temp}度，体感{feels}度。",
        "render": f"source_url: {source_url}\nevidence: queried_at={queried_at}; city={city}\n{message}",
        "ui": {"type": "info_card", "title": "深圳实时天气", "message": message, "source_url": source_url},
    }


if __name__ == "__main__":
    import asyncio

    fake = {
        "current_condition": [{
            "temp_C": "30", "FeelsLikeC": "35", "humidity": "78",
            "windspeedKmph": "12", "winddir16Point": "SE", "weatherDesc": [{"value": "多云"}],
        }]
    }
    r = asyncio.run(run(mock_data=fake))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
