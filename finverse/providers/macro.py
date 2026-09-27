"""Official macro data from keyless public APIs.

- US Treasury  : daily par yield curve (home.treasury.gov CSV)
- NY Fed       : EFFR + FOMC target range, SOFR
- BLS API v1   : CPI, core CPI, payrolls, unemployment, wages (25 req/day -> cached 12h)
- Calendar     : confirmed FOMC dates + rule-based release estimates (flagged EST)
"""
import asyncio
import csv
import io
import logging
from datetime import date, datetime, timedelta

from ..bus import bus
from ..store import store
from ..util import client, finite

log = logging.getLogger("finverse.macro")

TENORS = [("1 Mo", "1M", 1 / 12), ("3 Mo", "3M", 0.25), ("6 Mo", "6M", 0.5), ("1 Yr", "1Y", 1),
          ("2 Yr", "2Y", 2), ("3 Yr", "3Y", 3), ("5 Yr", "5Y", 5), ("7 Yr", "7Y", 7),
          ("10 Yr", "10Y", 10), ("20 Yr", "20Y", 20), ("30 Yr", "30Y", 30)]

BLS_SERIES = {
    "CUUR0000SA0": "cpi", "CUUR0000SA0L1E": "core_cpi", "CES0000000001": "payrolls",
    "LNS14000000": "unemployment", "CES0500000003": "wages",
}

# Federal Reserve published 2026 FOMC schedule (decision on day 2)
FOMC_2026 = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
             "2026-09-16", "2026-10-28", "2026-12-09"]


