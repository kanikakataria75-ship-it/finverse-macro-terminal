"""Quant engines. Everything here is computed from real market history; nothing is simulated.

regime()        Growth x Inflation compass (cross-asset momentum z-scores) with a 90d trail
pulse()         Fear/Greed composites for Global and India (percentile-ranked components)
anomalies()     Sigma moves: today's return vs 60d realised volatility
correlation()   Rolling correlation matrix + correlation-break detector (60d vs 250d)
transmission()  India Transmission Model: multivariate betas of Indian sectors on global drivers,
                today's attribution and the implied India open from last night's global moves
scenario()      What-if: shock the drivers, propagate through the betas
event_study()   "When X moved like this, what did Y do next?" with bootstrap CIs
portfolio_risk()  VaR, vol, beta, drawdown, stress tests for user holdings
"""
import time

import numpy as np
import pandas as pd
import yfinance as yf

from ..providers.markets import markets
from ..universe import BY_SYM, DRIVERS, INDIA_TARGETS, meta
from ..util import finite

RNG = np.random.default_rng(11)


def _closes(cols) -> pd.DataFrame:
    df = markets.closes
    cols = [c for c in dict.fromkeys(cols) if c in df]
    out = df[cols].ffill(limit=3).copy()
    # splice live prices in as today's value
    for c in cols:
        q = markets.quotes.get(c)
        if q and q.get("price") is not None and len(out[c].dropna()):
            last_idx = out[c].last_valid_index()
            out.loc[last_idx, c] = q["price"]
    return out


def _is_rate(sym):
    return BY_SYM.get(sym) is not None and BY_SYM[sym].cls == "rate"


def _mom(s: pd.Series, n: int, rate=False) -> pd.Series:
    return (s - s.shift(n)) if rate else (s / s.shift(n) - 1)


def _z_last(s: pd.Series, lookback=500):
    s = s.dropna().tail(lookback)
    if len(s) < 40 or s.std() == 0:
        return None
    return float((s.iloc[-1] - s.mean()) / s.std())


def _pctile(s: pd.Series, lookback=252):
    s = s.dropna().tail(lookback)
    if len(s) < 30:
        return None
    return float((s < s.iloc[-1]).mean() * 100)


# ============================================================== REGIME
GROWTH = [("^GSPC", None, "US equities"), ("HG=F", None, "Copper"), ("EEM", None, "EM equities"),
          ("XLI", "XLU", "Cyclicals vs defensives")]
INFLATION = [("BZ=F", None, "Brent"), ("TIP", "IEF", "Breakeven proxy (TIP/IEF)"), ("GC=F", None, "Gold"),
             ("^TNX", None, "US 10Y yield")]
QUADRANTS = {
    (True, False): ("GOLDILOCKS", "Growth up, inflation cooling", "Equities and duration both work; USD soft; volatility sold."),
    (True, True): ("REFLATION", "Growth up, inflation up", "Cyclicals, commodities, value, EM; bonds under pressure."),
    (False, True): ("STAGFLATION", "Growth down, inflation up", "Commodities and gold; cash; equities and bonds struggle."),
    (False, False): ("DEFLATION / RISK-OFF", "Growth down, inflation down", "Long duration, USD and JPY; defensives over cyclicals."),
}


def _axis(defs, df, n=60):
    comps, series = [], []
    for a, b, label in defs:
        if a not in df or (b and b not in df):
            continue
        base = df[a] / df[b] if b else df[a]
        m = _mom(base, n, rate=_is_rate(a) and not b)
        mu, sd = m.tail(500).mean(), m.tail(500).std()
        z = (m - mu) / sd if sd else m * 0
        series.append(z)
        comps.append({"label": label, "z": finite(z.dropna().iloc[-1], 2) if len(z.dropna()) else None})
    if not series:
        return None, comps
    return pd.concat(series, axis=1).mean(axis=1), comps


