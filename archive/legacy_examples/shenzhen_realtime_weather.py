"""深圳当前实时天气 one_shot skill。"""
from datetime import datetime, timezone
from urllib.parse import quote
import json
import httpx

RUN_SPEC = {
    "name": "shenzhen_realtime_weather",
    "description": "查询深圳当前实时天气并返回中文卡片。",
    "args_schema": {"type": "object", "properties": {"city": {"type": "string", "default": "Shenzhen"}}, "required": []},
}


async def run(city: str = "Shenzhen", **kwargs):
    city_name = str(city).strip() or "Shenzhen"
    source_url = f"https://wttr.in/{quote(city_name)}?format=j1"
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        mock_data = kwargs.get("_mock_data")
        if mock_data is None:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(source_url)
            data, status_code = (resp.json() if resp.status_code == 200 else {}), resp.status_code
        else:
            data, status_code = mock_data, 200
        cur = (data.get("current_condition") or [{}])[0]
        desc = str(((cur.get("weatherDesc") or [{}])[0]).get("value") or "").strip()
        temp = str(cur.get("temp_C") or "").strip()
        feels = str(cur.get("FeelsLikeC") or "").strip()
        humidity = str(cur.get("humidity") or "").strip()
        wind_speed = str(cur.get("windspeedKmph") or "").strip()
        wind_dir = str(cur.get("winddir16Point") or "").strip()
        if not all([desc, temp, feels, humidity, wind_speed, wind_dir]):
            raise ValueError("返回数据缺少关键字段")
        return {
            "speak": f"深圳现在{desc}，气温{temp}度，体感{feels}度。",
            "render": (
                f"城市: 深圳\n当前温度: {temp}°C\n体感温度: {feels}°C\n天气描述: {desc}\n湿度: {humidity}%\n"
                f"风速: {wind_speed} km/h\n风向: {wind_dir}\nsource_url: {source_url}\n"
                f"evidence: fetched_at={fetched_at}, status_code={status_code}, "
                f"fields={json.dumps({'temp_C': temp, 'FeelsLikeC': feels, 'weatherDesc': desc, 'humidity': humidity, 'windspeedKmph': wind_speed, 'winddir16Point': wind_dir}, ensure_ascii=False)}"
            ),
            "ui": {
                "type": "info_card",
                "title": "深圳实时天气",
                "message": (
                    f"城市: 深圳\n温度: {temp}°C\n体感: {feels}°C\n天气: {desc}\n"
                    f"湿度: {humidity}%\n风速: {wind_speed} km/h\n风向: {wind_dir}"
                ),
                "source_url": source_url,
            },
        }
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"
        return {
            "speak": "我暂时没查到深圳实时天气，请稍后再试。",
            "render": f"查询失败\nsource_url: {source_url}\nevidence: fetched_at={fetched_at}, error={reason}",
            "ui": {"type": "info_card", "title": "深圳实时天气获取失败", "message": f"失败原因: {reason}", "source_url": source_url},
        }


if __name__ == "__main__":
    import asyncio
    fake = {"current_condition": [{"weatherDesc": [{"value": "多云"}], "temp_C": "29", "FeelsLikeC": "33", "humidity": "78", "windspeedKmph": "15", "winddir16Point": "SE"}]}
    r = asyncio.run(run(city="Shenzhen", _mock_data=fake))
    assert isinstance(r, dict) and "speak" in r and "render" in r and isinstance(r.get("ui"), dict)
    print("OK")
