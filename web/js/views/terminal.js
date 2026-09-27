import { S, on, emit, meta, api } from "../core/state.js";
import { h, clear, fmtPx, fmtPct, cls, toast, debounce, store } from "../core/util.js";
import { sound } from "../core/sound.js";
import { panel, tickerTape, newsTape, clocks, feedChip, EMBLEM, icon } from "../panels/common.js";
import { rhetoricPanel, matrixPanel, worldMapPanel, oraclePanel, videoPanel, macroBoardPanel, feedPanel } from "../panels/macro.js";
import { weiPanel, crossAssetPanel, heatmapPanel, moversPanel, curvePanel } from "../panels/markets.js";
import { transmissionPanel, scenarioPanel, indiaSectorsPanel, pulsePanel, newsPanel } from "../panels/india.js";
import { cryptoBoardPanel, liqPanel, fundingPanel, liqLogPanel, cryptoSentPanel } from "../panels/crypto.js";
import { conflictPanel, globePanel, chokepointPanel, hazardPanel } from "../panels/geo.js";
import { regimePanel, correlationPanel, surfacePanel, eventStudyPanel } from "../panels/analytics.js";
import { holdingsPanel, riskPanel, alertsPanel, watchPanel, briefPanel } from "../panels/portfolio.js";
import "./overlays.js";
import { voiceButton } from "../core/voice.js";

export const WORKSPACES = [
  { id: "macro", name: "MACRO", key: "F1", icon: "globe", build: () => [rhetoricPanel("rh"), matrixPanel("mx"), worldMapPanel("map"), oraclePanel("or"), videoPanel("vid"), macroBoardPanel("mb"), feedPanel("fd")] },
  { id: "markets", name: "MARKETS", key: "F2", icon: "chart", build: () => [weiPanel("wei"), heatmapPanel("heat"), crossAssetPanel("fx"), moversPanel("movers"), curvePanel("curve")] },
  { id: "india", name: "INDIA", key: "F3", icon: "flag", build: () => [transmissionPanel("tx"), scenarioPanel("scen"), indiaSectorsPanel("sect"), pulsePanel("ipulse", "india", "India Pulse"), newsPanel("inews", { title: "India Wire", filter: (n) => n.region === "IN" || n.topics.includes("INDIA") || n.topics.includes("RBI"), mn: "INWR" })] },
  { id: "crypto", name: "CRYPTO", key: "F4", icon: "coin", build: () => [cryptoBoardPanel("cboard"), liqPanel("liq"), fundingPanel("fund"), liqLogPanel("liqlog"), cryptoSentPanel("csent")] },
  { id: "geo", name: "GEO", key: "F5", icon: "shield", build: () => [conflictPanel("conf"), globePanel("globe"), chokepointPanel("choke"), hazardPanel("haz"), newsPanel("gnews", { title: "Geopolitical Wire", filter: (n) => n.topics.includes("GEOPOLITICS") || n.topics.includes("ENERGY"), mn: "GWR" })] },
  { id: "analytics", name: "ANALYTICS", key: "F6", icon: "bolt", build: () => [regimePanel("regime"), pulsePanel("pulse", "global", "Global Pulse"), eventStudyPanel("evt"), correlationPanel("corr"), surfacePanel("surface")] },
  { id: "portfolio", name: "PORTFOLIO", key: "F7", icon: "wallet", build: () => [holdingsPanel("hold"), riskPanel("risk"), alertsPanel("alerts"), watchPanel("watch"), briefPanel("brief")] },
];

