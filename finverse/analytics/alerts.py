"""User alert rules, evaluated continuously against live data and intel events.

Rule JSON examples
  {"type":"price","sym":"BTC-USD","op":">","value":120000}
  {"type":"pct","sym":"^NSEI","op":"<","value":-1.5}
  {"type":"z","sym":"*","value":3}                       any 3-sigma move
  {"type":"keyword","value":"hormuz"}                    news / rhetoric / intel text
  {"type":"liq","value":2000000}                         single liquidation >= $2M
  {"type":"heat","value":70}                             Trump Meter post heat
Command syntax (terminal): ALRT BTC > 120000 | ALRT NIFTY PCT < -1.5 | ALRT Z 3 | ALRT NEWS hormuz
"""
import json
import logging
import re
import time

from ..bus import bus
from ..config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from ..providers.markets import markets
from ..store import store
from ..universe import meta, resolve
from ..util import client

log = logging.getLogger("finverse.alerts")
COOLDOWN = 30 * 60


def parse(text: str) -> dict | None:
    t = text.strip()
    if m := re.match(r"^(news|keyword|kw)\s+(.+)$", t, re.I):
        return {"type": "keyword", "value": m.group(2).strip().lower()}
    if m := re.match(r"^z\s+(\d+(?:\.\d+)?)$", t, re.I):
        return {"type": "z", "sym": "*", "value": float(m.group(1))}
    if m := re.match(r"^liq\s+(\d+(?:\.\d+)?)\s*(k|m)?$", t, re.I):
        mult = {"k": 1e3, "m": 1e6}.get((m.group(2) or "").lower(), 1)
        return {"type": "liq", "value": float(m.group(1)) * mult}
    if m := re.match(r"^heat\s+(\d+)$", t, re.I):
        return {"type": "heat", "value": int(m.group(1))}
    if m := re.match(r"^(\S+)\s+(pct|%)\s*([<>])\s*([+\-]?\d+(?:\.\d+)?)$", t, re.I):
        sym = resolve(m.group(1))
        return {"type": "pct", "sym": sym, "op": m.group(3), "value": float(m.group(4))} if sym else None
    if m := re.match(r"^(\S+)\s*([<>])\s*([\d,]+(?:\.\d+)?)$", t):
        sym = resolve(m.group(1))
        return {"type": "price", "sym": sym, "op": m.group(2), "value": float(m.group(3).replace(",", ""))} if sym else None
    return None


def describe(r: dict) -> str:
    t = r.get("type")
    if t == "price":
        return f"{meta(r['sym'])['code']} {r['op']} {r['value']:,}"
    if t == "pct":
        return f"{meta(r['sym'])['code']} day change {r['op']} {r['value']}%"
    if t == "z":
        return f"Any move ≥ {r['value']}σ"
    if t == "keyword":
        return f"Intel mentions “{r['value']}”"
    if t == "liq":
        return f"Liquidation ≥ ${r['value']:,.0f}"
    if t == "heat":
        return f"Trump post heat ≥ {r['value']}"
    return json.dumps(r)


class Alerts:
    def __init__(self):
        bus.on_intel(self.on_intel)

    def list(self) -> list[dict]:
        rows = store.query("SELECT * FROM alerts ORDER BY id DESC")
        for r in rows:
            r["rule"] = json.loads(r["rule"])
            r["label"] = describe(r["rule"])
        return rows

    def add(self, rule: dict) -> dict:
        cur = store.execute("INSERT INTO alerts(rule, created) VALUES(?,?)", (json.dumps(rule), time.time()))
        return {"id": cur.lastrowid, "rule": rule, "label": describe(rule)}

    def delete(self, rid: int):
        store.execute("DELETE FROM alerts WHERE id=?", (rid,))

    def toggle(self, rid: int, enabled: bool):
        store.execute("UPDATE alerts SET enabled=? WHERE id=?", (1 if enabled else 0, rid))

    def _fire(self, row: dict, message: str):
        if time.time() - (row.get("last_fired") or 0) < COOLDOWN:
            return
        store.execute("UPDATE alerts SET last_fired=?, fire_count=fire_count+1 WHERE id=?", (time.time(), row["id"]))
        ev = bus.emit("ALERT", message, tier="CRITICAL", asset=f"#{row['id']}", rule_id=row["id"])
        bus.publish("alert", ev)
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            import asyncio
            asyncio.get_event_loop().create_task(self._telegram(f"FINVERSE ALERT\n{message}"))

    async def _telegram(self, text):
        try:
            async with client(10) as c:
                await c.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                             json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        except Exception as e:
            log.warning("telegram: %s", e)

    def check_quotes(self):
        for row in self.list():
            if not row["enabled"]:
                continue
            r = row["rule"]
            t = r.get("type")
            if t in ("price", "pct"):
                q = markets.quotes.get(r["sym"])
                if not q:
                    continue
                val = q.get("price") if t == "price" else q.get("pct")
                if val is None:
                    continue
                hit = val > r["value"] if r["op"] == ">" else val < r["value"]
                if hit:
                    unit = "" if t == "price" else "%"
                    self._fire(row, f"{describe(r)} — now {val:,.4g}{unit}")
            elif t == "z":
                for sym, q in markets.quotes.items():
                    z = q.get("z")
                    if z is not None and abs(z) >= r["value"]:
                        self._fire(row, f"{meta(sym)['code']} {q.get('pct'):+.2f}% is a {z:+.1f}σ move")
                        break

    def on_intel(self, ev: dict):
        if ev.get("tag") == "ALERT":
            return
        for row in self.list():
            if not row["enabled"]:
                continue
            r = row["rule"]
            t = r.get("type")
            if t == "keyword" and r["value"] in ev.get("message", "").lower():
                self._fire(row, f"“{r['value']}” · [{ev['tag']}] {ev['message'][:160]}")
            elif t == "liq" and ev.get("tag") == "LIQUIDATION" and (ev.get("usd") or 0) >= r["value"]:
                self._fire(row, ev["message"])
            elif t == "heat" and ev.get("tag") == "RHETORIC" and (ev.get("heat") or 0) >= r["value"]:
                self._fire(row, f"Trump post heat {ev.get('heat')}: {ev['message'][:140]}")


alerts = Alerts()