def regime() -> dict:
    need = {x for d in (GROWTH, INFLATION) for a, b, _ in d for x in (a, b) if x}
    df = _closes(list(need) + ["HYG", "IEF", "^VIX", "SPY", "TLT"])
    if df.empty:
        return {"ready": False}
    g, gc = _axis(GROWTH, df)
    i, ic = _axis(INFLATION, df)
    if g is None or i is None:
        return {"ready": False}
    g_now, i_now = float(g.dropna().iloc[-1]), float(i.dropna().iloc[-1])
    name, desc, play = QUADRANTS[(g_now >= 0, i_now >= 0)]
    trail = []
    gi = pd.concat([g, i], axis=1).dropna().tail(120)
    for idx in range(0, len(gi), 5):
        row = gi.iloc[idx]
        trail.append({"d": str(gi.index[idx].date()), "g": finite(row.iloc[0], 3), "i": finite(row.iloc[1], 3)})
    trail.append({"d": str(gi.index[-1].date()), "g": finite(g_now, 3), "i": finite(i_now, 3)})
    # risk appetite
    ra_parts = []
    if "HYG" in df and "IEF" in df:
        ra_parts.append(_z_last(_mom(df["HYG"] / df["IEF"], 20)))
    if "SPY" in df and "TLT" in df:
        ra_parts.append(_z_last(_mom(df["SPY"], 20) - _mom(df["TLT"], 20)))
    if "^VIX" in df:
        z = _z_last(df["^VIX"])
        ra_parts.append(-z if z is not None else None)
    ra = [x for x in ra_parts if x is not None]
    risk = float(np.mean(ra)) if ra else 0.0
    return {
        "ready": True, "growth": finite(g_now, 3), "inflation": finite(i_now, 3), "regime": name,
        "description": desc, "playbook": play, "confidence": finite(min(1.0, (g_now ** 2 + i_now ** 2) ** 0.5 / 1.5), 2),
        "risk_appetite": finite(risk, 2), "risk_label": "RISK-ON" if risk > 0.35 else ("RISK-OFF" if risk < -0.35 else "BALANCED"),
        "components": {"growth": gc, "inflation": ic}, "trail": trail,
    }


# =============================================================== PULSE
def _label(v):
    if v is None:
        return "—"
    return ("EXTREME FEAR" if v < 22 else "FEAR" if v < 42 else "NEUTRAL" if v <= 58 else "GREED" if v <= 78 else "EXTREME GREED")


def _composite(parts: list[tuple[str, pd.Series, bool]]) -> dict:
    comps, hist = [], []
    for label, s, invert in parts:
        s = s.dropna()
        if len(s) < 80:
            continue
        rank = s.rolling(252, min_periods=60).apply(lambda w: (w[:-1] < w[-1]).mean() * 100, raw=True)
        if invert:
            rank = 100 - rank
        hist.append(rank)
        comps.append({"label": label, "value": finite(rank.dropna().iloc[-1], 1) if len(rank.dropna()) else None})
    if not hist:
        return {"value": None, "label": "—", "components": [], "series": []}
    h = pd.concat(hist, axis=1).mean(axis=1).dropna()
    v = float(h.iloc[-1])
    return {"value": round(v, 1), "label": _label(v), "components": comps,
            "series": [finite(x, 1) for x in h.tail(90).tolist()],
            "w1": finite(h.iloc[-6], 1) if len(h) > 6 else None, "m1": finite(h.iloc[-22], 1) if len(h) > 22 else None}


