import { S, on, emit, meta, api } from "../core/state.js";
import { h, s, clear, fmtPx, fmtPct, fmtBig, cls, tip, untip, hhmm, divColor, sparkline } from "../core/util.js";
import { panel, seg } from "./common.js";
import { gauge } from "./macro.js";
import { quoteTable } from "./markets.js";

export function cryptoBoardPanel(area = "cboard") {
  const p = panel(area, "Crypto · Live", { mn: "CRYP", tools: [h("span.tag.ice", "● BINANCE WS")] });
  p.body.classList.add("scroll");
  p.body.append(quoteTable(() => [["SPOT", S.universe.filter((u) => u.cls === "crypto").map((u) => u.sym)]], { cols: ["price", "pct", "m1", "spark"] }));
  const extra = h("div", { style: { padding: "10px 14px" } });
  p.body.append(extra);
  function draw() {
    const g = S.crypto?.global || {};
    clear(extra).append(
      h("div.kv", h("span", "Total crypto market cap"), h("b", `${fmtBig(g.mcap, "$")}  `, h("span", { class: cls(g.mcap_chg) }, fmtPct(g.mcap_chg)))),
      h("div.kv", h("span", "24h volume"), h("b", fmtBig(g.vol, "$"))),
      h("div.kv", h("span", "BTC dominance"), h("b", g.btc_dom != null ? `${g.btc_dom.toFixed(1)}%` : "—")),
      h("div.kv", h("span", "ETH dominance"), h("b", g.eth_dom != null ? `${g.eth_dom.toFixed(1)}%` : "—")),
      h("div.src-note", { style: { marginTop: "6px" } }, "CoinGecko global · Binance spot miniTicker (real-time)"));
  }
  on("crypto", draw); on("hydrated", draw);
  return p.el;
}

