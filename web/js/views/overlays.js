import { S, on, emit, meta, api } from "../core/state.js";
import { h, s, clear, fmtPx, fmtPct, fmtBig, cls, tip, untip, ago, toast, fmtSigned } from "../core/util.js";
import { seg, icon } from "../panels/common.js";
import { renderMd } from "../panels/portfolio.js";
import { sound } from "../core/sound.js";

function sheet(klass = "") {
  const close = () => { ov.remove(); document.removeEventListener("keydown", esc); untip(); };
  const esc = (e) => { if (e.key === "Escape") close(); };
  const box = h("div.sheet", { class: klass });
  const ov = h("div.overlay", { on: { mousedown: (e) => { if (e.target === ov) close(); } } }, box);
  document.addEventListener("keydown", esc);
  document.body.append(ov);
  return { box, close };
}

// ======================================================= SECURITY (DES/GP)
export async function openSecurity(sym) {
  sound.whoosh();
  const { box, close } = sheet();
  const m = meta(sym);
  const pxEl = h("span.sec-px", "—"), pctEl = h("span.mono", { style: { fontSize: "14px" } });
  const chartBox = h("div.sec-chart");
  const right = h("div.sec-right.scroll");
  let rng = "1Y", kind = "candle";
  const rangeSeg = seg([["1D", "1D"], ["5D", "5D"], ["1M", "1M"], ["6M", "6M"], ["1Y", "1Y"], ["5Y", "5Y"], ["MAX", "MAX"]], rng, (v) => { rng = v; loadChart(); });
  const kindSeg = seg([["candle", "CANDLE"], ["area", "AREA"]], kind, (v) => { kind = v; loadChart(); });
  box.append(
    h("div.sheet-head",
      h("div", h("div.row", h("span.tag.gold", m.cls?.toUpperCase() || "SECURITY"), h("span.mono.muted", sym)), h("div.sec-name", { style: { marginTop: "6px" } }, m.name)),
      h("div", { style: { marginLeft: "28px" } }, pxEl, h("div", pctEl)),
      h("div.row", { style: { marginLeft: "auto", gap: "6px" } },
        h("button.btn.sm", { on: { click: async () => { await api.post("/api/watchlist", { symbol: sym }); emit("ui:watch"); toast("WATCHLIST", `${m.code} added`); } } }, "+ WATCH"),
        h("button.btn.sm", { on: { click: () => { const q = S.quotes[sym]; const lvl = q?.price ? Math.round(q.price * 1.03 * 100) / 100 : ""; emit("ui:alert-add", `${m.code} > ${lvl}`); } } }, "+ ALERT 3% ↑"),
        h("button.btn.gold.sm", { on: { click: () => { close(); emit("ui:ask", `Why is ${m.code} moving?`); } } }, "ASK ORACLE"),
        h("button.icon-btn", { on: { click: close } }, icon("x")))),
    h("div.sheet-body", h("div.sec-grid",
      h("div.sec-left", h("div.row", { style: { padding: "10px 14px", borderBottom: "1px solid var(--line)" } }, rangeSeg, kindSeg, h("span.grow"), h("span.src-note", "Yahoo Finance · delayed")), chartBox),
      right)));

  let chart;
  async function loadChart() {
    clear(chartBox).append(h("div.empty", h("div.typing", h("i"), h("i"), h("i"))));
    try {
      const d = await api.get(`/api/chart/${encodeURIComponent(sym)}?range=${rng}`);
      clear(chartBox);
      if (!d.bars.length) { chartBox.append(h("div.empty", h("div", h("b", "NO DATA"), "No bars for this range."))); return; }
      chart = LightweightCharts.createChart(chartBox, {
        autoSize: true,
        layout: { background: { type: "solid", color: "transparent" }, textColor: "#7b8494", fontFamily: "JetBrains Mono", fontSize: 11 },
        grid: { vertLines: { color: "rgba(255,255,255,0.03)" }, horzLines: { color: "rgba(255,255,255,0.03)" } },
        rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
        timeScale: { borderColor: "rgba(255,255,255,0.08)", timeVisible: rng === "1D" || rng === "5D" || rng === "1M" },
        crosshair: { mode: 0, vertLine: { color: "rgba(217,181,109,0.4)", labelBackgroundColor: "#8c7140" }, horzLine: { color: "rgba(217,181,109,0.4)", labelBackgroundColor: "#8c7140" } },
      });
      const main = kind === "candle"
        ? chart.addCandlestickSeries({ upColor: "#2fe3a3", downColor: "#ff5773", borderVisible: false, wickUpColor: "#2fe3a3", wickDownColor: "#ff5773" })
        : chart.addAreaSeries({ lineColor: "#f4ddaa", topColor: "rgba(217,181,109,0.35)", bottomColor: "rgba(217,181,109,0)", lineWidth: 2 });
      main.setData(kind === "candle" ? d.bars : d.bars.map((b) => ({ time: b.time, value: b.close })));
      const vol = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol", color: "rgba(127,227,255,0.25)" });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
      vol.setData(d.bars.map((b) => ({ time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(47,227,163,0.28)" : "rgba(255,87,115,0.28)" })));
      if (typeof d.bars[0].time === "string") {
        [[50, "#7fe3ff"], [200, "#a58dff"]].forEach(([n, color]) => {
          if (d.bars.length < n + 5) return;
          const sma = []; let sum = 0;
          d.bars.forEach((b, i) => { sum += b.close; if (i >= n) sum -= d.bars[i - n].close; if (i >= n - 1) sma.push({ time: b.time, value: sum / n }); });
          chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false }).setData(sma);
        });
      }
      chart.timeScale().fitContent();
    } catch (e) { clear(chartBox).append(h("div.empty", e.message)); }
  }
  loadChart();

  const kv = (k, v, c = "") => h("div.kv", h("span", k), h("b", { class: c }, v ?? "—"));
  clear(right).append(h("div.sec-block", h("div.skeleton", { style: { height: "120px" } })));
  try {
    const d = await api.get(`/api/security/${encodeURIComponent(sym)}`);
    const q = d.quote || {}, P = d.profile || {};
    pxEl.textContent = fmtPx(q.price, sym);
    pctEl.textContent = `${fmtSigned(q.chg, 2)}  ${fmtPct(q.pct)}  ·  ${q.src === "YF" ? "delayed" : "live"}`;
    pctEl.className = `mono ${cls(q.pct)}`;
    clear(right);
    right.append(h("div.sec-block", h("h5", "Performance"), h("div.stat-grid",
      kv("1 week", fmtPct(q.w1), cls(q.w1)), kv("1 month", fmtPct(q.m1), cls(q.m1)), kv("3 months", fmtPct(q.m3), cls(q.m3)), kv("YTD", fmtPct(q.ytd), cls(q.ytd)),
      kv("1 year", fmtPct(q.y1), cls(q.y1)), kv("Realised vol", q.vol ? `${q.vol}%` : "—"), kv("52w high", fmtPx(q.hi52 ?? P.fiftyTwoWeekHigh, sym)), kv("52w low", fmtPx(q.lo52 ?? P.fiftyTwoWeekLow, sym)),
      kv("Today σ", q.z != null ? `${fmtSigned(q.z, 1)}σ` : "—", Math.abs(q.z || 0) >= 2 ? "gold" : ""))));
    if (Object.keys(P).length > 3) {
      right.append(h("div.sec-block", h("h5", "Fundamentals"), h("div.stat-grid",
        kv("Market cap", fmtBig(P.marketCap, P.currency === "INR" ? "₹" : "$")), kv("P/E (ttm)", P.trailingPE?.toFixed(1)), kv("Forward P/E", P.forwardPE?.toFixed(1)), kv("P/B", P.priceToBook?.toFixed(2)),
        kv("Div. yield", divYield(P, q)), kv("Beta", P.beta?.toFixed(2)),
        kv("Op. margin", P.operatingMargins != null ? `${(P.operatingMargins * 100).toFixed(1)}%` : "—"), kv("ROE", P.returnOnEquity != null ? `${(P.returnOnEquity * 100).toFixed(1)}%` : "—"),
        kv("Revenue growth", P.revenueGrowth != null ? fmtPct(P.revenueGrowth * 100, 1) : "—", cls(P.revenueGrowth)), kv("Debt/Equity", P.debtToEquity?.toFixed(0)),
        kv("Analysts", P.recommendationKey ? `${P.recommendationKey.toUpperCase()} (${P.numberOfAnalystOpinions ?? "?"})` : "—"), kv("Target (mean)", fmtPx(P.targetMeanPrice)))),
        P.longBusinessSummary ? h("div.sec-block", h("h5", [P.sector, P.industry].filter(Boolean).join(" · ") || "About"), h("div.about.scroll", P.longBusinessSummary)) : null);
    }
    if (d.macro_betas) {
      const B = d.macro_betas;
      right.append(h("div.sec-block", h("h5", `Macro sensitivities · R² ${B.r2}`), ...Object.entries(B.betas).map(([k, v]) => {
        const w = Math.min(50, Math.abs(v.b) * 60);
        return h("div.hbar", h("span.hb-l", v.code), h("div.hb-t", h("i", { style: { left: v.b >= 0 ? "50%" : `${50 - w}%`, width: `${w}%`, background: v.b >= 0 ? "var(--gold)" : "var(--ice)" } })), h("span.hb-v", v.b.toFixed(3)));
      }), h("div.src-note", { style: { marginTop: "6px" } }, "Multivariate OLS on 250 daily returns (US drivers lagged one session).")));
    }
    const isOptionable = !sym.includes(".") && !sym.startsWith("^") && !sym.includes("=") && !sym.includes("-");
    if (isOptionable) right.append(optionsBlock(sym));
    right.append(h("div.sec-block", h("h5", "On the wire"), ...(d.news.length ? d.news.slice(0, 8).map((n) => h("a.kv", { href: n.link, target: "_blank", rel: "noopener noreferrer" }, h("span", { style: { color: "var(--text-2)" } }, n.title), h("b.muted", { style: { fontSize: "10px" } }, ago(n.ts)))) : [h("div.src-note", "No recent headlines tagged to this instrument.")])));
  } catch (e) { clear(right).append(h("div.sec-block.down", e.message)); }
}

/** Dividend yield from rate ÷ price (unambiguous); Yahoo's own field changed units across versions. */
function divYield(P, q) {
  const px = q.price || P.currentPrice;
  if (P.dividendRate && px) return `${((P.dividendRate / px) * 100).toFixed(2)}%`;
  if (P.trailingAnnualDividendYield != null) return `${(P.trailingAnnualDividendYield * 100).toFixed(2)}%`;
  return P.dividendYield != null ? `${P.dividendYield.toFixed(2)}%` : "—";
}

function optionsBlock(sym) {
  const block = h("div.sec-block", h("h5", "Options analytics"), h("div.skeleton", { style: { height: "80px" } }));
  api.get(`/api/options/${encodeURIComponent(sym)}`).then((o) => {
    clear(block).append(h("h5", `Options analytics · exp ${o.expiry || "—"}`));
    if (o.error || !o.strikes?.length) { block.append(h("div.src-note", o.error || "No option chain.")); return; }
    const kv = (k, v, c = "") => h("div.kv", h("span", k), h("b", { class: c }, v ?? "—"));
    block.append(h("div.stat-grid", kv("Put/Call OI", o.pcr_oi, o.pcr_oi > 1 ? "down" : "up"), kv("Put/Call vol", o.pcr_vol), kv("Max pain", fmtPx(o.max_pain)), kv("ATM IV", o.atm_iv ? `${o.atm_iv}%` : "—"), kv("Call wall", fmtPx(o.call_wall)), kv("Put wall", fmtPx(o.put_wall))));
    const W = 380, H = 150, st = o.strikes, mx = Math.max(1, ...st.map((x) => Math.max(x.c_oi, x.p_oi)));
    const bw = W / st.length;
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, style: "width:100%;height:150px;margin-top:10px" });
    st.forEach((x, i) => {
      const hc = (x.c_oi / mx) * (H / 2 - 12), hp = (x.p_oi / mx) * (H / 2 - 12);
      svg.append(s("rect", { x: i * bw, y: H / 2 - hc, width: Math.max(1, bw - 1), height: hc, fill: "#2fe3a3", opacity: 0.75 }), s("rect", { x: i * bw, y: H / 2, width: Math.max(1, bw - 1), height: hp, fill: "#ff5773", opacity: 0.75 }));
      const hit = s("rect", { x: i * bw, y: 0, width: bw, height: H, fill: "transparent" });
      hit.addEventListener("mousemove", (e) => tip(e, `Strike ${x.k}`, [["Call OI", x.c_oi.toLocaleString(), "up"], ["Put OI", x.p_oi.toLocaleString(), "down"], ["Call IV", `${x.c_iv}%`], ["Put IV", `${x.p_iv}%`]]));
      hit.addEventListener("mouseleave", untip);
      svg.append(hit);
    });
    const si = st.findIndex((x) => x.k >= o.spot);
    if (si >= 0) svg.append(s("line", { x1: si * bw, x2: si * bw, y1: 0, y2: H, stroke: "#f4ddaa", "stroke-dasharray": "3 3" }), s("text", { x: si * bw + 4, y: 10, fill: "#f4ddaa", "font-size": 9, "font-family": "JetBrains Mono" }, `SPOT ${fmtPx(o.spot)}`));
    block.append(svg, h("div.src-note", "Open interest by strike (calls ▲ / puts ▼), ±25% of spot · Yahoo options chain"));
  }).catch((e) => { clear(block).append(h("h5", "Options analytics"), h("div.src-note", e.message)); });
  return block;
}

