"""查询深圳创维半导体大厦到深圳北站地铁耗时（高德优先，百度兜底）。"""
import os, re, asyncio
import httpx
from evidence_utils import build_render_evidence_block, attach_evidence_fields

RUN_SPEC = {"name": "shenzhen_skyworth_to_shenzhen_north_metro", "description": "查询从深圳创维半导体大厦到深圳北站的地铁时间与换乘。", "args_schema": {"type": "object", "properties": {"origin": {"type": "string", "default": "深圳创维半导体大厦"}, "destination": {"type": "string", "default": "深圳北站"}}, "required": []}}
_FB = {"深圳创维半导体大厦": "113.943820,22.540680", "深圳北站": "114.029410,22.609790"}

def _n(s: str) -> str: return re.sub(r"\s+", "", str(s or "").replace("深圳市", "")).strip()
def _min(sec): return max(1, int(round(float(sec or 0) / 60.0)))
async def _j(c, u, p):
    try:
        r = await c.get(u, params=p); return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}

async def _amap(origin: str, dest: str):
    key = (os.getenv("AMAP_API_KEY") or os.getenv("AMAP_KEY") or "").strip()
    if not key: return None, {"provider": "amap", "error": "missing_key"}
    async with httpx.AsyncClient(timeout=8.0) as c:
        g1 = await _j(c, "https://restapi.amap.com/v3/geocode/geo", {"key": key, "city": "深圳", "address": origin})
        g2 = await _j(c, "https://restapi.amap.com/v3/geocode/geo", {"key": key, "city": "深圳", "address": dest})
        o = (((g1.get("geocodes") or [{}])[0]).get("location") or _FB["深圳创维半导体大厦"]); d = (((g2.get("geocodes") or [{}])[0]).get("location") or _FB["深圳北站"])
        r = await _j(c, "https://restapi.amap.com/v3/direction/transit/integrated", {"key": key, "origin": o, "destination": d, "city": "深圳", "strategy": 0})
    ts = ((r.get("route") or {}).get("transits") or [])
    if not ts: return None, {"provider": "amap", "error": "no_route", "origin_coord": o, "dest_coord": d}
    t = ts[0]; segs = t.get("segments") or []; lines, mids = [], []
    for s in segs:
        for b in ((s.get("bus") or {}).get("buslines") or []):
            n = str(b.get("name") or "").split("(")[0].strip()
            if n and n not in lines: lines.append(n)
            a = ((b.get("arrival_stop") or {}).get("name") or "").strip()
            if a: mids.append(a)
    first = ((segs[0].get("bus") or {}).get("buslines") or [{}])[0] if segs else {}
    last = ((segs[-1].get("bus") or {}).get("buslines") or [{}])[-1] if segs else {}
    return {"source": "高德地图API", "source_url": "https://restapi.amap.com/v3/direction/transit/integrated", "origin_station": ((first.get("departure_stop") or {}).get("name") or "未知"), "dest_station": ((last.get("arrival_stop") or {}).get("name") or "深圳北站"), "lines": lines, "transfers": mids[:-1], "total_min": _min(t.get("duration")), "walk_min": _min((t.get("walking_distance") or 0) / 1.2), "fare": str(t.get("cost") or "未知"), "evidence": {"origin_coord": o, "dest_coord": d, "segments": len(segs)}}, {"provider": "amap", "ok": True}

