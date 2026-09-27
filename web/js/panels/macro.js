import { S, on, emit, meta, api } from "../core/state.js";
import { h, s, clear, fmtPx, fmtPct, cls, sparkline, setNum, tip, untip, ago, hhmm, seqColor, divColor, store, toast } from "../core/util.js";
import { ISO_NUM, NUM_ISO, EURO_AREA, COUNTRY_FX, FX_INVERTED } from "../core/world.js";
import { panel, seg, icon } from "./common.js";
import { sound } from "../core/sound.js";

// ============================================================ RHETORIC RADAR
export function gauge(value, { max = 100, label = "", sub = "", colors = ["#7fe3ff", "#d9b56d", "#ff5773"] } = {}) {
  const id = `gg${Math.random().toString(36).slice(2, 7)}`;
  const arc = (a0, a1, r) => {
    const p = (a) => [90 + r * Math.cos(Math.PI - a), 84 - r * Math.sin(Math.PI - a)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    return `M${x0},${y0} A${r},${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${x1},${y1}`;
  };
  const svg = s("svg", { viewBox: "0 0 180 96" },
    s("defs", {}, s("linearGradient", { id, x1: 0, x2: 1 }, ...colors.map((c, i) => s("stop", { offset: `${(i / (colors.length - 1)) * 100}%`, "stop-color": c })))),
    s("path", { d: arc(0, Math.PI, 70), stroke: "rgba(255,255,255,0.06)", "stroke-width": 7, fill: "none", "stroke-linecap": "round" }),
    ...Array.from({ length: 11 }, (_, i) => { const a = (i / 10) * Math.PI; return s("line", { x1: 90 + 78 * Math.cos(Math.PI - a), y1: 84 - 78 * Math.sin(Math.PI - a), x2: 90 + 83 * Math.cos(Math.PI - a), y2: 84 - 83 * Math.sin(Math.PI - a), stroke: "rgba(255,255,255,0.18)", "stroke-width": 1 }); }));
  const fill = s("path", { d: arc(0, 0.001, 70), stroke: `url(#${id})`, "stroke-width": 7, fill: "none", "stroke-linecap": "round", style: "filter: drop-shadow(0 0 6px rgba(217,181,109,0.5))" });
  const needle = s("g", { style: "transition: transform 1.2s cubic-bezier(.22,1,.36,1); transform-origin: 90px 84px" },
    s("line", { x1: 90, y1: 84, x2: 90, y2: 26, stroke: "#fff", "stroke-width": 1.6, "stroke-linecap": "round", style: "filter: drop-shadow(0 0 4px #fff)" }),
    s("circle", { cx: 90, cy: 84, r: 4, fill: "#0b0e15", stroke: "#f4ddaa", "stroke-width": 1.5 }));
  svg.append(fill, needle);
  const valEl = h("b", "—"), subEl = h("span", label);
  const box = h("div.gauge", svg, h("div.gv", valEl, subEl));
  box.set = (v, text) => {
    const t = Math.max(0, Math.min(1, (v ?? 0) / max));
    fill.setAttribute("d", arc(0, Math.max(0.001, t * Math.PI), 70));
    needle.style.transform = `rotate(${-90 + t * 180}deg)`;
    valEl.textContent = v == null ? "—" : text ?? Math.round(v);
  };
  box.set(value);
  return box;
}

export function rhetoricPanel(area = "rh") {
  let mode = "TRUMP";
  const p = panel(area, "Rhetoric Radar", { mn: "RHET", tools: [] });
  p.tools.append(seg([["TRUMP", "TRUMP"], ["FED", "FED"], ["RBI", "RBI"], ["ECB", "ECB"]], mode, (v) => { mode = v; render(); }));
  const root = h("div.rh");
  p.body.append(root);
  const g = gauge(0, { label: "MARKET HEAT" });
  function render() {
    clear(root);
    const R = S.rhetoric || {};
    if (mode === "TRUMP") {
      const m = R.meter || {};
      const pol = m.polarity || 0;
      g.set(m.heat || 0);
      const top = (R.posts || []).find((x) => x.relevance > 0) || (R.posts || [])[0];
      root.append(h("div.rh-top", h("div.rh-avatar", "DJT"), g,
        h("div.col", { style: { gap: "6px", alignItems: "flex-end" } },
          h("span.tag", { class: pol > 0.15 ? "up" : pol < -0.15 ? "down" : "" }, pol > 0.15 ? "CONSTRUCTIVE" : pol < -0.15 ? "HOSTILE" : "NEUTRAL TONE"),
          h("span.src-note", `${m.posts_24h || 0} posts · 24h`))));
      if (top) {
        root.append(h("div.rh-post",
          h("div.meta", h("span", top.published || ""), ...(top.market_topics || []).map((t) => h("span.tag.gold", t)), h("span.tag", { class: top.heat >= 60 ? "down" : "" }, `HEAT ${top.heat}`),
            top.url ? h("a", { href: top.url, target: "_blank", rel: "noopener noreferrer", style: { marginLeft: "auto", color: "var(--text-3)" } }, "SOURCE ↗") : null),
          h("div", top.text)));
        const hist = (top.history || [])[0];
        const st = R.study || {};
        root.append(h("div.rh-hist",
          hist ? h("div", "History · ", h("b", `${hist.topic}`), ` → ${hist.asset} 1W abnormal `, h("b", { class: cls(hist.abnormal) }, fmtPct(hist.abnormal)),
            ` (95% CI ${fmtPct(hist.ci?.[0])} … ${fmtPct(hist.ci?.[1])}, n=${hist.n}) `, h("span.tag", { class: hist.significant ? "warn" : "" }, hist.significant ? "SIG*" : "NOISE")) : h("div", "No market-relevant topic in the latest post."),
          h("div", { style: { marginTop: "4px" } }, `Study: ${st.significant ?? "—"}/${st.tests ?? "—"} tests significant vs ${st.expected_false_positives ?? "—"} expected by chance — ${st.verdict || ""}`)));
      }
      const list = h("div.rh-list.scroll");
      (R.posts || []).slice(0, 14).forEach((x) => list.append(h("div.rh-item", h("span.hv", { class: x.heat >= 60 ? "down" : x.heat >= 30 ? "gold" : "muted" }, x.heat), h("span.ellipsis", { title: x.text }, x.text))));
      root.append(list);
    } else {
      const b = (R.banks || {})[mode] || {};
      const st = b.stance;
      root.append(h("div.rh-top", h("div.rh-avatar", mode),
        h("div.col.grow", { style: { gap: "4px" } },
          h("span.label-xs", "Policy rate"),
          h("div.big-num", { style: { fontSize: "34px" } }, mode === "FED" && S.macro.fed?.target_to != null ? `${S.macro.fed.target_from.toFixed(2)}–${S.macro.fed.target_to.toFixed(2)}%` : b.rate != null ? `${b.rate.toFixed(2)}%` : "—"),
          h("span.src-note", mode === "FED" ? `NY Fed · EFFR ${S.macro.fed?.effr ?? "—"}%` : b.rate_src === "headline" ? `from headline ${b.rate_asof ? ago(b.rate_asof) + " ago" : ""}` : b.rate_src || "awaiting next policy statement"))));
      root.append(h("div.stance-lbl", h("span", "DOVISH"), h("span", st == null ? "NO RECENT POLICY COMMS" : `STANCE ${st > 0 ? "+" : ""}${st.toFixed(2)}`), h("span", "HAWKISH")));
      const bar = h("div.stance-bar", h("i", { style: { left: `${st == null ? 50 : 50 + st * 48}%`, opacity: st == null ? 0.25 : 1 } }));
      root.append(bar);
      const list = h("div.rh-list.scroll", { style: { marginTop: "8px" } });
      (b.items || []).forEach((it) => list.append(h("a.rh-item", { href: it.link || "#", target: "_blank", rel: "noopener noreferrer" },
        h("span.hv", { class: it.policy ? "gold" : "muted" }, it.policy ? "POL" : ago(it.ts)), h("span", it.title))));
      if (!(b.items || []).length) list.append(h("div.empty", h("div", h("b", "SYNCING"), "Central-bank feed loading…")));
      root.append(list);
    }
  }
  on("hydrated", render); on("rhetoric", render); on("macro", () => mode === "FED" && render());
  render();
  return p.el;
}

// ============================================================ ASSET MATRIX
export function matrixPanel(area = "mx", syms) {
  let tf = store.get("mx.tf", "D");
  const p = panel(area, "Macro Asset Matrix", { mn: "MTRX" });
  p.tools.append(seg([["D", "1D"], ["W", "1W"], ["M", "1M"], ["Y", "YTD"]], tf, (v) => { tf = v; store.set("mx.tf", v); render(); }));
  const grid = h("div.mx-grid");
  p.body.classList.add("scroll");
  p.body.append(grid);
  const cards = {};
  const val = (q) => (tf === "D" ? q.pct : tf === "W" ? q.w1 : tf === "M" ? q.m1 : q.ytd);
  function card(sym) {
    const m = meta(sym), q = S.quotes[sym] || {};
    const px = h("div.mc-px", fmtPx(q.price, sym)), pc = h("span.mc-pct"), src = h("span.mc-src"), sp = h("div");
    const el = h("div.mx-card", { on: { click: () => emit("ui:security", sym), mouseenter: () => sound.hover() } },
      h("div.mc-top", h("span.mc-code", m.code), src), px, h("div.mc-row", pc, h("span.mc-src", m.name.split(" ").slice(0, 2).join(" "))), sp);
    cards[sym] = { el, px, pc, src, sp };
    return el;
  }
  function paint(sym, prev) {
    const c = cards[sym], q = S.quotes[sym];
    if (!c || !q) return;
    setNum(c.px, fmtPx(q.price, sym), prev != null ? Math.sign(q.price - prev) : 0);
    const v = val(q);
    c.pc.textContent = `${v > 0 ? "▲" : v < 0 ? "▼" : "•"} ${fmtPct(v)}`;
    c.pc.className = `mc-pct ${cls(v)}`;
    const live = q.src === "BINANCE" || q.src === "ANGEL";
    c.src.textContent = live ? "● LIVE" : "DELAYED";
    c.src.className = `mc-src ${live ? "live" : ""}`;
    clear(c.sp).append(sparkline(q.spark, { w: 120, h: 34 }));
  }
  function render() {
    clear(grid);
    (syms || S.matrix).forEach((sym) => { grid.append(card(sym)); paint(sym); });
  }
  on("hydrated", render);
  on("quotes", ({ changed, prev }) => Object.keys(changed).forEach((sym) => paint(sym, prev[sym])));
  render();
  return p.el;
}

// ============================================================ WORLD MAP (2D)
export function worldMapPanel(area = "map") {
  let mode = store.get("map.mode", "risk");
  let dim = store.get("map.dim", "3d");
  const layers = store.get("map.layers", { quakes: true, choke: true });
  const p = panel(area, "Global Macro Radar", { mn: "GEO" });
  const wrap = h("div.map-wrap");       // flat D3 map
  const wrap3 = h("div.map3d-wrap");    // 3D macro terrain
  const legend = h("div.map-legend"), srcNote = h("div.map-src.src-note");
  const hint = h("div.map3d-hint", "DRAG TO ORBIT · SCROLL TO ZOOM · DOUBLE-CLICK TO RESET");
  const drawer = h("div.drawer");
  const modes = seg([["risk", "CONFLICT"], ["mkt", "EQUITIES"], ["fx", "FX vs USD"], ["oil", "OIL"], ["gold", "GOLD"]], mode, (v) => { mode = v; store.set("map.mode", v); color(); });
  const dimSeg = seg([["3d", "3D"], ["2d", "2D"]], dim, (v) => { dim = v; store.set("map.dim", v); applyDim(); });
  const lq = h("button.btn.sm", { class: layers.quakes ? "on" : "", on: { click: () => { layers.quakes = !layers.quakes; lq.classList.toggle("on"); store.set("map.layers", layers); overlays(); } } }, "QUAKES");
  const lc = h("button.btn.sm", { class: layers.choke ? "on" : "", on: { click: () => { layers.choke = !layers.choke; lc.classList.toggle("on"); store.set("map.layers", layers); overlays(); } } }, "CHOKEPOINTS");
  p.body.append(wrap3, wrap, h("div.map-modes", modes), h("div.map-layers", dimSeg, lq, lc), legend, srcNote, hint, drawer);
  let svg, gRoot, gCountries, gOver, proj, features = [], zoomK = 1;
  let m3 = null, m3Failed = false, active = false;

  const idxByIso = () => Object.fromEntries(S.universe.filter((u) => u.iso3 && u.cls === "index").map((u) => [u.iso3, u.sym]));
  function valueFor(iso) {
    const G = S.geo || {};
    if (mode === "risk") return G.conflict?.[iso]?.score ?? null;
    if (mode === "oil") return G.oil?.[iso] ?? null;
    if (mode === "gold") return G.gold?.[iso] ?? null;
    if (mode === "mkt") { const sym = idxByIso()[iso]; return sym ? S.quotes[sym]?.pct ?? null : null; }
    if (mode === "fx") {
      const pair = EURO_AREA.includes(iso) ? "EURUSD=X" : COUNTRY_FX[iso];
      if (!pair) return iso === "USA" ? -(S.quotes["DX-Y.NYB"]?.pct ?? 0) * -1 : null;
      const q = S.quotes[pair]; if (!q || q.pct == null) return null;
      return FX_INVERTED.has(pair) ? q.pct : -q.pct;
    }
  }
  function fill(v) {
    if (v == null) return "rgba(255,255,255,0.028)";
    if (mode === "risk") return seqColor(v / 100, ["#141922", "#3b1822", "#9c2438", "#ff5773"]);
    if (mode === "mkt") return divColor(v, 2);
    if (mode === "fx") return divColor(v, 1);
    const max = mode === "oil" ? 303 : 8133;
    return seqColor(Math.log1p(v) / Math.log1p(max), mode === "oil" ? ["#10161d", "#16303a", "#1f7f96", "#7fe3ff"] : ["#12141a", "#3a2c12", "#b8863a", "#f4ddaa"]);
  }
  /** 0..1 prism height for the 3D terrain */
  function norm(v) {
    if (v == null) return null;
    if (mode === "risk") return Math.pow(Math.max(0, v) / 100, 1.15);
    if (mode === "mkt") return Math.min(Math.abs(v), 3) / 3;
    if (mode === "fx") return Math.min(Math.abs(v), 1.5) / 1.5;
    return Math.log1p(v) / Math.log1p(mode === "oil" ? 303 : 8133);
  }
  function tipFor(iso, name) {
    const v = valueFor(iso), pctMode = mode === "mkt" || mode === "fx";
    const unit = { risk: "/100", mkt: "%", fx: "%", oil: " bn bbl", gold: " t" }[mode];
    const cf = S.geo?.conflict?.[iso];
    const scored = cf && cf.score != null;
    return [name, [
      [{ risk: "Conflict intensity", mkt: "Index today", fx: "Currency vs USD", oil: "Oil reserves", gold: "Gold holdings" }[mode],
        v == null ? "—" : `${pctMode ? fmtPct(v) : v.toLocaleString()}${pctMode ? "" : unit}`, pctMode ? cls(v) : ""],
      ...(scored && mode !== "risk" ? [["Conflict", `${cf.score.toFixed(0)}/100`]] : []),
      ...(scored && mode === "risk" ? [["Conflict share of coverage", `${cf.share}%`], ["Source", cf.method === "gdelt" ? "GDELT" : "Finverse wire"], ["Confidence", (cf.confidence || "—").toUpperCase(), cf.confidence === "low" ? "down" : ""]] : []),
      ...(cf && !scored && mode === "risk" ? [["Coverage", "insufficient to score"]] : [])]];
  }
  function terrainData() {
    const data = new Map(), ranked = [];
    for (const [num, iso] of Object.entries(NUM_ISO)) {
      const v = valueFor(iso);
      if (v == null) continue;
      const n = norm(v);
      data.set(+num, { color: fill(v), h: n });
      ranked.push({ num: +num, iso, v, n });
    }
    ranked.sort((x, y) => y.n - x.n);
    const codes = idxByIso();
    const labels = ranked.slice(0, 7).map((r) => ({
      id: r.num,
      text: mode === "mkt" && codes[r.iso] ? meta(codes[r.iso]).code : null,
      value: mode === "mkt" || mode === "fx" ? fmtPct(r.v) : mode === "risk" ? `${r.v.toFixed(0)}` : `${Math.round(r.v).toLocaleString()}${mode === "oil" ? " bn" : " t"}`,
      tone: mode === "mkt" || mode === "fx" ? cls(r.v) : mode === "risk" ? "down" : mode === "oil" ? "ice" : "gold",
    }));
    return [data, labels];
  }
  function color() {
    if (gCountries) gCountries.selectAll("path").attr("fill", (d) => fill(valueFor(NUM_ISO[+d.id])));
    if (m3) m3.setData(...terrainData());
    clear(legend);
    const ramps = {
      risk: ["linear-gradient(90deg,#141922,#9c2438,#ff5773)", "CALM", "INTENSE"],
      mkt: ["linear-gradient(90deg,#e2324f,#141a22,#12c088)", "−2%", "+2%"],
      fx: ["linear-gradient(90deg,#e2324f,#141a22,#12c088)", "WEAKER", "STRONGER"],
      oil: ["linear-gradient(90deg,#10161d,#1f7f96,#7fe3ff)", "LOW", "303 bn bbl"],
      gold: ["linear-gradient(90deg,#12141a,#b8863a,#f4ddaa)", "LOW", "8,133 t"],
    }[mode];
    legend.append(h("span", ramps[1]), h("span.ramp", { style: { background: ramps[0] } }), h("span", ramps[2]),
      dim === "3d" && !m3Failed ? h("span", { style: { marginLeft: "8px", color: "var(--text-4)" } }, "· HEIGHT = MAGNITUDE") : null);
    const src = S.geo?.sources || {};
    srcNote.textContent = { risk: src.conflict, mkt: "Benchmark index, session % · Yahoo (delayed)", fx: "Local currency vs USD, session %", oil: src.oil, gold: src.gold }[mode] || "";
  }
  function overlays() {
    const G = S.geo || {};
    const quakes = layers.quakes ? (G.quakes || []).filter((q) => q.mag >= 5).slice(0, 40) : [];
    const chokes = layers.choke ? G.chokepoints || [] : [];
    if (m3) m3.setOverlays({ quakes, chokepoints: chokes });
    if (!gOver) return;
    gOver.selectAll("*").remove();
    quakes.forEach((q) => {
      const [x, y] = proj([q.lon, q.lat]);
      const r = (q.mag - 4) * 2.4 / Math.sqrt(zoomK);
      const g = gOver.append("g").attr("transform", `translate(${x},${y})`).style("cursor", "pointer")
        .on("mouseenter", (e) => quakeTip(e, q)).on("mouseleave", untip);
      g.append("circle").attr("r", r).attr("fill", "rgba(255,182,72,0.5)");
      g.append("circle").attr("r", r).attr("class", "quake-ring").attr("stroke-width", 1 / zoomK);
    });
    chokes.forEach((c) => {
      const [x, y] = proj([c.lon, c.lat]);
      const col = c.status === "CRITICAL" ? "#ff3b5c" : c.status === "ELEVATED" ? "#ffb648" : "#7fe3ff";
      const sz = 4.2 / Math.sqrt(zoomK);
      const g = gOver.append("g").attr("class", "choke-mark").attr("transform", `translate(${x},${y})`)
        .on("mouseenter", (e) => chokeTip(e, c)).on("mouseleave", untip);
      if (c.status !== "NORMAL") g.append("circle").attr("r", sz * 1.6).attr("class", "hot-ring").attr("stroke", col).attr("stroke-width", 1 / zoomK);
      g.append("rect").attr("x", -sz / 2).attr("y", -sz / 2).attr("width", sz).attr("height", sz).attr("transform", "rotate(45)").attr("fill", col).attr("stroke", "#000").attr("stroke-width", 0.5 / zoomK);
    });
  }
  const quakeTip = (e, q) => tip(e, `M${q.mag.toFixed(1)} earthquake`, [q.place, ["When", `${ago(q.t)} ago`], ["Tsunami flag", q.tsunami ? "YES" : "no", q.tsunami ? "down" : ""]]);
  const chokeTip = (e, c) => tip(e, c.name, [["Status", c.status, c.status === "NORMAL" ? "up" : "down"], ["Risk", c.risk.toFixed(0)], ["Carries", c.flows], ...c.drivers.slice(0, 3)]);
  function openDrawer(iso, name) {
    const G = S.geo || {}, sym = idxByIso()[iso], q = sym ? S.quotes[sym] : null, cf = G.conflict?.[iso];
    const scored = cf && cf.score != null;
    const pair = EURO_AREA.includes(iso) ? "EURUSD=X" : COUNTRY_FX[iso];
    clear(drawer);
    drawer.append(h("div.row.between", h("h3", name), h("button.icon-btn", { on: { click: () => drawer.classList.remove("on") } }, icon("x"))),
      h("div.src-note", iso), h("div", { style: { height: "10px" } }),
      sym ? h("div.kv", { style: { cursor: "pointer" }, on: { click: () => emit("ui:security", sym) } }, h("span", meta(sym).name), h("b", { class: cls(q?.pct) }, `${fmtPx(q?.price, sym)}  ${fmtPct(q?.pct)}`)) : null,
      pair ? h("div.kv", h("span", `FX ${meta(pair).code}`), h("b", { class: cls(S.quotes[pair]?.pct) }, `${fmtPx(S.quotes[pair]?.price, pair)}  ${fmtPct(S.quotes[pair]?.pct)}`)) : null,
      scored ? h("div.kv", h("span", "Conflict intensity"), h("b", { class: cf.score >= 60 ? "down" : "" }, `${cf.score.toFixed(0)}/100`)) : null,
      scored && cf.escalation != null ? h("div.kv", h("span", "Escalation (24h)"), h("b", { class: cf.escalation >= 1.5 ? "down" : "" }, `${cf.escalation.toFixed(2)}×`)) : null,
      G.oil?.[iso] != null ? h("div.kv", h("span", "Proved oil reserves"), h("b", `${G.oil[iso]} bn bbl`)) : null,
      G.gold?.[iso] != null ? h("div.kv", h("span", "Official gold"), h("b", `${G.gold[iso].toLocaleString()} t`)) : null,
      h("div", { style: { height: "12px" } }),
      h("button.btn.gold", { style: { width: "100%" }, on: { click: () => emit("ui:ask", `Explain ${name} ${sym ? meta(sym).code : ""} today`) } }, "ASK ORACLE"),
      h("div.label-xs", { style: { margin: "16px 0 8px" } }, "On the wire"));
    const list = h("div");
    drawer.append(list);
    drawer.classList.add("on");
    api.get(`/api/news?q=${encodeURIComponent(name.split(" ")[0])}&n=8`).then((rows) => {
      if (!rows.length) list.append(h("div.src-note", "No recent headlines."));
      rows.forEach((r) => list.append(h("a.kv", { href: r.link, target: "_blank", rel: "noopener noreferrer" }, h("span", { style: { color: "var(--text-2)" } }, r.title))));
    }).catch(() => {});
  }

  // ---------------------------------------------------------------- 3D
  async function ensure3d() {
    if (m3 || m3Failed) return m3;
    try {
      const { MacroMap3D } = await import("../three/map3d.js");
      m3 = new MacroMap3D(wrap3, {
        onHover: (u, e) => {
          if (!u || !e) return untip();
          if (u.kind === "quake") return quakeTip(e, u.info);
          if (u.kind === "choke") return chokeTip(e, u.info);
          tip(e, ...tipFor(NUM_ISO[u.id] || "", u.name));
        },
        onClick: (u) => { if (!u.kind) { sound.click(); openDrawer(NUM_ISO[u.id] || "", u.name); } },
      });
      await m3.ready;
      color(); overlays(); sync();
    } catch (err) {
      console.warn("3D map unavailable, using 2D:", err);
      m3Failed = true; dim = "2d"; applyDim();
    }
    return m3;
  }
  function sync() {
    if (!m3) return;
    if (active && dim === "3d") { m3.resize(); m3.start(); } else m3.stop();
  }
  function applyDim() {
    const three = dim === "3d" && !m3Failed;
    wrap3.classList.toggle("hidden", !three);
    wrap.classList.toggle("hidden", three);
    hint.classList.toggle("hidden", !three);
    untip();
    if (three) ensure3d();
    else if (!svg) build2d();
    sync(); color(); overlays();
  }
  on("ui:ws", (ws) => { active = ws === "macro" && document.getElementById("terminal").classList.contains("active"); sync(); });
  on("ui:view", (v) => { if (v !== "terminal") { active = false; sync(); } });

  // ---------------------------------------------------------------- 2D
  async function build2d() {
    if (svg) return;
    const topo = await (await fetch("/vendor/data/countries-110m.json")).json();
    features = topojson.feature(topo, topo.objects.countries).features;
    const W = wrap.clientWidth || 800, H = wrap.clientHeight || 420;
    proj = d3.geoNaturalEarth1().fitExtent([[10, 34], [W - 10, H - 26]], { type: "Sphere" });
    const path = d3.geoPath(proj);
    svg = d3.select(wrap).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("preserveAspectRatio", "xMidYMid meet");
    gRoot = svg.append("g");
    gRoot.append("path").datum({ type: "Sphere" }).attr("class", "sphere").attr("d", path);
    gRoot.append("path").datum(d3.geoGraticule10()).attr("class", "graticule").attr("d", path);
    gCountries = gRoot.append("g");
    gCountries.selectAll("path").data(features).join("path").attr("class", "country").attr("d", path)
      .on("mousemove", (e, d) => tip(e, ...tipFor(NUM_ISO[+d.id], d.properties.name)))
      .on("mouseleave", untip)
      .on("click", (e, d) => { sound.click(); openDrawer(NUM_ISO[+d.id] || "", d.properties.name); });
    gOver = gRoot.append("g");
    svg.call(d3.zoom().scaleExtent([1, 8]).translateExtent([[0, 0], [W, H]]).on("zoom", (e) => { zoomK = e.transform.k; gRoot.attr("transform", e.transform); overlays(); }));
    color(); overlays();
  }

  on("hydrated", () => { color(); overlays(); });
  on("geo", () => { color(); overlays(); });
  let qt; on("quotes", () => { if (mode === "mkt" || mode === "fx") { clearTimeout(qt); qt = setTimeout(color, 800); } });
  setTimeout(applyDim, 0);
  return p.el;
}

// ============================================================ ORACLE
export function oraclePanel(area = "or") {
  const p = panel(area, "Oracle · Intelligence Console", { mn: "ASK" });
  const out = h("div.or-out.scroll");
  const input = h("input.input", { placeholder: "Ask anything — “why is Nifty IT down?”, “what if Brent +20%”, “compare gold vs bitcoin”", maxLength: 400 });
  const engine = h("span.tag", "ANALYST");
  p.tools.append(engine);
  p.body.append(h("div.or", out, h("form.or-in", { on: { submit: (e) => { e.preventDefault(); ask(input.value); } } }, input, h("button.btn.gold", { type: "submit" }, "ASK"))));
  const SUGG = ["Market overview", "Why is Nifty IT moving?", "What if Brent +20% and US10Y +50bp", "Compare gold vs bitcoin", "Explain the regime", "What's driving USD/INR?"];
  function welcome() {
    clear(out).append(h("div.or-title", "ORACLE is online."),
      h("div.dim", "Grounded answers from the terminal's live data — quotes, transmission betas, regime, news, rhetoric and geo-risk. Every figure is sourced; nothing is invented."),
      h("div.or-sugg", SUGG.map((q) => h("button", { on: { click: () => ask(q) } }, q))));
  }
  async function ask(q) {
    q = (q || "").trim();
    if (q.length < 2) return;
    input.value = "";
    sound.go();
    clear(out).append(h("div.or-title", q), h("div.typing", h("i"), h("i"), h("i")));
    try {
      const r = await api.post("/api/oracle", { q });
      clear(out).append(h("div.or-title", r.title || q));
      if (r.llm) out.append(h("div.or-llm", r.llm));
      for (const sct of r.sections || []) out.append(h("h4", sct.h), h("ul", sct.bullets.map((b) => h("li", b))));
      out.append(h("div.src-note", { style: { marginTop: "12px" } }, `${r.engine === "finverse-analyst" ? "Finverse deterministic analyst" : r.engine} · ${r.disclaimer}`));
      engine.textContent = r.llm ? "LLM · LOCAL" : "ANALYST";
      if (r.scenario) emit("ui:scenario", r.scenario);
    } catch (e) {
      clear(out).append(h("div.down", `Oracle error: ${e.message}`));
    }
  }
  on("ui:ask", ask);
  welcome();
  return p.el;
}

// ============================================================ VIDEO
const CHANNELS = [
  ["AL JAZEERA", "live_stream?channel=UCNye-wNBqNL5ZzHSJj3l8Bg"],
  ["BLOOMBERG", "live_stream?channel=UCIALMKvObZNtJ6AmdCLP7Lg"],
  ["NDTV PROFIT", "EN-N1xhtBqU"],
  ["FIRSTPOST", "GgnIf1TPHsA"],
  ["CNA", "XWq5kBlakcQ"],
  ["DW", "LuKwFajn37U"],
  ["SKY NEWS", "live_stream?channel=UCoMdktPbSTixAyNGwb-UYkQ"],
  ["NBC", "7cxCCru7QLI"],
  ["WAR FEED", "gCNeDWCI0vo"],
];
export function videoPanel(area = "vid") {
  let ch = store.get("vid.ch", 0), loaded = false;
  const p = panel(area, "Live Broadcast", { tools: [h("span.live-badge", h("i"), "LIVE")] });
  const frame = h("div.vid-frame");
  const chans = h("div.vid-chans.scroll");
  p.body.append(h("div.vid", frame, chans));
  function load() {
    loaded = true;
    const path = CHANNELS[ch][1];
    clear(frame).append(h("iframe", { src: `https://www.youtube-nocookie.com/embed/${path}${path.includes("?") ? "&" : "?"}autoplay=1&mute=1&playsinline=1&rel=0`, allow: "autoplay; encrypted-media; picture-in-picture", allowFullscreen: true, referrerPolicy: "strict-origin-when-cross-origin", title: CHANNELS[ch][0] }));
  }
  function cover() {
    clear(frame).append(h("div.vid-cover", { on: { click: () => { sound.click(); load(); } } },
      h("div.col", { style: { alignItems: "center", gap: "12px" } }, h("div.play", s("svg", { viewBox: "0 0 24 24", width: 20, height: 20, fill: "currentColor" }, s("path", { d: "M8 5v14l11-7z" }))),
        h("span.label-xs", `${CHANNELS[ch][0]} · CLICK TO TUNE IN`))));
  }
  CHANNELS.forEach(([name], i) => chans.append(h("button", { class: i === ch ? "on" : "", on: { click: (e) => { ch = i; store.set("vid.ch", i); [...chans.children].forEach((b, k) => b.classList.toggle("on", k === i)); loaded ? load() : cover(); } } }, name)));
  cover();
  return p.el;
}

// ============================================================ MACRO BOARD
export function macroBoardPanel(area = "mb") {
  const p = panel(area, "Macro Board", { mn: "ECO" });
  const grid = h("div.mb-grid");
  p.body.append(grid);
  const cell = (k, v, sub, spark, klass = "") => h("div.mb-cell", h("div.k", k), h("div.v", { class: klass }, v), h("div.s", sub), spark ? sparkline(spark, { w: 60, h: 22, color: "#d9b56d" }) : null);
  function render() {
    const M = S.macro || {}, f = M.fed || {}, b = M.bls || {}, c = M.curve || {}, pulse = S.analytics?.pulse?.global || {};
    const nextFomc = (M.calendar || []).find((e) => e.event.startsWith("FOMC"));
    const rbi = S.rhetoric?.banks?.RBI;
    clear(grid).append(
      cell("Fed funds target", f.target_to != null ? h("span", `${f.target_from.toFixed(2)}–${f.target_to.toFixed(2)}`, h("small", "%")) : "—",
        `EFFR ${f.effr ?? "—"}% · next FOMC ${nextFomc ? nextFomc.date.slice(5) : "—"}`),
      cell("US CPI", b.cpi ? h("span", b.cpi.value.toFixed(1), h("small", "% YoY")) : "—",
        b.cpi ? `${b.cpi.period} · core ${b.core_cpi?.value ?? "—"}% · prev ${b.cpi.prev}%` : "BLS", b.cpi?.series, b.cpi && b.cpi.value > b.cpi.prev ? "down" : "up"),
      cell("Non-farm payrolls", b.payrolls ? h("span", `${b.payrolls.value > 0 ? "+" : ""}${b.payrolls.value}`, h("small", "K")) : "—",
        b.payrolls ? `${b.payrolls.period} · unemployment ${b.unemployment?.value ?? "—"}%` : "BLS", b.payrolls?.series),
      cell("US 10Y · 2s10s", c.now ? h("span", c.now["10Y"]?.toFixed(2), h("small", `% · ${c.spreads?.["2s10s"] > 0 ? "+" : ""}${c.spreads?.["2s10s"]}bp`)) : "—",
        c.asof ? `Treasury par curve · ${c.asof}` : "US Treasury"),
      cell("Global pulse", pulse.value != null ? h("span", Math.round(pulse.value), h("small", pulse.label)) : "—",
        "Fear/greed composite · 6 components", pulse.series, pulse.value >= 55 ? "up" : pulse.value <= 45 ? "down" : ""),
      cell("RBI repo", rbi?.rate != null ? h("span", rbi.rate.toFixed(2), h("small", "%")) : "—",
        rbi?.rate_src === "headline" ? "headline-derived" : rbi?.rate_src || "awaiting MPC statement"),
    );
  }
  on("hydrated", render); on("macro", render); on("analytics", render); on("rhetoric", render);
  render();
  return p.el;
}

// ============================================================ INTEL FEED
const TAG_COLOR = {
  NEWS: "var(--gold)", RHETORIC: "var(--gold-2)", LIQUIDATION: "var(--violet)", SIGMA: "var(--ice)", DIVERGENCE: "var(--violet)",
  GEOPOLITICS: "var(--down)", HAZARD: "var(--warn)", CHOKEPOINT: "var(--warn)", "CENTRAL BANK": "var(--ice)", ALERT: "var(--gold)",
  REGIME: "var(--gold)", SYSTEM: "var(--text-3)", INSTITUTIONAL: "var(--up)",
};
const FILTERS = [["ALL", null], ["CRIT", (e) => e.tier === "CRITICAL"], ["NEWS", (e) => e.tag === "NEWS"], ["RHET", (e) => e.tag === "RHETORIC" || e.tag === "CENTRAL BANK"],
  ["σ MOVES", (e) => e.tag === "SIGMA" || e.tag === "DIVERGENCE"], ["LIQ", (e) => e.tag === "LIQUIDATION"], ["GEO", (e) => ["GEOPOLITICS", "HAZARD", "CHOKEPOINT"].includes(e.tag)], ["ALERTS", (e) => e.tag === "ALERT"]];

export function feedPanel(area = "fd") {
  let filter = 0;
  const pins = new Set(store.get("pins", []));
  const speed = h("span.tag", "0 EV/MIN");
  const p = panel(area, "Live Intel Feed", { mn: "TAPE", tools: [speed] });
  const fbar = h("div.fd-filters");
  const pinBox = h("div.fd-pins");
  const list = h("div.fd-list.scroll");
  p.body.append(h("div.fd", fbar, pinBox, list));
  FILTERS.forEach(([name], i) => fbar.append(h("button", { class: i === filter ? "on" : "", on: { click: () => { filter = i; [...fbar.children].forEach((b, k) => b.classList.toggle("on", k === i)); render(); } } }, name)));
  function row(e) {
    const color = TAG_COLOR[e.tag] || "var(--text-2)";
    const msg = e.link ? h("a", { href: e.link, target: "_blank", rel: "noopener noreferrer" }, e.message) : e.message;
    const pinned = pins.has(e.id);
    return h("div.ev", { class: `t-${e.tier} ${pinned ? "pinned" : ""}`, dataset: { id: e.id } },
      h("span.et", hhmm(e.ts)),
      h("div", h("div.eh", h("span.etag", { style: { color } }, `[${e.tag}]`), e.tier !== "INFO" ? h("span.tag", { class: e.tier === "CRITICAL" ? "crit" : e.tier === "HEAVY" ? "warn" : "ice" }, e.tier) : null, e.asset ? h("span.ea", e.asset) : null, e.source ? h("span.ea", `· ${e.source}`) : null),
        h("div.em", msg)),
      h("button.pin", { title: pinned ? "Unpin" : "Pin", on: { click: () => { pinned ? pins.delete(e.id) : pins.add(e.id); store.set("pins", [...pins].slice(-20)); render(); } } }, icon("pin")));
  }
  function render() {
    const f = FILTERS[filter][1];
    const evs = S.intel.filter((e) => !f || f(e)).slice(-160).reverse();
    clear(list);
    evs.filter((e) => !pins.has(e.id)).forEach((e) => list.append(row(e)));
    clear(pinBox);
    S.intel.filter((e) => pins.has(e.id)).forEach((e) => pinBox.append(row(e)));
    if (!evs.length) list.append(h("div.empty", h("div", h("b", "LISTENING"), "Streams clear. Events appear here the moment they happen.")));
  }
  on("hydrated", render);
  on("intel", (e) => {
    const f = FILTERS[filter][1];
    if (!f || f(e)) { list.prepend(row(e)); while (list.children.length > 200) list.lastChild.remove(); list.querySelector(".empty")?.remove(); }
    speed.textContent = `${S.tapeSpeed} EV/MIN`;
    speed.className = `tag ${S.tapeSpeed > 20 ? "crit" : S.tapeSpeed > 8 ? "warn" : ""}`;
    if (e.tier === "CRITICAL" && e.tag !== "ALERT") { toast(`${e.tag} · ${e.asset || ""}`, e.message, { crit: true }); sound.crit(); p.el.classList.add("alarm"); setTimeout(() => p.el.classList.remove("alarm"), 4000); }
  });
  on("health", () => { speed.textContent = `${S.tapeSpeed} EV/MIN`; });
  render();
  return p.el;
}