export function liqPanel(area = "liq") {
  let win = "1h";
  const p = panel(area, "Liquidation Waterfall · OKX · Bybit · Binance", { mn: "LIQ" });
  const stats = h("div.row", { style: { padding: "10px 14px", gap: "18px", borderBottom: "1px solid var(--line)" } });
  const chart = h("div", { style: { flex: 1, minHeight: 0, position: "relative" } });
  const tops = h("div.row", { style: { padding: "6px 14px 10px", gap: "6px", flexWrap: "wrap" } });
  p.body.append(h("div.col", { style: { position: "absolute", inset: 0, gap: 0 } }, stats, chart, tops));
  let summary = null;
  async function refresh() { try { summary = (await api.get("/api/crypto")).liq; draw(); } catch { /* retry next tick */ } }
  function draw() {
    if (!summary) return;
    const w = summary[win] || {};
    clear(stats).append(
      h("div", h("div.label-xs", "Longs liquidated"), h("div.big-num.down", { style: { fontSize: "26px" } }, fmtBig(w.long, "$"))),
      h("div", h("div.label-xs", "Shorts liquidated"), h("div.big-num.up", { style: { fontSize: "26px" } }, fmtBig(w.short, "$"))),
      h("div", h("div.label-xs", "Events"), h("div.big-num", { style: { fontSize: "26px" } }, w.count ?? 0)),
      w.largest ? h("div.grow", h("div.label-xs", "Largest"), h("div.mono", { style: { marginTop: "8px", fontSize: "12px" } }, `${w.largest.sym} ${w.largest.side} ${fmtBig(w.largest.usd, "$")}`)) : null);
    clear(chart);
    const W = chart.clientWidth, H = chart.clientHeight;
    if (W < 80 || H < 40) return;
    const mins = summary.minutes || [];
    const mx = Math.max(1, ...mins.map((m) => Math.max(m.long, m.short)));
    const svg = s("svg", { width: W, height: H });
    const bw = (W - 40) / Math.max(1, mins.length), mid = H / 2;
    svg.append(s("line", { x1: 30, x2: W - 6, y1: mid, y2: mid, stroke: "rgba(255,255,255,0.1)" }),
      s("text", { x: 8, y: 16, fill: "#2fe3a3", "font-size": 9, "font-family": "JetBrains Mono", "font-weight": 700 }, "SHORTS"),
      s("text", { x: 8, y: H - 8, fill: "#ff5773", "font-size": 9, "font-family": "JetBrains Mono", "font-weight": 700 }, "LONGS"));
    mins.forEach((m, i) => {
      const x = 32 + i * bw;
      const hs = (m.short / mx) * (mid - 14), hl = (m.long / mx) * (mid - 14);
      if (hs > 0) svg.append(s("rect", { x, y: mid - hs, width: Math.max(1, bw - 1.5), height: hs, rx: 1, fill: "#2fe3a3", opacity: 0.85 }));
      if (hl > 0) svg.append(s("rect", { x, y: mid, width: Math.max(1, bw - 1.5), height: hl, rx: 1, fill: "#ff5773", opacity: 0.85 }));
      const hit = s("rect", { x, y: 0, width: bw, height: H, fill: "transparent" });
      hit.addEventListener("mousemove", (e) => tip(e, `${m.m} min ago`, [["Shorts", fmtBig(m.short, "$"), "up"], ["Longs", fmtBig(m.long, "$"), "down"]]));
      hit.addEventListener("mouseleave", untip);
      svg.append(hit);
    });
    svg.append(s("text", { x: W - 8, y: H - 8, "text-anchor": "end", fill: "#626b7c", "font-size": 9, "font-family": "JetBrains Mono" }, "← 60 MIN · NOW"));
    chart.append(svg);
    clear(tops).append(h("span.label-xs", "Most liquidated"), ...(w.top || []).map(([sym, usd]) => h("span.tag", `${sym.replace("USDT", "")} ${fmtBig(usd, "$")}`)),
      h("span.grow"), ...Object.entries(w.venues || {}).map(([v, usd]) => h("span.tag.ice", `${v} ${fmtBig(usd, "$")}`)));
    if (!w.count) chart.append(h("div.empty", { style: { position: "absolute", inset: 0 } }, h("div", h("b", "QUIET TAPE"), "No forced liquidations in this window across OKX, Bybit and Binance.")));
  }
  p.tools.append(seg([["1h", "1H"], ["4h", "4H"], ["24h", "24H"]], win, (v) => { win = v; draw(); }));
  new ResizeObserver(draw).observe(chart);
  refresh(); setInterval(refresh, 10000);
  return p.el;
}

export function fundingPanel(area = "fund") {
  const p = panel(area, "Perp Funding · OI · Positioning", { mn: "FUND" });
  const grid = h("div", { style: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "6px", padding: "10px" } });
  const ls = h("div", { style: { padding: "4px 14px 12px" } });
  p.body.classList.add("scroll");
  p.body.append(grid, ls);
  function draw() {
    const F = S.crypto?.funding || {}, OI = S.crypto?.oi || {}, LS = S.crypto?.ls || {};
    clear(grid);
    Object.entries(F).sort((a, b) => Math.abs(b[1].rate) - Math.abs(a[1].rate)).forEach(([sym, f]) => {
      const bg = divColor((f.rate || 0) * 100, 3);
      grid.append(h("div", { style: { padding: "8px", borderRadius: "8px", background: bg, border: "1px solid rgba(0,0,0,0.4)", cursor: "default" },
        on: { mousemove: (e) => tip(e, sym, [["Funding (8h)", `${f.rate?.toFixed(4)}%`], ["Annualised", `${f.annual?.toFixed(1)}%`, cls(f.annual)], ["Mark", fmtPx(f.mark)], ...(OI[sym] ? [["Open interest", fmtBig(OI[sym].usd, "$")], ["OI change (1 min poll)", fmtPct(OI[sym].chg), cls(OI[sym].chg)]] : [])]), mouseleave: untip } },
        h("div.mono", { style: { fontWeight: 800, fontSize: "10.5px" } }, sym.replace("USDT", "")),
        h("div.mono", { style: { fontSize: "11px", marginTop: "4px" } }, `${f.rate > 0 ? "+" : ""}${f.rate?.toFixed(4)}%`),
        h("div.mono", { style: { fontSize: "9px", opacity: 0.75, marginTop: "2px" } }, `${f.annual?.toFixed(0)}% APR`)));
    });
    clear(ls).append(h("div.label-xs", { style: { margin: "8px 0" } }, "Global long/short account ratio (24h)"));
    Object.entries(LS).forEach(([sym, x]) => ls.append(h("div.meter-row",
      h("span.ml", { style: { width: "70px" } }, sym.replace("USDT", "")),
      h("div.meter", h("i", { style: { width: `${x.long_pct}%`, background: "linear-gradient(90deg, var(--up), rgba(47,227,163,0.4))" } })),
      h("span.mv", { style: { width: "60px" } }, `${x.long_pct?.toFixed(0)}% L`),
      h("div", { style: { width: "70px" } }, sparkline(x.series, { w: 70, h: 18, fill: false, color: "#d9b56d" })))));
    if (!Object.keys(F).length) grid.append(h("div.empty", { style: { gridColumn: "1 / -1" } }, h("div", h("b", "SYNCING"), "Binance futures positioning loading…")));
  }
  on("crypto", draw); on("hydrated", draw);
  return p.el;
}

