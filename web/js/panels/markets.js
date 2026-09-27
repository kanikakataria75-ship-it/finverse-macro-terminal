import { S, on, emit, meta } from "../core/state.js";
import { h, s, clear, fmtPx, fmtPct, cls, sparkline, setNum, tip, untip, divColor, fmtSigned } from "../core/util.js";
import { panel, seg } from "./common.js";

/** Generic live quote table */
export function quoteTable(groups, { cols = ["price", "pct", "w1", "ytd", "spark"] } = {}) {
  const tbody = h("tbody");
  const heads = { price: "Last", pct: "Chg %", w1: "1W", m1: "1M", ytd: "YTD", z: "σ", spark: "40D", vol: "Vol" };
  const table = h("table.grid", h("thead", h("tr", h("th", "Instrument"), cols.map((c) => h("th", heads[c])))), tbody);
  const cells = {};
  function build() {
    clear(tbody);
    for (const [gname, syms] of groups()) {
      if (gname) tbody.append(h("tr.group", h("td", { colSpan: cols.length + 1 }, gname)));
      for (const sym of syms) {
        const m = meta(sym), q = S.quotes[sym] || {};
        const c = {};
        const tr = h("tr", { on: { click: () => emit("ui:security", sym) } },
          h("td", h("div.cd", m.code), h("div.nm", m.name)),
          cols.map((col) => { c[col] = h("td"); return c[col]; }));
        cells[sym] = c;
        tbody.append(tr);
        paint(sym);
      }
    }
  }
  function paint(sym, prev) {
    const c = cells[sym], q = S.quotes[sym];
    if (!c || !q) return;
    for (const col of cols) {
      const el = c[col];
      if (col === "price") setNum(el, fmtPx(q.price, sym), prev != null ? Math.sign(q.price - prev) : 0);
      else if (col === "spark") clear(el).append(sparkline(q.spark, { w: 64, h: 18, fill: false }));
      else if (col === "z") { el.textContent = q.z == null ? "—" : fmtSigned(q.z, 1); el.className = Math.abs(q.z || 0) >= 2 ? "gold" : "muted"; }
      else if (col === "vol") { el.textContent = q.vol == null ? "—" : `${q.vol.toFixed(1)}%`; el.className = "muted"; }
      else {
        const v = q[col];
        clear(el).append(h("span.pct-cell", { class: cls(v), style: col === "pct" && v != null ? { background: divColor(v, 3).replace("rgb", "rgba").replace(")", ",0.35)") } : {} }, fmtPct(v)));
      }
    }
  }
  on("hydrated", build);
  on("quotes", ({ changed, prev }) => Object.keys(changed).forEach((sym) => paint(sym, prev[sym])));
  build();
  return table;
}

const bySymCls = (fn) => S.universe.filter(fn).map((u) => u.sym);

export function weiPanel(area = "wei") {
  const p = panel(area, "World Equity Indices", { mn: "WEI" });
  p.body.classList.add("scroll");
  const regions = [["AMERICAS", "AMER"], ["EUROPE · MIDDLE EAST", "EMEA"], ["ASIA PACIFIC", "APAC"], ["INDIA", "INDIA"]];
  p.body.append(quoteTable(() => regions.map(([n, r]) => [n, bySymCls((u) => u.region === r && (u.cls === "index" || (r === "INDIA" && u.cls === "index")))]), { cols: ["price", "pct", "w1", "ytd", "z", "spark"] }));
  return p.el;
}

export function crossAssetPanel(area = "fx") {
  let tab = "fx";
  const p = panel(area, "Cross-Asset Board", { mn: "XA" });
  const body = h("div.scroll", { style: { position: "absolute", inset: 0 } });
  p.body.append(body);
  const sets = {
    fx: () => [["G10 & DOLLAR", bySymCls((u) => u.cls === "fx" && ["DX-Y.NYB", "EURUSD=X", "JPY=X", "GBPUSD=X", "AUDUSD=X", "CHF=X", "CAD=X"].includes(u.sym))], ["EMERGING", bySymCls((u) => u.cls === "fx" && ["INR=X", "CNY=X", "BRL=X", "MXN=X", "KRW=X", "TRY=X", "ZAR=X"].includes(u.sym))]],
    cmd: () => [["ENERGY", ["BZ=F", "CL=F", "NG=F"]], ["METALS", ["GC=F", "SI=F", "HG=F", "PL=F"]], ["AGRICULTURE", ["ZW=F", "ZC=F", "ZS=F", "KC=F", "SB=F"]]],
    rates: () => [["US TREASURY YIELDS", ["^IRX", "^FVX", "^TNX", "^TYX"]], ["BOND ETFS", ["TLT", "IEF", "TIP", "HYG"]], ["VOLATILITY", ["^VIX", "^INDIAVIX"]]],
  };
  const draw = () => clear(body).append(quoteTable(sets[tab], { cols: ["price", "pct", "w1", "ytd", "spark"] }));
  p.tools.append(seg([["fx", "FX"], ["cmd", "COMDTY"], ["rates", "RATES"]], tab, (v) => { tab = v; draw(); }));
  draw();
  return p.el;
}

