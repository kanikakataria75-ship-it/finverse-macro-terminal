"""Engine: supervises every data feed and analytics loop as self-healing asyncio tasks.

One process, one command. Each feed reports into a Health registry that the UI shows
live (boot sequence, feed-status strip) so the operator always knows what is real-time,
delayed, cached or down.
"""
import asyncio
import logging
import random
import time
from datetime import date

from . import voice as veda
from .analytics import quant
from .analytics.alerts import alerts
from .bus import bus
from .config import GDELT_INTERVAL, HISTORY_INTERVAL, NEWS_INTERVAL, QUOTE_INTERVAL, RHETORIC_INTERVAL, SIGMA_ALERT
from .providers import angel
from .providers.crypto import crypto
from .providers.geo import geo
from .providers.macro import macro
from .providers.markets import HIST_PICKLE, markets
from .providers.news import news
from .providers.rhetoric import rhetoric
from .store import store
from .universe import meta

log = logging.getLogger("finverse.engine")


class Health:
    def __init__(self, key, label, source, cadence):
        self.key, self.label, self.source, self.cadence = key, label, source, cadence
        self.status, self.msg = "booting", "starting"
        self.last_ok = self.last_err = None
        self.runs = self.errors = 0

    def ok(self, msg=""):
        self.status, self.msg, self.last_ok = "ok", msg, time.time()

    def warn(self, msg=""):
        self.status, self.msg = "warn", msg

    def idle(self, msg=""):
        self.status, self.msg = "idle", msg

    def fail(self, msg=""):
        self.status, self.msg, self.last_err = "error", msg[:140], time.time()
        self.errors += 1

    def as_dict(self):
        return {"key": self.key, "label": self.label, "source": self.source, "cadence": self.cadence,
                "status": self.status, "msg": self.msg, "last_ok": self.last_ok, "errors": self.errors}


