import { S, on, emit, meta, api } from "../core/state.js";
import { h, s, clear, fmtPct, cls, tip, untip, mixHex, clamp, fmtSigned } from "../core/util.js";
import { panel, seg } from "./common.js";
import { CurveSurface } from "../three/surface.js";
import { sound } from "../core/sound.js";

const termActive = () => document.getElementById("terminal")?.classList.contains("active");

export function regimePanel(area = "regime") {
  const p = panel(area, "Macro Regime Compass", { mn: "RGM" });
  const cv = h("canvas", { style: { position: "absolute", left: 0, top: 0, width: "58%", height: "100%" } });
  const side = h("div.scroll", { style: { position: "absolute", right: 0, top: 0, bottom: 0, width: "42%", padding: "12px 14px", borderLeft: "1px solid var(--line)" } });
  p.body.append(cv, side);
  let t0 = performance.now(), raf;
  function paint() {
    const R = S.analytics?.regime;
    const dpr = Math.min(2, devicePixelRatio), W = cv.clientWidth, H = cv.clientHeight;
    if (!W || !H) return;
    cv.width = W * dpr; cv.height = H * dpr;
    const g = cv.getContext("2d"); g.scale(dpr, dpr);
    const cx = W / 2, cy = H / 2, r = Math.min(W, H) / 2 - 22, sc = r / 2.2;
    const quad = [["REFLATION", 1, -1, "rgba(217,181,109,0.06)"], ["GOLDILOCKS", 1, 1, "rgba(47,227,163,0.05)"], ["STAGFLATION", -1, -1, "rgba(255,87,115,0.06)"], ["DEFLATION", -1, 1, "rgba(127,227,255,0.05)"]];
    quad.forEach(([name, sx, sy, col]) => {
      g.fillStyle = col; g.fillRect(sx > 0 ? cx : cx - r, sy > 0 ? cy : cy - r, r, r);
      g.fillStyle = "rgba(255,255,255,0.28)"; g.font = "800 9px JetBrains Mono"; g.textAlign = sx > 0 ? "right" : "left";
      g.fillText(name, sx > 0 ? cx + r - 6 : cx - r + 6, sy > 0 ? cy + r - 8 : cy - r + 14);
    });
    g.strokeStyle = "rgba(255,255,255,0.12)"; g.lineWidth = 1;
    g.beginPath(); g.moveTo(cx - r, cy); g.lineTo(cx + r, cy); g.moveTo(cx, cy - r); g.lineTo(cx, cy + r); g.stroke();
    [1, 2].forEach((k) => { g.beginPath(); g.arc(cx, cy, k * sc, 0, Math.PI * 2); g.strokeStyle = "rgba(255,255,255,0.05)"; g.stroke(); });
    g.fillStyle = "#626b7c"; g.font = "700 8.5px JetBrains Mono"; g.textAlign = "center";
    g.fillText("GROWTH →", cx + r - 34, cy - 6); g.save(); g.translate(cx + 10, cy - r + 30); g.rotate(-Math.PI / 2); g.fillText("INFLATION →", 0, 0); g.restore();
    if (!R?.ready) return;
    const P = (pt) => [cx + clamp(pt.g, -2.2, 2.2) * sc, cy - clamp(pt.i, -2.2, 2.2) * sc];
    const tr = R.trail || [];
    g.lineWidth = 1.4;
    for (let k = 1; k < tr.length; k++) {
      const a = k / tr.length;
      g.strokeStyle = `rgba(217,181,109,${0.08 + a * 0.6})`;
      g.beginPath(); g.moveTo(...P(tr[k - 1])); g.lineTo(...P(tr[k])); g.stroke();
      g.fillStyle = `rgba(244,221,170,${0.15 + a * 0.6})`; g.beginPath(); g.arc(...P(tr[k]), 1.6 + a * 1.4, 0, Math.PI * 2); g.fill();
    }
    const [x, y] = P({ g: R.growth, i: R.inflation });
    const pulse = (Math.sin((performance.now() - t0) / 400) + 1) / 2;
    const grd = g.createRadialGradient(x, y, 0, x, y, 26 + pulse * 10);
    grd.addColorStop(0, "rgba(244,221,170,0.55)"); grd.addColorStop(1, "rgba(244,221,170,0)");
    g.fillStyle = grd; g.beginPath(); g.arc(x, y, 36, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#fff"; g.beginPath(); g.arc(x, y, 4.5, 0, Math.PI * 2); g.fill();
    g.strokeStyle = "#d9b56d"; g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 9 + pulse * 3, 0, Math.PI * 2); g.stroke();
  }
  function loop() { paint(); raf = requestAnimationFrame(loop); }
  function side_() {
    const R = S.analytics?.regime;
    clear(side);
    if (!R?.ready) { side.append(h("div.empty", h("div", h("b", "CALIBRATING"), "Needs market history…"))); return; }
    side.append(h("div.label-xs", "Current regime"), h("div", { style: { font: "300 22px/1.2 var(--f-display)", margin: "8px 0 4px", color: "var(--gold-2)" } }, R.regime),
      h("div.dim", { style: { fontSize: "12px" } }, R.description),
      h("div.row", { style: { margin: "10px 0", gap: "6px", flexWrap: "wrap" } }, h("span.tag", { class: R.risk_label === "RISK-ON" ? "up" : R.risk_label === "RISK-OFF" ? "down" : "" }, R.risk_label), h("span.tag.gold", `CONF ${Math.round(R.confidence * 100)}%`)),
      h("div", { style: { fontSize: "12px", color: "var(--text-2)", lineHeight: 1.5, padding: "8px 10px", borderRadius: "8px", background: "rgba(217,181,109,0.05)", border: "1px solid rgba(217,181,109,0.15)" } }, R.playbook),
      ...["growth", "inflation"].map((k) => h("div", { style: { marginTop: "12px" } }, h("div.label-xs", { style: { marginBottom: "4px" } }, `${k} signals (z)`),
        ...(R.components[k] || []).map((c) => { const v = c.z ?? 0, w = Math.min(50, Math.abs(v) * 20); return h("div.hbar", { style: { gridTemplateColumns: "1fr 70px 38px" } }, h("span.hb-l", { style: { fontFamily: "var(--f-ui)", fontWeight: 600 } }, c.label), h("div.hb-t", h("i", { style: { left: v >= 0 ? "50%" : `${50 - w}%`, width: `${w}%`, background: v >= 0 ? "var(--gold)" : "var(--ice)" } })), h("span.hb-v", fmtSigned(c.z, 2))); }))));
  }
  on("analytics", side_); on("hydrated", side_);
  on("ui:ws", (ws) => { cancelAnimationFrame(raf); if (ws === "analytics" && termActive()) loop(); });
  on("ui:view", (v) => { if (v !== "terminal") cancelAnimationFrame(raf); });
  side_();
  return p.el;
}

