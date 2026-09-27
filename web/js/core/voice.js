// VEDA — the voice of Finverse.  "Veda, what's the situation in the Gulf?"
//  · wake word: always-on Web Speech recogniser (Chrome/Edge) listening for "Veda"
//  · clap twice: AudioWorklet transient detector (on-device)
//  · answers: Oracle → narrator → free neural voices (server) with real lip-sync amplitude
import { api, emit, on } from "./state.js";
import { h, clear, store, toast } from "./util.js";
import { sound } from "./sound.js";

export const NAME = "VEDA";
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
// how recognisers tend to spell "Veda"
// how speech engines tend to write "Veda" (plus "Finverse" as an alternative wake word)
const WAKE_WORDS = "veda|vedha|vedaa|veeda|vida|weda|vaida|vada|wada|vedas|vedo|vayda|waida|bheda|vader|wader|finverse|fin verse|fine verse";
const WAKE = `(?:(?:hey|hi|ok|okay|hello|arey|arre|suno)\\s+)?(?:${WAKE_WORDS})\\b`;
const WAKE_ALL = new RegExp(`\\b${WAKE}`, "gi");
const DEVANAGARI = ["वेदा", "वेद", "वेडा", "विदा", "वीडा"];
const NOT_WAKE = new Set(["beta", "data", "meta", "vita", "video", "vendor", "wedding", "reda", "veto", "vote", "wade", "bed", "bead"]);
function lev(a, b) {
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++)
    d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return d[a.length][b.length];
}
/** index just after the last wake word in `low`, or -1 */
function wakeEnd(low) {
  let end = -1;
  for (const m of low.matchAll(WAKE_ALL)) end = m.index + m[0].length;
  for (const w of DEVANAGARI) { const i = low.lastIndexOf(w); if (i >= 0) end = Math.max(end, i + w.length); }
  for (const m of low.matchAll(/[a-z']+/g)) {       // near-misses: one edit away from "veda", v/w/b sound
    const t = m[0].replace(/'s$/, "");
    if (t.length >= 3 && t.length <= 6 && /^[vwb]/.test(t) && !NOT_WAKE.has(t) && lev(t, "veda") <= 1) end = Math.max(end, m.index + m[0].length);
  }
  return end;
}
const STOP_RX = /\b(stop|quiet|enough|thank you|thanks|that's all|bas)\b/i;

const WORKLET = `
class ClapDetector extends AudioWorkletProcessor {
  constructor() { super(); this.floor = 0.006; this.prev = 0; this.inBurst = false; this.burst = 0; this.peak = 0; this.cool = 0; this.t = 0; this.n = 0; this.acc = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    let sum = 0, pk = 0, zc = 0;
    for (let i = 0; i < ch.length; i++) { const v = ch[i]; sum += v * v; const a = v < 0 ? -v : v; if (a > pk) pk = a; if (i && (v >= 0) !== (ch[i - 1] >= 0)) zc++; }
    const dt = ch.length / sampleRate, rms = Math.sqrt(sum / ch.length), zcr = zc / ch.length;
    this.t += dt; if (this.cool > 0) this.cool -= dt;
    if (!this.inBurst) {
      this.floor = this.floor * 0.995 + Math.min(rms, 0.04) * 0.005;           // room ambience, slowly
      // a clap is a sudden, broadband jump in loudness — relative to the room, not an absolute level
      const attack = rms > Math.max(0.018, this.floor * 5) && rms > this.prev * 3 && pk > Math.max(0.05, this.floor * 9);
      if (this.cool <= 0 && attack && zcr > 0.04) { this.inBurst = true; this.burst = 0; this.peak = rms; }
    } else {
      this.burst += dt; if (rms > this.peak) this.peak = rms;
      if (rms < this.peak * 0.35) {                                              // decayed: it was a transient
        this.inBurst = false; this.cool = 0.07;
        if (this.burst < 0.25) this.port.postMessage({ type: "clap", t: this.t });
      } else if (this.burst > 0.4) { this.inBurst = false; this.cool = 0.3; }     // sustained: speech/music
    }
    this.prev = rms;
    this.acc += rms; this.n++;
    if (this.n >= 12) { this.port.postMessage({ type: "level", rms: this.acc / this.n }); this.n = 0; this.acc = 0; }
    return true;
  }
}
registerProcessor("clap-detector", ClapDetector);`;

function sentences(text) {
  const raw = (text || "").replace(/\s+/g, " ").match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [];
  const out = [];
  for (const s of raw.map((x) => x.trim()).filter(Boolean)) {
    if (out.length && (out[out.length - 1].length < 28 || s.length < 18)) out[out.length - 1] += " " + s;
    else out.push(s);
  }
  return out;
}

class Veda {
  constructor() {
    this.state = "off";           // off | armed | listening | thinking | speaking | linger
    this.enabled = false;
    this.lang = store.get("veda.lang", "en-IN");
    this.voiceId = store.get("veda.voice", null);
    this.wakeMode = store.get("veda.wake", "both");   // name | clap | both
    this.cfg = { name: NAME, voices: [], neural: true, acks: ["One moment."], greets: [], misses: [] };
    this.transcript = ""; this.caption = ""; this.answer = null; this.error = null;
    this.level = 0; this.fakeAmp = 0; this.from = 0; this.finalLen = 0; this.token = 0;
    this.subs = new Set();
    api.get("/api/voice/config").then((c) => { this.cfg = c; if (!this.voiceId) this.voiceId = c.default; this.emit(); }).catch(() => {});
  }
  get supported() { return { stt: !!SR, mic: !!navigator.mediaDevices?.getUserMedia }; }
  onChange(fn) { this.subs.add(fn); return () => this.subs.delete(fn); }
  emit() { this.subs.forEach((fn) => fn(this)); }
  set(state, extra = {}) { this.state = state; Object.assign(this, extra); this.emit(); }
  pick(list) { return list && list.length ? list[Math.floor(Math.random() * list.length)] : ""; }

  // ------------------------------------------------------------ lifecycle
  async enable() {
    if (this.enabled) return true;
    try {
      this.actx ||= new (window.AudioContext || window.webkitAudioContext)();
      // never await resume(): without a user gesture it stays pending forever; resume on the next interaction instead
      if (this.actx.state === "suspended") {
        this.actx.resume().catch(() => {});
        const wake = () => { this.actx.resume().catch(() => {}); };
        window.addEventListener("pointerdown", wake, { once: true }); window.addEventListener("keydown", wake, { once: true });
      }
      this.analyser = this.actx.createAnalyser();
      this.analyser.fftSize = 1024;
      this.analyser.connect(this.actx.destination);
      this.buf = new Float32Array(this.analyser.fftSize);
      if (this.supported.mic) {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } }); // raw: keep clap transients
        const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
        await this.actx.audioWorklet.addModule(url);
        const node = new AudioWorkletNode(this.actx, "clap-detector");
        const sink = this.actx.createGain(); sink.gain.value = 0;
        this.actx.createMediaStreamSource(this.stream).connect(node).connect(sink).connect(this.actx.destination);
        node.port.onmessage = (e) => { if (e.data.type === "level") this.level = e.data.rms; else this.onClap(e.data.t); };
        this.claps = [];
      }
    } catch (err) {
      toast(NAME, err.name === "NotAllowedError" ? "Microphone permission was denied." : `Voice unavailable: ${err.message}`);
      return false;
    }
    this.enabled = true;
    store.set("veda.enabled", true);
    this.startRecognizer();
    this.set("armed");
    toast(`${NAME} IS LISTENING`, SR ? "Say “Veda…” or clap twice, then ask anything. (Turn off from the mic menu.)" : "Clap twice or press V. (Speech needs Chrome or Edge.)");
    return true;
  }
  disable() {
    this.stopSpeaking();
    this.stopRecognizer();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.enabled = false;
    store.set("veda.enabled", false);
    this.set("off");
    emit("veda:dismiss");
  }

  // ------------------------------------------------- always-on recogniser
  startRecognizer() { if (!SR) return; this.recOn = true; this.net = 0; this.spawn(); }
  stopRecognizer() { this.recOn = false; try { this.rec?.abort(); } catch { /* not running */ } }
  spawn() {
    if (!this.recOn || this.rec) return;
    const rec = new SR();
    rec.lang = this.lang; rec.continuous = true; rec.interimResults = true; rec.maxAlternatives = 1;
    this.from = 0; this.finalLen = 0;
    rec.onresult = (e) => this.onSpeech(e);
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") { this.recOn = false; this.set(this.state, { error: "Speech recognition was blocked for this site." }); }
      else if (e.error === "network") this.net++;
    };
    rec.onend = () => { this.rec = null; if (this.recOn) setTimeout(() => this.spawn(), this.net > 3 ? 6000 : 250); };
    try { rec.start(); this.rec = rec; } catch { setTimeout(() => this.spawn(), 1000); }
  }
  onSpeech(e) {
    let text = "", allFinal = true, finals = 0;
    for (let i = 0; i < e.results.length; i++) if (e.results[i].isFinal) finals = i + 1;
    this.finalLen = finals;
    for (let i = this.from; i < e.results.length; i++) { text += e.results[i][0].transcript + " "; if (!e.results[i].isFinal) allFinal = false; }
    text = text.replace(/\s+/g, " ").trim();
    if (!text) return;
    const low = text.toLowerCase();
    const wEnd = this.wakeMode !== "clap" ? wakeEnd(low) : -1;
    const named = wEnd >= 0;
    if (this.state === "armed" && !named) this.set("armed", { heard: text.slice(-70), heardAt: Date.now() });
    if (this.state === "speaking" || this.state === "thinking" || this.state === "linger") {
      // her own voice echoes back into the mic: only her name or a clear "stop" interrupts
      if (named) { this.stopSpeaking(); this.summon("name", false); }
      else if (this.state !== "thinking" && STOP_RX.test(low) && low.split(" ").length <= 4) { this.from = e.results.length; this.stopSpeaking(); this.dismiss(); return; }
      else { if (allFinal) this.from = e.results.length; return; }
    }
    if (this.state === "armed") {
      if (named) this.summon("name", false);
      else { if (allFinal) this.from = e.results.length; return; }
    }
    if (this.state !== "listening") return;
    let cmd = named ? text.slice(wEnd) : text;
    cmd = cmd.replace(/^[\s,.!?:;-]+/, "").trim();
    this.set("listening", { transcript: cmd });
    clearTimeout(this.silence);
    const words = cmd ? cmd.split(/\s+/).length : 0;
    // people pause mid-question and Chrome finalises each phrase — wait for a real pause before answering
    const ready = words >= 2 || (allFinal && cmd.length >= 3);
    const len = e.results.length;
    this.silence = setTimeout(() => { if (this.state === "listening" && ready) this.finish(cmd, len); }, allFinal ? 1000 : 1600);
  }
  onClap(t) {
    if (this.wakeMode === "name") return;
    if (this.state === "armed") this.set("armed", { heard: "👏", heardAt: Date.now() });
    this.claps = (this.claps || []).filter((x) => t - x < 1.0);
    this.claps.push(t);
    const n = this.claps.length;
    if (n >= 2) {
      const gap = this.claps[n - 1] - this.claps[n - 2];
      if (gap >= 0.12 && gap <= 1.0) { this.claps = []; this.summon("clap"); }
    }
  }

  // ------------------------------------------------------------ dialogue
  summon(src = "button", fresh = true) {
    if (!this.enabled) { this.enable().then((ok) => ok && this.summon(src, fresh)); return; }
    if (this.state === "speaking" || this.state === "thinking" || this.state === "linger") this.stopSpeaking();
    clearTimeout(this.lingerT); clearTimeout(this.idleT);
    if (fresh) this.from = this.finalLen; // clap/button: ignore anything said before
    this.set("listening", { transcript: "", caption: "", answer: null, error: SR ? null : "Voice questions need Chrome or Edge — clap and V still open me." });
    sound.go();
    emit("veda:summon", src);
    if (SR && !this.rec) this.spawn();
    this.idleT = setTimeout(() => { if (this.state === "listening" && !this.transcript) this.dismiss(); }, 9000);
  }
  async finish(cmd, len) {
    clearTimeout(this.silence); clearTimeout(this.idleT);
    this.from = len;
    this.set("thinking", { transcript: cmd, caption: "" });
    const answer = api.post("/api/oracle", { q: cmd }).catch((e) => ({ error: e.message }));
    const token = ++this.token;
    await this.say([this.pick(this.cfg.acks) || "One moment."], token);
    const r = await answer;
    if (token !== this.token) return;
    if (r.error) { await this.say([this.pick(this.cfg.misses) || "I couldn't reach the data just now."], token); return this.after(token); }
    this.set("speaking", { answer: r });
    await this.say(sentences(r.spoken || r.title), token);
    this.after(token);
  }
  after(token) {
    if (token !== this.token) return;
    this.set("linger", { caption: "" });
    this.lingerT = setTimeout(() => { if (this.state === "linger") this.dismiss(); }, 4000);
  }
  dismiss() {
    clearTimeout(this.idleT); clearTimeout(this.silence); clearTimeout(this.lingerT);
    this.set(this.enabled ? "armed" : "off", { caption: "", transcript: "" });
    emit("veda:dismiss");
  }

  // --------------------------------------------------------------- voice
  async say(parts, token) {
    const bufs = parts.map((p) => this.tts(p).catch(() => null));
    for (let i = 0; i < parts.length; i++) {
      if (token !== this.token) return;
      this.set(this.state, { caption: parts[i] });
      const buf = await bufs[i];
      if (token !== this.token) return;
      if (buf) await this.play(buf); else await this.fallback(parts[i], token);
    }
  }
  async tts(text) {
    if (this.cfg.neural === false || !this.actx) throw new Error("neural voice off");
    const r = await fetch("/api/voice/tts", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text, voice: this.voiceId }) });
    if (!r.ok) { if (r.status === 503) this.cfg.neural = false; throw new Error(`tts ${r.status}`); }
    return this.actx.decodeAudioData(await r.arrayBuffer());
  }
  play(buf) {
    return new Promise((resolve) => {
      const src = this.actx.createBufferSource();
      src.buffer = buf;
      src.connect(this.analyser);
      src.onended = resolve;
      this.src = src;
      src.start();
    });
  }
  fallback(text, token) {
    if (!window.speechSynthesis) return Promise.resolve();
    return new Promise((resolve) => {
      const u = new SpeechSynthesisUtterance(text);
      const vs = speechSynthesis.getVoices();
      u.voice = vs.find((v) => /Natural/i.test(v.name) && v.lang.startsWith("en")) || vs.find((v) => v.lang === "en-IN") || null;
      u.rate = 1.0; u.pitch = 1.0;
      u.onboundary = () => { this.fakeAmp = 1; };
      u.onend = resolve; u.onerror = resolve;
      if (token !== this.token) return resolve();
      speechSynthesis.speak(u);
    });
  }
  stopSpeaking() {
    this.token++;
    try { this.src?.stop(); } catch { /* already ended */ }
    if (window.speechSynthesis) speechSynthesis.cancel();
  }
  /** 0..1 loudness of what VEDA is saying right now (drives the lips). */
  speechLevel() {
    this.fakeAmp *= 0.86;
    if (!this.analyser) return this.fakeAmp;
    this.analyser.getFloatTimeDomainData(this.buf);
    let s = 0;
    for (let i = 0; i < this.buf.length; i++) s += this.buf[i] * this.buf[i];
    return Math.max(this.fakeAmp * 0.8, Math.min(1, Math.pow(Math.sqrt(s / this.buf.length) * 3.2, 0.8)));
  }
  setLang(l) { this.lang = l; store.set("veda.lang", l); if (this.rec) { try { this.rec.abort(); } catch { /* restart picks it up */ } } this.emit(); }
  setVoice(v) { this.voiceId = v; store.set("veda.voice", v); this.emit(); }
  setWake(m) { this.wakeMode = m; store.set("veda.wake", m); this.emit(); }
}

