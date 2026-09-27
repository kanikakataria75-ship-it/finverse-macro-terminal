"""Crypto: real-time Binance streams + derivatives positioning (all public, keyless).

FIX: liquidations are a USD-M *futures* stream (fstream.binance.com). The legacy code
subscribed on the spot host, where !forceOrder@arr does not exist, so it never fired.
"""
import asyncio
import json
import logging
import time
from collections import deque

import websockets

from ..bus import bus
from ..config import LIQ_FEED_MIN_USD
from ..universe import BY_BINANCE
from ..util import client, finite
from .markets import markets

log = logging.getLogger("finverse.crypto")

SPOT_WS = "wss://stream.binance.com:9443/ws/!miniTicker@arr"
LIQ_WS = "wss://fstream.binance.com/ws/!forceOrder@arr"
FAPI = "https://fapi.binance.com"
PERPS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT",
         "LINKUSDT", "SUIUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT"]


def liq_tier(usd: float) -> str:
    if usd >= 5_000_000:
        return "CRITICAL"  # systemic whale
    if usd >= 1_000_000:
        return "HEAVY"     # heavy desk
    return "SIGNIFICANT"


class Crypto:
    def __init__(self):
        self.liqs: deque = deque(maxlen=5000)
        self.funding: dict = {}
        self.oi: dict = {}
        self.ls_ratio: dict = {}
        self.fng: dict = {}
        self.global_: dict = {}
        self._last_pub = 0.0
        self._pending: dict = {}

    # ------------------------------------------------------------ spot ticks
    async def spot_stream(self, health):
        async for ws in websockets.connect(SPOT_WS, ping_interval=20, open_timeout=15):
            try:
                health.ok("connected")
                async for raw in ws:
                    for t in json.loads(raw):
                        inst = BY_BINANCE.get(t.get("s"))
                        if not inst:
                            continue
                        q = markets.apply_live(inst.sym, float(t["c"]), float(t["o"]), "BINANCE")
                        self._pending[inst.sym] = q
                    if time.time() - self._last_pub > 1.0 and self._pending:
                        bus.publish("quotes", self._pending)
                        self._pending, self._last_pub = {}, time.time()
                        health.ok("streaming")
            except websockets.ConnectionClosed:
                health.warn("reconnecting")
                continue

    # ---------------------------------------------------------- liquidations
    def _on_liq(self, venue: str, sym: str, side: str, usd: float, price: float, t: int, health):
        """Common sink for every venue. side = the position that was force-closed."""
        if usd <= 0:
            return
        ev = {"t": t, "sym": sym, "side": side, "usd": round(usd, 2), "price": price, "venue": venue}
        self.liqs.append(ev)
        bus.publish("liq", ev)
        health.ok(f"{venue}: {sum(1 for x in self.liqs if x['venue'] == venue)} events")
        if usd >= LIQ_FEED_MIN_USD:
            tier = liq_tier(usd)
            label = {"CRITICAL": "SYSTEMIC WHALE", "HEAVY": "HEAVY DESK"}.get(tier, "SIGNIFICANT")
            base = sym.replace("USDT", "").replace("USD", "")
            bus.emit("LIQUIDATION", f"{label}: ${usd:,.0f} {side.lower()} liquidated on {base} @ {price:,.4g} · {venue}",
                     tier=tier, asset=base, usd=usd, side=side, venue=venue)

    async def liquidation_stream(self, health):
        """Binance USD-M futures. Some networks receive no futures market data even though the
        socket opens; the OKX and Bybit streams keep the tape alive regardless."""
        async for ws in websockets.connect(LIQ_WS, ping_interval=20, open_timeout=15):
            try:
                health.ok("connected · waiting for events")
                async for raw in ws:
                    o = json.loads(raw).get("o", {})
                    price = float(o.get("ap") or o.get("p") or 0)
                    qty = float(o.get("z") or o.get("q") or 0)
                    # order side SELL = a long position was force-closed
                    self._on_liq("BINANCE", o.get("s", "?"), "LONG" if o.get("S") == "SELL" else "SHORT",
                                 price * qty, price, int(o.get("T", time.time() * 1000)), health)
            except websockets.ConnectionClosed:
                health.warn("reconnecting")
                continue

    async def okx_liquidations(self, health):
        """OKX public 'liquidation-orders' channel: every SWAP liquidation on the venue.
        Contract specs come from the 'instruments' channel on the same socket (the REST host
        is unreachable on some networks while the WebSocket host is fine)."""
        specs: dict = {}
        async with client(12) as c:
            for host in ("my.okx.com", "www.okx.com", "aws.okx.com"):  # regional hosts differ in reachability
                try:
                    r = await c.get(f"https://{host}/api/v5/public/instruments", params={"instType": "SWAP"})
                    for i in r.json().get("data", []):
                        specs[i["instId"]] = (float(i.get("ctVal") or 0), i.get("ctType"))
                    if specs:
                        break
                except Exception as e:
                    log.debug("okx instruments via %s: %s", host, e)
        async for ws in websockets.connect("wss://ws.okx.com:8443/ws/v5/public", ping_interval=20, open_timeout=15):
            try:
                await ws.send(json.dumps({"op": "subscribe", "args": [
                    {"channel": "instruments", "instType": "SWAP"},
                    {"channel": "liquidation-orders", "instType": "SWAP"}]}))
                health.ok(f"subscribed · {len(specs)} contracts · waiting for events")
                async for raw in ws:
                    if raw == "pong":
                        continue
                    msg = json.loads(raw)
                    channel = msg.get("arg", {}).get("channel")
                    if channel == "instruments":
                        for i in msg.get("data", []):
                            specs[i["instId"]] = (float(i.get("ctVal") or 0), i.get("ctType"))
                        continue
                    if channel != "liquidation-orders":
                        continue
                    for x in msg.get("data", []):
                        inst_id = x.get("instId", "")
                        if inst_id not in specs:
                            continue  # contract size unknown yet: never guess a notional
                        ct_val, ct_type = specs[inst_id]
                        sym = inst_id.replace("-SWAP", "").replace("-", "")
                        for d in x.get("details", []):
                            sz, px = float(d.get("sz") or 0), float(d.get("bkPx") or 0)
                            usd = sz * ct_val if ct_type == "inverse" else sz * ct_val * px
                            pos = d.get("posSide")
                            side = pos.upper() if pos in ("long", "short") else ("LONG" if d.get("side") == "sell" else "SHORT")
                            self._on_liq("OKX", sym, side, usd, px, int(d.get("ts") or time.time() * 1000), health)
            except websockets.ConnectionClosed:
                health.warn("reconnecting")
                continue

    async def bybit_liquidations(self, health):
        """Bybit v5 'allLiquidation' topics for the major USDT perps."""
        topics = [f"allLiquidation.{p}" for p in PERPS]
        async for ws in websockets.connect("wss://stream.bybit.com/v5/public/linear", ping_interval=20, open_timeout=15):
            try:
                for i in range(0, len(topics), 10):
                    await ws.send(json.dumps({"op": "subscribe", "args": topics[i:i + 10]}))
                health.ok("subscribed · waiting for events")
                async for raw in ws:
                    msg = json.loads(raw)
                    if not str(msg.get("topic", "")).startswith("allLiquidation"):
                        continue
                    for x in msg.get("data", []):
                        v, px = float(x.get("v") or 0), float(x.get("p") or 0)
                        # Bybit: S == "Buy" means a long position was liquidated
                        self._on_liq("BYBIT", x.get("s", "?"), "LONG" if x.get("S") == "Buy" else "SHORT",
                                     v * px, px, int(x.get("T") or time.time() * 1000), health)
            except websockets.ConnectionClosed:
                health.warn("reconnecting")
                continue

    def liq_summary(self) -> dict:
        now = time.time() * 1000
        out = {}
        for label, win in (("1h", 3600e3), ("4h", 4 * 3600e3), ("24h", 24 * 3600e3)):
            rows = [x for x in self.liqs if now - x["t"] <= win]
            longs = sum(x["usd"] for x in rows if x["side"] == "LONG")
            shorts = sum(x["usd"] for x in rows if x["side"] == "SHORT")
            by_sym: dict = {}
            by_venue: dict = {}
            for x in rows:
                by_sym[x["sym"]] = by_sym.get(x["sym"], 0) + x["usd"]
                by_venue[x.get("venue", "?")] = by_venue.get(x.get("venue", "?"), 0) + x["usd"]
            out[label] = {
                "long": round(longs), "short": round(shorts), "count": len(rows),
                "top": sorted(by_sym.items(), key=lambda kv: -kv[1])[:6],
                "venues": {k: round(v) for k, v in by_venue.items()},
                "largest": max(rows, key=lambda x: x["usd"]) if rows else None,
            }
        out["recent"] = list(self.liqs)[-40:]
        # per-minute buckets for the waterfall chart (last 60 min)
        buckets = {}
        for x in self.liqs:
            if now - x["t"] <= 3600e3:
                m = int((now - x["t"]) // 60000)
                b = buckets.setdefault(m, {"long": 0, "short": 0})
                b["long" if x["side"] == "LONG" else "short"] += x["usd"]
        out["minutes"] = [{"m": m, **buckets.get(m, {"long": 0, "short": 0})} for m in range(59, -1, -1)]
        return out

    # ------------------------------------------------------- derivatives REST
    async def derivatives(self, health):
        async with client(15) as c:
            r = await c.get(f"{FAPI}/fapi/v1/premiumIndex")
            r.raise_for_status()
            for row in r.json():
                s = row.get("symbol")
                if s in PERPS:
                    self.funding[s] = {
                        "rate": finite(float(row["lastFundingRate"]) * 100, 5),
                        "annual": finite(float(row["lastFundingRate"]) * 3 * 365 * 100, 2),
                        "mark": finite(row["markPrice"], 6), "next": row.get("nextFundingTime"),
                    }
            for s in PERPS[:8]:
                try:
                    oi = (await c.get(f"{FAPI}/fapi/v1/openInterest", params={"symbol": s})).json()
                    mark = self.funding.get(s, {}).get("mark") or 0
                    prev = self.oi.get(s, {}).get("usd")
                    usd = float(oi["openInterest"]) * float(mark)
                    self.oi[s] = {"usd": round(usd), "chg": finite((usd / prev - 1) * 100, 2) if prev else None}
                    ls = (await c.get(f"{FAPI}/futures/data/globalLongShortAccountRatio",
                                      params={"symbol": s, "period": "1h", "limit": 24})).json()
                    if isinstance(ls, list) and ls:
                        self.ls_ratio[s] = {
                            "ratio": finite(ls[-1]["longShortRatio"], 3),
                            "long_pct": finite(float(ls[-1]["longAccount"]) * 100, 1),
                            "series": [finite(x["longShortRatio"], 3) for x in ls],
                        }
                except Exception as e:
                    log.debug("oi/ls %s: %s", s, e)
        health.ok(f"{len(self.funding)} perps")
        bus.publish("crypto", self.snapshot(light=True))

    async def sentiment(self, health):
        async with client(15) as c:
            try:
                d = (await c.get("https://api.alternative.me/fng/?limit=30")).json()["data"]
                self.fng = {"value": int(d[0]["value"]), "label": d[0]["value_classification"],
                            "series": [int(x["value"]) for x in d][::-1]}
            except Exception as e:
                log.debug("fng: %s", e)
            try:
                g = (await c.get("https://api.coingecko.com/api/v3/global")).json()["data"]
                self.global_ = {
                    "mcap": g["total_market_cap"]["usd"], "vol": g["total_volume"]["usd"],
                    "mcap_chg": finite(g.get("market_cap_change_percentage_24h_usd"), 2),
                    "btc_dom": finite(g["market_cap_percentage"].get("btc"), 2),
                    "eth_dom": finite(g["market_cap_percentage"].get("eth"), 2),
                }
            except Exception as e:
                log.debug("coingecko: %s", e)
        health.ok("sentiment")

    def snapshot(self, light=False) -> dict:
        out = {"funding": self.funding, "oi": self.oi, "ls": self.ls_ratio, "fng": self.fng, "global": self.global_}
        if not light:
            out["liq"] = self.liq_summary()
        return out


crypto = Crypto()
