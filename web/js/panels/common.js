import { S, on, emit, meta } from "../core/state.js";
import { h, s, clear, fmtPx, fmtPct, cls, sparkline, setNum, tip, untip } from "../core/util.js";
import { EXCHANGES, session } from "../core/world.js";
import { sound } from "../core/sound.js";

/** Glass panel frame */
export function panel(area, title, { mn, tools = [], foot, pad = false } = {}) {
  const body = h("div.p-body", { class: pad ? "pad" : "" });
  const toolsEl = h("div.p-tools", tools);
  const footEl = foot ? h("div.p-foot", foot) : null;
  const max = h("button.icon-btn.p-max", { title: "Maximize (Esc to restore)" }, icon("full"));
  const el = h("section.panel", { style: { gridArea: area } },
    h("header.p-head", h("div.p-title", title), mn ? h("span.p-mn", mn) : null, toolsEl, max), body, footEl);
  const toggle = (on) => {
    const next = on ?? !el.classList.contains("max");
    document.querySelectorAll(".panel.max").forEach((x) => x !== el && x.classList.remove("max"));
    el.classList.toggle("max", next);
    sound.click();
    window.dispatchEvent(new Event("resize"));
  };
  max.addEventListener("click", () => toggle());
  el.querySelector(".p-head").addEventListener("dblclick", (e) => { if (!e.target.closest("button, .seg, input, select")) toggle(); });
  return { el, body, tools: toolsEl, foot: footEl };
}
window.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || document.querySelector(".overlay, .veda:not(.hidden)")) return;
  document.querySelectorAll(".panel.max").forEach((x) => x.classList.remove("max"));
});

export function seg(options, value, onChange) {
  const box = h("div.seg");
  const render = (v) => [...box.children].forEach((b) => b.classList.toggle("on", b.dataset.v === String(v)));
  for (const [v, label] of options) box.append(h("button", { dataset: { v }, on: { click: () => { render(v); sound.click(); onChange(v); } } }, label));
  render(value);
  return box;
}

// ------------------------------------------------------------------ tapes
/** Seamless, never-resetting ticker tape (rAF-driven, pause on hover). */
export function tickerTape({ label = "MARKETS", speed = 42 } = {}) {
  const track = h("div.tape-track");
  const root = h("div.tape", h("div.tape-label", label), track);
  let x = 0, paused = false, last = performance.now(), width = 0;
  const syms = () => S.universe.filter((u) => u.tape).map((u) => u.sym);
  const item = (sym) => {
    const q = S.quotes[sym] || {}, m = meta(sym);
    const el = h("div.tape-item", { dataset: { sym }, on: { click: () => emit("ui:security", sym) } },
      q.src === "BINANCE" || q.src === "ANGEL" ? h("span.live-dot") : null,
      h("span.tc", m.code), h("span.tp", fmtPx(q.price, sym)), h("span.tx", { class: cls(q.pct) }, `${q.pct > 0 ? "▲" : q.pct < 0 ? "▼" : "•"} ${fmtPct(q.pct)}`),
      sparkline(q.spark, { w: 44, h: 16, fill: false, stroke: 1.2 }));
    return el;
  };
  const build = () => {
    clear(track);
    const list = syms();
    const one = list.map(item);
    one.forEach((n) => track.append(n));
    list.map(item).forEach((n) => track.append(n)); // duplicate for seamless loop
    requestAnimationFrame(() => { width = track.scrollWidth / 2; });
  };
  root.addEventListener("mouseenter", () => (paused = true));
  root.addEventListener("mouseleave", () => (paused = false));
  const step = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    if (!paused && width) { x -= speed * dt; if (-x >= width) x += width; track.style.transform = `translate3d(${x}px,0,0)`; }
    requestAnimationFrame(step);
  };
  on("hydrated", build);
  on("quotes", ({ changed, prev }) => {
    for (const [sym, q] of Object.entries(changed)) {
      track.querySelectorAll(`[data-sym="${CSS.escape(sym)}"]`).forEach((el) => {
        const p = el.querySelector(".tp"), x2 = el.querySelector(".tx");
        setNum(p, fmtPx(q.price, sym), prev[sym] != null ? Math.sign(q.price - prev[sym]) : 0);
        x2.textContent = `${q.pct > 0 ? "▲" : q.pct < 0 ? "▼" : "•"} ${fmtPct(q.pct)}`;
        x2.className = `tx ${cls(q.pct)}`;
      });
    }
  });
  if (S.universe.length) build();
  requestAnimationFrame(step);
  return root;
}

