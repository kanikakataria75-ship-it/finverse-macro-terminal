"""Cross-asset market data via Yahoo Finance (free, delayed) with batched downloads.

- quotes   : refreshed every QUOTE_INTERVAL for the whole universe in ONE request
- closes   : 2y daily close matrix, the backbone for every analytics engine
- on demand: OHLCV charts, company profiles, US option chains, symbol search
"""
import asyncio
import logging
import math
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

from ..bus import bus
from ..config import DATA_DIR
from ..store import store
from ..universe import BY_SYM, SYMBOLS, meta
from ..util import finite

log = logging.getLogger("finverse.markets")
HIST_PICKLE = DATA_DIR / "closes.pkl"
FUTURES = [s for s in SYMBOLS if s.endswith("=F")]
FRONT_TTL = 6 * 3600

RANGES = {
    "1D": ("1d", "5m"), "5D": ("5d", "15m"), "1M": ("1mo", "60m"), "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"), "1Y": ("1y", "1d"), "5Y": ("5y", "1wk"), "MAX": ("max", "1mo"),
}


def _download(symbols, period, interval) -> pd.DataFrame:
    return yf.download(
        symbols, period=period, interval=interval, group_by="column",
        auto_adjust=False, progress=False, threads=True,
    )


class Markets:
    def __init__(self):
        self.quotes: dict[str, dict] = {}
        self.closes: pd.DataFrame = pd.DataFrame()
        self.live: dict[str, dict] = {}  # real-time overrides (Binance / Angel One)
        self._cache: dict[str, tuple[float, object]] = {}
        self.last_quote_ts = 0.0
        self.fronts: dict[str, str] = {}  # continuous future -> current front contract, e.g. BZ=F -> BZZ26.NYM
        self._fronts_ts = 0.0

    # ------------------------------------------------------------------ boot
    def load_cache(self):
        if HIST_PICKLE.exists():
            try:
                self.closes = pd.read_pickle(HIST_PICKLE)
                log.info("history cache loaded: %s", self.closes.shape)
            except Exception as e:
                log.warning("history cache unreadable: %s", e)
        cached = store.kv_get("quotes")
        if cached:
            self.quotes = cached

    # --------------------------------------------------------------- history
    async def refresh_history(self):
        df = await asyncio.to_thread(_download, SYMBOLS, "2y", "1d")
        closes = df["Close"] if "Close" in df else pd.DataFrame()
        closes = closes.dropna(how="all")
        closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
        closes = closes.groupby(level=0).last()
        if closes.shape[1] < 10:
            raise RuntimeError(f"history download returned only {closes.shape[1]} series")
        self.closes = closes
        closes.to_pickle(HIST_PICKLE)
        log.info("history refreshed: %s", closes.shape)
        return closes.shape

    def series(self, sym: str, n: int | None = None) -> pd.Series:
        if self.closes.empty or sym not in self.closes:
            return pd.Series(dtype=float)
        s = self.closes[sym].dropna()
        # splice the live quote in as "today" so analytics see intraday moves
        q = self.quotes.get(sym)
        if q and q.get("price") is not None and len(s):
            last_day = str(s.index[-1].date())
            if q.get("asof_day") and q["asof_day"] > last_day:
                s = pd.concat([s, pd.Series([q["price"]], index=[pd.Timestamp(q["asof_day"])])])
            else:
                s = s.copy()
                s.iloc[-1] = q["price"]
        return s.tail(n) if n else s

    def returns(self, syms: list[str], n: int = 260) -> pd.DataFrame:
        cols = [s for s in dict.fromkeys(syms) if s in self.closes]  # de-duplicated: repeated columns break .corr()[sym]
        if not cols:
            return pd.DataFrame()
        df = self.closes[cols].tail(n + 5).ffill(limit=3)
        rets = df.pct_change(fill_method=None)
        for s in cols:  # yields: use change in level (percentage points), not % of a %
            if BY_SYM.get(s) and BY_SYM[s].cls == "rate":
                rets[s] = df[s].diff()
        return rets.tail(n)

    # ---------------------------------------------------------------- quotes
    def _resolve_fronts(self):
        """Yahoo's continuous futures (BZ=F) splice contracts together, so on a roll day the
        'previous close' belongs to the expiring contract and the % change is fake. Track the
        actual front contract so the day's move can be measured on one contract."""
        fronts = {}
        for sym in FUTURES:
            try:
                u = yf.Ticker(sym).info.get("underlyingSymbol")
                if u and u != sym:
                    fronts[sym] = u
            except Exception:
                pass
        return fronts

    async def refresh_quotes(self):
        if time.time() - self._fronts_ts > FRONT_TTL:
            fronts = await asyncio.to_thread(self._resolve_fronts)
            self._fronts_ts = time.time()
            if fronts:
                self.fronts = fronts
        df = await asyncio.to_thread(_download, SYMBOLS + list(self.fronts.values()), "5d", "1d")
        if df is None or df.empty:
            raise RuntimeError("empty quote download")
        close = df["Close"]
        changed = {}
        for sym in close.columns:
            if sym not in BY_SYM:
                continue  # a front contract, used below
            s = close[sym].dropna()
            if len(s) < 2:
                continue
            price, prev = float(s.iloc[-1]), float(s.iloc[-2])
            front = self.fronts.get(sym)
            if front in close.columns:
                c = close[front].dropna()
                # same contract trading now -> its own previous close is the honest one
                if len(c) >= 2 and abs(float(c.iloc[-1]) / price - 1) < 0.003:
                    prev = float(c.iloc[-2])
            if sym in self.live and time.time() - self.live[sym]["t"] < 120:
                continue  # a real-time feed owns this symbol
            q = self._make_quote(sym, price, prev, src="YF", asof_day=str(s.index[-1].date()))
            old = self.quotes.get(sym)
            self.quotes[sym] = q
            if not old or old.get("price") != q["price"]:
                changed[sym] = q
        self.last_quote_ts = time.time()
        store.kv_set("quotes", self.quotes)
        if changed:
            bus.publish("quotes", changed)
        return len(self.quotes)

    def _make_quote(self, sym, price, prev, src, asof_day=None) -> dict:
        chg = price - prev if prev else 0.0
        pct = (chg / prev * 100) if prev else 0.0
        inst = BY_SYM.get(sym)
        q = {
            "sym": sym, "code": inst.code if inst else sym, "price": finite(price, 6),
            "prev": finite(prev, 6), "chg": finite(chg, 6), "pct": finite(pct, 4),
            "src": src, "ts": int(time.time() * 1000), "asof_day": asof_day,
        }
        q.update(self.stats(sym, price, prev))
        return q

    def apply_live(self, sym: str, price: float, prev: float, src: str):
        """Real-time tick from a streaming feed."""
        self.live[sym] = {"t": time.time()}
        q = self.quotes.get(sym, {})
        base = self._make_quote(sym, price, prev, src, asof_day=q.get("asof_day"))
        self.quotes[sym] = base
        return base

    # ----------------------------------------------------------------- stats
    def stats(self, sym: str, price: float | None = None, prev: float | None = None) -> dict:
        if self.closes.empty or sym not in self.closes:
            return {}
        s = self.closes[sym].dropna()
        if len(s) < 25:
            return {}
        p = price if price is not None else float(s.iloc[-1])

        def ret(days):
            if len(s) <= days:
                return None
            base = float(s.iloc[-days - 1])
            return finite((p / base - 1) * 100, 3) if base else None

        ytd_base = s[s.index < pd.Timestamp(datetime.now().year, 1, 1)]
        r = s.pct_change().dropna()
        vol = float(r.tail(60).std()) if len(r) > 20 else None
        base = prev if prev else (float(s.iloc[-2]) if len(s) > 2 else None)
        last_ret = (p / base - 1) if base else 0.0
        z = (last_ret / vol) if vol else None
        year = s.tail(252)
        return {
            "w1": ret(5), "m1": ret(21), "m3": ret(63), "y1": ret(252),
            "ytd": finite((p / float(ytd_base.iloc[-1]) - 1) * 100, 3) if len(ytd_base) else None,
            "hi52": finite(year.max()), "lo52": finite(year.min()),
            "vol": finite(vol * math.sqrt(252) * 100, 2) if vol else None,
            "z": finite(z, 2),
            "spark": [finite(v, 5) for v in s.tail(40).tolist()],
        }

    def snapshot(self) -> dict:
        return self.quotes

    # ------------------------------------------------------------- on demand
    def _cached(self, key, ttl):
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        return None

    async def chart(self, sym: str, rng: str = "1Y") -> dict:
        period, interval = RANGES.get(rng, RANGES["1Y"])
        key = f"chart:{sym}:{rng}"
        ttl = 60 if interval.endswith("m") else 900
        if (hit := self._cached(key, ttl)) is not None:
            return hit
        df = await asyncio.to_thread(lambda: yf.Ticker(sym).history(period=period, interval=interval, auto_adjust=False))
        bars = []
        if df is not None and not df.empty:
            intraday = interval.endswith("m")
            for ts, row in df.iterrows():
                if any(pd.isna(row.get(k)) for k in ("Open", "High", "Low", "Close")):
                    continue
                t = int(pd.Timestamp(ts).timestamp()) if intraday else pd.Timestamp(ts).strftime("%Y-%m-%d")
                bars.append({
                    "time": t, "open": finite(row["Open"], 6), "high": finite(row["High"], 6),
                    "low": finite(row["Low"], 6), "close": finite(row["Close"], 6),
                    "volume": finite(row.get("Volume", 0), 0) or 0,
                })
        out = {"sym": sym, "range": rng, "interval": interval, "bars": bars}
        self._cache[key] = (time.time(), out)
        return out

    async def profile(self, sym: str) -> dict:
        key = f"profile:{sym}"
        hit = store.kv_get(key, max_age=6 * 3600)
        if hit:
            return hit
        info = await asyncio.to_thread(lambda: yf.Ticker(sym).info or {})
        fields = [
            "longName", "shortName", "sector", "industry", "country", "website", "fullTimeEmployees",
            "longBusinessSummary", "marketCap", "enterpriseValue", "trailingPE", "forwardPE",
            "priceToBook", "pegRatio", "dividendYield", "dividendRate", "trailingAnnualDividendYield", "currentPrice", "beta", "profitMargins", "operatingMargins",
            "returnOnEquity", "debtToEquity", "totalRevenue", "revenueGrowth", "earningsGrowth",
            "freeCashflow", "currency", "exchange", "quoteType", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
            "targetMeanPrice", "recommendationKey", "numberOfAnalystOpinions", "earningsTimestamp",
            "averageVolume", "sharesOutstanding", "heldPercentInsiders", "heldPercentInstitutions",
        ]
        out = {k: info.get(k) for k in fields if info.get(k) is not None}
        for k, v in list(out.items()):
            if isinstance(v, float):
                out[k] = finite(v, 6)
        store.kv_set(key, out)
        return out

    async def search(self, q: str) -> list[dict]:
        from ..universe import UNIVERSE
        ql = q.lower().strip()
        local = []
        for i in UNIVERSE:
            hay = " ".join([i.sym.lower(), i.code.lower(), i.name.lower(), *i.aliases])
            if ql and ql in hay:
                score = 0 if ql in (i.code.lower(), i.sym.lower()) else (1 if i.name.lower().startswith(ql) else 2)
                local.append((score, {"sym": i.sym, "code": i.code, "name": i.name, "cls": i.cls, "src": "universe"}))
        local.sort(key=lambda x: x[0])
        results = [r for _, r in local[:8]]
        if len(results) < 6 and len(ql) >= 2:
            try:
                remote = await asyncio.wait_for(asyncio.to_thread(lambda: yf.Search(q, max_results=8).quotes), 6)
                seen = {r["sym"] for r in results}
                for r in remote or []:
                    s = r.get("symbol")
                    if s and s not in seen:
                        results.append({
                            "sym": s, "code": s, "name": r.get("longname") or r.get("shortname") or s,
                            "cls": (r.get("quoteType") or "").lower(), "exch": r.get("exchDisp"), "src": "yahoo",
                        })
            except Exception:
                pass
        return results[:12]

    async def quote_one(self, sym: str) -> dict:
        if sym in self.quotes:
            return self.quotes[sym]
        df = await asyncio.to_thread(lambda: yf.Ticker(sym).history(period="5d", interval="1d"))
        s = df["Close"].dropna() if df is not None and not df.empty else pd.Series(dtype=float)
        if len(s) < 2:
            return {"sym": sym, "price": None}
        return self._make_quote(sym, float(s.iloc[-1]), float(s.iloc[-2]), "YF")

    async def options(self, sym: str, expiry: str | None = None) -> dict:
        key = f"opt:{sym}:{expiry}"
        if (hit := self._cached(key, 300)) is not None:
            return hit

        def work():
            t = yf.Ticker(sym)
            exps = list(t.options or [])
            if not exps:
                return {"sym": sym, "expiries": [], "error": "No listed options for this symbol on Yahoo."}
            exp = expiry if expiry in exps else exps[0]
            ch = t.option_chain(exp)
            spot = None
            h = t.history(period="1d")
            if h is not None and not h.empty:
                spot = float(h["Close"].iloc[-1])
            calls, puts = ch.calls.fillna(0), ch.puts.fillna(0)
            strikes = sorted(set(calls["strike"]).union(puts["strike"]))
            if spot:
                strikes = [k for k in strikes if 0.75 * spot <= k <= 1.25 * spot]
            c_oi = calls.set_index("strike")["openInterest"].to_dict()
            p_oi = puts.set_index("strike")["openInterest"].to_dict()
            c_iv = calls.set_index("strike")["impliedVolatility"].to_dict()
            p_iv = puts.set_index("strike")["impliedVolatility"].to_dict()
            # max pain: strike minimising total intrinsic value paid to holders
            all_k = sorted(set(c_oi) | set(p_oi))
            pain = []
            for k in all_k:
                v = sum(max(0, k - s) * oi for s, oi in c_oi.items()) + sum(max(0, s - k) * oi for s, oi in p_oi.items())
                pain.append((v, k))
            max_pain = min(pain)[1] if pain else None
            tot_c_oi, tot_p_oi = float(calls["openInterest"].sum()), float(puts["openInterest"].sum())
            tot_c_v, tot_p_v = float(calls["volume"].sum()), float(puts["volume"].sum())
            atm = min(strikes, key=lambda k: abs(k - spot)) if spot and strikes else None
            return {
                "sym": sym, "expiry": exp, "expiries": exps[:16], "spot": finite(spot),
                "pcr_oi": finite(tot_p_oi / tot_c_oi, 3) if tot_c_oi else None,
                "pcr_vol": finite(tot_p_v / tot_c_v, 3) if tot_c_v else None,
                "max_pain": finite(max_pain), "atm": finite(atm),
                "atm_iv": finite(((c_iv.get(atm, 0) + p_iv.get(atm, 0)) / 2) * 100, 2) if atm else None,
                "call_wall": finite(max(c_oi, key=c_oi.get)) if c_oi else None,
                "put_wall": finite(max(p_oi, key=p_oi.get)) if p_oi else None,
                "strikes": [
                    {"k": finite(k), "c_oi": int(c_oi.get(k, 0)), "p_oi": int(p_oi.get(k, 0)),
                     "c_iv": finite(c_iv.get(k, 0) * 100, 2), "p_iv": finite(p_iv.get(k, 0) * 100, 2)}
                    for k in strikes
                ],
            }

        out = await asyncio.to_thread(work)
        self._cache[key] = (time.time(), out)
        return out


markets = Markets()


def safe_corr(a: np.ndarray, b: np.ndarray) -> float | None:
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 15:
        return None
    return float(np.corrcoef(a[m], b[m])[0, 1])


__all__ = ["markets", "Markets", "meta", "safe_corr"]