def pulse() -> dict:
    df = _closes(["^GSPC", "^VIX", "SPY", "TLT", "HYG", "IEF", "RSP", "^NSEI", "^INDIAVIX", "INR=X", "^NSEBANK"])
    out = {}
    if {"^GSPC", "^VIX", "SPY", "TLT"} <= set(df):
        spx = df["^GSPC"].dropna()
        parts = [
            ("Momentum · S&P vs 125d avg", spx / spx.rolling(125).mean() - 1, False),
            ("Volatility · VIX vs 50d avg", df["^VIX"] / df["^VIX"].rolling(50).mean(), True),
            ("Safe-haven demand · stocks vs bonds 20d", _mom(df["SPY"], 20) - _mom(df["TLT"], 20), False),
            ("Strength · distance from 52w high", spx / spx.rolling(252, min_periods=60).max(), False),
        ]
        if "HYG" in df and "IEF" in df:
            parts.append(("Junk-bond demand · HYG/IEF 20d", _mom(df["HYG"] / df["IEF"], 20), False))
        if "RSP" in df:
            parts.append(("Breadth · equal-weight vs cap-weight", _mom(df["RSP"] / df["SPY"], 20), False))
        out["global"] = _composite(parts)
    if {"^NSEI", "^INDIAVIX"} <= set(df):
        n = df["^NSEI"].dropna()
        parts = [
            ("Momentum · Nifty vs 125d avg", n / n.rolling(125).mean() - 1, False),
            ("Volatility · India VIX vs 50d avg", df["^INDIAVIX"] / df["^INDIAVIX"].rolling(50).mean(), True),
            ("Strength · distance from 52w high", n / n.rolling(252, min_periods=60).max(), False),
        ]
        if "INR=X" in df:
            parts.append(("Rupee · USD/INR 20d change", _mom(df["INR=X"], 20), True))
        if "^NSEBANK" in df:
            parts.append(("Leadership · Bank Nifty vs Nifty 20d", _mom(df["^NSEBANK"] / df["^NSEI"], 20), False))
        out["india"] = _composite(parts)
    return out


# =========================================================== ANOMALIES
def anomalies(min_z=1.5) -> list[dict]:
    rows = []
    for sym, q in markets.quotes.items():
        z = q.get("z")
        if z is not None and abs(z) >= min_z:
            m = meta(sym)
            rows.append({"sym": sym, "code": m["code"], "name": m["name"], "cls": m["cls"],
                         "pct": q.get("pct"), "z": z, "price": q.get("price")})
    rows.sort(key=lambda r: -abs(r["z"]))
    return rows[:40]


# ========================================================= CORRELATION
CORR_SET = ["^GSPC", "^IXIC", "^NSEI", "^N225", "^GDAXI", "^HSI", "GC=F", "BZ=F", "HG=F", "DX-Y.NYB",
            "^TNX", "INR=X", "JPY=X", "EURUSD=X", "BTC-USD", "^VIX", "TLT"]


def correlation(syms=None, short=60, long=250) -> dict:
    syms = [s for s in (syms or CORR_SET) if s in markets.closes]
    rets = markets.returns(syms, n=long)
    if rets.empty:
        return {"ready": False}
    c_s = rets.tail(short).corr(min_periods=20)
    c_l = rets.corr(min_periods=60)
    breaks = []
    for a_i, a in enumerate(syms):
        for b in syms[a_i + 1:]:
            s, lg = c_s.loc[a, b], c_l.loc[a, b]
            if pd.notna(s) and pd.notna(lg) and abs(s - lg) >= 0.45:
                breaks.append({"a": a, "b": b, "a_code": meta(a)["code"], "b_code": meta(b)["code"],
                               "short": finite(s, 2), "long": finite(lg, 2), "delta": finite(s - lg, 2)})
    breaks.sort(key=lambda x: -abs(x["delta"]))

    def mat(c):
        return [[finite(c.loc[a, b], 2) for b in syms] for a in syms]

    return {"ready": True, "syms": syms, "codes": [meta(s)["code"] for s in syms],
            "short": mat(c_s), "long": mat(c_l), "window": [short, long], "breaks": breaks[:12]}


# ======================================================== TRANSMISSION
LAGGED = {"^IXIC", "^TNX", "DX-Y.NYB", "BZ=F", "GC=F"}  # settle after Indian close -> affect next session
_TX_CACHE: dict = {}


def _fit(y: pd.Series, X: pd.DataFrame):
    d = pd.concat([y, X], axis=1).dropna()
    if len(d) < 80:
        return None
    Y = d.iloc[:, 0].to_numpy()
    Xm = np.column_stack([np.ones(len(d)), d.iloc[:, 1:].to_numpy()])
    coef, *_ = np.linalg.lstsq(Xm, Y, rcond=None)
    resid = Y - Xm @ coef
    ss_tot = ((Y - Y.mean()) ** 2).sum()
    r2 = 1 - (resid ** 2).sum() / ss_tot if ss_tot else 0
    sigma2 = (resid ** 2).sum() / max(1, len(Y) - Xm.shape[1])
    try:
        se = np.sqrt(np.diag(sigma2 * np.linalg.inv(Xm.T @ Xm)))
    except np.linalg.LinAlgError:
        se = np.full(len(coef), np.nan)
    return coef, se, float(r2), int(len(d)), float(np.std(resid))