export function correlationPanel(area = "corr") {
  let win = "short";
  const p = panel(area, "Cross-Asset Correlation", { mn: "CORR" });
  const box = h("div", { style: { position: "absolute", inset: 0, display: "flex", flexDirection: "column" } });
  p.body.append(box);
  const col = (v) => (v == null ? "rgba(255,255,255,0.03)" : v >= 0 ? mixHex("#141922", "#d9b56d", Math.min(1, v)) : mixHex("#141922", "#3aa6d6", Math.min(1, -v)));
  function draw() {
    const C = S.analytics?.correlation;
    clear(box);
    if (!C?.ready) { box.append(h("div.empty", h("div", h("b", "COMPUTING"), "Correlation matrix loading…"))); return; }
    const n = C.syms.length, M = C[win];
    const cellH = Math.max(13, Math.min(26, Math.floor((box.clientHeight - 118) / (n + 1))));
    const grid = h("div.corr", { style: { gridTemplateColumns: `44px repeat(${n}, 1fr)`, gridAutoRows: `${cellH}px`, padding: "8px 10px 4px" } });
    grid.append(h("div.h"));
    C.codes.forEach((c) => grid.append(h("div.h", c.slice(0, 5))));
    C.codes.forEach((a, i) => {
      grid.append(h("div.h", { style: { justifyContent: "end", placeItems: "center end", paddingRight: "4px" } }, a.slice(0, 6)));
      M[i].forEach((v, j) => grid.append(h("div", { style: { background: col(v), color: Math.abs(v ?? 0) > 0.55 ? "#0b0e15" : "rgba(255,255,255,0.75)" },
        on: { mousemove: (e) => tip(e, `${C.codes[i]} × ${C.codes[j]}`, [[`${C.window[0]}d`, fmtSigned(C.short[i][j], 2)], [`${C.window[1]}d`, fmtSigned(C.long[i][j], 2)], ["Δ", fmtSigned((C.short[i][j] ?? 0) - (C.long[i][j] ?? 0), 2)]]), mouseleave: untip } }, i === j ? "" : v == null ? "" : (v * 100).toFixed(0))));
    });
    box.append(h("div.scroll", { style: { flex: 1, minHeight: 0 } }, grid,
      h("div", { style: { padding: "6px 14px 10px" } }, h("div.label-xs", { style: { marginBottom: "6px" } }, "Correlation breaks (60d vs 250d)"),
        ...(C.breaks.length ? C.breaks.slice(0, 6).map((b) => h("div.kv", h("span", `${b.a_code} × ${b.b_code}`), h("b", { class: cls(b.delta) }, `${fmtSigned(b.short, 2)} vs ${fmtSigned(b.long, 2)}`))) : [h("div.src-note", "No material breaks — relationships are stable.")]))));
  }
  p.tools.append(seg([["short", "60D"], ["long", "250D"]], win, (v) => { win = v; draw(); }));
  new ResizeObserver(() => draw()).observe(box);
  on("analytics", draw); on("hydrated", draw);
  return p.el;
}

