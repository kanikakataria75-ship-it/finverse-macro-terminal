// Synthesised sound design (WebAudio, no assets). Subtle by default, one toggle to mute.
import { store } from "./util.js";

let ctx, master, enabled = store.get("sound", true);

function ac() {
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    master = ctx.createGain();
    master.gain.value = 0.55;
    const comp = ctx.createDynamicsCompressor();
    master.connect(comp).connect(ctx.destination);
  }
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

function tone({ f = 440, type = "sine", t = 0, dur = 0.3, gain = 0.1, attack = 0.005, glide, filter }) {
  if (!enabled) return;
  const c = ac(), now = c.currentTime + t;
  const o = c.createOscillator(), g = c.createGain();
  o.type = type; o.frequency.setValueAtTime(f, now);
  if (glide) o.frequency.exponentialRampToValueAtTime(glide, now + dur);
  g.gain.setValueAtTime(0.0001, now);
  g.gain.exponentialRampToValueAtTime(gain, now + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, now + dur);
  let node = o.connect(g);
  if (filter) { const bq = c.createBiquadFilter(); bq.type = "lowpass"; bq.frequency.value = filter; node = g.connect(bq); }
  node.connect(master);
  o.start(now); o.stop(now + dur + 0.05);
}

function noise({ t = 0, dur = 1, gain = 0.05, from = 200, to = 4000, q = 0.8 }) {
  if (!enabled) return;
  const c = ac(), now = c.currentTime + t;
  const buf = c.createBuffer(1, c.sampleRate * dur, c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  const src = c.createBufferSource(); src.buffer = buf;
  const bq = c.createBiquadFilter(); bq.type = "bandpass"; bq.Q.value = q;
  bq.frequency.setValueAtTime(from, now); bq.frequency.exponentialRampToValueAtTime(to, now + dur);
  const g = c.createGain();
  g.gain.setValueAtTime(0.0001, now); g.gain.exponentialRampToValueAtTime(gain, now + dur * 0.6); g.gain.exponentialRampToValueAtTime(0.0001, now + dur);
  src.connect(bq).connect(g).connect(master);
  src.start(now); src.stop(now + dur);
}

export const sound = {
  get on() { return enabled; },
  toggle() { enabled = !enabled; store.set("sound", enabled); if (enabled) sound.click(); return enabled; },
  unlock() { ac(); },
  boot() {
    // sub drone swelling into a shimmer
    tone({ f: 41, type: "sine", dur: 5.5, gain: 0.22, attack: 2.2, glide: 55 });
    tone({ f: 82, type: "triangle", dur: 5, gain: 0.05, attack: 2.5, glide: 110, filter: 600 });
    noise({ t: 0.2, dur: 3.2, gain: 0.035, from: 120, to: 5200 });
    [880, 1318.5, 1760].forEach((f, i) => tone({ f, type: "sine", t: 2.2 + i * 0.12, dur: 2.4, gain: 0.018, attack: 0.6 }));
  },
  reveal() {
    // A-minor add9 bell chord
    [220, 261.63, 329.63, 493.88, 659.25].forEach((f, i) => {
      tone({ f, type: "sine", t: i * 0.05, dur: 3.6, gain: 0.05 - i * 0.006, attack: 0.01 });
      tone({ f: f * 2.01, type: "sine", t: i * 0.05, dur: 1.4, gain: 0.012, attack: 0.01 });
    });
    tone({ f: 55, type: "sine", dur: 3, gain: 0.18, attack: 0.02, glide: 50 });
  },
  whoosh() { noise({ dur: 0.9, gain: 0.06, from: 300, to: 7000, q: 0.6 }); tone({ f: 180, type: "sine", dur: 0.7, gain: 0.05, glide: 60 }); },
  click() { tone({ f: 1850, type: "sine", dur: 0.05, gain: 0.025 }); },
  hover() { tone({ f: 2600, type: "sine", dur: 0.03, gain: 0.008 }); },
  key() { tone({ f: 3200 + Math.random() * 300, type: "square", dur: 0.012, gain: 0.004, filter: 5000 }); },
  go() { tone({ f: 660, type: "triangle", dur: 0.12, gain: 0.04 }); tone({ f: 990, type: "triangle", t: 0.07, dur: 0.16, gain: 0.035 }); },
  alert() { tone({ f: 988, type: "sine", dur: 0.35, gain: 0.07 }); tone({ f: 1319, type: "sine", t: 0.14, dur: 0.5, gain: 0.06 }); },
  crit() { [0, 0.22].forEach((t) => { tone({ f: 740, type: "sawtooth", t, dur: 0.16, gain: 0.03, filter: 2200 }); tone({ f: 554, type: "sawtooth", t: t + 0.08, dur: 0.16, gain: 0.03, filter: 2200 }); }); },
};