const CMDS = [
  ["ASK", "Ask Oracle a question", (a) => ask(a)], ["WEI", "World equity indices", () => go("markets")], ["MKT", "Markets workspace", () => go("markets")],
  ["HMAP", "Market heatmap", () => go("markets")], ["GC", "Treasury curve", () => go("markets")], ["INDIA", "India workspace", () => go("india")],
  ["TX", "Transmission map · implied open", () => go("india")], ["SCEN", "Scenario simulator", () => go("india")], ["CRYPTO", "Crypto workspace", () => go("crypto")],
  ["LIQ", "Liquidations", () => go("crypto")], ["FUND", "Funding & positioning", () => go("crypto")], ["GEO", "Geo-intelligence globe", () => go("geo")],
  ["CHOKE", "Chokepoint radar", () => go("geo")], ["RGM", "Regime compass", () => go("analytics")], ["CORR", "Correlation matrix", () => go("analytics")],
  ["EVT", "Event study lab", () => go("analytics")], ["GC3D", "3D yield surface", () => go("analytics")], ["PORT", "Portfolio & risk", () => go("portfolio")],
  ["MACRO", "Macro workspace", () => go("macro")], ["ECO", "Macro board", () => go("macro")], ["BRIEF", "Daily brief", () => emit("ui:brief")],
  ["ALRT", "Arm alert — ALRT BTC > 120000", (a) => a ? emit("ui:alert-add", a) : go("portfolio")], ["WATCH", "Add to watchlist — WATCH TSLA", (a) => watch(a)],
  ["N", "Search news — N hormuz", (a) => emit("ui:news-search", a)], ["GP", "Chart — GP NVDA", (a) => sec(a)], ["DES", "Security page — DES TCS", (a) => sec(a)],
  ["HEALTH", "Feed health", () => emit("ui:health")], ["HOME", "3D home", () => emit("ui:home")], ["HELP", "Command reference", () => emit("ui:help")],
  ["MUTE", "Toggle sound", () => toast("SOUND", sound.toggle() ? "On" : "Muted")],
  ["VEDA", "Talk to VEDA — or just say “Veda…”", () => emit("ui:voice")],
  ["VOICE", "Talk to VEDA (voice)", () => emit("ui:voice")],
];

let current = null;
function go(id) { emit("ui:go", id); }
function ask(q) { go("macro"); setTimeout(() => emit("ui:ask", q), 60); }
async function sec(a) {
  if (!a) return;
  const local = S.universe.find((u) => [u.code, u.sym].includes(a.toUpperCase()) || u.aliases?.includes(a.toLowerCase()));
  if (local) return emit("ui:security", local.sym);
  const r = await api.get(`/api/search?q=${encodeURIComponent(a)}`).catch(() => []);
  if (r[0]) emit("ui:security", r[0].sym); else toast("NOT FOUND", `No instrument matches “${a}”.`);
}
async function watch(a) { if (!a) return go("portfolio"); try { const r = await api.post("/api/watchlist", { symbol: a }); emit("ui:watch"); toast("WATCHLIST", `${r.symbol} added`); } catch (e) { toast("WATCHLIST", e.message); } }

function run(raw) {
  const text = raw.trim();
  if (!text) return;
  sound.go();
  const [head, ...rest] = text.split(/\s+/);
  const arg = rest.join(" ");
  const cmd = CMDS.find(([k]) => k === head.toUpperCase());
  if (cmd) return cmd[2](arg);
  if (text.endsWith("?") || /^(why|what|how|when|compare|explain|is|should|which)\b/i.test(text)) return ask(text);
  sec(text);
}

