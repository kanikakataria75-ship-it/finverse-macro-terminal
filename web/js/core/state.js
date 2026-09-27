// Reactive terminal state, hydrated by /api/snapshot and kept live over one WebSocket.

const listeners = new Map();
export const S = {
  universe: [], bySym: {}, matrix: [], drivers: [], quotes: {}, macro: {}, analytics: {}, rhetoric: {},
  geo: {}, news: [], top: [], topics: {}, intel: [], crypto: {}, health: { feeds: [] }, liqs: [], connected: false,
  tapeSpeed: 0, serverOffset: 0,
};

export function on(key, fn) {
  if (!listeners.has(key)) listeners.set(key, new Set());
  listeners.get(key).add(fn);
  return () => listeners.get(key).delete(fn);
}
export function emit(key, payload) {
  (listeners.get(key) || []).forEach((fn) => { try { fn(payload); } catch (e) { console.error(key, e); } });
}

export const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || r.statusText);
    return j;
  },
  async del(path) { return (await fetch(path, { method: "DELETE" })).json(); },
};

export const meta = (sym) => S.bySym[sym] || { sym, code: sym, name: sym, cls: "equity" };

export async function hydrate() {
  const snap = await api.get("/api/snapshot");
  S.universe = snap.universe;
  S.bySym = Object.fromEntries(snap.universe.map((u) => [u.sym, u]));
  Object.assign(S, {
    matrix: snap.matrix, drivers: snap.drivers, quotes: snap.quotes, macro: snap.macro, analytics: snap.analytics,
    rhetoric: snap.rhetoric, geo: snap.geo, news: snap.news, top: snap.top, topics: snap.topics, intel: snap.intel,
    crypto: snap.crypto, health: snap.health, serverOffset: snap.server_time - Date.now(),
  });
  S.liqs = (snap.crypto.liq && snap.crypto.liq.recent) || [];
  emit("hydrated", S);
  return S;
}

let ws, retry = 0;
export function connect() {
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
  ws = new WebSocket(url);
  ws.onopen = () => { S.connected = true; retry = 0; emit("conn", true); };
  ws.onclose = () => {
    S.connected = false; emit("conn", false);
    setTimeout(async () => { try { await hydrate(); } catch { /* server still down */ } connect(); }, Math.min(15000, 1000 * 2 ** retry++));
  };
  ws.onmessage = (m) => {
    const { ch, data } = JSON.parse(m.data);
    switch (ch) {
      case "quotes": {
        const prev = {};
        for (const [sym, q] of Object.entries(data)) { prev[sym] = S.quotes[sym]?.price; S.quotes[sym] = q; }
        emit("quotes", { changed: data, prev });
        break;
      }
      case "intel":
        S.intel.push(data); if (S.intel.length > 400) S.intel.shift();
        S.tapeSpeed = data.tape_speed || S.tapeSpeed;
        emit("intel", data); break;
      case "news":
        S.news = [...data.slice().reverse(), ...S.news].slice(0, 300); emit("news", data); break;
      case "macro": Object.assign(S.macro, data); emit("macro", S.macro); break;
      case "analytics": S.analytics = data; emit("analytics", data); break;
      case "rhetoric": S.rhetoric = data; emit("rhetoric", data); break;
      case "geo": S.geo = data; emit("geo", data); break;
      case "crypto": Object.assign(S.crypto, data); emit("crypto", S.crypto); break;
      case "liq": S.liqs.push(data); if (S.liqs.length > 400) S.liqs.shift(); emit("liq", data); break;
      case "health": S.health = data; S.tapeSpeed = data.tape_speed; emit("health", data); break;
      case "alert": emit("alert", data); break;
    }
  };
  setInterval(() => ws && ws.readyState === 1 && ws.send("ping"), 25000);
}
