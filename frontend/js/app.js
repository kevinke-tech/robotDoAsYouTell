/**
 * app.js — wires voice + camera + chat UI + /plan + /ws/output
 *
 * Flow per utterance:
 *   1. Voice.onSpeechEnd(wavBlob)
 *   2. POST /asr (wavBlob) → transcript
 *   3. Camera.snapshot() → base64 JPEG
 *   4. POST /plan { transcript, image_b64 } → { kind, speak, render }
 *   5. Render in chat log; if speak, Voice.speak(speak)
 *
 * WebSocket /ws/output reserved for phase 4 (watcher-initiated speech).
 */

(function () {
    "use strict";

    const BACKEND = "http://localhost:5001";
    const FRAMES_WS_URL = BACKEND.replace(/^http/, "ws") + "/ws/frames";
    const FRAMES_INTERVAL_MS = 1000;  // 1 fps to /ws/frames

    // ───── DOM ─────
    const chatLog = document.getElementById("chat-log");
    const textForm = document.getElementById("text-input-form");
    const textInput = document.getElementById("text-input");
    const micToggleBtn = document.getElementById("mic-toggle");
    const camToggleBtn = document.getElementById("cam-toggle");
    const statusDot = document.getElementById("status-dot");
    const statusText = document.getElementById("status-text");
    const snapshotTimeEl = document.getElementById("snapshot-time");
    const skillsListEl = document.getElementById("skills-list");
    const skillsRefreshBtn = document.getElementById("skills-refresh");

    // ───── chat rendering ─────
    function appendMessage(who, text) {
        const div = document.createElement("div");
        div.className = "msg " + who;
        const whoLine = document.createElement("div");
        whoLine.className = "who";
        whoLine.textContent = who;
        const body = document.createElement("div");
        body.textContent = text;
        div.appendChild(whoLine);
        div.appendChild(body);
        chatLog.appendChild(div);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    // ───── status indicator ─────
    const STATUS_ZH = {
        idle: "空闲",
        ready: "就绪",
        listening: "倾听中",
        processing: "处理中",
        speaking: "说话中",
        error: "错误",
        connecting: "连接中",
    };
    function setStatus(state, detail) {
        const cls = STATUS_ZH[state] ? state : "ready";
        statusDot.className = "dot " + cls;
        const zh = STATUS_ZH[state] || state;
        statusText.textContent = detail ? `${zh}: ${detail}` : zh;
    }

    // ───── /plan call ─────
    async function callPlan(transcript, imageB64) {
        const resp = await fetch(BACKEND + "/plan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ transcript, image_b64: imageB64 }),
        });
        if (!resp.ok) throw new Error(`/plan ${resp.status}: ${await resp.text()}`);
        return resp.json();
    }

    // ───── /asr call (returns text) ─────
    async function callAsr(wavBlob) {
        const resp = await fetch(BACKEND + "/asr", {
            method: "POST",
            headers: { "Content-Type": "application/octet-stream" },
            body: wavBlob,
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(`/asr error: ${data.error}`);
        return data.text || "";
    }

    // ───── core handler ─────
    async function handleUtterance(transcript) {
        if (!transcript) return;
        appendMessage("user", transcript);

        let imageB64 = null;
        try {
            imageB64 = await window.Camera.snapshot();
            if (imageB64) {
                snapshotTimeEl.textContent = new Date().toLocaleTimeString();
            }
        } catch (e) {
            console.warn("[app] camera snapshot failed:", e);
        }

        let plan;
        try {
            plan = await callPlan(transcript, imageB64);
        } catch (e) {
            console.error("[app] /plan failed:", e);
            appendMessage("agent", `[错误] ${e.message}`);
            return;
        }

        if (plan.render) appendMessage("agent", plan.render);
        if (plan.speak) await window.Voice.speak(plan.speak);
    }

    async function onSpeechEnd(wavBlob) {
        let transcript = "";
        try {
            transcript = await callAsr(wavBlob);
            console.log("[app] ASR transcript:", transcript);
        } catch (e) {
            console.error("[app] /asr failed:", e);
            appendMessage("agent", `[语音识别错误] ${e.message}`);
            return;
        }
        if (!transcript.trim()) {
            console.log("[app] empty transcript, skipping");
            return;
        }
        await handleUtterance(transcript.trim());
    }

    // ───── text-input fallback (works without mic) ─────
    textForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = textInput.value.trim();
        if (!text) return;
        textInput.value = "";
        await handleUtterance(text);
    });

    // ───── mic & cam toggle buttons ─────
    micToggleBtn.addEventListener("click", async () => {
        if (window.Voice.isActive()) {
            window.Voice.stop();
            micToggleBtn.textContent = "开启麦克风";
            micToggleBtn.classList.remove("active");
        } else {
            await window.Voice.start();
            micToggleBtn.textContent = "关闭麦克风";
            micToggleBtn.classList.add("active");
        }
    });

    camToggleBtn.addEventListener("click", async () => {
        if (window.Camera.isActive()) {
            window.Camera.stop();
            camToggleBtn.textContent = "开启摄像头";
        } else {
            try {
                await window.Camera.start("camera-preview");
                camToggleBtn.textContent = "关闭摄像头";
                if (needFrames) ensureFrameStream();
            } catch (e) {
                console.error("[app] camera start failed:", e);
                appendMessage("agent", `[摄像头错误] ${e.message}`);
            }
        }
    });

    // ───── alert tone (played before watcher-initiated TTS) ─────
    let toneCtx = null;
    function getToneCtx() {
        if (!toneCtx) toneCtx = new (window.AudioContext || window.webkitAudioContext)();
        return toneCtx;
    }
    function playAlertTone() {
        return new Promise((resolve) => {
            try {
                const ctx = getToneCtx();
                const t0 = ctx.currentTime;
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.setValueAtTime(880, t0);
                gain.gain.setValueAtTime(0.0001, t0);
                gain.gain.exponentialRampToValueAtTime(0.18, t0 + 0.02);
                gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.22);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(t0);
                osc.stop(t0 + 0.24);
                osc.onended = () => resolve();
            } catch (_) { resolve(); }
        });
    }

    async function handleWatcherFire(msg) {
        // Tone + interrupt: stop any current TTS, play tone, speak the message.
        // voice.speak() handles VAD suppression internally so we won't capture our own audio.
        window.Voice.stopTTS();
        appendMessage("agent", `🔔 ${msg.text}` + (msg.from ? `(来源: ${msg.from})` : ""));
        await playAlertTone();
        await window.Voice.speak(msg.text);
    }

    // ───── skills panel ─────
    async function fetchSkills() {
        try {
            const resp = await fetch(BACKEND + "/skills");
            if (!resp.ok) throw new Error(`${resp.status}`);
            const data = await resp.json();
            renderSkills(data.skills || []);
        } catch (e) {
            console.warn("[skills] fetch failed:", e);
            skillsListEl.innerHTML = `<li class="skills-empty">加载失败: ${e.message}</li>`;
        }
    }

    function renderSkills(skills) {
        if (!skills.length) {
            skillsListEl.innerHTML = `<li class="skills-empty">还没有技能 —— 让 vox 帮你建一个</li>`;
            return;
        }
        skillsListEl.innerHTML = "";
        for (const s of skills) {
            skillsListEl.appendChild(renderSkillRow(s));
        }
    }

    function renderSkillRow(s) {
        const li = document.createElement("li");
        li.className = "skill-row";

        const main = document.createElement("div");
        main.className = "skill-main";

        const body = document.createElement("div");
        body.className = "skill-body";
        const nameEl = document.createElement("div");
        nameEl.className = "skill-name";
        nameEl.textContent = s.name;
        body.appendChild(nameEl);
        if (s.description) {
            const descEl = document.createElement("div");
            descEl.className = "skill-desc";
            descEl.textContent = s.description;
            body.appendChild(descEl);
        }
        if (s.active_instances && s.active_instances.length > 0) {
            const ac = document.createElement("div");
            ac.className = "skill-active-count";
            const total = s.active_instances.length;
            const running = typeof s.running_count === "number"
                ? s.running_count
                : s.active_instances.filter(i => i && i.is_active).length;
            ac.textContent = running === total
                ? `● ${total} 个实例,全部运行中`
                : `● ${total} 个实例 (${running} 运行中, ${total - running} 已停)`;
            body.appendChild(ac);
        }

        const controls = document.createElement("div");
        controls.className = "skill-controls";

        const needsArgs = (s.required_args || []).length > 0;

        if (s.kind === "background") {
            const hint = document.createElement("span");
            hint.className = "skill-bg-hint";
            hint.textContent = needsArgs ? "用语音启动实例" : "可激活";
            hint.title = needsArgs
                ? `需要参数 (${s.required_args.join(", ")}) —— 请用语音激活,例如"看到X就说Y"。激活后,实例会显示在下面,可以单独勾选/取消。`
                : "可以用语音启动一个实例;实例会显示在下面,可单独勾选/取消。";
            controls.appendChild(hint);
        } else {
            const runBtn = document.createElement("button");
            runBtn.className = "skill-run";
            runBtn.textContent = "运行";
            runBtn.disabled = needsArgs;
            runBtn.title = needsArgs
                ? `需要参数: ${s.required_args.join(", ")} —— 请用语音调用`
                : "立即运行该技能";
            runBtn.addEventListener("click", () => onSkillRun(s, runBtn));
            controls.appendChild(runBtn);
        }

        const delBtn = document.createElement("button");
        delBtn.className = "skill-delete";
        delBtn.textContent = "✕";
        delBtn.title = "删除该技能(.py 文件)";
        delBtn.addEventListener("click", () => onSkillDelete(s));
        controls.appendChild(delBtn);

        main.appendChild(body);
        main.appendChild(controls);
        li.appendChild(main);

        const instances = (s.active_instances || []).filter(i => i && typeof i === "object");
        if (instances.length > 0) {
            const instList = document.createElement("ul");
            instList.className = "skill-instances";
            for (const inst of instances) {
                instList.appendChild(renderInstanceRow(s, inst));
            }
            li.appendChild(instList);
        }

        return li;
    }

    function renderInstanceRow(skill, inst) {
        const li = document.createElement("li");
        li.className = "skill-instance" + (inst.is_active ? "" : " inactive");

        const body = document.createElement("div");
        body.className = "inst-body";

        const idLine = document.createElement("div");
        idLine.className = "inst-id";
        const kindIcon = inst.kind === "vision" ? "👁" : (inst.kind === "timer" ? "⏰" : "•");
        const stateBadge = inst.is_active ? "" : "  [已停]";
        idLine.textContent = `${kindIcon} ${inst.id}${stateBadge}`;
        body.appendChild(idLine);

        const labelLine = document.createElement("div");
        labelLine.className = "inst-label";
        if (inst.kind === "vision") {
            const trig = inst.trigger || inst.label || "?";
            const say = inst.say_on_match || "";
            labelLine.textContent = say ? `${trig} → ${say}` : trig;
        } else if (inst.kind === "timer") {
            labelLine.textContent = inst.message || inst.label || "(无消息)";
        } else {
            labelLine.textContent = inst.label || "?";
        }
        body.appendChild(labelLine);

        const metaLine = document.createElement("div");
        metaLine.className = "inst-meta";
        const parts = [];
        if (inst.kind === "vision") {
            if (inst.cooldown_sec != null) parts.push(`冷却 ${inst.cooldown_sec}s`);
            if (inst.rate_hz != null) parts.push(`${inst.rate_hz} Hz`);
        } else if (inst.kind === "timer") {
            if (inst.is_active && inst.fire_at != null) {
                const remain = Math.max(0, Math.round(inst.fire_at - Date.now() / 1000));
                parts.push(remain > 0 ? `还有 ${remain} 秒` : "即将触发");
            } else if (inst.delay_seconds != null) {
                parts.push(`延时 ${inst.delay_seconds}s (再勾选即重新计时)`);
            }
        }
        if (inst.created_at) parts.push(`创建于 ${inst.created_at}`);
        metaLine.textContent = parts.join(" · ");
        if (metaLine.textContent) body.appendChild(metaLine);

        const label = document.createElement("label");
        label.className = "inst-toggle";
        label.title = inst.is_active
            ? "取消勾选 = 停掉这个实例(配置保留,可再次勾选启动)"
            : "勾选 = 重新启动这个实例";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = !!inst.is_active;
        cb.addEventListener("change", () => onInstanceToggle(skill, inst, cb));
        label.appendChild(cb);
        label.appendChild(document.createTextNode("激活"));

        const delBtn = document.createElement("button");
        delBtn.className = "inst-delete";
        delBtn.textContent = "✕";
        delBtn.title = "彻底删除这个实例(配置不保留)";
        delBtn.addEventListener("click", () => onInstanceDelete(skill, inst));

        li.appendChild(body);
        li.appendChild(label);
        li.appendChild(delBtn);
        return li;
    }

    async function onInstanceToggle(skill, inst, cb) {
        const desired = cb.checked;
        const path = desired ? "start" : "stop";
        const verb = desired ? "启动" : "停止";
        cb.disabled = true;
        try {
            const resp = await fetch(`${BACKEND}/instances/${encodeURIComponent(inst.id)}/${path}`, {
                method: "POST",
            });
            const data = await resp.json();
            if (!data.ok) {
                appendMessage("agent", `[${skill.name}] ${verb} ${inst.id} 失败: ${data.error || "未知错误"}`);
                cb.checked = !desired;
            }
        } catch (e) {
            appendMessage("agent", `[${skill.name}] ${verb} ${inst.id} 请求失败: ${e.message}`);
            cb.checked = !desired;
        } finally {
            cb.disabled = false;
            fetchSkills();
        }
    }

    async function onInstanceDelete(skill, inst) {
        if (!confirm(`彻底删除实例 ${inst.id}?\n(配置也会丢, 不可再次启动)`)) return;
        try {
            const resp = await fetch(`${BACKEND}/instances/${encodeURIComponent(inst.id)}`, {
                method: "DELETE",
            });
            const data = await resp.json();
            if (!data.ok) {
                appendMessage("agent", `[${skill.name}] 删除 ${inst.id} 失败: ${data.error || "未知错误"}`);
            }
        } catch (e) {
            appendMessage("agent", `[${skill.name}] 删除 ${inst.id} 请求失败: ${e.message}`);
        } finally {
            fetchSkills();
        }
    }

    async function onSkillRun(s, btn) {
        btn.disabled = true;
        try {
            const resp = await fetch(`${BACKEND}/skills/${encodeURIComponent(s.name)}/run`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ args: {} }),
            });
            const data = await resp.json();
            if (!data.ok) {
                appendMessage("agent", `[${s.name}] 错误: ${data.error || "运行失败"}`);
            } else {
                const r = data.result || {};
                if (r.render) appendMessage("agent", `[${s.name}] ${r.render}`);
            }
        } catch (e) {
            appendMessage("agent", `[${s.name}] 请求失败: ${e.message}`);
        } finally {
            btn.disabled = false;
            fetchSkills();
        }
    }

    async function onSkillDelete(s) {
        const msg = (s.active_instances && s.active_instances.length > 0)
            ? `确定删除技能 "${s.name}" 吗?\n这将停掉 ${s.active_instances.length} 个运行中的实例,并删除对应的 .py 文件。`
            : `确定删除技能 "${s.name}" 吗?\n这将从磁盘删除对应的 .py 文件。`;
        if (!confirm(msg)) return;
        try {
            const resp = await fetch(`${BACKEND}/skills/${encodeURIComponent(s.name)}`, {
                method: "DELETE",
            });
            const data = await resp.json();
            if (!data.ok) {
                appendMessage("agent", `[${s.name}] 删除失败: ${data.error || "未知错误"}`);
            }
        } catch (e) {
            appendMessage("agent", `[${s.name}] 删除请求失败: ${e.message}`);
        } finally {
            fetchSkills();
        }
    }

    skillsRefreshBtn.addEventListener("click", fetchSkills);

    // ───── /ws/output (watcher fires + frames_required signal) ─────
    let needFrames = false;
    function openOutputSocket() {
        const wsUrl = BACKEND.replace(/^http/, "ws") + "/ws/output";
        const ws = new WebSocket(wsUrl);
        ws.onopen = () => console.log("[app] /ws/output connected");
        ws.onclose = () => {
            console.log("[app] /ws/output closed, reconnecting in 3s");
            window.Camera.stopFrameStream();
            setTimeout(openOutputSocket, 3000);
        };
        ws.onerror = (e) => console.warn("[app] /ws/output error:", e);
        ws.onmessage = (e) => {
            let msg;
            try { msg = JSON.parse(e.data); }
            catch (_) { console.log("[app] /ws/output non-JSON:", e.data); return; }
            console.log("[app] /ws/output msg:", msg);

            if (msg.type === "hello") {
                needFrames = !!msg.frames_required;
                if (needFrames) ensureFrameStream();
                return;
            }
            if (msg.type === "frames_required") {
                needFrames = !!msg.value;
                if (needFrames) ensureFrameStream();
                else window.Camera.stopFrameStream();
                return;
            }
            if (msg.type === "speak" && msg.text) {
                handleWatcherFire(msg);
                return;
            }
            if (msg.type === "skills_changed") {
                fetchSkills();
                return;
            }
        };
    }

    function ensureFrameStream() {
        if (!window.Camera.isActive()) {
            appendMessage("agent", "[提示] 有视觉监视器在运行,但摄像头还没开 —— 点 \"开启摄像头\"。");
            return;
        }
        if (window.Camera.isStreaming()) return;
        window.Camera.startFrameStream(FRAMES_WS_URL, FRAMES_INTERVAL_MS);
    }

    // ───── init ─────
    function init() {
        window.Voice.setBackend(BACKEND);
        window.Voice.onStatus(setStatus);
        window.Voice.onSpeechEnd(onSpeechEnd);
        appendMessage("agent", "vox 已就绪。试试:\"现在几点\"、\"打开 Hacker News\"、\"30 秒后提醒我喝水\"、\"看到我挥手就告诉我\"。我也能现场为你写新技能 —— 想要的功能没有的话直接说。");
        setStatus("idle");
        openOutputSocket();
        fetchSkills();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
