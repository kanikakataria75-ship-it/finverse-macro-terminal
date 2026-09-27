import { S, on, emit, meta, api } from "../core/state.js";
import { h, s, clear, fmtPct, cls, tip, untip, debounce, ago } from "../core/util.js";
import { panel, seg } from "./common.js";
import { gauge } from "./macro.js";
import { quoteTable } from "./markets.js";
import { sound } from "../core/sound.js";

export function transmissionPanel(area = "tx") {
  const p = panel(area, "India Transmission Map · Implied Open", { mn: "TXM" });
  const box = h("div", { style: { position: "absolute", inset: 0 } });
  p.body.append(box);
  const note = h("span.src-note");
  p.tools.append(note);
  function draw() {
    clear(box);
    const T = S.analytics?.transmission;
    if (!T || !T.targets?.length) { box.append(h("div.empty", h("div", h("b", "CALIBRATING"), "Fitting 250-day betas of Indian sectors on global drivers…"))); return; }
    const W = box.clientWidth, H = box.clientHeight;
    if (W < 300 || H < 120) return;
    const drivers = T.drivers, targets = [...T.targets].sort((a, b) => (b.implied_pct ?? 0) - (a.implied_pct ?? 0));
    const dx = 150, tx = Math.max(dx + 260, W - 330);
    const dy = (i) => 30 + (i + 0.5) * ((H - 40) / drivers.length);
    const ty = (i) => 24 + (i + 0.5) * ((H - 30) / targets.length);
    const svg = s("svg", { width: W, height: H });
    const edges = s("g"), nodes = s("g");
    svg.append(s("defs", {}, s("filter", { id: "txglow" }, s("feGaussianBlur", { stdDeviation: 2.2, result: "b" }), s("feMerge", {}, s("feMergeNode", { in: "b" }), s("feMergeNode", { in: "SourceGraphic" })))), edges, nodes);
    const maxC = Math.max(0.02, ...targets.flatMap((t) => Object.values(t.contrib_pct).map((v) => Math.abs(v || 0))));
    const edgeEls = [];
    targets.forEach((t, j) => drivers.forEach((d, i) => {
      const c = t.contrib_pct[d.sym] || 0;
      const w = 0.35 + (Math.abs(c) / maxC) * 4.2;
      const x0 = dx + 8, y0 = dy(i), x1 = tx - 8, y1 = ty(j), mx = (x0 + x1) / 2;
      const col = c > 0 ? "#2fe3a3" : c < 0 ? "#ff5773" : "rgba(255,255,255,0.2)";
      const path = s("path", { d: `M${x0},${y0} C${mx},${y0} ${mx},${y1} ${x1},${y1}`, fill: "none", stroke: col, "stroke-width": w, opacity: 0.12 + Math.min(0.6, Math.abs(c) / maxC),
        "stroke-dasharray": Math.abs(c) / maxC > 0.25 ? "6 10" : null, style: Math.abs(c) / maxC > 0.25 ? `animation: dash ${2.4 - Math.min(1.6, Math.abs(c) / maxC)}s linear infinite` : "" });
      path.dataset.t = t.sym; path.dataset.d = d.sym;
      edges.append(path); edgeEls.push(path);
    }));
    drivers.forEach((d, i) => {
      const y = dy(i);
      nodes.append(s("circle", { cx: dx, cy: y, r: 6, fill: "#0b0e15", stroke: d.move > 0 ? "#2fe3a3" : "#ff5773", "stroke-width": 2, filter: "url(#txglow)" }),
        s("text", { x: dx - 14, y: y - 3, "text-anchor": "end", fill: "#eceff5", "font-size": 11, "font-weight": 800, "font-family": "JetBrains Mono" }, d.code),
        s("text", { x: dx - 14, y: y + 11, "text-anchor": "end", fill: d.move > 0 ? "#2fe3a3" : "#ff5773", "font-size": 10, "font-family": "JetBrains Mono" },
          `${d.move > 0 ? "+" : ""}${d.move?.toFixed(d.unit === "pp" ? 3 : 2)}${d.unit === "pp" ? "pp" : "%"}${d.lagged ? " · T-1" : ""}`));
    });
    targets.forEach((t, j) => {
      const y = ty(j);
      const g = s("g", { style: "cursor:pointer" });
      g.append(s("rect", { x: tx - 6, y: y - 9, width: W - tx - 6, height: 18, rx: 4, fill: "transparent" }),
        s("circle", { cx: tx, cy: y, r: 3.5, fill: t.implied_pct >= 0 ? "#2fe3a3" : "#ff5773" }),
        s("text", { x: tx + 10, y: y + 3.5, fill: "#eceff5", "font-size": 10.5, "font-weight": 700, "font-family": "JetBrains Mono" }, t.code));
      const bx = tx + 118, bw = 80, sc = 1.2;
      const v = Math.max(-sc, Math.min(sc, t.implied_pct || 0));
      g.append(s("line", { x1: bx + bw / 2, x2: bx + bw / 2, y1: y - 7, y2: y + 7, stroke: "rgba(255,255,255,0.12)" }),
        s("rect", { x: v >= 0 ? bx + bw / 2 : bx + bw / 2 + (v / sc) * (bw / 2), y: y - 4, width: Math.abs(v / sc) * (bw / 2), height: 8, rx: 2, fill: v >= 0 ? "#2fe3a3" : "#ff5773", opacity: 0.85 }),
        s("text", { x: bx + bw + 8, y: y + 3.5, fill: v >= 0 ? "#2fe3a3" : "#ff5773", "font-size": 10.5, "font-family": "JetBrains Mono" }, fmtPct(t.implied_pct)),
        s("text", { x: bx + bw + 66, y: y + 3.5, fill: "#626b7c", "font-size": 10, "font-family": "JetBrains Mono" }, `R² ${t.r2?.toFixed(2)}`));
      g.addEventListener("mouseenter", (e) => {
        edgeEls.forEach((p2) => p2.style.opacity = p2.dataset.t === t.sym ? 1 : 0.04);
        tip(e, `${t.name} · model`, [["Implied (overnight drivers)", fmtPct(t.implied_pct), cls(t.implied_pct)], ["Actual last session", fmtPct(t.actual_pct), cls(t.actual_pct)], ["Residual (stock-specific)", fmtPct(t.residual_pct), cls(t.residual_pct)],
          ...Object.entries(t.contrib_pct).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 4).map(([sym, c]) => [`  ${meta(sym).code} β ${t.betas[sym].b.toFixed(2)}`, fmtPct(c, 3), cls(c)])]);
      });
      g.addEventListener("mouseleave", () => { edgeEls.forEach((p2) => (p2.style.opacity = "")); untip(); });
      g.addEventListener("click", () => emit("ui:security", t.sym));
      nodes.append(g);
    });
    nodes.append(s("text", { x: dx - 14, y: 16, "text-anchor": "end", fill: "#626b7c", "font-size": 9, "font-weight": 800, "letter-spacing": 2, "font-family": "JetBrains Mono" }, "GLOBAL DRIVERS"),
      s("text", { x: tx + 10, y: 14, fill: "#626b7c", "font-size": 9, "font-weight": 800, "letter-spacing": 2, "font-family": "JetBrains Mono" }, "INDIA · IMPLIED MOVE"));
    box.append(svg);
    note.textContent = "OLS β · 250d · US drivers lagged T-1";
  }
  const style = document.createElement("style");
  style.textContent = "@keyframes dash { to { stroke-dashoffset: -32; } }";
  document.head.append(style);
  new ResizeObserver(draw).observe(box);
  on("analytics", draw); on("hydrated", draw);
  return p.el;
}

