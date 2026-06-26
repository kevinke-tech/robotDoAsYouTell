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
    const skillsDeleteAllBtn = document.getElementById("skills-delete-all");
    let awaitingSlotState = null;
    const SESSION_ID = (() => {
        const k = "vox_session_id";
        const old = localStorage.getItem(k);
        if (old) return old;
        const id = (window.crypto && window.crypto.randomUUID)
            ? window.crypto.randomUUID()
            : (`sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`);
        localStorage.setItem(k, id);
        return id;
    })();

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

    // ───── dynamic UI renderer registry ─────
    const UI_RENDERERS = Object.create(null);
    function registerUIRenderer(type, renderFn) {
        const key = String(type || "").trim().toLowerCase();
        if (!key || typeof renderFn !== "function") return;
        UI_RENDERERS[key] = renderFn;
    }

    registerUIRenderer("info_card", (ui, div) => {
        const title = document.createElement("div");
        title.className = "ui-title";
        title.textContent = ui.title || "信息";
        div.appendChild(title);
        if (ui.message || ui.text) {
            const text = document.createElement("div");
            text.className = "ui-meta";
            text.textContent = ui.message || ui.text;
            div.appendChild(text);
        }
    });

    registerUIRenderer("key_value", (ui, div) => {
        const title = document.createElement("div");
        title.className = "ui-title";
        title.textContent = ui.title || "详情";
        div.appendChild(title);
        const rows = Array.isArray(ui.items) ? ui.items : [];
        for (const it of rows) {
            const row = document.createElement("div");
            row.className = "ui-meta";
            row.textContent = `${it.key || "key"}: ${it.value || ""}`;
            div.appendChild(row);
        }
    });

    registerUIRenderer("image_card", (ui, div) => {
        const title = document.createElement("div");
        title.className = "ui-title";
        title.textContent = ui.title || "图片";
        div.appendChild(title);

        const imageUrl = String(ui.image_url || ui.imageUrl || ui.url || "").trim();
        if (!imageUrl) {
            const err = document.createElement("div");
            err.className = "ui-note";
            err.textContent = "image_card 缺少 image_url。";
            div.appendChild(err);
            return;
        }

        const img = document.createElement("img");
        img.src = imageUrl;
        img.alt = String(ui.alt || ui.caption || ui.title || "image");
        img.style.width = "100%";
        img.style.maxHeight = "420px";
        img.style.objectFit = "contain";
        img.style.borderRadius = "10px";
        img.style.border = "1px solid #333";
        img.style.background = "#111";
        img.loading = "lazy";
        div.appendChild(img);

        const caption = String(ui.caption || "").trim();
        if (caption) {
            const cap = document.createElement("div");
            cap.className = "ui-meta";
            cap.textContent = caption;
            div.appendChild(cap);
        }

        const sourceUrl = String(ui.source_url || ui.action_url || "").trim();
        if (sourceUrl) {
            const src = document.createElement("div");
            src.className = "ui-note";
            const a = document.createElement("a");
            a.href = sourceUrl;
            a.target = "_blank";
            a.rel = "noreferrer";
            a.textContent = "查看来源";
            src.appendChild(a);
            div.appendChild(src);
        }
    });

    registerUIRenderer("card_grid", (ui, div) => {
        const title = document.createElement("div");
        title.className = "ui-title";
        title.textContent = ui.title || "卡片列表";
        div.appendChild(title);

        const cards = Array.isArray(ui.cards) ? ui.cards : (Array.isArray(ui.items) ? ui.items : []);
        if (!cards.length) {
            const note = document.createElement("div");
            note.className = "ui-note";
            note.textContent = "card_grid 没有可展示内容。";
            div.appendChild(note);
            return;
        }

        const wrap = document.createElement("div");
        wrap.style.display = "grid";
        wrap.style.gridTemplateColumns = "repeat(auto-fill, minmax(180px, 1fr))";
        wrap.style.gap = "10px";
        for (const c of cards) {
            const item = document.createElement("div");
            item.style.border = "1px solid #333";
            item.style.borderRadius = "10px";
            item.style.padding = "8px";
            item.style.background = "#121212";

            const imgUrl = String(c.image_url || c.thumbnail || "").trim();
            if (imgUrl) {
                const img = document.createElement("img");
                img.src = imgUrl;
                img.alt = String(c.title || "card");
                img.style.width = "100%";
                img.style.height = "110px";
                img.style.objectFit = "cover";
                img.style.borderRadius = "8px";
                item.appendChild(img);
            }

            const tt = document.createElement("div");
            tt.className = "ui-meta";
            tt.style.marginTop = "6px";
            tt.textContent = String(c.title || "未命名");
            item.appendChild(tt);

            const sub = String(c.subtitle || c.description || "").trim();
            if (sub) {
                const subEl = document.createElement("div");
                subEl.className = "ui-note";
                subEl.textContent = sub;
                item.appendChild(subEl);
            }

            const action = String(c.action_url || c.url || "").trim();
            if (action) {
                const a = document.createElement("a");
                a.href = action;
                a.target = "_blank";
                a.rel = "noreferrer";
                a.textContent = "打开";
                a.className = "ui-note";
                item.appendChild(a);
            }
            wrap.appendChild(item);
        }
        div.appendChild(wrap);
    });

    registerUIRenderer("iframe_card", (ui, div) => {
        const title = document.createElement("div");
        title.className = "ui-title";
        title.textContent = ui.title || "内嵌内容";
        div.appendChild(title);

        const iframeUrl = String(ui.iframe_url || ui.url || "").trim();
        if (!iframeUrl) {
            const err = document.createElement("div");
            err.className = "ui-note";
            err.textContent = "iframe_card 缺少 iframe_url。";
            div.appendChild(err);
            return;
        }
        const frame = document.createElement("iframe");
        frame.src = iframeUrl;
        frame.style.width = "100%";
        frame.style.height = `${Math.max(220, Math.min(720, Number(ui.height || 380)))}px`;
        frame.style.border = "1px solid #333";
        frame.style.borderRadius = "10px";
        frame.setAttribute("allow", "autoplay; fullscreen");
        frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms allow-popups");
        div.appendChild(frame);
    });

    registerUIRenderer("html_card", (ui, div) => {
        const title = document.createElement("div");
        title.className = "ui-title";
        title.textContent = ui.title || "动态卡片";
        div.appendChild(title);

        const html = String(ui.html || "").trim();
        const css = String(ui.css || "").trim();
        const js = String(ui.js || "").trim();
        const srcdoc = String(ui.srcdoc || "").trim();

        if (!html && !srcdoc && !js) {
            const err = document.createElement("div");
            err.className = "ui-note";
            err.textContent = "html_card 缺少可渲染内容（需要 html/srcdoc/js 之一）。";
            div.appendChild(err);
            return;
        }

        const frame = document.createElement("iframe");
        frame.className = "ui-html-card";
        frame.style.width = "100%";
        const h = Number(ui.height || 260);
        const height = Number.isFinite(h) ? Math.max(120, Math.min(720, h)) : 260;
        frame.style.height = `${height}px`;
        frame.style.border = "1px solid #333";
        frame.style.borderRadius = "10px";
        frame.style.background = "#0f0f0f";
        frame.setAttribute("sandbox", "allow-scripts allow-same-origin");
        frame.setAttribute("allow", "autoplay");

        if (srcdoc) {
            frame.srcdoc = srcdoc;
        } else {
            frame.srcdoc = [
                "<!doctype html><html><head><meta charset=\"utf-8\"/>",
                "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/>",
                `<style>html,body{margin:0;padding:0;background:#0f0f0f;color:#eee;font-family:system-ui} ${css}</style>`,
                "</head><body>",
                html,
                `<script>${js}<\/script>`,
                "</body></html>",
            ].join("");
        }

        div.appendChild(frame);

        if (ui.source || ui.source_url) {
            const src = document.createElement("div");
            src.className = "ui-note";
            const sourceText = ui.source ? `Source: ${ui.source}` : "Source";
            if (ui.source_url) {
                const a = document.createElement("a");
                a.href = ui.source_url;
                a.target = "_blank";
                a.rel = "noreferrer";
                a.textContent = sourceText;
                src.appendChild(a);
            } else {
                src.textContent = sourceText;
            }
            div.appendChild(src);
        }
    });

    function reportMediaPlaybackFailure(payload) {
        fetch(BACKEND + "/feedback/media_playback_failure", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: SESSION_ID,
                skill: payload.skill || "",
                ui_type: payload.ui_type || "",
                media_url: payload.media_url || "",
                error: payload.error || "unknown playback error",
            }),
        }).catch(() => {});
    }

    function appendUICard(ui, meta = {}) {
        if (!ui || typeof ui !== "object") return;
        const uiType = String(ui.type || "").trim().toLowerCase();
        const skillName = String(meta.skill || ui.skill || ui.skill_name || "").trim();
        const div = document.createElement("div");
        div.className = "msg agent ui-card";
        div.dataset.uiType = uiType || "unknown";
        if (skillName) div.dataset.skill = skillName;
        const whoLine = document.createElement("div");
        whoLine.className = "who";
        whoLine.textContent = "agent-ui";
        div.appendChild(whoLine);

        const customRenderer = UI_RENDERERS[uiType];
        if (customRenderer) {
            try {
                customRenderer(ui, div);
            } catch (e) {
                const err = document.createElement("div");
                err.className = "ui-note";
                err.textContent = `UI render error: ${e.message}`;
                div.appendChild(err);
            }
            chatLog.appendChild(div);
            chatLog.scrollTop = chatLog.scrollHeight;
            return;
        }

        if (uiType === "music_player") {
            const title = document.createElement("div");
            title.className = "ui-title";
            title.textContent = ui.title || "Music Player";
            div.appendChild(title);

            const meta = document.createElement("div");
            meta.className = "ui-meta";
            meta.textContent = `${ui.track || "Unknown"} — ${ui.artist || "Unknown Artist"}`;
            div.appendChild(meta);

            const audio = document.createElement("audio");
            audio.controls = true;
            audio.autoplay = true;
            audio.loop = !!ui.loop;
            audio.preload = "auto";
            audio.src = ui.audio_url || "";
            audio.className = "ui-audio";
            div.appendChild(audio);
            let mediaFailureReported = false;
            const reportFailureOnce = (reason) => {
                if (mediaFailureReported) return;
                mediaFailureReported = true;
                reportMediaPlaybackFailure({
                    skill: skillName,
                    ui_type: "music_player",
                    media_url: audio.src || "",
                    error: reason || "audio playback failed",
                });
            };
            audio.addEventListener("error", () => {
                reportFailureOnce("audio element error event");
            });

            const status = document.createElement("div");
            status.className = "ui-note";
            status.textContent = "Starting playback...";
            div.appendChild(status);

            const retry = document.createElement("button");
            retry.textContent = "Tap to start audio";
            retry.className = "ui-btn";
            retry.addEventListener("click", async () => {
                try {
                    await audio.play();
                    status.textContent = "Playing in loop.";
                } catch (e) {
                    status.textContent = "Play failed. Please try again.";
                    reportFailureOnce(`manual play failed: ${e && e.message ? e.message : "unknown"}`);
                }
            });
            div.appendChild(retry);

            audio.play().then(() => {
                status.textContent = "Playing in loop.";
            }).catch(() => {
                status.textContent = "Autoplay blocked. Click the button to start audio.";
            });

            if (ui.source || ui.source_url) {
                const src = document.createElement("div");
                src.className = "ui-note";
                const sourceText = ui.source ? `Source: ${ui.source}` : "Source";
                if (ui.source_url) {
                    const a = document.createElement("a");
                    a.href = ui.source_url;
                    a.target = "_blank";
                    a.rel = "noreferrer";
                    a.textContent = sourceText;
                    src.appendChild(a);
                } else {
                    src.textContent = sourceText;
                }
                div.appendChild(src);
            }
        } else if (uiType === "video_player") {
            const title = document.createElement("div");
            title.className = "ui-title";
            title.textContent = ui.title || "Video Player";
            div.appendChild(title);

            const meta = document.createElement("div");
            meta.className = "ui-meta";
            meta.textContent = ui.video_title || "Untitled video";
            div.appendChild(meta);

            const video = document.createElement("video");
            video.controls = true;
            video.autoplay = ui.autoplay !== false;
            video.loop = !!ui.loop;
            video.preload = "metadata";
            video.src = ui.video_url || ui.videoUrl || ui.url || "";
            video.className = "ui-audio";
            div.appendChild(video);
            let mediaFailureReported = false;
            const reportFailureOnce = (reason) => {
                if (mediaFailureReported) return;
                mediaFailureReported = true;
                reportMediaPlaybackFailure({
                    skill: skillName,
                    ui_type: "video_player",
                    media_url: video.src || "",
                    error: reason || "video playback failed",
                });
            };
            video.addEventListener("error", () => {
                reportFailureOnce("video element error event");
            });

            const status = document.createElement("div");
            status.className = "ui-note";
            status.textContent = "Loading video...";
            div.appendChild(status);

            const retry = document.createElement("button");
            retry.textContent = "Tap to play video";
            retry.className = "ui-btn";
            retry.addEventListener("click", async () => {
                try {
                    await video.play();
                    status.textContent = "Playing.";
                } catch (e) {
                    status.textContent = "Play failed. Please try again.";
                    reportFailureOnce(`manual play failed: ${e && e.message ? e.message : "unknown"}`);
                }
            });
            div.appendChild(retry);

            video.play().then(() => {
                status.textContent = "Playing.";
            }).catch(() => {
                status.textContent = "Autoplay blocked. Click the button to start.";
            });

            if (ui.source || ui.source_url) {
                const src = document.createElement("div");
                src.className = "ui-note";
                const sourceText = ui.source ? `Source: ${ui.source}` : "Source";
                if (ui.source_url) {
                    const a = document.createElement("a");
                    a.href = ui.source_url;
                    a.target = "_blank";
                    a.rel = "noreferrer";
                    a.textContent = sourceText;
                    src.appendChild(a);
                } else {
                    src.textContent = sourceText;
                }
                div.appendChild(src);
            }
        } else if (uiType === "awaiting_slot") {
            awaitingSlotState = {
                slot: ui.slot || "slot",
                question: ui.question || "",
                canCancel: ui.can_cancel !== false,
            };
            const title = document.createElement("div");
            title.className = "ui-title";
            title.textContent = ui.title || "等待补充信息";
            div.appendChild(title);

            const q = document.createElement("div");
            q.className = "ui-meta";
            q.textContent = ui.question || "请补充必要信息。";
            div.appendChild(q);

            const hint = document.createElement("div");
            hint.className = "ui-note";
            hint.textContent = `当前等待字段: ${ui.slot || "slot"}。你可以直接说答案，或取消本次等待。`;
            div.appendChild(hint);

            if (awaitingSlotState.canCancel) {
                const cancelBtn = document.createElement("button");
                cancelBtn.className = "ui-btn";
                cancelBtn.textContent = "取消本轮等待";
                cancelBtn.addEventListener("click", async () => {
                    cancelBtn.disabled = true;
                    try {
                        const resp = await fetch(BACKEND + "/queue/cancel", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ session_id: SESSION_ID }),
                        });
                        const data = await resp.json();
                        if (data && data.ok) {
                            appendMessage("agent", "[进展] 已取消等待，你可以直接说新任务。");
                        } else {
                            appendMessage("agent", `[错误] 取消失败: ${(data && data.error) || "未知错误"}`);
                        }
                    } catch (e) {
                        appendMessage("agent", `[错误] 取消请求失败: ${e.message}`);
                    } finally {
                        cancelBtn.disabled = false;
                    }
                });
                div.appendChild(cancelBtn);
            }
        } else {
            const fallback = document.createElement("div");
            fallback.textContent = `[ui] unsupported type: ${ui.type || "unknown"}`;
            div.appendChild(fallback);
        }

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
            body: JSON.stringify({ transcript, image_b64: imageB64, session_id: SESSION_ID }),
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
        const uiCards = Array.isArray(plan.ui_cards) ? plan.ui_cards : (plan.ui ? [plan.ui] : []);
        for (const ui of uiCards) appendUICard(ui, { skill: plan.skill || "" });
        if (plan.speak) await window.Voice.speak(plan.speak, plan.tts || {});
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
        appendMessage("agent", `🔔 ${msg.text}`);
        if (msg.ui && typeof msg.ui === "object") {
            appendUICard(msg.ui, { skill: msg.from || "" });
        }
        await playAlertTone();
        await window.Voice.speak(msg.text, msg.tts || {});
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
        const bp = (s.behavior_preview && typeof s.behavior_preview === "object") ? s.behavior_preview : null;
        if (bp) {
            if (bp.watch_for) {
                const watchEl = document.createElement("div");
                watchEl.className = "skill-desc";
                watchEl.textContent = `触发条件: ${bp.watch_for}`;
                body.appendChild(watchEl);
            }
            if (bp.delay_seconds != null && bp.delay_seconds !== "") {
                const delayEl = document.createElement("div");
                delayEl.className = "skill-desc";
                delayEl.textContent = `定时: ${bp.delay_seconds} 秒后触发`;
                body.appendChild(delayEl);
            }
            if (bp.on_trigger) {
                const onEl = document.createElement("div");
                onEl.className = "skill-desc";
                onEl.textContent = `触发后动作: ${bp.on_trigger}`;
                body.appendChild(onEl);
            } else if (bp.summary) {
                const sumEl = document.createElement("div");
                sumEl.className = "skill-desc";
                sumEl.textContent = `行为说明: ${bp.summary}`;
                body.appendChild(sumEl);
            }
        }
        const stateEl = document.createElement("div");
        stateEl.className = "skill-active-count";
        stateEl.textContent = s.is_active ? "● 激活中" : "○ 未激活";
        body.appendChild(stateEl);

        const manifest = (s.manifest && typeof s.manifest === "object") ? s.manifest : {};
        const qualityState = String(s.quality_state || manifest.quality_state || "active").toLowerCase();
        const qualityLabel = (
            qualityState === "degraded" ? "degraded" :
            qualityState === "draft" ? "draft" : "active"
        );
        const qualityLine = document.createElement("div");
        qualityLine.className = "skill-desc";
        qualityLine.textContent = `质量状态: ${qualityLabel}`;
        body.appendChild(qualityLine);

        if (manifest.quality_reason) {
            const reasonLine = document.createElement("div");
            reasonLine.className = "skill-desc";
            reasonLine.textContent = `质量说明: ${manifest.quality_reason}`;
            body.appendChild(reasonLine);
        }
        if (Array.isArray(manifest.last_validation_reasons) && manifest.last_validation_reasons.length > 0) {
            const vrLine = document.createElement("div");
            vrLine.className = "skill-desc";
            vrLine.textContent = `最近验收失败: ${manifest.last_validation_reasons.join(" ; ")}`;
            body.appendChild(vrLine);
        }

        if (s.kind !== "background") {
            const hint = document.createElement("div");
            hint.className = "skill-desc";
            hint.textContent = "one-shot: 激活执行一次后会自动回到未激活。";
            body.appendChild(hint);
        }

        const controls = document.createElement("div");
        controls.className = "skill-controls";
        const label = document.createElement("label");
        label.className = "inst-toggle";
        label.title = s.is_active ? "取消激活技能" : "激活技能";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = !!s.is_active;
        cb.addEventListener("change", () => onSkillToggle(s, cb));
        label.appendChild(cb);
        label.appendChild(document.createTextNode("激活"));
        controls.appendChild(label);

        const delBtn = document.createElement("button");
        delBtn.className = "skill-delete";
        delBtn.textContent = "✕";
        delBtn.title = "删除该技能(.py 文件)";
        delBtn.addEventListener("click", () => onSkillDelete(s));
        controls.appendChild(delBtn);

        main.appendChild(body);
        main.appendChild(controls);
        li.appendChild(main);

        return li;
    }

    function coerceInputValue(raw) {
        const v = (raw || "").trim();
        if (!v) return "";
        if (v === "true") return true;
        if (v === "false") return false;
        if (!Number.isNaN(Number(v)) && /^-?\d+(\.\d+)?$/.test(v)) return Number(v);
        if ((v.startsWith("{") && v.endsWith("}")) || (v.startsWith("[") && v.endsWith("]"))) {
            try { return JSON.parse(v); } catch (_) { return v; }
        }
        return v;
    }

    function collectRequiredArgs(skill) {
        const required = skill.required_args || [];
        const args = {};
        for (const key of required) {
            const raw = prompt(`[${skill.name}] 请输入参数 ${key}`, "");
            if (raw === null) return null;
            args[key] = coerceInputValue(raw);
        }
        return args;
    }

    async function onSkillToggle(s, cb) {
        const desired = cb.checked;
        cb.disabled = true;
        try {
            const path = desired ? "activate" : "deactivate";
            let payload = {};
            if (desired && (s.required_args || []).length > 0) {
                const picked = collectRequiredArgs(s);
                if (picked === null) {
                    cb.checked = !desired;
                    return;
                }
                payload.args = picked;
            }
            const resp = await fetch(`${BACKEND}/skills/${encodeURIComponent(s.name)}/${path}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();
            if (!data.ok) {
                appendMessage("agent", `[${s.name}] ${desired ? "激活" : "停用"}失败: ${data.error || "未知错误"}`);
                cb.checked = !desired;
                return;
            }
            const r = data.result || {};
            if (r.render) appendMessage("agent", `[${s.name}] ${r.render}`);
            if (r.ui) appendUICard(r.ui, { skill: s.name });
            if (r.speak) {
                await window.Voice.speak(r.speak, r.tts || {});
            }
        } catch (e) {
            appendMessage("agent", `[${s.name}] ${desired ? "激活" : "停用"}请求失败: ${e.message}`);
            cb.checked = !desired;
        } finally {
            cb.disabled = false;
            fetchSkills();
        }
    }

    async function onSkillDelete(s) {
        const msg = `确定删除技能 "${s.name}" 吗?\n这将停掉该技能的运行并删除对应 .py 文件。`;
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

    async function onDeleteAllSkills() {
        let skills = [];
        try {
            const resp = await fetch(BACKEND + "/skills");
            if (!resp.ok) throw new Error(`${resp.status}`);
            const data = await resp.json();
            skills = Array.isArray(data.skills) ? data.skills : [];
        } catch (e) {
            appendMessage("agent", `[技能批量删除] 获取技能列表失败: ${e.message}`);
            return;
        }
        if (!skills.length) {
            appendMessage("agent", "[技能批量删除] 当前没有可删除的技能。");
            return;
        }

        const ok = confirm(
            `确定删除全部技能吗?\n将删除 ${skills.length} 个技能文件，并停掉关联运行实例。`
        );
        if (!ok) return;

        if (skillsDeleteAllBtn) skillsDeleteAllBtn.disabled = true;
        const failed = [];
        try {
            for (const s of skills) {
                try {
                    const resp = await fetch(`${BACKEND}/skills/${encodeURIComponent(s.name)}`, {
                        method: "DELETE",
                    });
                    const data = await resp.json();
                    if (!data.ok) failed.push(`${s.name}: ${data.error || "未知错误"}`);
                } catch (e) {
                    failed.push(`${s.name}: ${e.message}`);
                }
            }
            const success = skills.length - failed.length;
            if (failed.length === 0) {
                appendMessage("agent", `[技能批量删除] 已删除 ${success} 个技能。`);
            } else {
                appendMessage("agent", `[技能批量删除] 已删除 ${success}/${skills.length}，失败 ${failed.length} 个。`);
            }
        } finally {
            if (skillsDeleteAllBtn) skillsDeleteAllBtn.disabled = false;
            fetchSkills();
        }
    }

    skillsRefreshBtn.addEventListener("click", fetchSkills);
    if (skillsDeleteAllBtn) {
        skillsDeleteAllBtn.addEventListener("click", onDeleteAllSkills);
    }

    // ───── /ws/output (watcher fires + frames_required signal) ─────
    let needFrames = false;
    function openOutputSocket() {
        const wsUrl = BACKEND.replace(/^http/, "ws") + `/ws/output?session_id=${encodeURIComponent(SESSION_ID)}`;
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
            if (msg.session_id && msg.session_id !== SESSION_ID) return;

            if (msg.type === "hello") {
                needFrames = !!msg.frames_required;
                if (needFrames) ensureFrameStream();
                if (msg.awaiting_slot) {
                    appendUICard({
                        type: "awaiting_slot",
                        title: "等待补充信息",
                        slot: msg.awaiting_slot,
                        question: `请补充: ${msg.awaiting_slot}`,
                        can_cancel: true,
                    });
                }
                return;
            }
            if (msg.type === "frames_required") {
                needFrames = !!msg.value;
                if (needFrames) ensureFrameStream();
                else window.Camera.stopFrameStream();
                return;
            }
            if (msg.type === "watcher_fire" && msg.text) {
                handleWatcherFire(msg);
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
            if (msg.type === "progress" && msg.text) {
                appendMessage("agent", `[进展] ${msg.text}`);
                return;
            }
            if (msg.type === "awaiting_slot") {
                if (msg.active) {
                    appendUICard({
                        type: "awaiting_slot",
                        title: "等待补充信息",
                        slot: msg.slot || "slot",
                        question: msg.question || "请补充必要信息。",
                        can_cancel: true,
                    });
                } else if (awaitingSlotState) {
                    awaitingSlotState = null;
                    appendMessage("agent", "[进展] 等待补充信息已结束。");
                }
                return;
            }
            if (msg.type === "planner_queue_progress") {
                const idx = msg.index || "?";
                const total = msg.total || "?";
                const act = msg.action_type || "action";
                const st = msg.status || "running";
                appendMessage("agent", `[进展] ${idx}/${total} ${act} -> ${st}`);
                return;
            }
        };
    }

    function ensureFrameStream() {
        if (!window.Camera.isActive()) {
            appendMessage("agent", "[提示] 有视觉条件任务在运行，但摄像头还没开 —— 点 \"开启摄像头\"。");
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