def _driver_frame(n=300) -> pd.DataFrame:
    X = markets.returns(DRIVERS, n=n + 2)
    for d in DRIVERS:
        if d in X and d in LAGGED:
            X[d] = X[d].shift(1)
    return X


def betas_for(sym: str, n=250):
    key = (sym, int(time.time() // 3600))
    if key in _TX_CACHE:
        return _TX_CACHE[key]
    X = _driver_frame(n)
    y = markets.returns([sym], n=n + 2)
    if y.empty or X.empty:
        return None
    fit = _fit(y[sym].rename("y"), X[[d for d in DRIVERS if d in X]])
    _TX_CACHE[key] = fit
    return fit


def transmission() -> dict:
    X = _driver_frame()
    drivers = [d for d in DRIVERS if d in X]
    # driver moves feeding the NEXT Indian session (lagged ones use their latest completed move)
    latest = {}
    for d in drivers:  # each driver's own last completed session (no weekend forward-fill)
        s = markets.series(d).dropna()
        if len(s) < 2:
            latest[d] = 0.0
        else:
            latest[d] = float(s.iloc[-1] - s.iloc[-2]) if _is_rate(d) else float(s.iloc[-1] / s.iloc[-2] - 1)
    targets = []
    for t in INDIA_TARGETS:
        fit = betas_for(t)
        if not fit:
            continue
        coef, se, r2, n, resid_sd = fit
        contrib = {d: coef[k + 1] * latest[d] for k, d in enumerate(drivers)}
        implied = sum(contrib.values())
        q = markets.quotes.get(t, {})
        actual = (q.get("pct") or 0) / 100
        targets.append({
            "sym": t, "code": meta(t)["code"], "name": meta(t)["name"], "r2": finite(r2, 3), "n": n,
            "betas": {d: {"b": finite(coef[k + 1], 4), "t": finite(coef[k + 1] / se[k + 1], 2) if se[k + 1] else None}
                      for k, d in enumerate(drivers)},
            "implied_pct": finite(implied * 100, 3), "actual_pct": finite(actual * 100, 3),
            "residual_pct": finite((actual - implied) * 100, 3),
            "contrib_pct": {d: finite(v * 100, 3) for d, v in contrib.items()},
            "implied_band": finite(resid_sd * 100, 3),
        })
    return {
        "drivers": [{"sym": d, "code": meta(d)["code"], "name": meta(d)["name"], "lagged": d in LAGGED,
                     "move": finite(latest[d] * (1 if _is_rate(d) else 100), 3),
                     "unit": "pp" if _is_rate(d) else "%"} for d in drivers],
        "targets": targets,
        "note": "OLS on 250 daily returns. US-settled drivers are lagged one session (they close after India). "
                "'Implied' = model-expected move from the latest driver moves; residual = idiosyncratic.",
    }


def scenario(shocks: dict) -> dict:
    """shocks: {driver_sym: value} — % for prices, basis points for ^TNX."""
    drivers = [d for d in DRIVERS if d in markets.closes]
    vec = {}
    for d in drivers:
        v = float(shocks.get(d, 0) or 0)
        vec[d] = v / 100.0 if not _is_rate(d) else v / 100.0  # % -> fraction ; bp -> percentage points
    out = []
    for t in INDIA_TARGETS + [s for s in shocks.get("_extra", []) if s in markets.closes]:
        fit = betas_for(t)
        if not fit:
            continue
        coef, se, r2, n, _ = fit
        impact = sum(coef[k + 1] * vec[d] for k, d in enumerate(drivers))
        out.append({"sym": t, "code": meta(t)["code"], "name": meta(t)["name"],
                    "impact_pct": finite(impact * 100, 2), "r2": finite(r2, 2)})
    out.sort(key=lambda r: r["impact_pct"] or 0)
    return {"shocks": {d: shocks.get(d, 0) for d in drivers}, "impacts": out}


# ========================================================= EVENT STUDY
_HIST_CACHE: dict = {}


def _long_history(sym: str) -> pd.Series:
    hit = _HIST_CACHE.get(sym)
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    df = yf.Ticker(sym).history(period="15y", interval="1d", auto_adjust=False)
    s = df["Close"].dropna() if df is not None and not df.empty else pd.Series(dtype=float)
    if len(s):
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        s = s.groupby(level=0).last()
    _HIST_CACHE[sym] = (time.time(), s)
    return s


def event_study(trigger: str, op: str, threshold: float, target: str,
                horizons=(1, 5, 20), decluster: int = 5) -> dict:
    trg = _long_history(trigger)
    tgt = _long_history(target)
    if len(trg) < 300 or len(tgt) < 300:
        return {"error": "Not enough history for one of the symbols."}
    trg_ret = (trg.diff() if _is_rate(trigger) else trg.pct_change() * 100).dropna()
    hits = trg_ret[trg_ret >= threshold] if op == "gt" else trg_ret[trg_ret <= threshold]
    events, last_pos = [], -10 ** 9
    tgt_idx = tgt.index
    for d, v in hits.items():
        pos = tgt_idx.searchsorted(d, side="right") - 1  # target close on/before the event day
        if pos < 0 or pos - last_pos < decluster:
            continue
        last_pos = pos
        events.append((d, float(v), pos))
    if len(events) < 5:
        return {"error": f"Only {len(events)} qualifying events — loosen the threshold.", "n": len(events)}
    arr = tgt.to_numpy()
    H = max(horizons)
    stats = []
    for h in horizons:
        fwd = np.array([(arr[p + h] / arr[p] - 1) * 100 for _, _, p in events if p + h < len(arr)])
        uncond = (arr[h:] / arr[:-h] - 1) * 100
        base = float(np.mean(uncond))
        abn = fwd - base
        idx = RNG.integers(0, len(abn), size=(3000, len(abn)))
        boots = abn[idx].mean(axis=1)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        stats.append({
            "h": h, "n": int(len(fwd)), "mean": finite(fwd.mean(), 3), "median": finite(np.median(fwd), 3),
            "baseline": finite(base, 3), "abnormal": finite(abn.mean(), 3), "ci": [finite(lo, 3), finite(hi, 3)],
            "hit_rate": finite((fwd > 0).mean() * 100, 1), "base_hit": finite((uncond > 0).mean() * 100, 1),
            "significant": bool(lo > 0 or hi < 0), "worst": finite(fwd.min(), 2), "best": finite(fwd.max(), 2),
        })
    # average cumulative path from -5 to +H
    path = []
    for k in range(-5, H + 1):
        vals = [(arr[p + k] / arr[p] - 1) * 100 for _, _, p in events if 0 <= p + k < len(arr)]
        path.append({"k": k, "mean": finite(np.mean(vals), 3) if vals else None,
                     "p25": finite(np.percentile(vals, 25), 3) if vals else None,
                     "p75": finite(np.percentile(vals, 75), 3) if vals else None})
    mid = horizons[len(horizons) // 2]
    dist = [finite((arr[p + mid] / arr[p] - 1) * 100, 3) for _, _, p in events if p + mid < len(arr)]
    recent = [{"date": str(d.date()), "trigger": finite(v, 2),
               **{f"h{h}": finite((arr[p + h] / arr[p] - 1) * 100, 2) if p + h < len(arr) else None for h in horizons}}
              for d, v, p in events[-15:]][::-1]
    return {
        "trigger": trigger, "target": target, "op": op, "threshold": threshold,
        "trigger_code": meta(trigger)["code"], "target_code": meta(target)["code"],
        "unit": "pp" if _is_rate(trigger) else "%", "n_events": len(events),
        "span": [str(tgt.index[0].date()), str(tgt.index[-1].date())], "stats": stats, "path": path,
        "dist_h": mid, "dist": dist, "recent": recent,
        "method": f"Declustered ({decluster}d), abnormal = forward return − unconditional mean, 95% bootstrap CI.",
    }


# ======================================================= PORTFOLIO RISK
def portfolio_risk(holdings: list[dict]) -> dict:
    if not holdings:
        return {"empty": True}
    usdinr = (markets.quotes.get("INR=X") or {}).get("price") or 83.0
    rows, syms = [], []
    for h in holdings:
        sym = h["symbol"]
        q = markets.quotes.get(sym) or {}
        price = q.get("price")
        if price is None:
            continue
        m = meta(sym)
        ccy = m.get("ccy") or ("INR" if sym.endswith((".NS", ".BO")) else "USD")
        fx = 1.0 if ccy == "INR" else usdinr
        value = price * h["qty"] * fx
        cost = h["cost"] * h["qty"] * fx
        day = (q.get("chg") or 0) * h["qty"] * fx
        rows.append({**h, "code": m["code"], "name": m["name"], "price": price, "ccy": ccy, "value_inr": round(value, 2),
                     "pnl_inr": round(value - cost, 2), "pnl_pct": finite((value / cost - 1) * 100, 2) if cost else None,
                     "day_inr": round(day, 2), "day_pct": q.get("pct")})
        syms.append(sym)
    total = sum(r["value_inr"] for r in rows) or 1
    for r in rows:
        r["weight"] = round(r["value_inr"] / total * 100, 2)
    out = {"rows": rows, "total_inr": round(total, 2), "pnl_inr": round(sum(r["pnl_inr"] for r in rows), 2),
           "day_inr": round(sum(r["day_inr"] for r in rows), 2), "usdinr": usdinr}
    rets = markets.returns(list(dict.fromkeys(syms + ["^NSEI", "^GSPC"])), n=250)
    held = [s for s in syms if s in rets]
    if held:
        w = np.array([next(r["weight"] for r in rows if r["symbol"] == s) / 100 for s in held])
        R = rets[held].fillna(0)
        port = R.to_numpy() @ w
        ps = pd.Series(port, index=R.index)
        vol = float(np.std(port) * np.sqrt(252) * 100)
        var95 = float(-np.percentile(port, 5) * total)
        cvar = float(-port[port <= np.percentile(port, 5)].mean() * total) if len(port) > 20 else None
        curve = (1 + ps).cumprod()
        mdd = float((curve / curve.cummax() - 1).min() * 100)

        def beta(bench):
            if bench not in rets:
                return None
            b = rets[bench].fillna(0).to_numpy()
            return finite(np.cov(port, b)[0, 1] / np.var(b), 2) if np.var(b) else None

        stress = scenario_for_portfolio(rows)
        out.update({"vol": finite(vol, 2), "var95_1d": round(var95, 0), "cvar95_1d": round(cvar, 0) if cvar else None,
                    "max_dd_1y": finite(mdd, 2), "beta_nifty": beta("^NSEI"), "beta_spx": beta("^GSPC"),
                    "curve": [finite(x, 4) for x in curve.tail(250).tolist()], "stress": stress})
    return out


STRESS = {
    "Oil shock (+25% Brent)": {"BZ=F": 25},
    "Taper tantrum (+75bp US10Y, +3% DXY)": {"^TNX": 75, "DX-Y.NYB": 3},
    "Rupee crisis (+5% USD/INR)": {"INR=X": 5},
    "Tech crash (−12% Nasdaq)": {"^IXIC": -12},
    "Risk-on melt-up (+6% Nasdaq, −2% DXY)": {"^IXIC": 6, "DX-Y.NYB": -2},
}


def scenario_for_portfolio(rows) -> list[dict]:
    out = []
    drivers = [d for d in DRIVERS if d in markets.closes]
    for name, shocks in STRESS.items():
        pnl = 0.0
        for r in rows:
            fit = betas_for(r["symbol"])
            if not fit:
                continue
            coef = fit[0]
            impact = sum(coef[k + 1] * (shocks.get(d, 0) / 100.0) for k, d in enumerate(drivers))
            pnl += impact * r["value_inr"]
        out.append({"name": name, "pnl_inr": round(pnl, 0)})
    return out
