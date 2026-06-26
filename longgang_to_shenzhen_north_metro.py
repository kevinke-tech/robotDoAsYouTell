"""查询深圳龙岗区图书馆到深圳北站的地铁时间与换乘。"""
import asyncio, os, re, httpx
from evidence_utils import attach_evidence_fields, build_render_evidence_block

RUN_SPEC = {"name": "longgang_to_shenzhen_north_metro", "description": "查询龙岗区图书馆到深圳北站地铁耗时与换乘。", "args_schema": {"type": "object", "properties": {"origin": {"type": "string", "default": "深圳龙岗区图书馆"}, "destination": {"type": "string", "default": "深圳北站地铁站"}, "city": {"type": "string", "default": "深圳"}, "amap_key": {"type": "string"}, "baidu_key": {"type": "string"}}, "required": []}}
_O, _D = ["深圳龙岗区图书馆", "龙岗区图书馆", "龙城广场地铁站"], ["深圳北站地铁站", "深圳北站"]

async def _amap(c, key, origin, dest, city):
    g, src = "https://restapi.amap.com/v3/geocode/geo", "https://restapi.amap.com/v3/direction/transit/integrated"
    if not key: return {"ok": False, "source_url": src, "error": "missing_amap_key"}
    async def geocode(name):
        try:
            r = await c.get(g, params={"address": name, "city": city, "key": key}, timeout=6.0)
            ps = (r.json() if r.status_code == 200 else {}).get("geocodes") or []
            return str(ps[0].get("location") or "").strip()
        except Exception: return ""
    o_name, d_name = next((x for x in [origin] + _O if x), _O[0]), next((x for x in [dest] + _D if x), _D[0])
    o_loc, d_loc = "", ""
    for x in [o_name] + _O:
        o_loc = o_loc or await geocode(x)
    for x in [d_name] + _D:
        d_loc = d_loc or await geocode(x)
    if not o_loc or not d_loc: return {"ok": False, "source_url": src, "error": "amap_geocode_failed", "evidence": {"origin_coord": o_loc, "dest_coord": d_loc}}
    try:
        r = await c.get(src, params={"origin": o_loc, "destination": d_loc, "city": city, "cityd": city, "strategy": 0, "key": key}, timeout=8.0)
        t = ((((r.json() if r.status_code == 200 else {}).get("route") or {}).get("transits") or [None])[0]) or {}
        segs = t.get("segments") or []; lines, hops = [], []
        for s in segs:
            for b in ((s.get("bus") or {}).get("buslines") or []):
                n = str(b.get("name") or "").split("(")[0].strip()
                if n and n not in lines: lines.append(n)
                a, z = ((b.get("departure_stop") or {}).get("name") or "").strip(), ((b.get("arrival_stop") or {}).get("name") or "").strip()
                if a and z: hops.append(f"{a}→{z}")
        if not t: return {"ok": False, "source_url": src, "error": "amap_no_route", "evidence": {"origin_coord": o_loc, "dest_coord": d_loc}}
        return {"ok": True, "provider": "高德地图", "source_url": src, "from": o_name, "to": d_name, "duration_min": max(1, int(float(t.get("duration") or 0) / 60)), "walk_m": int(float(t.get("walking_distance") or 0)), "lines": lines[:4], "hops": hops[:3], "evidence": {"origin_coord": o_loc, "dest_coord": d_loc, "segments": len(segs)}}
    except Exception as e: return {"ok": False, "source_url": src, "error": f"amap_exception:{type(e).__name__}"}