export function liqLogPanel(area = "liqlog") {
  const p = panel(area, "Liquidation Tape", { mn: "LTAP" });
  const list = h("div.scroll", { style: { position: "absolute", inset: 0, fontFamily: "var(--f-mono)" } });
  p.body.append(list);
  const row = (x) => h("div.list-row", { style: { padding: "6px 14px", fontSize: "11px", animation: "evIn .5s var(--ease) both" } },
    h("span.muted", { style: { width: "64px" } }, hhmm(x.t)), h("span", { style: { width: "80px", fontWeight: 800 } }, x.sym.replace("USDT", "")),
    h("span.muted", { style: { width: "58px", fontSize: "9px" } }, x.venue || ""),
    h("span.tag", { class: x.side === "LONG" ? "down" : "up" }, x.side), h("span.grow"),
    h("span", { class: x.usd >= 1e6 ? "gold" : "", style: { fontWeight: x.usd >= 250000 ? 800 : 500 } }, fmtBig(x.usd, "$")));
  function draw() { clear(list); S.liqs.slice(-80).reverse().forEach((x) => list.append(row(x))); if (!S.liqs.length) list.append(h("div.empty", h("div", h("b", "ARMED"), "Listening to OKX, Bybit and Binance for forced liquidations…"))); }
  on("hydrated", draw);
  on("liq", (x) => { list.querySelector(".empty")?.remove(); list.prepend(row(x)); while (list.children.length > 120) list.lastChild.remove(); });
  draw();
  return p.el;
}

export function cryptoSentPanel(area = "csent") {
  const p = panel(area, "Crypto Sentiment", { mn: "CFG" });
  const g = gauge(0, { label: "FEAR & GREED", colors: ["#ff5773", "#d9b56d", "#2fe3a3"] });
  const lbl = h("div.label-xs", { style: { textAlign: "center", marginTop: "6px" } });
  const hist = h("div", { style: { padding: "10px 14px" } });
  p.body.append(h("div", { style: { padding: "12px 44px 0" } }, g), lbl, hist);
  function draw() {
    const f = S.crypto?.fng;
    if (!f) return;
    g.set(f.value);
    lbl.textContent = `${f.label} · alternative.me`;
    lbl.className = `label-xs ${f.value >= 55 ? "up" : f.value <= 45 ? "down" : "gold"}`;
    clear(hist).append(h("div.src-note", { style: { marginBottom: "4px" } }, "30-DAY HISTORY"), sparkline(f.series, { w: 300, h: 50, color: "#d9b56d" }));
    hist.lastChild.style.cssText = "width:100%;height:50px;position:static";
  }
  on("crypto", draw); on("hydrated", draw);
  return p.el;
}