const SLIDERS = [["BZ=F", "BRENT", -40, 60, "%"], ["DX-Y.NYB", "DXY", -8, 8, "%"], ["^TNX", "US10Y", -150, 150, "bp"], ["INR=X", "USDINR", -8, 8, "%"], ["^IXIC", "NASDAQ", -25, 25, "%"], ["GC=F", "GOLD", -20, 30, "%"]];
const PRESETS = {
  "Oil shock": { "BZ=F": 25 }, "Taper tantrum": { "^TNX": 75, "DX-Y.NYB": 3 }, "Rupee crisis": { "INR=X": 5 },
  "Tech crash": { "^IXIC": -12 }, "Risk-on": { "^IXIC": 6, "DX-Y.NYB": -2, "BZ=F": 5 }, "Reset": {},
};
export function scenarioPanel(area = "scen") {
  const p = panel(area, "Scenario Simulator", { mn: "SCEN" });
  const vals = Object.fromEntries(SLIDERS.map(([sym]) => [sym, 0]));
  const sliders = h("div", { style: { padding: "8px 14px 4px" } });
  const presets = h("div.chip-list", { style: { padding: "4px 14px 10px" } });
  const out = h("div.scroll", { style: { flex: 1, minHeight: 0, padding: "4px 14px 10px", borderTop: "1px solid var(--line)" } });
  p.body.append(h("div.col", { style: { position: "absolute", inset: 0, gap: 0 } }, sliders, presets, out));
  const inputs = {};
  SLIDERS.forEach(([sym, label, lo, hi, unit]) => {
    const o = h("output", "0");
    const r = h("input", { type: "range", min: lo, max: hi, step: unit === "bp" ? 5 : 0.5, value: 0, on: { input: () => { vals[sym] = +r.value; o.textContent = `${r.value > 0 ? "+" : ""}${r.value}${unit}`; o.className = cls(+r.value); run(); } } });
    inputs[sym] = { r, o, unit };
    sliders.append(h("div.slider-row", h("label", label), r, o));
  });
  Object.keys(PRESETS).forEach((name) => presets.append(h("button.btn.sm", { on: { click: () => { sound.click(); apply(PRESETS[name]); } } }, name)));
  function apply(shocks) {
    for (const [sym, { r, o, unit }] of Object.entries(inputs)) {
      const v = shocks[sym] || 0; r.value = v; vals[sym] = v; o.textContent = `${v > 0 ? "+" : ""}${v}${unit}`; o.className = cls(v);
    }
    run();
  }
  const run = debounce(async () => {
    if (Object.values(vals).every((v) => !v)) { clear(out).append(h("div.empty", h("div", h("b", "DIAL IN A SHOCK"), "Move a slider or pick a preset. Impacts propagate through live 250-day betas."))); return; }
    const res = await api.post("/api/scenario", { shocks: vals });
    clear(out);
    const mx = Math.max(0.5, ...res.impacts.map((r) => Math.abs(r.impact_pct || 0)));
    res.impacts.forEach((r) => {
      const v = r.impact_pct || 0, w = (Math.abs(v) / mx) * 50;
      out.append(h("div.hbar", { style: { cursor: "pointer" }, on: { click: () => emit("ui:security", r.sym) } }, h("span.hb-l", r.code),
        h("div.hb-t", h("i", { style: { left: v >= 0 ? "50%" : `${50 - w}%`, width: `${w}%`, background: v >= 0 ? "linear-gradient(90deg, rgba(47,227,163,0.35), #2fe3a3)" : "linear-gradient(90deg, #ff5773, rgba(255,87,115,0.35))" } })),
        h("span.hb-v", { class: cls(v) }, fmtPct(v))));
    });
    out.append(h("div.src-note", { style: { marginTop: "8px" } }, "First-order linear propagation through estimated betas. Not a forecast; not investment advice."));
  }, 220);
  on("ui:scenario", (sc) => apply(Object.fromEntries(Object.entries(sc.shocks || {}).map(([k, v]) => [k, +v]))));
  run();
  return p.el;
}

