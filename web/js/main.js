// FINVERSE boot orchestrator: gate → cinematic intro → 3D home → terminal.
import { S, on, emit, hydrate, connect, api } from "./core/state.js";
import { h, store, toast } from "./core/util.js";
import { sound } from "./core/sound.js";
import { EMBLEM } from "./panels/common.js";
import { buildTerminal } from "./views/terminal.js";
import { buildHome } from "./views/home.js";
import { veda, mountVoiceUI } from "./core/voice.js";

const $gate = document.getElementById("gate");
const $intro = document.getElementById("intro");
const $home = document.getElementById("home");
const $term = document.getElementById("terminal");
let home, term, view = null;

function swap(next) {
  const els = { gate: $gate, intro: $intro, home: $home, terminal: $term };
  const prev = view && els[view];
  const el = els[next];
  if (prev === el) return;
  el.classList.remove("hidden");
  el.classList.add("entering", "active");
  void el.offsetWidth; // commit the start state; a timer (not rAF) so throttled/background tabs still finish
  setTimeout(() => el.classList.remove("entering"), 30);
  if (prev) { prev.classList.add("leaving"); prev.classList.remove("active"); setTimeout(() => { prev.classList.add("hidden"); prev.classList.remove("leaving"); }, 900); }
  view = next;
  if (next === "home") home?.show(); else home?.hide();
  emit("ui:view", next);
  if (next === "terminal") emit("ui:ws", term.current());
}

function enterTerminal(ws) {
  sound.whoosh();
  swap("terminal");
  if (ws) emit("ui:go", ws);
}

function buildGate(onGo) {
  const skip = h("input", { type: "checkbox", checked: store.get("skipIntro", false), on: { change: (e) => store.set("skipIntro", e.target.checked) } });
  const vedaBox = h("input", { type: "checkbox", checked: store.get("veda.enabled", true), on: { change: (e) => store.set("veda.enabled", e.target.checked) } });
  const btn = h("button.gate-btn", "Initialize");
  $gate.append(h("div.gate-inner", h("div.emblem", EMBLEM()), h("div.gate-word", "FINVERSE"), h("div.gate-sub", "Macro Intelligence Terminal"), btn, h("div.gate-hint", "PRESS ENTER")),
    h("div.gate-foot", h("span", "Markets"), h("span", "Macro"), h("span", "Geopolitics"), h("span", "Rhetoric"), h("span", "Crypto")),
    h("label.gate-opt", skip, "SKIP CINEMATIC NEXT TIME"),
    h("label.gate-veda", vedaBox, "WAKE ", h("b", "VEDA"), " — SAY “VEDA” TO TALK"));
  const go = () => { window.removeEventListener("keydown", key); onGo(); };
  const key = (e) => { if (e.key === "Enter" || e.key === " ") go(); };
  btn.addEventListener("click", go);
  window.addEventListener("keydown", key);
}

async function boot() {
  const ready = hydrate().catch((e) => { console.error(e); toast("OFFLINE", "Engine unreachable — retrying…", { crit: true }); });
  const health = api.get("/api/health").catch(() => ({ feeds: [] }));
  const params = new URLSearchParams(location.search);
  const skipIntro = params.get("intro") === "0" || store.get("skipIntro", false);
  swap("gate");
  buildGate(async () => {
    sound.unlock();
    await ready;
    connect();
    home = buildHome($home, { enter: enterTerminal });
    term = buildTerminal($term);
    emit("hydrated", S); // components built after the first snapshot paint from it now
    const vui = mountVoiceUI();
    on("ui:voice", () => vui.talk());
    // the Initialize click is the user gesture that audio + mic need, so VEDA can listen from the start
    if (store.get("veda.enabled", true)) veda.enable();
    if (skipIntro || params.get("to") === "terminal") {
      if (params.get("to") === "terminal") return enterTerminal();
      sound.reveal();
      return swap("home");
    }
    swap("intro");
    const { playIntro } = await import("./three/intro.js");
    playIntro($intro, { health: await health, sound, onDone: () => swap("home") });
  });
  if (params.get("auto") === "1") $gate.querySelector(".gate-btn")?.click();

  window.addEventListener("keydown", (e) => {
    if (view === "home" && (e.key === "Enter" || /^F[1-7]$/.test(e.key))) {
      e.preventDefault();
      const ws = { F1: "macro", F2: "markets", F3: "india", F4: "crypto", F5: "geo", F6: "analytics", F7: "portfolio" }[e.key];
      enterTerminal(ws);
    }
  });
  on("ui:home", () => { sound.whoosh(); swap("home"); });
}

boot();
