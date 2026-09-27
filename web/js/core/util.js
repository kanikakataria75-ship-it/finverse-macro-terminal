// Small, dependency-free helpers. Every string reaches the DOM via textContent — never innerHTML.

// Optional children are passed as null/false throughout the UI; native append() would render them
// as the literal text "null", so skip them once, here, for every element.
for (const proto of [Element.prototype, DocumentFragment.prototype]) {
  for (const m of ["append", "prepend"]) {
    const native = proto[m];
    proto[m] = function (...nodes) { return native.apply(this, nodes.filter((n) => n != null && n !== false)); };
  }
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** h('div.cls#id', {attrs, on:{click}}, ...children) — safe DOM builder */
export function h(tag, props, ...kids) {
  const m = /^([a-z0-9]+)?((?:[.#][\w-]+)*)$/i.exec(tag) || [];
  const node = document.createElement(m[1] || "div");
  (m[2] || "").replace(/([.#])([\w-]+)/g, (_, t, v) => (t === "." ? node.classList.add(v) : (node.id = v)));
  if (props && (typeof props !== "object" || props instanceof Node || Array.isArray(props))) { kids.unshift(props); props = null; }
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === "on") for (const [ev, fn] of Object.entries(v)) node.addEventListener(ev, fn);
      else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
      else if (k === "class") node.className += " " + v;
      else if (k === "dataset") Object.assign(node.dataset, v);
      else if (k === "text") node.textContent = v;
      else if (k in node && k !== "list") { try { node[k] = v; } catch { node.setAttribute(k, v); } }
      else node.setAttribute(k, v === true ? "" : v);
    }
  }
  append(node, kids);
  return node;
}
function append(node, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    node.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}
export const svgNS = "http://www.w3.org/2000/svg";
export function s(tag, attrs = {}, ...kids) {
  const n = document.createElementNS(svgNS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  for (const k of kids.flat()) if (k != null) n.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return n;
}
export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }

// ------------------------------------------------------------------ format
export function fmtPx(v, sym) {
  if (v == null || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  if (sym && /=X$/.test(sym) && a < 20) return v.toFixed(4);
  if (a >= 10000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (a >= 1000) return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (a >= 100) return v.toFixed(2);
  if (a >= 10) return v.toFixed(3);
  if (a >= 1) return v.toFixed(4);
  return v.toPrecision(4);
}
export const fmtPct = (v, d = 2) => (v == null || Number.isNaN(v) ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
export const fmtSigned = (v, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}`);
export function fmtBig(v, cur = "") {
  if (v == null) return "—";
  const a = Math.abs(v);
  const [d, u] = a >= 1e12 ? [1e12, "T"] : a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
  return `${v < 0 ? "−" : ""}${cur}${(a / d).toFixed(a / d >= 100 ? 0 : a / d >= 10 ? 1 : 2)}${u}`;
}
export function fmtINR(v) {
  if (v == null) return "—";
  const a = Math.abs(v);
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
  return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}
export const cls = (v) => (v == null || Math.abs(v) < 1e-9 ? "flat" : v > 0 ? "up" : "down");
export function ago(ms) {
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 60) return `${Math.floor(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}
export const hhmm = (ms) => new Date(ms).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const lerp = (a, b, t) => a + (b - a) * t;

// ------------------------------------------------------------------ colours
export function mixHex(a, b, t) {
  const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
  const r = Math.round(lerp(pa >> 16, pb >> 16, t)), g = Math.round(lerp((pa >> 8) & 255, (pb >> 8) & 255, t)), bl = Math.round(lerp(pa & 255, pb & 255, t));
  return `rgb(${r},${g},${bl})`;
}
/** diverging scale for returns: red ← neutral → green */
export function divColor(v, span = 3) {
  if (v == null) return "rgba(255,255,255,0.04)";
  const t = clamp(v / span, -1, 1);
  return t >= 0 ? mixHex("#141a22", "#12c088", Math.pow(t, 0.75)) : mixHex("#141a22", "#e2324f", Math.pow(-t, 0.75));
}
export function seqColor(t, stops = ["#0c1118", "#3a2a12", "#b8863a", "#f4ddaa"]) {
  t = clamp(t, 0, 1);
  const seg = (stops.length - 1) * t, i = Math.min(stops.length - 2, Math.floor(seg));
  return mixHex(stops[i], stops[i + 1], seg - i);
}

// ------------------------------------------------------------------ svg bits
export function sparkPath(values, w, h, pad = 2) {
  const v = (values || []).filter((x) => x != null);
  if (v.length < 2) return "";
  const lo = Math.min(...v), hi = Math.max(...v), rng = hi - lo || 1;
  return v.map((x, i) => `${i ? "L" : "M"}${((i / (v.length - 1)) * (w - pad * 2) + pad).toFixed(1)},${(h - pad - ((x - lo) / rng) * (h - pad * 2)).toFixed(1)}`).join("");
}
let _gid = 0;
export function sparkline(values, { w = 60, h = 20, color, fill = true, stroke = 1.3 } = {}) {
  const v = (values || []).filter((x) => x != null);
  const up = v.length > 1 ? v[v.length - 1] >= v[0] : true;
  const c = color || (up ? "#2fe3a3" : "#ff5773");
  const d = sparkPath(v, w, h);
  const id = `sg${++_gid}`;
  const svg = s("svg", { viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: "none", class: "spark" });
  if (!d) return svg;
  if (fill) {
    svg.append(s("defs", {}, s("linearGradient", { id, x1: 0, y1: 0, x2: 0, y2: 1 },
      s("stop", { offset: "0%", "stop-color": c, "stop-opacity": 0.28 }), s("stop", { offset: "100%", "stop-color": c, "stop-opacity": 0 }))));
    svg.append(s("path", { d: `${d}L${w - 2},${h}L2,${h}Z`, fill: `url(#${id})` }));
  }
  svg.append(s("path", { d, fill: "none", stroke: c, "stroke-width": stroke, "vector-effect": "non-scaling-stroke", "stroke-linejoin": "round" }));
  return svg;
}

/** swap text & flash green/red when a number changes */
export function setNum(node, text, dir) {
  if (!node || node.textContent === text) return;
  node.textContent = text;
  if (dir) {
    node.classList.remove("flash-up", "flash-down");
    void node.offsetWidth;
    node.classList.add(dir > 0 ? "flash-up" : "flash-down");
  }
}

// ------------------------------------------------------------------ tooltip
let tipEl;
export function tip(e, title, rows = []) {
  tipEl ||= document.getElementById("tip");
  clear(tipEl);
  if (title) tipEl.append(h("div.tt-title", title));
  for (const r of rows) tipEl.append(Array.isArray(r) ? h("div.tt-row", h("span", r[0]), h("b", { class: r[2] || "" }, r[1])) : h("div", { style: { fontSize: "12px", color: "var(--text-2)", marginTop: "4px", lineHeight: 1.45 } }, r));
  const x = Math.min(window.innerWidth - 320, e.clientX + 16), y = Math.min(window.innerHeight - tipEl.offsetHeight - 10, e.clientY + 14);
  tipEl.style.left = `${x}px`; tipEl.style.top = `${y}px`;
  tipEl.classList.add("on");
}
export function untip() { (tipEl ||= document.getElementById("tip")).classList.remove("on"); }

export function toast(title, body, { crit = false, ms = 6500 } = {}) {
  const box = document.getElementById("toasts");
  const t = h("div.toast", { class: crit ? "crit" : "" }, h("div.t-head", h("span.dot.live", { style: { color: crit ? "var(--crit)" : "var(--gold)" } }), title), h("div.t-body", body));
  box.prepend(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 450); }, ms);
  while (box.children.length > 4) box.lastChild.remove();
}

export const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
export const store = {
  get(k, d) { try { const v = localStorage.getItem("fv." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("fv." + k, JSON.stringify(v)); } catch { /* private mode */ } },
};