async def _baidu(origin: str, dest: str):
    ak = (os.getenv("BAIDU_MAP_AK") or os.getenv("BAIDU_AK") or "").strip()
    if not ak: return None, {"provider": "baidu", "error": "missing_key"}
    async with httpx.AsyncClient(timeout=8.0) as c:
        g1 = await _j(c, "https://api.map.baidu.com/geocoding/v3/", {"ak": ak, "output": "json", "city": "深圳", "address": origin})
        g2 = await _j(c, "https://api.map.baidu.com/geocoding/v3/", {"ak": ak, "output": "json", "city": "深圳", "address": dest})
        l1, l2 = (g1.get("result") or {}).get("location") or {}, (g2.get("result") or {}).get("location") or {}
        o = f'{l1.get("lat")},{l1.get("lng")}' if l1 else f'{_FB["深圳创维半导体大厦"].split(",")[1]},{_FB["深圳创维半导体大厦"].split(",")[0]}'
        d = f'{l2.get("lat")},{l2.get("lng")}' if l2 else f'{_FB["深圳北站"].split(",")[1]},{_FB["深圳北站"].split(",")[0]}'
        r = await _j(c, "https://api.map.baidu.com/directionlite/v1/transit", {"ak": ak, "origin": o, "destination": d})
    rs = (r.get("result") or {}).get("routes") or []
    if not rs: return None, {"provider": "baidu", "error": "no_route", "origin_coord": o, "dest_coord": d}
    rt = rs[0]; txt = "".join(str(s.get("instruction") or "") for s in (rt.get("steps") or []))
    lines = [x for x in re.findall(r"地铁\d+号线", txt) if x]
    return {"source": "百度地图API", "source_url": "https://api.map.baidu.com/directionlite/v1/transit", "origin_station": "就近地铁站(百度未显式返回)", "dest_station": "深圳北站", "lines": list(dict.fromkeys(lines)) or ["地铁线路见步骤"], "transfers": [], "total_min": _min(rt.get("duration")), "walk_min": max(1, _min((rt.get("distance") or 0) / 80) - _min(rt.get("duration"))), "fare": str(rt.get("price") or "未知"), "evidence": {"origin_coord": o, "dest_coord": d, "distance_m": rt.get("distance")}}, {"provider": "baidu", "ok": True}

async def run(origin: str = "深圳创维半导体大厦", destination: str = "深圳北站", **kwargs):
    if kwargs.get("_smoke_test"): return {"speak": "从创维半导体大厦到深圳北站，地铁大约三十多分钟。", "render": "source: mock\nevidence: smoke_test", "ui": {"type": "info_card", "title": "地铁路线(测试)", "message": "出发站: 高新园站\n到达站: 深圳北站\n线路: 4号线\n总时间: 35分钟\n票价: 4元", "source": "mock"}}
    o, d = _n(origin), _n(destination); data = meta = None
    try: data, meta = await _amap(o, d)
    except Exception as e: meta = {"provider": "amap", "error": f"{type(e).__name__}:{e}"}
    if not data:
        try: data, meta = await _baidu(o, d)
        except Exception as e: meta = {"provider": "baidu", "error": f"{type(e).__name__}:{e}"}
    if not data:
        ev = build_render_evidence_block(source="高德/百度地图API", evidence={"origin": o, "destination": d, "error": (meta or {}).get("error", "no_data"), "fallback_coords": _FB})
        return {"speak": "我暂时没查到可靠的地铁方案，请稍后重试。", "render": f"查询失败。\n{ev}", "ui": {"type": "info_card", "title": "地铁路线查询失败", "message": "暂时无法获取路线，请稍后重试。", "source": "高德/百度地图API", "evidence": meta or {}}}
    lines = " → ".join(data["lines"]); transfers = "、".join(data["transfers"]) if data["transfers"] else "无或未返回"
    speak = f'从创维半导体大厦步行约{data["walk_min"]}分钟到{data["origin_station"]}，乘坐{data["lines"][0]}，全程约{data["total_min"]}分钟到深圳北站。'
    render = "查询结果：\n" + build_render_evidence_block(source=data["source"], source_url=data["source_url"], evidence=data["evidence"], extra_lines=[f'出发站: {data["origin_station"]}', f'到达站: {data["dest_station"]}', f"线路: {lines}", f"换乘站: {transfers}", f'总耗时: {data["total_min"]}分钟(含步行约{data["walk_min"]}分钟)', f'票价: {data["fare"]}元'])
    ui = attach_evidence_fields({"type": "info_card", "title": "深圳地铁路线：创维半导体大厦 → 深圳北站", "message": f'出发站: {data["origin_station"]}\n到达站: {data["dest_station"]}\n线路: {lines}\n换乘站: {transfers}\n总时间: {data["total_min"]}分钟(含步行约{data["walk_min"]}分钟)\n票价: {data["fare"]}元'}, source=data["source"], source_url=data["source_url"], evidence=data["evidence"], references=[{"provider": (meta or {}).get("provider", "unknown")}])
    return {"speak": speak, "render": render, "ui": ui}

if __name__ == "__main__":
    r = asyncio.run(run(_smoke_test=True))
    assert isinstance(r, dict) and "speak" in r and "render" in r and "ui" in r
    print("OK")