class Engine:
    def __init__(self):
        self.health: dict[str, Health] = {}
        self.tasks: list[asyncio.Task] = []
        self.started = time.time()
        self.analytics: dict = store.kv_get("analytics", {})
        self._sigma_seen: dict = {}
        self._breaks_seen: set = set()
        self._corr_ts = 0.0
        self._last_regime = self.analytics.get("regime", {}).get("regime")

    def h(self, key, label, source, cadence) -> Health:
        self.health[key] = Health(key, label, source, cadence)
        return self.health[key]

    # ------------------------------------------------------------ supervisors
    def every(self, key, label, source, seconds, fn, delay=0.0, jitter=0.1):
        hl = self.h(key, label, source, f"{seconds}s" if seconds < 120 else f"{seconds // 60}m")

        async def loop():
            await asyncio.sleep(delay)
            backoff = 5
            while True:
                hl.runs += 1
                try:
                    nxt = await fn(hl)
                    backoff = 5
                    wait = nxt if isinstance(nxt, (int, float)) else seconds * (1 + random.uniform(-jitter, jitter))
                except Exception as e:
                    log.warning("%s failed: %s: %s", key, type(e).__name__, e)
                    hl.fail(f"{type(e).__name__}: {e}".rstrip(": "))
                    wait = min(backoff, seconds)
                    backoff = min(backoff * 2, 600)
                await asyncio.sleep(wait)

        self.tasks.append(asyncio.create_task(loop(), name=key))

    def forever(self, key, label, source, fn):
        hl = self.h(key, label, source, "stream")

        async def loop():
            backoff = 3
            while True:
                try:
                    await fn(hl)
                    backoff = 3
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("%s stream error: %s: %s", key, type(e).__name__, e)
                    hl.fail(f"{type(e).__name__}: {e}".rstrip(": "))
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 120)

        self.tasks.append(asyncio.create_task(loop(), name=key))

    # ------------------------------------------------------------------ jobs
    async def _history(self, hl):
        shape = await markets.refresh_history()
        hl.ok(f"{shape[1]} series × {shape[0]} days")

    async def _quotes(self, hl):
        n = await markets.refresh_quotes()
        hl.ok(f"{n} instruments (delayed)")
        alerts.check_quotes()

    async def _analytics(self, hl):
        if markets.closes.empty:
            hl.warn("waiting for history")
            return
        reg = await asyncio.to_thread(quant.regime)
        pul = await asyncio.to_thread(quant.pulse)
        tx = await asyncio.to_thread(quant.transmission)
        an = quant.anomalies()
        self.analytics.update({"regime": reg, "pulse": pul, "transmission": tx, "anomalies": an,
                               "updated": int(time.time() * 1000)})
        if time.time() - self._corr_ts > 600 or "correlation" not in self.analytics:
            self._corr_ts = time.time()
            self.analytics["correlation"] = await asyncio.to_thread(quant.correlation)
            today = date.today().isoformat()
            for b in self.analytics["correlation"].get("breaks", [])[:5]:
                key = f"{today}:{b['a']}:{b['b']}"
                if key not in self._breaks_seen and not self._seen_today(f"{b['a_code']}/{b['b_code']}"):
                    self._breaks_seen.add(key)
                    bus.emit("DIVERGENCE", f"Correlation break {b['a_code']}/{b['b_code']}: 60d {b['short']:+.2f} vs "
                             f"250d {b['long']:+.2f} (Δ {b['delta']:+.2f})", tier="SIGNIFICANT", asset=b["a_code"])
        today = date.today().isoformat()
        for a in an:
            if abs(a["z"]) >= SIGMA_ALERT and self._sigma_seen.get(a["sym"]) != today                     and not self._seen_today(f"{a['code']} {a['pct']:+.2f}%"[:len(a['code']) + 1]):
                self._sigma_seen[a["sym"]] = today
                bus.emit("SIGMA", f"{a['code']} {a['pct']:+.2f}% — a {a['z']:+.1f}σ move vs 60-day volatility",
                         tier="HEAVY" if abs(a["z"]) >= 3.5 else "SIGNIFICANT", asset=a["code"], z=a["z"])
        if reg.get("ready") and self._last_regime and reg["regime"] != self._last_regime:
            bus.emit("REGIME", f"Macro regime shift: {self._last_regime} → {reg['regime']} ({reg['description']})",
                     tier="CRITICAL", asset="MACRO")
        if reg.get("ready"):
            self._last_regime = reg["regime"]
        store.kv_set("analytics", self.analytics)
        bus.publish("analytics", self.analytics)
        hl.ok(f"{reg.get('regime', '—')} · pulse {pul.get('global', {}).get('value', '—')}")

    @staticmethod
    def _seen_today(fragment: str) -> bool:
        day_start = time.mktime(date.today().timetuple()) * 1000
        return any(fragment in e.get("message", "") and e["ts"] >= day_start for e in bus.intel)

    async def _heartbeat(self, hl):
        bus.publish("health", self.health_snapshot())
        hl.ok(f"{bus.clients} terminal(s) connected")

    async def _prune(self, hl):
        store.intel_prune()
        hl.ok("pruned")

    # ------------------------------------------------------------------ boot
    async def start(self):
        markets.load_cache()
        bus.load_history()
        history_stale = not HIST_PICKLE.exists() or time.time() - HIST_PICKLE.stat().st_mtime > HISTORY_INTERVAL
        self.every("history", "Market history (2y)", "Yahoo Finance", HISTORY_INTERVAL, self._history,
                   delay=0 if history_stale else HISTORY_INTERVAL)
        if not history_stale:
            self.health["history"].ok("cache warm")
        self.every("quotes", "Cross-asset quotes", "Yahoo Finance", QUOTE_INTERVAL, self._quotes, delay=1)
        self.forever("crypto_spot", "Crypto spot ticks", "Binance WS", crypto.spot_stream)
        self.forever("liquidations", "Liquidations · Binance", "Binance Futures WS", crypto.liquidation_stream)
        self.forever("liq_okx", "Liquidations · OKX", "OKX public WS", crypto.okx_liquidations)
        self.forever("liq_bybit", "Liquidations · Bybit", "Bybit v5 public WS", crypto.bybit_liquidations)
        self.every("derivs", "Funding · OI · long/short", "Binance Futures", 60, crypto.derivatives, delay=3)
        self.every("crypto_sent", "Crypto sentiment", "alternative.me · CoinGecko", 900, crypto.sentiment, delay=4)
        self.every("curve", "US Treasury curve", "US Treasury", 3 * 3600, macro.refresh_curve, delay=2)
        self.every("fed", "Fed funds · SOFR", "NY Fed", 3 * 3600, macro.refresh_fed, delay=2)
        self.every("bls", "US CPI · payrolls · jobs", "BLS", 12 * 3600, macro.refresh_bls, delay=5)
        self.every("news", "News wire (18 feeds)", "RSS", NEWS_INTERVAL, news.poll, delay=2)
        self.every("trump", "Truth Social", "trumpstruth.org mirror", RHETORIC_INTERVAL, rhetoric.poll_trump, delay=6)
        self.every("banks", "Central banks", "Fed · RBI · ECB", 600, rhetoric.poll_banks, delay=8)
        self.every("hazards", "Quakes · natural events", "USGS · NASA EONET", 900, geo.refresh_hazards, delay=5)
        self.every("conflict", "Conflict intensity", "GDELT / Google News", GDELT_INTERVAL, geo.sweep_conflict,
                   delay=20 if not geo.conflict else 600)
        if geo.conflict:
            self.health["conflict"].ok(f"{len(geo.conflict)} countries (cached)")
        self.every("analytics", "Quant engines", "Finverse", 60, self._analytics, delay=12)
        self.forever("angel", "NSE real-time", "Angel One SmartAPI", angel.run)
        self.every("voice", "VEDA neural voice", "Microsoft neural TTS (edge-tts)", 24 * 3600, veda.warmup, delay=15)
        self.every("heartbeat", "Gateway", "WebSocket", 15, self._heartbeat, delay=1)
        self.every("prune", "Housekeeping", "SQLite", 86400, self._prune, delay=60)
        bus.emit("SYSTEM", "Finverse engine online — all feeds supervised.", tier="INFO", asset="CORE")

    async def stop(self):
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    def health_snapshot(self) -> dict:
        return {"feeds": [h.as_dict() for h in self.health.values() if h.key not in ("heartbeat", "prune")],
                "uptime": int(time.time() - self.started), "clients": bus.clients, "tape_speed": bus.tape_speed()}


engine = Engine()