export function surfacePanel(area = "surface") {
  const p = panel(area, "Yield Curve Surface · 3D", { mn: "GC3D", tools: [h("span.src-note", "drag to orbit")] });
  const canvas = h("canvas.stage");
  p.body.append(canvas);
  let surf, loaded = false;
  async function ensure() {
    if (!surf) surf = new CurveSurface(canvas);
    if (!loaded) { try { surf.setData(await api.get("/api/curve/surface")); loaded = true; } catch { /* retry on next open */ } }
    surf.start();
  }
  on("ui:ws", (ws) => { if (ws === "analytics" && termActive()) ensure(); else surf && surf.stop(); });
  on("ui:view", (v) => { if (v !== "terminal" && surf) surf.stop(); });
  return p.el;
}

const PRESETS = [
  ["Brent +4% → Nifty", "BZ=F", "gt", 4, "^NSEI"], ["VIX +20% → Bitcoin", "^VIX", "gt", 20, "BTC-USD"], ["USD/INR +0.8% → Bank Nifty", "INR=X", "gt", 0.8, "^NSEBANK"],
  ["US10Y +0.15pp → Nifty IT", "^TNX", "gt", 0.15, "^CNXIT"], ["Nasdaq −3% → Nifty IT", "^IXIC", "lt", -3, "^CNXIT"], ["Gold +2% → Nifty", "GC=F", "gt", 2, "^NSEI"],
  ["S&P −3% → Gold", "^GSPC", "lt", -3, "GC=F"], ["DXY +1% → EM (EEM)", "DX-Y.NYB", "gt", 1, "EEM"],
];
export function eventStudyPanel(area = "evt") {
  const p = panel(area, "Event Study Lab", { mn: "EVT" });
  const dl = h("datalist#evt-syms");
  const trig = h("input.input", { value: "BZ=F", list: "evt-syms", style: { width: "110px" } });
  const op = h("select.input", h("option", { value: "gt" }, "rises ≥"), h("option", { value: "lt" }, "falls ≤"));
  const thr = h("input.input", { type: "number", value: 4, step: "0.1", style: { width: "70px" } });
  const tgt = h("input.input", { value: "^NSEI", list: "evt-syms", style: { width: "110px" } });
  const out = h("div.scroll", { style: { flex: 1, minHeight: 0, padding: "10px 14px" } });
  const form = h("form.row", { style: { padding: "10px 14px", flexWrap: "wrap", gap: "6px", borderBottom: "1px solid var(--line)" }, on: { submit: (e) => { e.preventDefault(); run(); } } },
    h("span.label-xs", "WHEN"), trig, op, thr, h("span.label-xs", "% / pp THEN"), tgt, h("button.btn.gold.sm", { type: "submit" }, "RUN"), dl);
  const presets = h("div.chip-list", { style: { padding: "8px 14px", borderBottom: "1px solid var(--line)" } },
    PRESETS.map(([name, a, o, t, b]) => h("button.btn.sm", { on: { click: () => { trig.value = a; op.value = o; thr.value = t; tgt.value = b; run(); } } }, name)));
  p.body.append(h("div.col", { style: { position: "absolute", inset: 0, gap: 0 } }, form, presets, out));
  on("hydrated", () => { clear(dl); S.universe.forEach((u) => dl.append(h("option", { value: u.sym }, `${u.code} · ${u.name}`))); });
  clear(out).append(h("div.empty", h("div", h("b", "HISTORICAL EVIDENCE ENGINE"), "Pick a preset or define a trigger. 15 years of daily data, declustered events, abnormal returns with 95% bootstrap confidence intervals.")));
  async function run() {
    sound.go();
    clear(out).append(h("div.typing", h("i"), h("i"), h("i")), h("span.src-note", "  pulling 15 years of history…"));
    try {
      const r = await api.get(`/api/eventstudy?trigger=${encodeURIComponent(trig.value)}&target=${encodeURIComponent(tgt.value)}&threshold=${thr.value}&op=${op.value}`);
      clear(out);
      if (r.error) { out.append(h("div.empty", h("div", h("b", "INSUFFICIENT EVENTS"), r.error))); return; }
      out.append(h("div", { style: { font: "300 15px/1.4 var(--f-display)", marginBottom: "4px" } }, `When ${r.trigger_code} ${r.op === "gt" ? "rises ≥" : "falls ≤"} ${r.threshold}${r.unit} in a day → ${r.target_code}`),
        h("div.src-note", `${r.n_events} independent events · ${r.span[0]} → ${r.span[1]} · ${r.method}`));
      const tb = h("tbody");
      r.stats.forEach((st) => tb.append(h("tr", h("td", h("b", `+${st.h}D`)), h("td", { class: cls(st.mean) }, fmtPct(st.mean)), h("td.muted", fmtPct(st.baseline)),
        h("td", { class: cls(st.abnormal) }, fmtPct(st.abnormal)), h("td.muted", `${fmtPct(st.ci[0])} … ${fmtPct(st.ci[1])}`),
        h("td", `${st.hit_rate}% `, h("span.muted", `(${st.base_hit}%)`)), h("td", h("span.tag", { class: st.significant ? "gold" : "" }, st.significant ? "SIGNIFICANT" : "NOISE")))));
      out.append(h("table.grid", { style: { margin: "10px 0" } }, h("thead", h("tr", ...["Horizon", "Mean", "Base", "Abnormal", "95% CI", "Hit rate (base)", "Verdict"].map((x) => h("th", x)))), tb));
      out.append(pathChart(r.path), h("div.row", { style: { gap: "14px", alignItems: "flex-start", marginTop: "10px" } }, histChart(r.dist, r.dist_h), recentTable(r)));
    } catch (e) { clear(out).append(h("div.down", e.message)); }
  }
  return p.el;
}