async def _baidu(c, key, origin, dest, city):
    src = "https://api.map.baidu.com/directionlite/v1/transit"
    if not key: return {"ok": False, "source_url": src, "error": "missing_baidu_key"}
    try:
        for o in [origin] + _O:
            for d in [dest] + _D:
                r = await c.get(src, params={"origin": o, "destination": d, "region": city, "tactics_incity": 0, "ak": key}, timeout=8.0)
                rt = (((r.json() if r.status_code == 200 else {}).get("result") or {}).get("routes") or [None])[0]
                if not rt: continue
                ins = [re.sub(r"<[^>]+>", "", str(x.get("instruction") or "")) for s in (rt.get("steps") or []) for x in (s if isinstance(s, list) else [s])]
                lines = [x[:24] for x in ins if "地铁" in x][:4]
                return {"ok": True, "provider": "百度地图", "source_url": src, "from": o, "to": d, "duration_min": max(1, int(float(rt.get("duration") or 0) / 60)), "walk_m": sum(int((x if isinstance(x, dict) else {}).get("distance") or 0) for s in (rt.get("steps") or []) for x in (s if isinstance(s, list) else [s])), "lines": lines, "hops": [x[:28] for x in ins if "换乘" in x][:3], "evidence": {"steps": len(rt.get("steps") or [])}}
        return {"ok": False, "source_url": src, "error": "baidu_no_route"}
    except Exception as e: return {"ok": False, "source_url": src, "error": f"baidu_exception:{type(e).__name__}"}

async def run(origin: str = _O[0], destination: str = _D[0], city: str = "深圳", amap_key: str = "", baidu_key: str = "", **kwargs):
    if kwargs.get("mock_data"): return {"speak": "结构检查通过。", "render": "source: mock\nevidence: smoke_test", "ui": {"type": "info_card", "title": "冒烟测试", "message": "结构检查通过"}}
    try:
        ak = amap_key or os.getenv("AMAP_WEB_SERVICE_KEY", "") or os.getenv("AMAP_API_KEY", "")
        bk = baidu_key or os.getenv("BAIDU_MAP_AK", "") or os.getenv("BAIDU_MAP_API_KEY", "")
        async with httpx.AsyncClient(timeout=9.0) as c:
            a = await _amap(c, ak, origin, destination, city); b = await _baidu(c, bk, origin, destination, city) if not a.get("ok") else {"ok": False}
        best = a if a.get("ok") else b
        if not best.get("ok"):
            ev = build_render_evidence_block(source="高德+百度", source_url=a.get("source_url") or "", evidence={"amap_error": a.get("error"), "baidu_error": b.get("error")}, references=[{"provider": "高德", "url": a.get("source_url")}, {"provider": "百度", "url": b.get("source_url")}])
            ui = attach_evidence_fields({"type": "info_card", "title": "地铁路线查询失败", "message": "高德和百度都未返回有效路线，请稍后再试。"}, source="高德+百度", source_url=a.get("source_url") or "", evidence={"amap_error": a.get("error"), "baidu_error": b.get("error")})
            return {"speak": "我暂时没查到可用路线，已把失败原因给你。", "render": f"出发地：{origin}\n目的地：{destination}\n{ev}", "ui": ui}
        route = " / ".join(best.get("lines") or []) or "见换乘信息"; hops = "；".join(best.get("hops") or []) or "无明显换乘提示"
        body = f"出发地：{best['from']}\n目的地：{best['to']}\n总时长：约{best['duration_min']}分钟\n路线简介：{route}\n换乘概览：{hops}\n步行约{best['walk_m']}米"
        ev = build_render_evidence_block(source=best["provider"], source_url=best["source_url"], evidence=best.get("evidence"), references=[{"key_fields": ["duration", "steps/segments", "walking_distance"]}])
        ui = attach_evidence_fields({"type": "info_card", "title": "深圳地铁出行估算", "message": body}, source=best["provider"], source_url=best["source_url"], evidence=best.get("evidence"))
        return {"speak": f"查到了，大约{best['duration_min']}分钟，主要线路是{route}。", "render": f"{body}\n{ev}", "ui": ui}
    except Exception as e:
        err = f"run_exception:{type(e).__name__}"
        return {"speak": "查询时出了点问题，我已返回可排查信息。", "render": build_render_evidence_block(source="runtime", evidence=err), "ui": {"type": "info_card", "title": "地铁查询异常", "message": err, "evidence": err}}

if __name__ == "__main__":
    x = asyncio.run(run(mock_data=True))
    assert isinstance(x, dict) and "speak" in x and "render" in x and "ui" in x
    print("OK")