export function heatmapPanel(area = "heat") {
  let universe = "global";
  const p = panel(area, "Market Heatmap", { mn: "HMAP" });
  const box = h("div.treemap");
  p.body.append(box);
  const sets = {
    global: () => [["US", ["^GSPC", "^IXIC", "^DJI", "^RUT"]], ["EUROPE", ["^FTSE", "^GDAXI", "^FCHI", "^STOXX50E", "FTSEMIB.MI", "^IBEX", "^SSMI", "^AEX"]],
      ["ASIA", ["^N225", "^HSI", "000001.SS", "^KS11", "^TWII", "^AXJO", "^NSEI", "^STI", "^JKSE"]], ["EM & OTHER", ["^BVSP", "^MXX", "^GSPTSE", "XU100.IS", "^TA125.TA", "^MERV"]]],
    india: () => [["INDICES", ["^NSEI", "^NSEBANK", "^CNXIT", "^CNXPHARMA", "AUTOBEES.NS", "FMCGIETF.NS", "METALIETF.NS", "ENERGY.NS", "MOREALTY.NS", "PSUBNKBEES.NS", "FINIETF.NS"]],
      ["LARGE CAPS", bySymCls((u) => u.region === "INDIA" && u.cls === "equity")]],
    us: () => [["SECTORS", bySymCls((u) => u.region === "USSECT")], ["MEGA CAPS", bySymCls((u) => u.region === "US" && u.cls === "equity")]],
    cross: () => [["COMMODITIES", ["BZ=F", "CL=F", "NG=F", "GC=F", "SI=F", "HG=F", "ZW=F", "ZC=F"]], ["CRYPTO", bySymCls((u) => u.cls === "crypto")], ["FX", bySymCls((u) => u.cls === "fx")]],
  };
  // weights: equal within group but proportional to |move| + base so moves "pop"
  function draw() {
    clear(box);
    const W = box.clientWidth, H = box.clientHeight;
    if (!W || !H) return;
    const root = d3.hierarchy({ children: sets[universe]().map(([name, syms]) => ({ name, children: syms.filter((x) => S.quotes[x]).map((sym) => ({ sym, v: 1 + Math.min(4, Math.abs(S.quotes[sym].pct || 0)) })) })) })
      .sum((d) => d.v || 0);
    d3.treemap().size([W, H]).paddingTop(16).paddingInner(2).paddingOuter(3).round(true)(root);
    for (const g of root.children || []) box.append(h("div.tm-group", { style: { left: `${g.x0}px`, top: `${g.y0}px` } }, g.data.name));
    for (const leaf of root.leaves()) {
      const q = S.quotes[leaf.data.sym], m = meta(leaf.data.sym), w = leaf.x1 - leaf.x0, hh = leaf.y1 - leaf.y0;
      box.append(h("div.tm-cell", {
        style: { left: `${leaf.x0}px`, top: `${leaf.y0}px`, width: `${w}px`, height: `${hh}px`, background: divColor(q.pct, universe === "cross" ? 3 : 2) },
        on: { click: () => emit("ui:security", leaf.data.sym), mousemove: (e) => tip(e, m.name, [["Last", fmtPx(q.price, leaf.data.sym)], ["Today", fmtPct(q.pct), cls(q.pct)], ["1W", fmtPct(q.w1), cls(q.w1)], ["YTD", fmtPct(q.ytd), cls(q.ytd)]]), mouseleave: untip },
      }, w > 44 && hh > 26 ? [h("div.a", m.code), h("div.b", fmtPct(q.pct))] : null));
    }
  }
  p.tools.append(seg([["global", "GLOBAL"], ["india", "INDIA"], ["us", "US"], ["cross", "CROSS"]], universe, (v) => { universe = v; draw(); }));
  new ResizeObserver(() => draw()).observe(box);
  on("hydrated", draw);
  let t; on("quotes", () => { clearTimeout(t); t = setTimeout(draw, 1500); });
  return p.el;
}