function commandLine() {
  const input = h("input", { placeholder: "Ticker, function or question — RELIANCE ⏎ · WEI · ASK why is gold rising?", spellcheck: false, autocomplete: "off" });
  const drop = h("div.cmd-drop.scroll.hidden");
  let items = [], sel = 0;
  const render = () => {
    clear(drop);
    if (!items.length) return drop.classList.add("hidden");
    drop.classList.remove("hidden");
    let lastSec = null;
    items.forEach((it, i) => {
      if (it.sec !== lastSec) { drop.append(h("div.cmd-sec", it.sec)); lastSec = it.sec; }
      const q = it.sym ? S.quotes[it.sym] : null;
      drop.append(h("div.cmd-item", { class: i === sel ? "sel" : "", on: { mousedown: (e) => { e.preventDefault(); pick(i); } } },
        h("span.ck", it.k), h("span.cn", it.n), q ? h("span.cv", { class: cls(q.pct) }, `${fmtPx(q.price, it.sym)}  ${fmtPct(q.pct)}`) : null));
    });
  };
  const pick = (i) => {
    const it = items[i];
    if (!it) return run(input.value);
    input.value = "";
    items = []; render();
    if (it.sym) emit("ui:security", it.sym); else if (it.needsArg) { input.value = `${it.k} `; input.focus(); } else run(it.k);
  };
  const remote = debounce(async (q) => {
    const r = await api.get(`/api/search?q=${encodeURIComponent(q)}`).catch(() => []);
    if (input.value.trim() !== q) return;
    const seen = new Set(items.map((i) => i.sym));
    items = items.concat(r.filter((x) => !seen.has(x.sym) && x.src === "yahoo").slice(0, 5).map((x) => ({ sec: "GLOBAL SEARCH", k: x.sym, n: `${x.name}${x.exch ? " · " + x.exch : ""}`, sym: x.sym })));
    render();
  }, 250);
  input.addEventListener("input", () => {
    sound.key();
    const q = input.value.trim();
    sel = 0;
    if (!q) { items = []; return render(); }
    const up = q.toUpperCase(), low = q.toLowerCase();
    const [head] = up.split(" ");
    const cmds = CMDS.filter(([k, n]) => k.startsWith(head) || n.toLowerCase().includes(low)).slice(0, 6)
      .map(([k, n]) => ({ sec: "FUNCTIONS", k, n, needsArg: ["ASK", "ALRT", "WATCH", "N", "GP", "DES"].includes(k) && !q.includes(" ") }));
    const inst = S.universe.filter((u) => u.code.startsWith(up) || u.sym.startsWith(up) || u.name.toLowerCase().includes(low) || u.aliases.some((a) => a.startsWith(low)))
      .slice(0, 8).map((u) => ({ sec: "INSTRUMENTS", k: u.code, n: u.name, sym: u.sym }));
    items = q.includes(" ") && cmds.length ? [] : [...cmds, ...inst];
    if (/\?$|^(why|what|how|compare|explain)\b/i.test(q)) items.unshift({ sec: "ORACLE", k: "ASK", n: q });
    render();
    if (q.length >= 2 && !q.includes(" ")) remote(q);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(items.length - 1, sel + 1); render(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); render(); }
    else if (e.key === "Enter") {
      e.preventDefault();
      const it = items[sel];
      if (it && it.sec === "ORACLE") { const q = input.value; input.value = ""; items = []; render(); return ask(q); }
      if (it && input.value.trim().split(" ").length === 1) return pick(sel);
      const v = input.value; input.value = ""; items = []; render(); run(v);
    } else if (e.key === "Escape") { input.value = ""; items = []; render(); input.blur(); }
  });
  input.addEventListener("blur", () => setTimeout(() => { items = []; render(); }, 120));
  const box = h("div.cmd", h("div.cmd-box", h("span.cmd-prompt", "FV›"), input, h("button.cmd-go", { on: { mousedown: (e) => { e.preventDefault(); const v = input.value; input.value = ""; run(v); } } }, "GO")), drop);
  box.focus = () => input.focus();
  return box;
}