export function indiaSectorsPanel(area = "sect") {
  const p = panel(area, "India Board", { mn: "IN" });
  p.body.classList.add("scroll");
  p.body.append(quoteTable(() => [["INDICES & SECTORS", S.universe.filter((u) => u.region === "INDIA" && (u.cls === "index" || u.cls === "sector" || u.cls === "vol")).map((u) => u.sym)],
    ["LARGE CAPS", S.universe.filter((u) => u.region === "INDIA" && u.cls === "equity").map((u) => u.sym)]], { cols: ["price", "pct", "w1", "ytd", "spark"] }));
  return p.el;
}

export function pulsePanel(area, which = "india", title = "India Pulse") {
  const p = panel(area, title, { mn: which === "india" ? "INPL" : "PULSE" });
  const g = gauge(0, { label: "FEAR ↔ GREED", colors: ["#ff5773", "#d9b56d", "#2fe3a3"] });
  const lbl = h("div.label-xs", { style: { textAlign: "center", marginTop: "6px" } });
  const comps = h("div", { style: { padding: "8px 14px" } });
  const hist = h("div", { style: { padding: "0 14px" } });
  p.body.classList.add("scroll");
  p.body.append(h("div", { style: { padding: "10px 40px 0" } }, g), lbl, hist, comps);
  function draw() {
    const P = S.analytics?.pulse?.[which];
    if (!P) return;
    g.set(P.value);
    lbl.textContent = `${P.label} · 1W ago ${P.w1 ?? "—"} · 1M ago ${P.m1 ?? "—"}`;
    lbl.className = `label-xs ${P.value >= 58 ? "up" : P.value <= 42 ? "down" : "gold"}`;
    clear(hist);
    if (P.series?.length) {
      const W = 320, H = 46;
      const sv = s("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", style: "width:100%;height:46px" });
      [25, 50, 75].forEach((v) => sv.append(s("line", { x1: 0, x2: W, y1: H - (v / 100) * H, y2: H - (v / 100) * H, stroke: "rgba(255,255,255,0.06)", "stroke-dasharray": "2 4" })));
      const d = P.series.map((v, i) => `${i ? "L" : "M"}${(i / (P.series.length - 1)) * W},${H - (v / 100) * H}`).join("");
      sv.append(s("path", { d, fill: "none", stroke: "#d9b56d", "stroke-width": 1.5, "vector-effect": "non-scaling-stroke" }));
      hist.append(h("div.src-note", { style: { margin: "6px 0 2px" } }, "90-DAY HISTORY"), sv);
    }
    clear(comps);
    (P.components || []).forEach((c) => {
      const v = c.value ?? 0;
      comps.append(h("div.meter-row", h("span.ml", c.label), h("div.meter", h("i", { style: { width: `${v}%`, background: v >= 58 ? "var(--up)" : v <= 42 ? "var(--down)" : "var(--gold)" } })), h("span.mv", c.value == null ? "—" : Math.round(v))));
    });
  }
  on("analytics", draw); on("hydrated", draw);
  draw();
  return p.el;
}