export function moversPanel(area = "movers") {
  let tab = "movers";
  const p = panel(area, "Movers · Outliers", { mn: "MOV" });
  const body = h("div.scroll", { style: { position: "absolute", inset: 0 } });
  p.body.append(body);
  function draw() {
    clear(body);
    if (tab === "movers") {
      const qs = Object.values(S.quotes).filter((q) => q.pct != null && meta(q.sym).cls !== "etf");
      qs.sort((a, b) => b.pct - a.pct);
      const col = (title, rows) => h("div", { style: { flex: 1, minWidth: 0 } }, h("div.label-xs", { style: { padding: "10px 14px 6px" } }, title),
        rows.map((q) => h("div.list-row", { style: { cursor: "pointer" }, on: { click: () => emit("ui:security", q.sym) } },
          h("span.mono", { style: { width: "92px", fontWeight: 700 } }, meta(q.sym).code), h("span.grow.ellipsis.muted", meta(q.sym).name), h("span.mono", { class: cls(q.pct) }, fmtPct(q.pct)))));
      body.append(h("div.row", { style: { alignItems: "stretch", gap: 0 } }, col("Leaders", qs.slice(0, 10)), col("Laggards", qs.slice(-10).reverse())));
    } else {
      const an = S.analytics?.anomalies || [];
      if (!an.length) body.append(h("div.empty", h("div", h("b", "NO OUTLIERS"), "Nothing is moving more than 1.5σ vs its 60-day volatility.")));
      an.forEach((a) => body.append(h("div.list-row", { style: { cursor: "pointer" }, on: { click: () => emit("ui:security", a.sym) } },
        h("span.mono", { style: { width: "92px", fontWeight: 700 } }, a.code), h("span.grow.ellipsis.muted", a.name),
        h("span.mono", { class: cls(a.pct), style: { width: "70px", textAlign: "right" } }, fmtPct(a.pct)),
        h("span.tag", { class: Math.abs(a.z) >= 2.5 ? "warn" : "ice", style: { width: "58px", justifyContent: "center" } }, `${fmtSigned(a.z, 1)}σ`))));
    }
  }
  p.tools.append(seg([["movers", "MOVERS"], ["sigma", "σ OUTLIERS"]], tab, (v) => { tab = v; draw(); }));
  on("hydrated", draw); on("analytics", draw);
  let t; on("quotes", () => { clearTimeout(t); t = setTimeout(draw, 2000); });
  draw();
  return p.el;
}

export function curvePanel(area = "curve") {
  const p = panel(area, "US Treasury Curve", { mn: "GC" });
  const box = h("div", { style: { position: "absolute", inset: "8px 12px 30px 8px" } });
  const note = h("div.src-note", { style: { position: "absolute", left: "14px", bottom: "8px" } });
  p.body.append(box, note);
  function draw() {
    clear(box);
    const c = S.macro?.curve;
    if (!c || !c.now) { box.append(h("div.empty", h("div", h("b", "LOADING"), "Treasury curve syncing…"))); return; }
    const W = box.clientWidth, H = box.clientHeight;
    if (W < 120 || H < 60) return;
    const ten = c.tenors.filter((t) => c.now[t.code] != null);
    const series = [["y1", "1Y AGO", "rgba(255,255,255,0.18)"], ["m1", "1M AGO", "rgba(127,227,255,0.55)"], ["now", "NOW", "#f4ddaa"]];
    const all = series.flatMap(([k]) => ten.map((t) => c[k]?.[t.code]).filter((v) => v != null));
    const lo = Math.min(...all) - 0.15, hi = Math.max(...all) + 0.15;
    const x = d3.scalePoint(ten.map((t) => t.code), [36, W - 10]), y = d3.scaleLinear([lo, hi], [H - 18, 8]);
    const svg = s("svg", { width: W, height: H });
    y.ticks(5).forEach((v) => svg.append(s("line", { x1: 36, x2: W - 10, y1: y(v), y2: y(v), stroke: "rgba(255,255,255,0.05)" }), s("text", { x: 30, y: y(v) + 3, "text-anchor": "end", fill: "#626b7c", "font-size": 9, "font-family": "JetBrains Mono" }, v.toFixed(1))));
    ten.forEach((t) => svg.append(s("text", { x: x(t.code), y: H - 4, "text-anchor": "middle", fill: "#626b7c", "font-size": 9, "font-family": "JetBrains Mono" }, t.code)));
    series.forEach(([k, name, col], i) => {
      const pts = ten.filter((t) => c[k]?.[t.code] != null).map((t) => [x(t.code), y(c[k][t.code])]);
      const d = d3.line().curve(d3.curveMonotoneX)(pts);
      svg.append(s("path", { d, fill: "none", stroke: col, "stroke-width": k === "now" ? 2.2 : 1.2, style: k === "now" ? "filter: drop-shadow(0 0 6px rgba(217,181,109,0.6))" : "" }));
      if (k === "now") pts.forEach(([px, py], j) => svg.append(s("circle", { cx: px, cy: py, r: 2.6, fill: "#0b0e15", stroke: col, "stroke-width": 1.4 })));
      svg.append(s("text", { x: 44, y: 16 + i * 12, fill: col, "font-size": 9, "font-family": "JetBrains Mono", "font-weight": 700 }, name));
    });
    box.append(svg);
    const sp = c.spreads || {};
    note.textContent = `2s10s ${sp["2s10s"]}bp · 3m10y ${sp["3m10y"]}bp · 5s30s ${sp["5s30s"]}bp · US Treasury par yields ${c.asof}`;
  }
  new ResizeObserver(draw).observe(box);
  on("macro", draw); on("hydrated", draw);
  return p.el;
}