export function buildTerminal(root) {
  const cmd = commandLine();
  const soundBtn = h("button.icon-btn", { title: "Sound", on: { click: () => { const on_ = sound.toggle(); clear(soundBtn).append(icon(on_ ? "sound" : "mute")); } } }, icon(sound.on ? "sound" : "mute"));
  const bell = h("button.icon-btn", { title: "Enable alert notifications", on: { click: async () => { if ("Notification" in window) { const p = await Notification.requestPermission(); toast("NOTIFICATIONS", p === "granted" ? "Browser notifications enabled for alerts." : "Permission not granted."); } } } }, icon("bell"));
  const head = h("header.t-head",
    h("div.brand", { style: { cursor: "pointer" }, on: { click: () => emit("ui:home") } }, EMBLEM(), h("span.w", "FINVERSE"), h("span.ed", "OBSIDIAN")),
    cmd, clocks(),
    h("div.hd-right", feedChip(() => emit("ui:health")), voiceButton(), bell, soundBtn,
      h("button.icon-btn", { title: "Daily brief", on: { click: () => emit("ui:brief") } }, icon("brief")),
      h("button.icon-btn", { title: "Help (?)", on: { click: () => emit("ui:help") } }, icon("help")),
      h("button.icon-btn", { title: "Home", on: { click: () => emit("ui:home") } }, icon("home"))));
  const tabs = h("nav.t-tabs");
  const conn = h("span", "● LIVE"), clock = h("b", "--:--:--"), evm = h("b", "0");
  WORKSPACES.forEach((w) => tabs.append(h("button.t-tab", { dataset: { ws: w.id }, on: { click: () => { sound.click(); go(w.id); } } }, h("span.fk", w.key), w.name)));
  tabs.append(h("span.spacer"), h("div.t-status", conn, h("span", "TAPE ", evm, " EV/MIN"), h("span", "UTC ", clock)));
  const wsEls = {};
  const main = h("div", { style: { flex: "1 1 auto", minHeight: 0, display: "flex", flexDirection: "column" } });
  WORKSPACES.forEach((w) => { const el = h("div.ws", { class: `ws-${w.id}`, dataset: { ws: w.id } }, w.build()); wsEls[w.id] = el; main.append(el); });
  const systemic = h("div.systemic.hidden");
  root.append(head, tickerTape(), tabs, main, newsTape(), systemic);

  on("ui:go", (id) => {
    if (!wsEls[id]) return;
    current = id;
    store.set("ws", id);
    Object.entries(wsEls).forEach(([k, el]) => el.classList.toggle("on", k === id));
    [...tabs.querySelectorAll(".t-tab")].forEach((t) => t.classList.toggle("on", t.dataset.ws === id));
    emit("ui:ws", id);
  });
  on("conn", (ok) => { conn.textContent = ok ? "● LIVE" : "○ RECONNECTING"; conn.style.color = ok ? "var(--up)" : "var(--warn)"; });
  on("health", () => { evm.textContent = S.tapeSpeed; systemic.classList.toggle("hidden", !(S.tapeSpeed > 25)); });
  on("intel", () => { evm.textContent = S.tapeSpeed; systemic.classList.toggle("hidden", !(S.tapeSpeed > 25)); });
  on("alert", (ev) => {
    sound.alert();
    toast("ALERT FIRED", ev.message, { crit: true, ms: 12000 });
    if ("Notification" in window && Notification.permission === "granted") new Notification("Finverse alert", { body: ev.message, silent: true });
  });
  setInterval(() => { clock.textContent = new Date(Date.now() + S.serverOffset).toISOString().slice(11, 19); }, 1000);

  // spotlight that follows the cursor across glass panels
  main.addEventListener("pointermove", (e) => {
    const p = e.target.closest(".panel");
    if (!p) return;
    const r = p.getBoundingClientRect();
    p.style.setProperty("--mx", `${e.clientX - r.left}px`);
    p.style.setProperty("--my", `${e.clientY - r.top}px`);
  });
  window.addEventListener("keydown", (e) => {
    if (!root.classList.contains("active")) return;
    const k = WORKSPACES.findIndex((w) => w.key === e.key);
    if (k >= 0) { e.preventDefault(); sound.click(); go(WORKSPACES[k].id); return; }
    if (document.activeElement && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
    if (e.key === "/" || (e.key === "k" && (e.ctrlKey || e.metaKey))) { e.preventDefault(); cmd.focus(); }
    else if (e.key === "?") emit("ui:help");
  });
  go(store.get("ws", "macro"));
  return { focus: () => cmd.focus(), current: () => current };
}