export const veda = new Veda();
export const voice = veda; // backwards-compatible name

// ================================================================== UI
const STATUS = { listening: "Listening", thinking: "Reading the tape", speaking: "Speaking", linger: "", armed: "Standing by", off: "" };

export function mountVoiceUI() {
  const canvas = h("canvas.veda-stage");
  const chip = h("span.veda-chip");
  const you = h("div.veda-you");
  const status = h("div.veda-status");
  const caption = h("div.veda-caption");
  const err = h("div.veda-err");
  const details = h("div.veda-details.scroll.hidden");
  const detailsBtn = h("button.btn.sm.hidden", { on: { click: () => details.classList.toggle("hidden") } }, "DETAILS");
  const voiceSel = h("select.input", { on: { change: (e) => veda.setVoice(e.target.value) } });
  const langSel = h("select.input", { on: { change: (e) => veda.setLang(e.target.value) } },
    [["en-IN", "English · India"], ["en-US", "English · US"], ["en-GB", "English · UK"], ["hi-IN", "Hindi"]].map(([v, n]) => h("option", { value: v }, n)));
  const wakeSeg = h("div.seg", [["name", "SAY “VEDA”"], ["clap", "CLAP ×2"], ["both", "BOTH"]].map(([v, n]) =>
    h("button", { dataset: { v }, on: { click: () => veda.setWake(v) } }, n)));
  const power = h("button.btn.sm", { on: { click: () => (veda.enabled ? veda.disable() : veda.enable()) } });
  const ear = h("div.veda-ear.hidden");
  document.body.append(ear);
  let earT;
  const root = h("div.veda.hidden",
    canvas,
    h("div.veda-brand", h("div.veda-name", NAME), h("div.veda-sub", "Voice of Finverse"), chip),
    h("button.veda-close.icon-btn", { title: "Close (Esc)", on: { click: () => { veda.stopSpeaking(); veda.dismiss(); } } }, "✕"),
    you,
    h("div.veda-bottom", status, caption, err),
    details,
    h("div.veda-bar", detailsBtn, h("span.label-xs", "Voice"), voiceSel, h("span.label-xs", "Hear"), langSel, h("span.label-xs", "Wake"), wakeSeg, power,
      h("span.veda-credit", "Avatar: “Infinite, 3D Head Scan” by Lee Perry-Smith · CC BY 3.0")));
  document.body.append(root);

  let avatar = null, hideT = null, loop = 0;
  async function show() {
    clearTimeout(hideT);
    root.classList.remove("hidden", "leaving");
    if (!avatar) {
      const { VedaAvatar } = await import("../three/avatar.js");
      avatar = new VedaAvatar(canvas);
      await avatar.ready;
    }
    avatar.resize();
    avatar.start();
    avatar.form();
    cancelAnimationFrame(loop);
    const tick = () => {
      loop = requestAnimationFrame(tick);
      avatar.setAmp(veda.speechLevel());
      avatar.setListen(veda.state === "listening" ? Math.min(1, veda.level * 12) : 0);
      avatar.think(veda.state === "thinking");
    };
    tick();
  }
  function hide() {
    if (!avatar) { root.classList.add("hidden"); return; }
    avatar.dissolve();                                   // grains scatter back into the nebula…
    clearTimeout(hideT);
    hideT = setTimeout(() => {
      root.classList.add("leaving");                     // …then the stage fades
      hideT = setTimeout(() => { root.classList.add("hidden"); root.classList.remove("leaving"); avatar.stop(); cancelAnimationFrame(loop); }, 850);
    }, 1100);
  }
  on("veda:summon", show);
  on("veda:dismiss", hide);

  const render = () => {
    if (voiceSel.options.length !== (veda.cfg.voices || []).length) {
      clear(voiceSel);
      (veda.cfg.voices || []).forEach((v) => voiceSel.append(h("option", { value: v.id }, v.label)));
    }
    voiceSel.value = veda.voiceId || veda.cfg.default || "";
    voiceSel.disabled = veda.cfg.neural === false;
    langSel.value = veda.lang;
    [...wakeSeg.children].forEach((b) => b.classList.toggle("on", b.dataset.v === veda.wakeMode));
    power.textContent = veda.enabled ? "TURN OFF" : "TURN ON";
    chip.textContent = veda.enabled ? (veda.cfg.neural === false ? "BROWSER VOICE" : "NEURAL VOICE") : "OFF";
    chip.className = `veda-chip ${veda.state}`;
    you.textContent = veda.transcript ? `“${veda.transcript}”` : veda.state === "listening" ? "Ask about markets, a region, a stock, a what-if…" : "";
    you.classList.toggle("hint", !veda.transcript);
    status.textContent = STATUS[veda.state] ?? "";
    status.className = `veda-status ${veda.state}`;
    if (caption.textContent !== veda.caption) {
      caption.textContent = veda.caption || "";
      caption.classList.remove("in"); void caption.offsetWidth; caption.classList.add("in");
    }
    err.textContent = veda.error || "";
    if (veda.state === "armed" && veda.heardAt && Date.now() - veda.heardAt < 300) {
      clear(ear).append(h("b", "VEDA heard"), h("span", veda.heard === "👏" ? "👏 one clap — clap again to wake me" : `“${veda.heard}” — start with “Veda…” to ask`));
      ear.classList.remove("hidden");
      clearTimeout(earT); earT = setTimeout(() => ear.classList.add("hidden"), 3500);
    } else if (veda.state !== "armed") ear.classList.add("hidden");
    const a = veda.answer;
    detailsBtn.classList.toggle("hidden", !a);
    clear(details);
    if (a) {
      details.append(h("div.or-title", a.title));
      (a.sections || []).slice(0, 5).forEach((s) => details.append(h("h4", s.h), h("ul", s.bullets.slice(0, 4).map((b) => h("li", b)))));
      details.append(h("div.src-note", a.disclaimer || ""));
    }
  };
  veda.onChange(render);
  render();

  window.addEventListener("keydown", (e) => {
    const typing = document.activeElement && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
    if (e.key === "Escape" && !root.classList.contains("hidden")) { veda.stopSpeaking(); veda.dismiss(); return; }
    if (!typing && (e.key === "v" || e.key === "V") && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); veda.summon("key"); }
  });
  return { talk: () => veda.summon("command"), show, hide };
}

/** Header button: shows VEDA's state; click to summon (turns her on the first time). */
export function voiceButton() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("fill", "none"); svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.6"); svg.setAttribute("stroke-linecap", "round");
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", "M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zM5 11a7 7 0 0 0 14 0M12 18v3");
  svg.append(p);
  const b = h("button.icon-btn.vb", { title: "VEDA · say “Veda”, clap twice, or press V", on: { click: () => veda.summon("button") } }, svg, h("i.vb-dot"));
  const paint = () => { b.dataset.state = veda.state; };
  veda.onChange(paint); paint();
  return b;
}