// ================================================================ BRIEF
export async function openBrief() {
  const { box, close } = sheet("sm");
  const body = h("div.sheet-body.scroll");
  box.append(h("div.sheet-head", h("div.sec-name", { style: { fontSize: "18px" } }, "Daily Brief"), h("a.btn.sm", { href: "/api/briefing.md", download: "finverse-brief.md", style: { marginLeft: "auto" } }, "EXPORT .MD"), h("button.icon-btn", { on: { click: close } }, icon("x"))), body);
  body.append(h("div.md", h("div.skeleton", { style: { height: "300px" } })));
  const b = await api.get("/api/briefing");
  clear(body).append(renderMd(b.markdown));
}

// =============================================================== HEALTH
export function openHealth() {
  const { box, close } = sheet("sm");
  const body = h("div.sheet-body.scroll");
  box.append(h("div.sheet-head", h("div", h("div.sec-name", { style: { fontSize: "18px" } }, "Feed Health"), h("div.src-note", "Every data source, its cadence and its live status")), h("button.icon-btn", { style: { marginLeft: "auto" }, on: { click: close } }, icon("x"))), body);
  const draw = () => {
    clear(body);
    const H = S.health;
    body.append(h("div.row", { style: { padding: "12px 22px", gap: "20px", borderBottom: "1px solid var(--line)" } },
      h("span.label-xs", `UPTIME ${Math.floor((H.uptime || 0) / 60)}m`), h("span.label-xs", `TERMINALS ${H.clients ?? 0}`), h("span.label-xs", `TAPE ${H.tape_speed ?? 0} EV/MIN`)));
    (H.feeds || []).forEach((f) => body.append(h("div.health-row", h("span.hs", { class: f.status }), h("b", f.label), h("span.muted", f.source), h("span.mono.muted", f.cadence), h("span.mono", { style: { fontSize: "11px", color: f.status === "error" ? "var(--down)" : "var(--text-2)" } }, `${f.msg}${f.last_ok ? ` · ${ago(f.last_ok * 1000)} ago` : ""}`))));
  };
  const off = on("health", () => (box.isConnected ? draw() : off()));
  draw();
}

