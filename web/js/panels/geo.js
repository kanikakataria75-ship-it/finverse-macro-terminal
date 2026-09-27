import { S, on, emit, meta } from "../core/state.js";
import { h, clear, fmtPct, cls, tip, untip, ago, seqColor } from "../core/util.js";
import { panel } from "./common.js";
import { Globe } from "../three/globe.js";

export function conflictPanel(area = "conf") {
  const p = panel(area, "Conflict Intensity Index", { mn: "CII" });
  const list = h("div.scroll", { style: { position: "absolute", inset: 0 } });
  p.body.append(list);
  function draw() {
    const G = S.geo || {}, all = Object.entries(G.conflict || {});
    const rows = all.filter(([, c]) => c.score != null).sort((a, b) => b[1].score - a[1].score);
    const unscored = all.filter(([, c]) => c.score == null).map(([, c]) => c.name);
    clear(list);
    if (!rows.length) { list.append(h("div.empty", h("div", h("b", `SWEEPING ${Math.round((G.sweep || 0) * 100)}%`), "First conflict sweep in progress (GDELT, 1 request / 6s)…"))); return; }
    rows.forEach(([iso, c]) => list.append(h("div.list-row", { style: { gap: "10px", opacity: c.confidence === "low" ? 0.7 : 1 }, on: { mousemove: (e) => tip(e, c.name, [["Intensity", `${c.score.toFixed(0)}/100`],
      ...(c.method === "gdelt" ? [["Conflict share · 7d", `${c.share}%`], ["Conflict share · 24h", `${c.share24}%`], ["Escalation", `${c.escalation?.toFixed(2) ?? "—"}×`, c.escalation >= 1.5 ? "down" : ""], ["Coverage analysed", `${c.coverage?.toLocaleString()} articles`]] : [["Conflict share of wire stories", `${c.share}%`], ["Stories analysed", c.mentions]]),
      ["Method", c.method === "gdelt" ? `GDELT${c.stale ? " (last good reading)" : ""}` : "Finverse wire (GDELT unreachable)"], ["Confidence", (c.confidence || "—").toUpperCase(), c.confidence === "low" ? "down" : ""]]), mouseleave: untip } },
      h("span.mono.muted", { style: { width: "34px", fontSize: "10px" } }, iso),
      h("span", { style: { width: "110px", fontWeight: 600 } }, c.name),
      h("div.meter", h("i", { style: { width: `${c.score}%`, background: seqColor(c.score / 100, ["#3b1822", "#9c2438", "#ff5773", "#ffc2cc"]) } })),
      h("span.mono", { style: { width: "30px", textAlign: "right", fontSize: "11px" } }, c.score.toFixed(0)),
      h("span.mono", { style: { width: "42px", textAlign: "right", fontSize: "10px" }, class: c.escalation >= 1.5 ? "down" : "muted" }, c.confidence === "low" ? "LOW·C" : c.escalation >= 1.5 ? `▲${c.escalation.toFixed(1)}×` : c.stale ? "STALE" : "·"))));
    if (unscored.length) list.append(h("div.src-note", { style: { padding: "10px 14px 0" } }, `Insufficient coverage to score: ${unscored.join(", ")}`));
    list.append(h("div.src-note", { style: { padding: "10px 14px" } }, `${G.sources?.conflict || ""} · updated ${G.conflict_asof ? ago(G.conflict_asof) + " ago" : "—"}. Measures how much of a country's coverage is about armed conflict — a proxy, not a casualty count.`));
  }
  on("geo", draw); on("hydrated", draw);
  return p.el;
}

let geoGlobe;
export function globePanel(area = "globe") {
  const p = panel(area, "Geo-Intelligence Globe", { mn: "GLOBE" });
  const canvas = h("canvas.stage");
  const labels = h("div.globe-labels");
  const legend = h("div.globe-legend", { style: { top: "46px", right: "14px" } },
    ...[["#f4ddaa", "Exchange open"], ["#6f86a8", "Exchange closed"], ["#ff5773", "Conflict hotspot"], ["#ffb648", "Quake M5.2+ / elevated"], ["#7fe3ff", "Chokepoint"]]
      .map(([c, t]) => h("div.li", h("span.sw", { style: { background: c, boxShadow: `0 0 8px ${c}` } }), t)));
  p.body.append(canvas, labels, legend, h("div.src-note", { style: { position: "absolute", left: "14px", bottom: "10px" } }, "Drag to rotate · scroll to zoom · real-time day/night terminator"));
  let wantRun = false;
  const sync = () => { if (!geoGlobe) return; if (wantRun) { geoGlobe.resize(); geoGlobe.start(); } else geoGlobe.stop(); };
  setTimeout(() => {
    geoGlobe = new Globe(canvas, {
      labels, dots: 26000, zoom: 3.6, bloom: true,
      onHover: (d, e) => {
        if (!d || !e) return untip();
        if (d.kind === "exchange") { const q = S.quotes[d.ex.idx]; tip(e, `${d.ex.id} · ${d.ex.city}`, [["Session", `${d.ex.open}–${d.ex.close}`], ...(q ? [["Benchmark", `${meta(d.ex.idx).code} ${fmtPct(q.pct)}`, cls(q.pct)]] : [])]); }
        else if (d.kind === "quake") tip(e, `M${d.info.mag.toFixed(1)} earthquake`, [d.info.place, ["When", `${ago(d.info.t)} ago`]]);
        else if (d.kind === "choke") tip(e, d.info.name, [["Status", d.info.status, d.info.status === "NORMAL" ? "up" : "down"], ["Risk", d.info.risk.toFixed(0)], ["Carries", d.info.flows], ...d.info.drivers.slice(0, 3)]);
      },
    });
    geoGlobe.setGeo(S.geo || {}); geoGlobe.setQuotes(S.quotes);
    sync();
  }, 0);
  on("geo", (g) => geoGlobe && geoGlobe.setGeo(g));
  on("quotes", () => geoGlobe && geoGlobe.setQuotes(S.quotes));
  on("ui:ws", (ws) => { wantRun = ws === "geo" && document.getElementById("terminal").classList.contains("active"); sync(); });
  on("ui:view", (v) => { if (v !== "terminal") { wantRun = false; sync(); } });
  on("ui:focus", ({ lat, lon }) => geoGlobe && geoGlobe.focus(lat, lon));
  return p.el;
}

