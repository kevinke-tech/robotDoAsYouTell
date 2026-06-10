/**
 * voice.js — adaptive VAD + recording, ported from vui's voice-doubao.js
 *
 * Exposes window.Voice with:
 *   start() / stop() / toggle()        — control mic capture
 *   onSpeechEnd(handler)               — register async (wavBlob) => void callback
 *   speak(text)                        — POST /tts and play, with barge-in
 *   stopTTS()                          — stop current TTS playback
 *   isActive() / isSpeaking() / isTTSPlaying()
 *   setBackend(url)                    — override default ("http://localhost:5001")
 *
 * Differences from vui:
 *   - No video-element echo suppression (no video in vox)
 *   - No /asr or /intent calls here; voice.js just delivers wavBlob to the consumer
 *   - No DOM coupling beyond a single status-update hook (set via window.Voice.onStatus)
 */

(function () {
    "use strict";

    let BACKEND = "http://localhost:5001";
    const TARGET_SR = 16000;

    // VAD tuning — matches vui's tested values
    const NOISE_FLOOR_INIT = 0.008;
    const NOISE_FLOOR_ALPHA = 0.03;
    const SPEECH_THRESHOLD_RATIO = 3.0;
    const SPEECH_THRESHOLD_MIN = 0.012;
    const SILENCE_MS = 500;
    const MIN_SPEECH_MS = 250;
    const MAX_SPEECH_MS = 15000;
    const PRE_BUFFER_FRAMES = 4;
    const BARGE_IN_RATIO = 5.0;

    // Anti-transient (keyboard, finger snap, click) — applied only at onset
    const SPEECH_ONSET_FRAMES = 3;   // require N consecutive speech-like frames before "speaking"
    const ZCR_MAX_ONSET = 0.35;      // reject high-ZCR (percussive) frames while still candidate
                                     // speech vowels ≈ 0.05–0.2, fricatives ≈ 0.3–0.5 (handled
                                     // post-onset only — ZCR is not checked once speaking)

    let audioCtx = null;
    let mediaStream = null;
    let scriptNode = null;
    let isActive = false;
    let isSpeaking = false;
    let processing = false;
    let speechStart = 0;
    let lastSpeechTime = 0;
    let speechBuffer = [];
    let preBuffer = [];
    let noiseFloor = NOISE_FLOOR_INIT;
    let noiseFrameCount = 0;
    let speechFrameStreak = 0;       // consecutive candidate speech frames before onset commit
    let currentTTS = null;
    let ttsPlaying = false;

    let onSpeechEndHandler = null;
    let onStatusHandler = null;

    // ───── WAV encoding ─────
    function float32ToWav16Mono(samples, sampleRate) {
        const n = samples.length;
        const buf = new ArrayBuffer(44 + n * 2);
        const v = new DataView(buf);
        const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
        w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVE"); w(12, "fmt ");
        v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
        v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true);
        v.setUint16(32, 2, true); v.setUint16(34, 16, true);
        w(36, "data"); v.setUint32(40, n * 2, true);
        for (let i = 0; i < n; i++) {
            const s = Math.max(-1, Math.min(1, samples[i]));
            v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        }
        return new Blob([buf], { type: "audio/wav" });
    }

    function resampleLinear(input, fromRate, toRate) {
        if (fromRate === toRate) return input;
        const ratio = fromRate / toRate;
        const outLen = Math.round(input.length / ratio);
        const out = new Float32Array(outLen);
        for (let i = 0; i < outLen; i++) {
            const srcIdx = i * ratio;
            const idx0 = Math.floor(srcIdx);
            const idx1 = Math.min(idx0 + 1, input.length - 1);
            const frac = srcIdx - idx0;
            out[i] = input[idx0] * (1 - frac) + input[idx1] * frac;
        }
        return out;
    }

    function mergeBuffers(buffers) {
        let total = 0;
        for (const b of buffers) total += b.length;
        const result = new Float32Array(total);
        let off = 0;
        for (const b of buffers) { result.set(b, off); off += b.length; }
        return result;
    }

    // ───── status ─────
    function setStatus(state, detail) {
        if (onStatusHandler) onStatusHandler(state, detail);
    }

    // ───── TTS ─────
    function stopTTS() {
        if (currentTTS) {
            try { currentTTS.pause(); } catch (_) {}
            currentTTS.src = "";
            currentTTS = null;
        }
        ttsPlaying = false;
    }

    async function speak(text) {
        if (!text) return;
        stopTTS();
        ttsPlaying = true;
        setStatus("speaking", text);

        try {
            const resp = await fetch(BACKEND + "/tts", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text }),
            });
            const ctype = resp.headers.get("content-type") || "";
            if (!resp.ok || !ctype.includes("audio")) {
                console.warn("[voice] TTS failed:", resp.status, await resp.text());
                ttsPlaying = false;
                return;
            }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = new Audio(url);
            currentTTS = a;
            await new Promise((resolve) => {
                a.onended = () => { URL.revokeObjectURL(url); currentTTS = null; ttsPlaying = false; resolve(); };
                a.onerror = () => { URL.revokeObjectURL(url); currentTTS = null; ttsPlaying = false; resolve(); };
                a.play().catch(() => { ttsPlaying = false; resolve(); });
            });
        } catch (e) {
            console.warn("[voice] speak error:", e);
            ttsPlaying = false;
        } finally {
            if (isActive) setStatus("ready");
        }
    }

    // ───── VAD threshold ─────
    function speechThreshold() {
        return Math.max(SPEECH_THRESHOLD_MIN, noiseFloor * SPEECH_THRESHOLD_RATIO);
    }

    // ───── audio capture ─────
    async function startAudioCapture() {
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
        });

        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const nativeSR = audioCtx.sampleRate;
        console.log("[voice] native SR:", nativeSR);

        const source = audioCtx.createMediaStreamSource(mediaStream);
        scriptNode = audioCtx.createScriptProcessor(4096, 1, 1);

        noiseFloor = NOISE_FLOOR_INIT;
        noiseFrameCount = 0;
        preBuffer = [];

        scriptNode.onaudioprocess = (e) => {
            if (!isActive) return;

            const input = e.inputBuffer.getChannelData(0);

            // RMS energy
            let rms = 0;
            for (let i = 0; i < input.length; i++) rms += input[i] * input[i];
            rms = Math.sqrt(rms / input.length);

            // Zero-crossing rate (ZCR) — high for percussive transients (keyboard, claps),
            // lower for tonal/sustained speech. Used only at onset to reject taps.
            let zc = 0;
            for (let i = 1; i < input.length; i++) {
                if ((input[i] >= 0) !== (input[i - 1] >= 0)) zc++;
            }
            const zcr = zc / input.length;

            const now = Date.now();
            const thr = speechThreshold();
            const isAmplitudeSpeech = rms > thr;
            // Skip ZCR check once already speaking — fricatives like "s/sh/f" have high ZCR
            // and would otherwise truncate words mid-utterance.
            const isSpeechFrame = isSpeaking
                ? isAmplitudeSpeech
                : (isAmplitudeSpeech && zcr < ZCR_MAX_ONSET);

            // TTS echo suppression — only barge-in can break through
            if (ttsPlaying) {
                const bargeThr = Math.max(SPEECH_THRESHOLD_MIN * 2, noiseFloor * BARGE_IN_RATIO);
                if (rms > bargeThr && zcr < ZCR_MAX_ONSET) {
                    console.log("[voice] barge-in detected, stopping TTS");
                    stopTTS();
                } else {
                    return;
                }
            }

            if (processing) return;

            // Silence + not speaking → track noise floor, age preBuffer, reset onset streak
            if (!isSpeechFrame && !isSpeaking) {
                if (speechFrameStreak > 0) speechFrameStreak = 0;
                noiseFrameCount++;
                if (noiseFrameCount > 10) {
                    noiseFloor = noiseFloor * (1 - NOISE_FLOOR_ALPHA) + rms * NOISE_FLOOR_ALPHA;
                    noiseFloor = Math.max(0.001, Math.min(0.05, noiseFloor));
                }
                preBuffer.push(new Float32Array(input));
                if (preBuffer.length > PRE_BUFFER_FRAMES) preBuffer.shift();
                return;
            }

            if (isSpeechFrame) {
                noiseFrameCount = 0;
                if (!isSpeaking) {
                    // Candidate streak: must see N consecutive speech-like frames before
                    // committing. Keyboard taps clear in ≤2 frames.
                    speechFrameStreak++;
                    preBuffer.push(new Float32Array(input));
                    if (preBuffer.length > PRE_BUFFER_FRAMES) preBuffer.shift();
                    if (speechFrameStreak < SPEECH_ONSET_FRAMES) return;
                    // Commit
                    isSpeaking = true;
                    speechStart = now;
                    speechBuffer = preBuffer.slice();   // backfill includes the streak frames
                    preBuffer = [];
                    setStatus("listening");
                    lastSpeechTime = now;
                    return;
                }
                lastSpeechTime = now;
                speechBuffer.push(new Float32Array(input));
            } else if (isSpeaking) {
                speechBuffer.push(new Float32Array(input));
                const dur = now - speechStart;
                if ((now - lastSpeechTime > SILENCE_MS && dur > MIN_SPEECH_MS) || dur > MAX_SPEECH_MS) {
                    isSpeaking = false;
                    speechFrameStreak = 0;
                    const merged = mergeBuffers(speechBuffer);
                    speechBuffer = [];
                    preBuffer = [];
                    handleSpeechEnd(merged, nativeSR);
                }
            }
        };

        source.connect(scriptNode);
        scriptNode.connect(audioCtx.destination);
        console.log("[voice] capture started, threshold:", speechThreshold().toFixed(4));
    }

    function stopAudioCapture() {
        if (scriptNode) { try { scriptNode.disconnect(); } catch (_) {} scriptNode = null; }
        if (mediaStream) { mediaStream.getTracks().forEach((t) => t.stop()); mediaStream = null; }
        if (audioCtx) { try { audioCtx.close(); } catch (_) {} audioCtx = null; }
        speechBuffer = [];
        preBuffer = [];
        isSpeaking = false;
        stopTTS();
    }

    async function handleSpeechEnd(float32, nativeSR) {
        if (processing) return;
        processing = true;
        setStatus("processing");
        try {
            const resampled = resampleLinear(float32, nativeSR, TARGET_SR);
            if (resampled.length < TARGET_SR * 0.2) {
                console.log("[voice] utterance < 200ms, ignoring");
                setStatus("ready");
                return;
            }
            const wav = float32ToWav16Mono(resampled, TARGET_SR);
            console.log("[voice] speech-end,", (resampled.length / TARGET_SR).toFixed(1) + "s");
            if (onSpeechEndHandler) {
                await onSpeechEndHandler(wav);
            }
        } catch (e) {
            console.error("[voice] handleSpeechEnd error:", e);
            setStatus("error", e.message);
        } finally {
            processing = false;
            if (isActive && !ttsPlaying) setStatus("ready");
        }
    }

    // ───── public API ─────
    async function start() {
        if (isActive) return;
        isActive = true;
        setStatus("connecting");
        try {
            await startAudioCapture();
            setStatus("ready");
        } catch (e) {
            console.error("[voice] start failed:", e);
            setStatus("error", e.message);
            isActive = false;
        }
    }

    function stop() {
        isActive = false;
        stopAudioCapture();
        setStatus("idle");
    }

    function toggle() { if (isActive) stop(); else start(); }

    window.Voice = {
        start,
        stop,
        toggle,
        speak,
        stopTTS,
        onSpeechEnd(fn) { onSpeechEndHandler = fn; },
        onStatus(fn) { onStatusHandler = fn; },
        setBackend(url) { BACKEND = url; },
        isActive: () => isActive,
        isSpeaking: () => isSpeaking,
        isTTSPlaying: () => ttsPlaying,
    };
})();