// ========================================================== NEWS SEARCH
export async function openNewsSearch(q) {
  const { box, close } = sheet("sm");
  const input = h("input.input", { value: q || "", placeholder: "Search the wire…", style: { flex: 1 } });
  const body = h("div.sheet-body.scroll");
  const run = async () => {
    clear(body).append(h("div.md", h("div.skeleton", { style: { height: "200px" } })));
    const rows = await api.get(`/api/news?q=${encodeURIComponent(input.value)}&n=120`).catch(() => []);
    clear(body);
    if (!rows.length) body.append(h("div.empty", h("div", h("b", "NO MATCHES"), `Nothing on the wire for “${input.value}” in the last 36 hours.`)));
    rows.forEach((n) => body.append(h("a.list-row", { href: n.link, target: "_blank", rel: "noopener noreferrer", style: { padding: "10px 22px" } },
      h("span.mono.muted", { style: { width: "36px", fontSize: "10px" } }, ago(n.ts)), h("div.grow", h("div", { style: { color: "var(--text)" } }, n.title), h("div.src-note", { style: { marginTop: "4px" } }, `${n.source}${n.confirmations > 1 ? ` · ${n.confirmations} sources` : ""} · ${n.topics.join(" ")}`)),
      h("span.mono", { class: cls(n.sentiment), style: { fontSize: "10px" } }, fmtSigned(n.sentiment, 2)))));
  };
  box.append(h("div.sheet-head", h("form.row.grow", { on: { submit: (e) => { e.preventDefault(); run(); } } }, h("span.label-xs", "N ›"), input, h("button.btn.gold.sm", { type: "submit" }, "SEARCH")), h("button.icon-btn", { on: { click: close } }, icon("x"))), body);
  input.focus();
  run();
}