export function newsPanel(area, { title = "News", filter = () => true, mn = "N" } = {}) {
  const p = panel(area, title, { mn });
  const list = h("div.scroll", { style: { position: "absolute", inset: 0 } });
  p.body.append(list);
  function draw() {
    clear(list);
    const rows = S.news.filter(filter).slice(0, 60);
    if (!rows.length) list.append(h("div.empty", h("div", h("b", "QUIET"), "No matching headlines in the last 36 hours.")));
    rows.forEach((n) => list.append(h("a.list-row", { href: n.link, target: "_blank", rel: "noopener noreferrer", style: { alignItems: "flex-start" } },
      h("span.mono.muted", { style: { width: "34px", flex: "none", fontSize: "10px", paddingTop: "2px" } }, ago(n.ts)),
      h("div.grow", h("div", { style: { color: "var(--text)", lineHeight: 1.4 } }, n.title),
        h("div.row", { style: { marginTop: "5px", gap: "6px", flexWrap: "wrap" } }, h("span.src-note", n.source),
          n.confirmations > 1 ? h("span.tag.gold", `${n.confirmations} SOURCES`) : null,
          ...n.topics.slice(0, 3).map((t) => h("span.tag", t)),
          n.sentiment ? h("span.tag", { class: n.sentiment > 0.15 ? "up" : n.sentiment < -0.15 ? "down" : "" }, n.sentiment > 0 ? `+${n.sentiment.toFixed(2)}` : n.sentiment.toFixed(2)) : null)),
      h("span.mono", { style: { flex: "none", fontSize: "10px", color: n.importance >= 70 ? "var(--gold)" : "var(--text-4)" } }, n.importance))));
  }
  on("hydrated", draw);
  let t; on("news", () => { clearTimeout(t); t = setTimeout(draw, 800); });
  return p.el;
}
