// 3D home: live globe + hero stats + workspace launcher.
import { S, on, emit, meta } from "../core/state.js";
import { h, clear, fmtPx, fmtPct, cls, tip, untip, ago } from "../core/util.js";
import { Globe } from "../three/globe.js";
import { EMBLEM, icon, clocks, feedChip, tickerTape } from "../panels/common.js";
import { WORKSPACES } from "./terminal.js";
import { sound } from "../core/sound.js";
import { voiceButton } from "../core/voice.js";

export function buildHome(root, { enter }) {
  const canvas = h("canvas.stage");
  const labels = h("div.globe-labels");
  const greet = h("div.greet"), time = h("div.hero-time"), date = h("div.hero-date");
  const stats = h("div.hero-stats"), heads = h("div.hero-heads");
  const cards = h("div.ws-grid");
  root.append(canvas, labels,
    h("div.home-top", h("div.brand", EMBLEM(), h("span.w", "FINVERSE"), h("span.ed", "OBSIDIAN")), h("span.grow"), clocks(), voiceButton(), feedChip(() => emit("ui:health"))),
    h("div.home-left", greet, time, date, stats, heads,
      h("div.hero-cta", h("button.btn.gold", { on: { click: () => enter() } }, "Enter terminal"),
        h("button.btn", { style: { height: "46px", borderRadius: "12px", letterSpacing: "0.2em" }, on: { click: () => emit("ui:voice") } }, "Talk to VEDA"), h("span.row", { style: { color: "var(--text-3)", fontSize: "11px" } }, h("span.kbd", "↵"), " or ", h("span.kbd", "F1–F7")))),
    h("div.globe-legend", ...[["#f4ddaa", "Exchange open"], ["#6f86a8", "Closed"], ["#ff5773", "Conflict hotspot"], ["#ffb648", "Quake / elevated risk"], ["#7fe3ff", "Chokepoint"]]
      .map(([c, t]) => h("div.li", h("span.sw", { style: { background: c, boxShadow: `0 0 8px ${c}` } }), t))),
    h("div.home-right", h("div.ws-title", h("span", "Workspaces"), h("span", "Live")), cards),
    h("div.home-tape", tickerTape({ label: "LIVE" })));

  const globe = new Globe(canvas, {
    labels, dots: 34000, zoom: 4.35, offsetX: 0.13,
    onHover: (d, e) => {
      if (!d || !e) return untip();
      if (d.kind === "exchange") { const q = S.quotes[d.ex.idx]; tip(e, `${d.ex.id} · ${d.ex.city}`, [["Session (local)", `${d.ex.open}–${d.ex.close}`], ...(q ? [[meta(d.ex.idx).name, `${fmtPx(q.price)}  ${fmtPct(q.pct)}`, cls(q.pct)]] : [])]); }
      else if (d.kind === "quake") tip(e, `M${d.info.mag.toFixed(1)} earthquake`, [d.info.place, ["When", `${ago(d.info.t)} ago`]]);
      else if (d.kind === "choke") tip(e, d.info.name, [["Status", d.info.status, d.info.status === "NORMAL" ? "up" : "down"], ["Carries", d.info.flows], ...d.info.drivers.slice(0, 2)]);
    },
  });

  function hero() {
    const now = new Date(), hr = now.getHours();
    greet.textContent = `${hr < 5 ? "Late session" : hr < 12 ? "Good morning" : hr < 17 ? "Good afternoon" : "Good evening"} · Operator`;
    time.textContent = now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    date.textContent = now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }) + " · " + Intl.DateTimeFormat().resolvedOptions().timeZone;
  }
  function data() {
    const A = S.analytics || {}, gp = A.pulse?.global, ip = A.pulse?.india, rg = A.regime;
    clear(stats).append(
      h("div.hero-stat", h("div.k", "Global pulse"), h("div.v", { class: gp?.value >= 58 ? "up" : gp?.value <= 42 ? "down" : "gold" }, gp?.value != null ? Math.round(gp.value) : "—"), h("div.s", gp?.label || "—")),
      h("div.hero-stat", h("div.k", "India pulse"), h("div.v", { class: ip?.value >= 58 ? "up" : ip?.value <= 42 ? "down" : "gold" }, ip?.value != null ? Math.round(ip.value) : "—"), h("div.s", ip?.label || "—")),
      h("div.hero-stat", h("div.k", "Macro regime"), h("div.v", { style: { fontSize: "17px", paddingTop: "8px", paddingBottom: "5px" } }, rg?.regime || "—"), h("div.s", { class: rg?.risk_label === "RISK-ON" ? "up" : rg?.risk_label === "RISK-OFF" ? "down" : "" }, rg?.risk_label || "—")));
    clear(heads);
    (S.top.length ? S.top : S.news).slice(0, 4).forEach((n) => heads.append(h("a.hero-head", { href: n.link, target: "_blank", rel: "noopener noreferrer" }, h("span.src", n.source), h("span", n.title))));
    const q = (s) => S.quotes[s] || {};
    const tx = A.transmission?.targets?.find((t) => t.sym === "^NSEI");
    const choke = (S.geo?.chokepoints || [])[0];
    const stat = {
      macro: `Tape ${S.tapeSpeed} ev/min · ${S.intel.length} intel`,
      markets: `SPX ${fmtPct(q("^GSPC").pct)} · NKY ${fmtPct(q("^N225").pct)}`,
      india: `NIFTY ${fmtPct(q("^NSEI").pct)} · implied ${tx ? fmtPct(tx.implied_pct) : "—"}`,
      crypto: `BTC ${fmtPx(q("BTC-USD").price)} ${fmtPct(q("BTC-USD").pct)}`,
      geo: choke ? `${choke.name} · ${choke.status}` : "Scanning",
      analytics: rg?.regime ? `${rg.regime}` : "Calibrating",
      portfolio: "Holdings · risk · alerts",
    };
    clear(cards);
    WORKSPACES.forEach((w, i) => {
      const card = h("button.ws-card", { class: i === 0 ? "primary" : "", style: { animationDelay: `${0.25 + i * 0.06}s` },
        on: {
          click: () => enter(w.id), mouseenter: () => sound.hover(),
          mousemove: (e) => { const r = card.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height; card.style.transform = `rotateY(${(x - 0.5) * 14}deg) rotateX(${(0.5 - y) * 12}deg) translateZ(10px)`; card.style.setProperty("--mx", `${x * 100}%`); card.style.setProperty("--my", `${y * 100}%`); },
          mouseleave: () => { card.style.transform = ""; },
        } }, h("span.ic", icon(w.icon)), h("span.fk", w.key), h("span.nm", w.name), h("span.st", stat[w.id]));
      cards.append(card);
    });
  }
  hero(); data();
  setInterval(hero, 1000 * 15);
  on("hydrated", () => { data(); globe.setGeo(S.geo); globe.setQuotes(S.quotes); });
  on("analytics", data); on("geo", (g) => globe.setGeo(g));
  let t; on("quotes", () => { globe.setQuotes(S.quotes); clearTimeout(t); t = setTimeout(data, 3000); });
  globe.setGeo(S.geo || {}); globe.setQuotes(S.quotes);
  return {
    show() { globe.resize(); globe.start(); },
    hide() { globe.stop(); },
  };
}