export function newsTape() {
  const track = h("div.tape-track");
  const root = h("div.tape.news", h("div.tape-label", "WIRE"), track);
  let x = 0, paused = false, last = performance.now(), width = 0;
  const build = () => {
    clear(track);
    const items = (S.top.length ? S.top : S.news.slice(0, 14)).slice(0, 14);
    const mk = (n) => h("a.tape-item", { href: n.link || "#", target: "_blank", rel: "noopener noreferrer" },
      h("span.ns", n.source), h("span.nt", n.title), n.confirmations > 1 ? h("span.tag.gold", `×${n.confirmations}`) : null);
    items.forEach((n) => track.append(mk(n)));
    items.forEach((n) => track.append(mk(n)));
    requestAnimationFrame(() => { width = track.scrollWidth / 2; });
  };
  root.addEventListener("mouseenter", () => (paused = true));
  root.addEventListener("mouseleave", () => (paused = false));
  const step = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    if (!paused && width) { x -= 34 * dt; if (-x >= width) x += width; track.style.transform = `translate3d(${x}px,0,0)`; }
    requestAnimationFrame(step);
  };
  on("hydrated", build);
  let pending;
  on("news", () => { clearTimeout(pending); pending = setTimeout(async () => { try { S.top = await (await fetch("/api/news?top=1&n=14")).json(); } catch {} build(); }, 3000); });
  if (S.news.length) build();
  requestAnimationFrame(step);
  return root;
}

// ------------------------------------------------------------------ clocks
export function clocks() {
  const box = h("div.clocks");
  const list = EXCHANGES.filter((e) => e.clock);
  const els = list.map((ex) => {
    const t = h("div.cl-time", "--:--:--"), bar = h("i");
    const c = h("div.clock", { on: { mouseenter: (e) => { const st = session(ex); tip(e, ex.city, [["Exchange", ex.id], ["Session", `${ex.open}–${ex.close} local`], ["Status", st.open ? "OPEN" : "CLOSED", st.open ? "up" : "down"]]); }, mouseleave: untip } },
      h("div.cl-top", h("span.dot"), ex.short), t, h("div.cl-bar", bar));
    box.append(c);
    return { ex, c, t, bar };
  });
  const tick = () => {
    const now = new Date();
    for (const e of els) {
      const st = session(e.ex, now);
      e.t.textContent = st.time;
      e.c.classList.toggle("open", st.open);
      e.bar.style.width = `${st.progress * 100}%`;
    }
  };
  tick(); setInterval(tick, 1000);
  return box;
}

export function feedChip(onClick) {
  const bars = h("div.bars");
  const txt = h("span", "FEEDS");
  const chip = h("button.feed-chip", { on: { click: onClick } }, bars, txt);
  const render = () => {
    clear(bars);
    const f = S.health.feeds || [];
    f.forEach((x, i) => bars.append(h("i", { class: x.status === "ok" ? "" : x.status, style: { height: `${5 + ((i * 37) % 7)}px` } })));
    const ok = f.filter((x) => x.status === "ok").length;
    txt.textContent = `${ok}/${f.length} LIVE`;
  };
  on("health", render); on("hydrated", render);
  return chip;
}

export const EMBLEM = () => s("svg", { viewBox: "0 0 64 64", fill: "none", class: "emblem-svg" },
  s("defs", {}, s("linearGradient", { id: "eg", x1: 0, y1: 0, x2: 1, y2: 1 }, s("stop", { offset: "0", "stop-color": "#f4ddaa" }), s("stop", { offset: "1", "stop-color": "#8c7140" }))),
  s("circle", { cx: 32, cy: 32, r: 29, stroke: "url(#eg)", "stroke-width": 1.2, class: "ring", "stroke-dasharray": "3 5" }),
  s("circle", { cx: 32, cy: 32, r: 23, stroke: "rgba(127,227,255,0.5)", "stroke-width": 0.8, class: "ring2", "stroke-dasharray": "40 10 4 10" }),
  s("path", { d: "M22 44 V20 H42 M22 32 H37", stroke: "url(#eg)", "stroke-width": 3.2, "stroke-linecap": "square" }),
  s("circle", { cx: 42, cy: 44, r: 2.4, fill: "#7fe3ff" }));

export function icon(name) {
  const P = {
    home: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
    sound: "M4 9v6h4l5 4V5L8 9zM16 8a5 5 0 0 1 0 8M19 5a9 9 0 0 1 0 14",
    mute: "M4 9v6h4l5 4V5L8 9zM17 9l5 6M22 9l-5 6",
    help: "M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20zM9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5v.5",
    brief: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7",
    pin: "M9 3h6l-1 6 4 4H6l4-4zM12 13v8",
    x: "M6 6l12 12M18 6L6 18",
    bell: "M6 16V11a6 6 0 1 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0",
    full: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
    globe: "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18zM3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18",
    grid: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
    bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
    chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
    shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
    wallet: "M3 7h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H3zM3 7l12-4v4M17 13.5h.01",
    coin: "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18zM9 8h4.5a2 2 0 0 1 0 4H9zm0 4h5a2 2 0 0 1 0 4H9zM11 6v2M11 16v2",
    flag: "M5 21V4M5 4h11l-2 4 2 4H5",
  };
  return s("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 1.6, "stroke-linecap": "round", "stroke-linejoin": "round" }, s("path", { d: P[name] || P.grid }));
}