class Macro:
    def __init__(self):
        self.curve: dict = store.kv_get("macro:curve", {})
        self.fed: dict = store.kv_get("macro:fed", {})
        self.bls: dict = store.kv_get("macro:bls", {})

    # ---------------------------------------------------------------- curve
    async def refresh_curve(self, health):
        year = datetime.now().year
        rows = []
        async with client(40) as c:
            for y in (year - 1, year):
                url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                       f"daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve"
                       f"&field_tdr_date_value={y}&page&_format=csv")
                r = await c.get(url)
                if r.status_code == 200 and "Date" in r.text[:50]:
                    rows += list(csv.DictReader(io.StringIO(r.text)))
        if not rows:
            raise RuntimeError("treasury curve unavailable")
        hist = []
        for row in rows:
            d = datetime.strptime(row["Date"], "%m/%d/%Y").date()
            pts = {code: finite(row.get(col)) for col, code, _ in TENORS if row.get(col)}
            hist.append({"d": d.isoformat(), **pts})
        hist.sort(key=lambda r: r["d"])

        def ago(days):
            target = (date.fromisoformat(hist[-1]["d"]) - timedelta(days=days)).isoformat()
            older = [h for h in hist if h["d"] <= target]
            return older[-1] if older else hist[0]

        last = hist[-1]
        self.curve = {
            "asof": last["d"],
            "tenors": [{"code": code, "years": yrs} for _, code, yrs in TENORS],
            "now": last, "w1": ago(7), "m1": ago(30), "y1": ago(365),
            "spreads": {
                "2s10s": finite((last.get("10Y", 0) - last.get("2Y", 0)) * 100, 1),
                "3m10y": finite((last.get("10Y", 0) - last.get("3M", 0)) * 100, 1),
                "5s30s": finite((last.get("30Y", 0) - last.get("5Y", 0)) * 100, 1),
            },
            "surface": hist[-160:],
        }
        store.kv_set("macro:curve", self.curve)
        bus.publish("macro", {"curve": self._curve_light()})
        health.ok(f"curve {last['d']}")

    def _curve_light(self):
        return {k: v for k, v in self.curve.items() if k != "surface"}

    # ------------------------------------------------------------------ fed
    async def refresh_fed(self, health):
        async with client(20) as c:
            effr = (await c.get("https://markets.newyorkfed.org/api/rates/unsecured/effr/last/1.json")).json()
            sofr = (await c.get("https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json")).json()
        e = effr["refRates"][0]
        s = sofr["refRates"][0]
        prev = self.fed.get("target_to")
        self.fed = {
            "effr": e.get("percentRate"), "date": e.get("effectiveDate"),
            "target_from": e.get("targetRateFrom"), "target_to": e.get("targetRateTo"),
            "sofr": s.get("percentRate"), "sofr_date": s.get("effectiveDate"),
        }
        if prev is not None and prev != self.fed["target_to"]:
            bus.emit("CENTRAL BANK", f"FOMC target range changed to {self.fed['target_from']:.2f}–"
                     f"{self.fed['target_to']:.2f}% (was upper {prev:.2f}%)", tier="CRITICAL", asset="FED")
        store.kv_set("macro:fed", self.fed)
        bus.publish("macro", {"fed": self.fed})
        health.ok(f"EFFR {self.fed['effr']}")

    # ------------------------------------------------------------------ bls
    async def refresh_bls(self, health):
        cached = store.kv_get("macro:bls", max_age=12 * 3600)
        if cached:
            self.bls = cached
            health.ok("cached")
            return
        async with client(40) as c:
            r = await c.post("https://api.bls.gov/publicAPI/v1/timeseries/data/",
                             json={"seriesid": list(BLS_SERIES)})
            data = r.json()
        if data.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS: {data.get('message')}")
        out = {}
        for s in data["Results"]["series"]:
            key = BLS_SERIES[s["seriesID"]]
            pts = [(int(p["year"]), int(p["period"][1:]), float(p["value"]))
                   for p in s["data"] if p["period"].startswith("M") and p["value"] not in ("-", "")]
            pts.sort()
            out[key] = pts
        res = {}

        def yoy_at(pts, idx):
            y, m, v = pts[idx]
            base = next((p[2] for p in pts if p[0] == y - 1 and p[1] == m), None)
            return finite((v / base - 1) * 100, 2) if base else None

        def yoy(pts):
            if len(pts) < 14:
                return None, None
            return yoy_at(pts, -1), yoy_at(pts, -2)

        def label(pts):
            y, m, _ = pts[-1]
            return date(y, m, 1).strftime("%b %Y")

        if out.get("cpi"):
            now, prev = yoy(out["cpi"])
            res["cpi"] = {"value": now, "prev": prev, "period": label(out["cpi"]), "unit": "% YoY",
                          "series": [finite(v, 3) for *_, v in out["cpi"][-24:]]}
        if out.get("core_cpi"):
            now, prev = yoy(out["core_cpi"])
            res["core_cpi"] = {"value": now, "prev": prev, "period": label(out["core_cpi"]), "unit": "% YoY"}
        if out.get("payrolls") and len(out["payrolls"]) > 2:
            p = out["payrolls"]
            res["payrolls"] = {"value": round(p[-1][2] - p[-2][2]), "prev": round(p[-2][2] - p[-3][2]),
                               "period": label(p), "unit": "K jobs m/m",
                               "series": [round(p[i][2] - p[i - 1][2]) for i in range(max(1, len(p) - 24), len(p))]}
        if out.get("unemployment"):
            u = out["unemployment"]
            res["unemployment"] = {"value": u[-1][2], "prev": u[-2][2], "period": label(u), "unit": "%",
                                   "series": [v for *_, v in u[-24:]]}
        if out.get("wages"):
            now, prev = yoy(out["wages"])
            res["wages"] = {"value": now, "prev": prev, "period": label(out["wages"]), "unit": "% YoY"}
        self.bls = res
        store.kv_set("macro:bls", res)
        bus.publish("macro", {"bls": res})
        health.ok(f"CPI {res.get('cpi', {}).get('period', '?')}")

    # ------------------------------------------------------------- calendar
    def calendar(self, days: int = 45) -> list[dict]:
        today = date.today()
        end = today + timedelta(days=days)
        ev = []
        for d in FOMC_2026:
            dd = date.fromisoformat(d)
            if today - timedelta(days=3) <= dd <= end:
                ev.append({"date": d, "time": "14:00 ET", "region": "US", "event": "FOMC Rate Decision",
                           "impact": 3, "est": False, "last": self._fed_str()})
        m = date(today.year, today.month, 1)
        for _ in range(3):
            # NFP: first Friday of the month (BLS usual practice)
            first = m + timedelta(days=(4 - m.weekday()) % 7)
            # CPI: typically released around the 10th-15th business window
            cpi_d = m + timedelta(days=11)
            while cpi_d.weekday() >= 5:
                cpi_d += timedelta(days=1)
            # India CPI (MoSPI): 12th of each month, 16:00 IST
            in_cpi = date(m.year, m.month, 12)
            for d, t, reg, name, imp, last in (
                (first, "08:30 ET", "US", "Non-Farm Payrolls", 3, self._bls_str("payrolls", "K")),
                (first, "08:30 ET", "US", "Unemployment Rate", 2, self._bls_str("unemployment", "%")),
                (cpi_d, "08:30 ET", "US", "CPI (YoY)", 3, self._bls_str("cpi", "%")),
                (in_cpi, "16:00 IST", "IN", "India CPI Inflation", 2, None),
            ):
                if today - timedelta(days=3) <= d <= end:
                    ev.append({"date": d.isoformat(), "time": t, "region": reg, "event": name,
                               "impact": imp, "est": True, "last": last})
            m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        # India GDP: last working day of Feb/May/Aug/Nov
        for mo in (2, 5, 8, 11):
            for yr in (today.year, today.year + 1):
                nxt = date(yr + (mo == 12), (mo % 12) + 1, 1) - timedelta(days=1)
                while nxt.weekday() >= 5:
                    nxt -= timedelta(days=1)
                if today <= nxt <= end:
                    ev.append({"date": nxt.isoformat(), "time": "16:00 IST", "region": "IN",
                               "event": "India GDP (Quarterly)", "impact": 3, "est": True, "last": None})
        ev.sort(key=lambda e: e["date"])
        return ev

    def _fed_str(self):
        f = self.fed
        return f"{f['target_from']:.2f}–{f['target_to']:.2f}%" if f.get("target_to") is not None else None

    def _bls_str(self, key, unit):
        v = self.bls.get(key, {}).get("value")
        return f"{v:+,}{unit}" if key == "payrolls" and v is not None else (f"{v}{unit}" if v is not None else None)

    def snapshot(self) -> dict:
        return {"curve": self._curve_light(), "fed": self.fed, "bls": self.bls, "calendar": self.calendar()}

    def surface(self) -> dict:
        return {"tenors": self.curve.get("tenors", []), "rows": self.curve.get("surface", [])}


macro = Macro()


async def _selftest():
    class H:
        def ok(self, m): print("ok", m)
    await macro.refresh_curve(H())
    await macro.refresh_fed(H())
    await macro.refresh_bls(H())
    print(macro.snapshot())

if __name__ == "__main__":
    asyncio.run(_selftest())