export function chokepointPanel(area = "choke") {
  const p = panel(area, "Chokepoint Radar", { mn: "CHOKE" });
  const list = h("div.scroll", { style: { position: "absolute", inset: 0 } });
  p.body.append(list);
  function draw() {
    clear(list);
    (S.geo?.chokepoints || []).forEach((c) => list.append(h("div", { style: { padding: "10px 14px", borderBottom: "1px solid rgba(255,255,255,0.04)", cursor: "pointer" }, on: { click: () => emit("ui:focus", { lat: c.lat, lon: c.lon }) } },
      h("div.row.between", h("span", { style: { fontWeight: 700 } }, c.name), h("span.status-pill", { class: c.status }, c.status)),
      h("div.row", { style: { marginTop: "6px", gap: "8px" } }, h("div.meter", h("i", { style: { width: `${c.risk}%`, background: c.status === "NORMAL" ? "var(--ice)" : c.status === "ELEVATED" ? "var(--warn)" : "var(--crit)" } })), h("span.mono", { style: { fontSize: "10px", width: "26px", textAlign: "right" } }, c.risk.toFixed(0))),
      h("div.src-note", { style: { marginTop: "5px" } }, c.flows),
      c.drivers.length ? h("div", { style: { marginTop: "4px", fontSize: "11px", color: "var(--text-2)" } }, c.drivers.slice(0, 2).join(" · ")) : null,
      h("div.chip-list", { style: { marginTop: "6px" } }, ...c.exposed.slice(0, 5).map((sym) => { const q = S.quotes[sym]; return h("span.tag", { class: q ? cls(q.pct) : "", style: { cursor: "pointer" }, on: { click: (e) => { e.stopPropagation(); emit("ui:security", sym); } } }, `${meta(sym).code} ${q ? fmtPct(q.pct) : ""}`); })))));
    if (!(S.geo?.chokepoints || []).length) list.append(h("div.empty", h("div", h("b", "SCANNING"), "Computing chokepoint risk…")));
  }
  on("geo", draw); on("hydrated", draw);
  return p.el;
}

export function hazardPanel(area = "haz") {
  const p = panel(area, "Physical Hazards", { mn: "HAZ" });
  const list = h("div.scroll", { style: { position: "absolute", inset: 0 } });
  p.body.append(list);
  function draw() {
    clear(list);
    const G = S.geo || {};
    const quakes = [...(G.quakes || [])].sort((a, b) => b.mag - a.mag).slice(0, 12);
    list.append(h("div.label-xs", { style: { padding: "10px 14px 4px" } }, "Earthquakes · USGS M4.5+ (7d)"));
    quakes.forEach((q) => list.append(h("div.list-row", { style: { cursor: "pointer" }, on: { click: () => emit("ui:focus", { lat: q.lat, lon: q.lon }) } },
      h("span.mono", { style: { width: "40px", fontWeight: 800 }, class: q.mag >= 6.5 ? "down" : q.mag >= 5.5 ? "gold" : "" }, `M${q.mag.toFixed(1)}`),
      h("span.grow.ellipsis", q.place), q.tsunami ? h("span.tag.down", "TSUNAMI") : null, h("span.mono.muted", { style: { fontSize: "10px" } }, ago(q.t)))));
    list.append(h("div.label-xs", { style: { padding: "14px 14px 4px" } }, "Natural events · NASA EONET"));
    (G.events || []).slice(0, 16).forEach((e) => list.append(h("div.list-row", { style: { cursor: "pointer" }, on: { click: () => emit("ui:focus", { lat: e.lat, lon: e.lon }) } },
      h("span.tag.warn", { style: { width: "96px", justifyContent: "center" } }, (e.cat || "EVENT").slice(0, 14)), h("span.grow.ellipsis", e.title))));
  }
  on("geo", draw); on("hydrated", draw);
  return p.el;
}
