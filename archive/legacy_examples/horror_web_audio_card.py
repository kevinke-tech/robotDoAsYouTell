"""一次性技能：注入 Web Audio 恐怖氛围音乐卡片并自动播放。"""

RUN_SPEC = {
    "name": "horror_web_audio_card",
    "description": "在前端注入可自动播放的恐怖氛围音乐 Web Audio 卡片。",
    "args_schema": {"type": "object", "properties": {}, "required": []},
}


async def run(**kwargs):
    html = (
        '<div id="horror-card"><div class="title">恐怖音乐 💀</div>'
        '<button id="horror-toggle" class="pulse">STOP</button>'
        '<div id="horror-state">播放中</div></div>'
    )
    css = (
        "#horror-card{background:#120607;color:#f8eaea;border:1px solid #5a0f15;border-radius:14px;padding:14px;"
        "font-family:system-ui}#horror-card .title{font-size:18px;font-weight:700;color:#ff4d5f}"
        "#horror-toggle{margin-top:10px;background:#2a0a0d;color:#ffd7db;border:1px solid #8b1a26;border-radius:10px;"
        "padding:8px 14px;cursor:pointer}#horror-state{margin-top:8px;color:#ff9ca7}"
        ".pulse{animation:pulse 1.8s infinite}@keyframes pulse{0%,100%{box-shadow:0 0 0 0 #7a1422}50%{box-shadow:0 0 0 10px #7a142200}}"
    )
    js = r"""
(()=>{const d=document,c=d.getElementById("horror-card");if(!c||c.dataset.bound)return;c.dataset.bound="1";
let ctx,mix,master,delay,stopped=true,timers=[];const b=d.getElementById("horror-toggle"),s=d.getElementById("horror-state");
const ir=()=>{const n=ctx.sampleRate*1.8,buf=ctx.createBuffer(2,n,ctx.sampleRate);for(let ch=0;ch<2;ch++){const x=buf.getChannelData(ch);for(let i=0;i<n;i++)x[i]=(Math.random()*2-1)*Math.exp(-i/(n*0.18));}return buf;};
const note=(f,t,dur,tg,w="sine",g=.08)=>{const o=ctx.createOscillator(),gn=ctx.createGain(),lp=ctx.createBiquadFilter();o.type=w;o.frequency.setValueAtTime(f,t);if(tg) o.frequency.exponentialRampToValueAtTime(tg,t+dur);
lp.type="lowpass";lp.frequency.value=1800;gn.gain.setValueAtTime(.0001,t);gn.gain.exponentialRampToValueAtTime(g,t+.03);gn.gain.exponentialRampToValueAtTime(.0001,t+dur);o.connect(lp).connect(gn).connect(mix);o.start(t);o.stop(t+dur+.1);};
const stab=(t)=>{const o=ctx.createOscillator(),g=ctx.createGain(),bp=ctx.createBiquadFilter();o.type="sawtooth";o.frequency.setValueAtTime(120,t);o.frequency.exponentialRampToValueAtTime(900,t+.08);bp.type="bandpass";bp.frequency.value=700;
g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.35,t+.01);g.gain.exponentialRampToValueAtTime(.0001,t+.35);o.connect(bp).connect(g).connect(mix);o.start(t);o.stop(t+.45);};
const loop=()=>{if(stopped)return;const n=ctx.currentTime+.05;note(46,n,7,42,"triangle",.13);note(92,n+.2,6,87,"sine",.06);note(277,n+1.2,3.4,261,"sawtooth",.04);
if(Math.random()<.42)stab(n+2+Math.random()*2.2);timers.push(setTimeout(loop,4600+Math.random()*2200));};
const start=async()=>{if(!ctx){ctx=new(window.AudioContext||window.webkitAudioContext)();mix=ctx.createGain();master=ctx.createGain();delay=ctx.createDelay(1.2);const fb=ctx.createGain(),wet=ctx.createGain(),conv=ctx.createConvolver();
conv.buffer=ir();mix.gain.value=.8;master.gain.value=.52;delay.delayTime.value=.34;fb.gain.value=.38;wet.gain.value=.3;mix.connect(master).connect(ctx.destination);mix.connect(delay).connect(fb).connect(delay);delay.connect(wet).connect(master);mix.connect(conv);conv.connect(wet);}
stopped=false;await ctx.resume();b.textContent="STOP";s.textContent="播放中";b.classList.add("pulse");loop();};
const stop=()=>{stopped=true;timers.forEach(clearTimeout);timers=[];if(master)master.gain.setTargetAtTime(.0001,ctx.currentTime,.12);b.textContent="PLAY";s.textContent="已停止";b.classList.remove("pulse");};
b.onclick=()=>stopped?start():stop();start();})();
"""
    return {
        "speak": "恐怖氛围音乐已经开始播放，你可以随时点按钮暂停或继续。",
        "render": "source: Web Audio API (OscillatorNode/GainNode/BiquadFilterNode/ConvolverNode/DelayNode)\n"
        "evidence: 已注入深沉低频 drone、不协和高频弦音、随机突发音、回声混响与暗色氛围垫，并默认自动播放。",
        "ui": {"type": "html_card", "title": "恐怖音乐", "html": html, "css": css, "js": js, "source": "browser_web_audio"},
    }


if __name__ == "__main__":
    import asyncio

    out = asyncio.run(run())
    assert isinstance(out, dict) and "speak" in out and "render" in out and out.get("ui", {}).get("js")
    print("OK")
