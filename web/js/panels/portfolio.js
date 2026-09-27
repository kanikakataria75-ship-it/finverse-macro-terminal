import { S, on, emit, meta, api } from "../core/state.js";
import { h, clear, fmtPx, fmtPct, fmtINR, cls, sparkline, toast, ago } from "../core/util.js";
import { panel } from "./common.js";
import { sound } from "../core/sound.js";

let PF = null;
async function loadPF() { try { PF = await api.get("/api/portfolio"); } catch { PF = { empty: true }; } emit("pf", PF); }

export function holdingsPanel(area = "hold") {
  const p = panel(area, "Holdings · Live P&L", { mn: "PORT" });
  const sym = h("input.input", { placeholder: "Symbol (RELIANCE, AAPL, BTC…)", style: { flex: 2 } });
  const qty = h("input.input", { type: "number", placeholder: "Qty", step: "any", style: { flex: 1 } });
  const cost = h("input.input", { type: "number", placeholder: "Avg cost", step: "any", style: { flex: 1 } });
  const form = h("form.form-row", { on: { submit: async (e) => {
    e.preventDefault();
    try { await api.post("/api/portfolio", { symbol: sym.value, qty: +qty.value, cost: +cost.value }); sym.value = qty.value = cost.value = ""; sound.go(); loadPF(); }
    catch (err) { toast("PORTFOLIO", err.message); }
  } } }, sym, qty, cost, h("button.btn.gold.sm", { type: "submit" }, "ADD"));
  const head = h("div.row", { style: { padding: "12px 14px", gap: "26px", borderBottom: "1px solid var(--line)" } });
  const body = h("div.scroll", { style: { flex: 1, minHeight: 0 } });
  p.body.append(h("div.col", { style: { position: "absolute", inset: 0, gap: 0 } }, form, head, body));
  function draw() {
    clear(head); clear(body);
    if (!PF || PF.empty || !PF.rows?.length) {
      body.append(h("div.empty", h("div", h("b", "NO POSITIONS"), "Add holdings above — Indian (₹) and global ($) assets are consolidated in INR at the live USD/INR rate. Stored locally in SQLite.")));
      return;
    }
    head.append(h("div", h("div.label-xs", "Portfolio value"), h("div.big-num", { style: { fontSize: "30px" } }, fmtINR(PF.total_inr))),
      h("div", h("div.label-xs", "Unrealised P&L"), h("div.big-num", { style: { fontSize: "30px" }, class: cls(PF.pnl_inr) }, fmtINR(PF.pnl_inr))),
      h("div", h("div.label-xs", "Today"), h("div.big-num", { style: { fontSize: "30px" }, class: cls(PF.day_inr) }, fmtINR(PF.day_inr))));
    const tb = h("tbody");
    PF.rows.forEach((r) => tb.append(h("tr", { on: { click: () => emit("ui:security", r.symbol) } },
      h("td", h("div.cd", r.code), h("div.nm", r.name)), h("td", r.qty), h("td", fmtPx(r.cost)), h("td", fmtPx(r.price, r.symbol)),
      h("td", { class: cls(r.day_pct) }, fmtPct(r.day_pct)), h("td", fmtINR(r.value_inr)), h("td", { class: cls(r.pnl_inr) }, `${fmtINR(r.pnl_inr)} `, h("span.muted", fmtPct(r.pnl_pct))),
      h("td", `${r.weight}%`), h("td", h("button.btn.ghost.sm", { on: { click: async (e) => { e.stopPropagation(); await api.del(`/api/portfolio/${r.id}`); loadPF(); } } }, "✕")))));
    body.append(h("table.grid", h("thead", h("tr", ...["Asset", "Qty", "Cost", "Last", "Day", "Value", "P&L", "Wt", ""].map((x) => h("th", x)))), tb));
  }
  on("pf", draw);
  on("ui:ws", (ws) => ws === "portfolio" && loadPF());
  let t; on("quotes", () => { if (!PF || PF.empty) return; clearTimeout(t); t = setTimeout(loadPF, 5000); });
  draw();
  return p.el;
}

