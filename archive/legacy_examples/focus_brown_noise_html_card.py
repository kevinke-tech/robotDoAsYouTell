"""一次性专注音频技能：前端生成白噪音/棕噪音播放器。"""

RUN_SPEC = {
    "name": "focus_brown_noise_html_card",
    "description": "生成可播放的专注噪音播放器（白噪音/棕噪音）。",
    "args_schema": {
        "type": "object",
        "properties": {
            "noise_type": {"type": "string", "enum": ["brown", "white"], "default": "brown"},
            "volume": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.35},
        },
        "required": [],
    },
}


async def run(noise_type: str = "brown", volume: float = 0.35, **kwargs):
    noise = noise_type if noise_type in {"brown", "white"} else "brown"
    vol = min(1.0, max(0.0, float(volume)))
    title = "专注棕噪音" if noise == "brown" else "专注白噪音"
    srcdoc = f"""<!doctype html><html><body style='margin:0;font-family:sans-serif;background:#0f172a;color:#e2e8f0'>
<div style='padding:16px;max-width:480px;margin:auto'><h3 style='margin:0 0 12px'>{title}</h3>
<p style='margin:0 0 12px;color:#94a3b8'>本页使用 Web Audio API 本地合成，无需外网。</p>
<button id='pp' style='padding:8px 14px;border:0;border-radius:10px;background:#22c55e;color:#052e16'>播放</button>
<label style='display:block;margin-top:10px'>音量 <input id='vol' type='range' min='0' max='1' step='0.01' value='{vol}'></label></div>
<script>
let ctx,node,gain,playing=false,last=0;
function makeNoise(type){{
  const b=ctx.createBuffer(1,ctx.sampleRate*2,ctx.sampleRate),d=b.getChannelData(0);let o=0;
  for(let i=0;i<d.length;i++){{const w=Math.random()*2-1;o=type==='brown'?(o+0.02*w)/1.02:w;d[i]=type==='brown'?o*3.5:o;}}
  const s=ctx.createBufferSource();s.buffer=b;s.loop=true;return s;
}}
function start(){{
  if(!ctx)ctx=new (window.AudioContext||window.webkitAudioContext)();
  if(node)node.stop(); node=makeNoise('{noise}'); gain=ctx.createGain(); gain.gain.value=parseFloat(document.getElementById('vol').value);
  node.connect(gain).connect(ctx.destination); node.start(); playing=true; pp.textContent='暂停';
}}
function stop(){{if(node)node.stop(); node=null; playing=false; pp.textContent='播放';}}
pp.onclick=()=>playing?stop():start();
vol.oninput=e=>{{if(gain)gain.gain.value=parseFloat(e.target.value);}};
</script></body></html>"""
    return {
        "speak": f"已为你准备好{title}，点播放就能开始专注。",
        "render": (
            f"source: Web Audio API (browser local synthesis)\n"
            f"evidence: noise_type={noise}, initial_volume={vol:.2f}, controls=play_pause+volume, network=none\n"
            f"说明: 音频由前端实时生成，可直接播放。"
        ),
        "ui": {"type": "html_card", "title": title, "srcdoc": srcdoc},
    }


if __name__ == "__main__":
    import asyncio

    res = asyncio.run(run(noise_type="brown", volume=0.4))
    assert isinstance(res, dict) and "speak" in res and "render" in res and "ui" in res
    assert res["ui"].get("type") == "html_card" and "source:" in res["render"]
    print("OK")