// ================================================================= HELP
export function openHelp() {
  const { box, close } = sheet("sm");
  const rows = [
    ["<TICKER> ⏎", "Security page — e.g. RELIANCE, AAPL, BTC, NIFTY"], ["GP <TICKER>", "Chart"], ["ASK <question>", "Ask Oracle anything"], ["WEI / MKT", "Markets workspace"],
    ["INDIA / TX", "Transmission map & implied open"], ["SCEN", "Scenario simulator"], ["CRYPTO / LIQ", "Crypto & liquidations"], ["GEO / CHOKE", "Globe, conflict & chokepoints"],
    ["RGM / CORR / EVT", "Analytics workspace"], ["PORT / WATCH <T>", "Portfolio · add to watchlist"], ["ALRT <rule>", "e.g. ALRT BTC > 120000 · ALRT NEWS hormuz"],
    ["BRIEF", "Daily brief (exportable)"], ["N <query>", "Search the news wire"], ["HEALTH", "Feed status"], ["HOME", "3D home"], ["MUTE", "Toggle sound"], ["“Veda …” · 👏👏 · V", "Talk to VEDA — ask out loud, hear the answer"],
    ["F1 – F7", "Switch workspace"], ["/  or  Ctrl K", "Focus command line"], ["Esc", "Close overlay"], ["?", "This help"],
  ];
  box.append(h("div.sheet-head", h("div.sec-name", { style: { fontSize: "18px" } }, "Command Reference"), h("button.icon-btn", { style: { marginLeft: "auto" }, on: { click: close } }, icon("x"))),
    h("div.sheet-body.scroll", h("div.help-grid", rows.map(([k, v]) => h("div.hk", h("code", k), h("span", v)))),
      h("div.md", { style: { paddingTop: 0 } }, h("h2", "About the data"), h("ul",
        h("li", "Quotes: Yahoo Finance (delayed) · crypto: Binance WebSocket (real-time) · optional NSE real-time via your Angel One account."),
        h("li", "Macro: US Treasury, NY Fed, BLS. Geo: GDELT / Google News, USGS, NASA EONET. Rhetoric: Truth Social mirror, Fed/RBI/ECB press."),
        h("li", "All analytics are computed locally from this data. Nothing here is investment advice.")))));
}

on("ui:security", openSecurity);
on("ui:brief", openBrief);
on("ui:health", openHealth);
on("ui:help", openHelp);
on("ui:news-search", openNewsSearch);