export function riskPanel(area = "risk") {
  const p = panel(area, "Risk Engine", { mn: "RISK" });
  const body = h("div.scroll", { style: { position: "absolute", inset: 0, padding: "12px 14px" } });
  p.body.append(body);
  function draw() {
    clear(body);
    if (!PF || PF.empty || PF.vol == null) { body.append(h("div.empty", h("div", h("b", "AWAITING POSITIONS"), "Risk metrics compute from 250 days of returns once you hold assets."))); return; }
    const kv = (k, v, c = "") => h("div.kv", h("span", k), h("b", { class: c }, v));
    body.append(kv("Annualised volatility", `${PF.vol}%`), kv("1-day VaR (95%, historical)", fmtINR(PF.var95_1d), "down"), kv("1-day CVaR (95%)", fmtINR(PF.cvar95_1d), "down"),
      kv("Max drawdown (1y)", `${PF.max_dd_1y}%`, "down"), kv("Beta vs Nifty", PF.beta_nifty ?? "—"), kv("Beta vs S&P 500", PF.beta_spx ?? "—"),
      h("div.label-xs", { style: { margin: "14px 0 6px" } }, "1-year equity curve (current weights)"));
    const sp = sparkline(PF.curve, { w: 300, h: 60, color: "#d9b56d" }); sp.style.cssText = "width:100%;height:60px"; body.append(sp);
    body.append(h("div.label-xs", { style: { margin: "14px 0 6px" } }, "Macro stress tests (β-propagated)"));
    const mx = Math.max(1, ...PF.stress.map((x) => Math.abs(x.pnl_inr)));
    PF.stress.forEach((x) => { const w = (Math.abs(x.pnl_inr) / mx) * 50; body.append(h("div.hbar", { style: { gridTemplateColumns: "1.4fr 1fr 80px" } }, h("span.hb-l", { style: { fontFamily: "var(--f-ui)", fontWeight: 600 } }, x.name),
      h("div.hb-t", h("i", { style: { left: x.pnl_inr >= 0 ? "50%" : `${50 - w}%`, width: `${w}%`, background: x.pnl_inr >= 0 ? "var(--up)" : "var(--down)" } })), h("span.hb-v", { class: cls(x.pnl_inr) }, fmtINR(x.pnl_inr)))); });
  }
  on("pf", draw); draw();
  return p.el;
}

export function alertsPanel(area = "alerts") {
  const p = panel(area, "Alerts", { mn: "ALRT" });
  const input = h("input.input", { placeholder: "BTC > 120000 · NIFTY PCT < -1.5 · Z 3 · NEWS hormuz · LIQ 2M · HEAT 70", style: { flex: 1 } });
  const list = h("div.scroll", { style: { flex: 1, minHeight: 0 } });
  const form = h("form.form-row", { on: { submit: async (e) => { e.preventDefault(); await add(input.value); input.value = ""; } } }, input, h("button.btn.gold.sm", { type: "submit" }, "ARM"));
  p.body.append(h("div.col", { style: { position: "absolute", inset: 0, gap: 0 } }, form, list));
  async function add(text) {
    try { const r = await api.post("/api/alerts", { text }); toast("ALERT ARMED", r.label); sound.go(); draw(); }
    catch (e) { toast("ALERT", e.message); }
  }
  async function draw() {
    const rows = await api.get("/api/alerts").catch(() => []);
    clear(list);
    if (!rows.length) list.append(h("div.empty", h("div", h("b", "NO ALERTS ARMED"), "Alerts evaluate continuously against live quotes and the intel stream. Fired alerts ping here, in the feed, as a browser notification and (optionally) Telegram.")));
    rows.forEach((r) => list.append(h("div.list-row",
      h("span.dot", { style: { color: r.enabled ? "var(--up)" : "var(--text-4)" } }), h("span.grow", { style: { fontWeight: 600 } }, r.label),
      h("span.src-note", r.fire_count ? `fired ${r.fire_count}× · ${ago(r.last_fired * 1000)} ago` : "armed"),
      h("button.btn.ghost.sm", { on: { click: async () => { await api.post(`/api/alerts/${r.id}/toggle?enabled=${!r.enabled}`, {}); draw(); } } }, r.enabled ? "PAUSE" : "RESUME"),
      h("button.btn.ghost.sm", { on: { click: async () => { await api.del(`/api/alerts/${r.id}`); draw(); } } }, "✕"))));
  }
  on("ui:alert-add", add);
  on("alert", draw);
  on("ui:ws", (ws) => ws === "portfolio" && draw());
  return p.el;
}

