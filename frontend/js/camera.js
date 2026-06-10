/**
 * camera.js — always-on camera preview + snapshot-on-demand
 *
 * Exposes window.Camera with:
 *   start(videoElId)   — request getUserMedia, attach to <video> element
 *   stop()             — release the stream
 *   snapshot()         — Promise<string> base64 JPEG (no data: prefix), of the current preview frame
 *   startFrameStream(wsUrl, intervalMs)   — open /ws/frames and push snapshots at the given rate
 *   stopFrameStream()  — close the frame stream
 *   isStreaming()
 *   isActive()
 *   setQuality(0..1)   — JPEG quality (default 0.8)
 *   setMaxDim(px)      — downscale longest edge before encoding (default 1024)
 */

(function () {
    "use strict";

    let stream = null;
    let videoEl = null;
    let canvas = null;
    let active = false;
    let quality = 0.8;
    let maxDim = 1024;

    // Frame streaming state
    let frameWs = null;
    let frameTimer = null;
    let frameMaxDim = 640;       // smaller frames over WS to keep bandwidth low
    let frameQuality = 0.6;

    async function start(videoElId) {
        if (active) return;
        videoEl = document.getElementById(videoElId);
        if (!videoEl) {
            throw new Error(`camera: no element with id "${videoElId}"`);
        }
        stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
            audio: false,
        });
        videoEl.srcObject = stream;
        await videoEl.play().catch(() => {});
        active = true;
        console.log("[camera] started");
    }

    function stop() {
        if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
        if (videoEl) videoEl.srcObject = null;
        active = false;
        console.log("[camera] stopped");
    }

    function snapshot() {
        return new Promise((resolve, reject) => {
            if (!active || !videoEl || !videoEl.videoWidth) {
                resolve(null); // no frame available
                return;
            }
            const vw = videoEl.videoWidth;
            const vh = videoEl.videoHeight;
            const scale = Math.min(1, maxDim / Math.max(vw, vh));
            const w = Math.round(vw * scale);
            const h = Math.round(vh * scale);

            if (!canvas) canvas = document.createElement("canvas");
            canvas.width = w;
            canvas.height = h;
            const ctx = canvas.getContext("2d");
            ctx.drawImage(videoEl, 0, 0, w, h);
            canvas.toBlob(
                (blob) => {
                    if (!blob) { reject(new Error("canvas.toBlob returned null")); return; }
                    const reader = new FileReader();
                    reader.onload = () => {
                        const dataUrl = reader.result; // "data:image/jpeg;base64,..."
                        const b64 = dataUrl.split(",")[1];
                        resolve(b64);
                    };
                    reader.onerror = reject;
                    reader.readAsDataURL(blob);
                },
                "image/jpeg",
                quality,
            );
        });
    }

    // ───── frame stream (for vision watchers) ─────
    function captureStreamFrame() {
        return new Promise((resolve) => {
            if (!active || !videoEl || !videoEl.videoWidth) { resolve(null); return; }
            const vw = videoEl.videoWidth;
            const vh = videoEl.videoHeight;
            const scale = Math.min(1, frameMaxDim / Math.max(vw, vh));
            const w = Math.round(vw * scale);
            const h = Math.round(vh * scale);
            if (!canvas) canvas = document.createElement("canvas");
            canvas.width = w;
            canvas.height = h;
            const ctx = canvas.getContext("2d");
            ctx.drawImage(videoEl, 0, 0, w, h);
            canvas.toBlob(
                (blob) => {
                    if (!blob) { resolve(null); return; }
                    const r = new FileReader();
                    r.onload = () => resolve(r.result.split(",")[1]);
                    r.onerror = () => resolve(null);
                    r.readAsDataURL(blob);
                },
                "image/jpeg",
                frameQuality,
            );
        });
    }

    async function pushOneFrame() {
        if (!frameWs || frameWs.readyState !== WebSocket.OPEN) return;
        if (!active) return;
        const b64 = await captureStreamFrame();
        if (!b64) return;
        try {
            frameWs.send(JSON.stringify({ type: "frame", image_b64: b64 }));
        } catch (e) {
            console.warn("[camera] frame send failed:", e);
        }
    }

    function startFrameStream(wsUrl, intervalMs = 1000) {
        if (frameWs && frameWs.readyState === WebSocket.OPEN) {
            console.log("[camera] frame stream already running");
            return;
        }
        frameWs = new WebSocket(wsUrl);
        frameWs.onopen = () => {
            console.log("[camera] frame stream opened →", wsUrl, intervalMs + "ms");
            if (frameTimer) clearInterval(frameTimer);
            frameTimer = setInterval(pushOneFrame, intervalMs);
        };
        frameWs.onclose = () => {
            console.log("[camera] frame stream closed");
            if (frameTimer) { clearInterval(frameTimer); frameTimer = null; }
            frameWs = null;
        };
        frameWs.onerror = (e) => console.warn("[camera] frame stream error:", e);
    }

    function stopFrameStream() {
        if (frameTimer) { clearInterval(frameTimer); frameTimer = null; }
        if (frameWs) {
            try { frameWs.close(); } catch (_) {}
            frameWs = null;
        }
    }

    window.Camera = {
        start,
        stop,
        snapshot,
        startFrameStream,
        stopFrameStream,
        isStreaming: () => !!(frameWs && frameWs.readyState === WebSocket.OPEN),
        isActive: () => active,
        setQuality(q) { quality = Math.max(0.1, Math.min(1, q)); },
        setMaxDim(d) { maxDim = Math.max(64, d); },
    };
})();