function pathChart(path) {
  const W = 560, H = 150, pad = 28;
  const ks = path.map((p) => p.k), vals = path.flatMap((p) => [p.p25, p.p75, p.mean]).filter((v) => v != null);
  const lo = Math.min(...vals, 0), hi = Math.max(...vals, 0);
  const x = (k) => pad + ((k - ks[0]) / (ks[ks.length - 1] - ks[0])) * (W - pad - 8), y = (v) => 10 + (1 - (v - lo) / (hi - lo || 1)) * (H - 26);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, style: "width:100%;height:150px" });
  svg.append(s("line", { x1: pad, x2: W - 8, y1: y(0), y2: y(0), stroke: "rgba(255,255,255,0.12)" }), s("line", { x1: x(0), x2: x(0), y1: 6, y2: H - 16, stroke: "rgba(217,181,109,0.45)", "stroke-dasharray": "3 4" }),
    s("text", { x: x(0) + 4, y: 14, fill: "#d9b56d", "font-size": 9, "font-family": "JetBrains Mono" }, "EVENT"));
  const band = path.filter((p) => p.p25 != null);
  svg.append(s("path", { d: `M${band.map((p) => `${x(p.k)},${y(p.p75)}`).join("L")}L${band.slice().reverse().map((p) => `${x(p.k)},${y(p.p25)}`).join("L")}Z`, fill: "rgba(127,227,255,0.08)" }));
  svg.append(s("path", { d: `M${path.filter((p) => p.mean != null).map((p) => `${x(p.k)},${y(p.mean)}`).join("L")}`, fill: "none", stroke: "#f4ddaa", "stroke-width": 2 }));
  [-5, 0, 5, 10, 15, 20].forEach((k) => svg.append(s("text", { x: x(k), y: H - 3, "text-anchor": "middle", fill: "#626b7c", "font-size": 9, "font-family": "JetBrains Mono" }, k > 0 ? `+${k}` : k)));
  svg.append(s("text", { x: 2, y: y(hi) + 4, fill: "#626b7c", "font-size": 9, "font-family": "JetBrains Mono" }, `${hi.toFixed(1)}%`), s("text", { x: 2, y: y(lo), fill: "#626b7c", "font-size": 9, "font-family": "JetBrains Mono" }, `${lo.toFixed(1)}%`));
  return h("div", h("div.label-xs", "Average cumulative path · interquartile band"), svg);
}
function histChart(dist, hz) {
  const W = 240, H = 110, bins = 18;
  const v = dist.filter((x) => x != null);
  const lo = Math.min(...v), hi = Math.max(...v), step = (hi - lo) / bins || 1;
  const counts = Array(bins).fill(0);
  v.forEach((x) => counts[Math.min(bins - 1, Math.floor((x - lo) / step))]++);
  const mx = Math.max(...counts);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, style: "width:240px;height:110px" });
  counts.forEach((c, i) => { const x0 = lo + i * step; svg.append(s("rect", { x: 4 + i * ((W - 8) / bins), y: H - 14 - (c / mx) * (H - 24), width: (W - 8) / bins - 2, height: (c / mx) * (H - 24), rx: 1.5, fill: x0 + step / 2 >= 0 ? "#2fe3a3" : "#ff5773", opacity: 0.8 })); });
  svg.append(s("text", { x: 4, y: H - 2, fill: "#626b7c", "font-size": 9, "font-family": "JetBrains Mono" }, `${lo.toFixed(1)}%`), s("text", { x: W - 4, y: H - 2, "text-anchor": "end", fill: "#626b7c", "font-size": 9, "font-family": "JetBrains Mono" }, `${hi.toFixed(1)}%`));
  return h("div", h("div.label-xs", `+${hz}D outcome distribution`), svg);
}
function recentTable(r) {
  const tb = h("tbody");
  r.recent.slice(0, 8).forEach((e) => tb.append(h("tr", h("td.muted", e.date), h("td", fmtSigned(e.trigger, 2)), ...[1, 5, 20].map((k) => h("td", { class: cls(e[`h${k}`]) }, e[`h${k}`] == null ? "—" : fmtPct(e[`h${k}`], 1))))));
  return h("div.grow", h("div.label-xs", "Most recent events"), h("table.grid", h("thead", h("tr", h("th", "Date"), h("th", "Trig"), h("th", "+1D"), h("th", "+5D"), h("th", "+20D"))), tb));
}