export function watchPanel(area = "watch") {
  const p = panel(area, "Watchlist", { mn: "WL" });
  const input = h("input.input", { placeholder: "Add symbol…", style: { flex: 1 } });
  const list = h("div.scroll", { style: { flex: 1, minHeight: 0 } });
  p.body.append(h("div.col", { style: { position: "absolute", inset: 0, gap: 0 } },
    h("form.form-row", { on: { submit: async (e) => { e.preventDefault(); try { await api.post("/api/watchlist", { symbol: input.value }); input.value = ""; draw(); } catch (err) { toast("WATCHLIST", err.message); } } } }, input, h("button.btn.sm", { type: "submit" }, "ADD")), list));
  async function draw() {
    const rows = await api.get("/api/watchlist").catch(() => []);
    clear(list);
    if (!rows.length) list.append(h("div.empty", h("div", h("b", "EMPTY"), "Add symbols you follow. Use WATCH <ticker> from the command line.")));
    rows.forEach((r) => { const q = S.quotes[r.symbol] || r.quote || {}; list.append(h("div.list-row", { style: { cursor: "pointer" }, on: { click: () => emit("ui:security", r.symbol) } },
      h("span.mono", { style: { width: "96px", fontWeight: 800 } }, r.code || r.symbol), h("span.grow.ellipsis.muted", r.name || ""),
      sparkline(q.spark, { w: 56, h: 18, fill: false }), h("span.mono", { style: { width: "80px", textAlign: "right" } }, fmtPx(q.price, r.symbol)),
      h("span.mono", { style: { width: "64px", textAlign: "right" }, class: cls(q.pct) }, fmtPct(q.pct)),
      h("button.btn.ghost.sm", { on: { click: async (e) => { e.stopPropagation(); await api.del(`/api/watchlist/${encodeURIComponent(r.symbol)}`); draw(); } } }, "✕"))); });
  }
  on("ui:watch", draw);
  on("ui:ws", (ws) => ws === "portfolio" && draw());
  return p.el;
}

export function briefPanel(area = "brief") {
  const p = panel(area, "Daily Brief", { mn: "BRIEF" });
  const body = h("div.scroll", { style: { position: "absolute", inset: 0 } });
  p.tools.append(h("a.btn.sm", { href: "/api/briefing.md", download: "finverse-brief.md" }, "EXPORT .MD"), h("button.btn.sm", { on: { click: () => emit("ui:brief") } }, "EXPAND"));
  p.body.append(body);
  async function draw() {
    const b = await api.get("/api/briefing").catch(() => null);
    clear(body);
    if (!b) return;
    body.append(renderMd(b.markdown, true));
  }
  on("ui:ws", (ws) => ws === "portfolio" && draw());
  return p.el;
}

/** Minimal markdown renderer (headings, bullets, emphasis) — text only, no HTML injection. */
export function renderMd(md, compact = false) {
  const root = h("div.md", { style: compact ? { padding: "12px 16px", fontSize: "12px" } : {} });
  let ul = null;
  for (const line of md.split("\n")) {
    if (line.startsWith("# ")) { ul = null; root.append(h("h1", { style: compact ? { fontSize: "15px" } : {} }, line.slice(2))); }
    else if (line.startsWith("## ")) { ul = null; root.append(h("h2", line.slice(3))); }
    else if (line.startsWith("- ")) { if (!ul) { ul = h("ul"); root.append(ul); } ul.append(h("li", line.slice(2))); }
    else if (line.startsWith("_") && line.endsWith("_")) { ul = null; root.append(h("p", h("em", line.slice(1, -1)))); }
    else if (line.trim() && line !== "---") { ul = null; root.append(h("p", line)); }
  }
  return root;
}
