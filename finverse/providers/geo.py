"""Geopolitical & physical-risk intelligence (keyless).

- Conflict Intensity Index : GDELT DOC 2.0 coverage volume of conflict terms per country (7d),
                             log-normalised 0-100, with 24h escalation detection.
                             Replaces the legacy ACLED score that silently added hardcoded baselines.
- Hazards                  : USGS earthquakes (M4.5+) + NASA EONET open natural events
- Chokepoint Radar         : distance-weighted hazards + adjacent conflict intensity for the
                             maritime/industrial chokepoints that move oil, chips and freight.
- Reference layers         : proved oil reserves and official gold holdings (static, sourced).
"""
import asyncio
import logging
import math
import time

import httpx

from ..bus import bus
from ..store import store
from ..util import client, finite, haversine_km

log = logging.getLogger("finverse.geo")

# iso3 -> (display name, GDELT query name)
CONFLICT_WATCH = {
    "UKR": ("Ukraine", "Ukraine"), "RUS": ("Russia", "Russia"), "ISR": ("Israel", "Israel"),
    "PSE": ("Palestine", "Gaza"), "LBN": ("Lebanon", "Lebanon"), "SYR": ("Syria", "Syria"),
    "IRN": ("Iran", "Iran"), "IRQ": ("Iraq", "Iraq"), "YEM": ("Yemen", "Yemen"),
    "SAU": ("Saudi Arabia", "Saudi Arabia"), "SDN": ("Sudan", "Sudan"), "SSD": ("South Sudan", "South Sudan"),
    "ETH": ("Ethiopia", "Ethiopia"), "SOM": ("Somalia", "Somalia"), "LBY": ("Libya", "Libya"),
    "EGY": ("Egypt", "Egypt"), "MLI": ("Mali", "Mali"), "BFA": ("Burkina Faso", "Burkina Faso"),
    "NER": ("Niger", "Niger"), "NGA": ("Nigeria", "Nigeria"), "COD": ("DR Congo", "Congo"),
    "AFG": ("Afghanistan", "Afghanistan"), "PAK": ("Pakistan", "Pakistan"), "IND": ("India", "India"),
    "MMR": ("Myanmar", "Myanmar"), "CHN": ("China", "China"), "TWN": ("Taiwan", "Taiwan"),
    "PRK": ("North Korea", "North Korea"), "KOR": ("South Korea", "South Korea"),
    "PHL": ("Philippines", "Philippines"), "VEN": ("Venezuela", "Venezuela"), "HTI": ("Haiti", "Haiti"),
    "COL": ("Colombia", "Colombia"), "MEX": ("Mexico", "Mexico"), "ARM": ("Armenia", "Armenia"),
    "AZE": ("Azerbaijan", "Azerbaijan"), "SRB": ("Serbia", "Serbia"), "USA": ("United States", "United States"),
}
CONFLICT_TERMS = '(airstrike OR shelling OR militants OR insurgents OR rebels OR clashes OR bombing OR "armed forces" OR offensive)'
GN_TERMS = 'airstrike OR shelling OR militants OR insurgents OR rebels OR clashes OR "killed in" OR bombing OR offensive'

# name variants used when scoring from the Finverse wire (fallback when GDELT is unreachable)
ALIASES = {
    "UKR": ["Ukraine", "Ukrainian", "Kyiv"], "RUS": ["Russia", "Russian", "Moscow", "Kremlin"], "ISR": ["Israel", "Israeli"],
    "PSE": ["Gaza", "Palestinian", "West Bank", "Hamas"], "LBN": ["Lebanon", "Lebanese", "Hezbollah", "Beirut"],
    "SYR": ["Syria", "Syrian", "Damascus"], "IRN": ["Iran", "Iranian", "Tehran"], "IRQ": ["Iraq", "Iraqi", "Baghdad"],
    "YEM": ["Yemen", "Yemeni", "Houthi", "Houthis"], "SAU": ["Saudi", "Riyadh"], "SDN": ["Sudan", "Sudanese", "Khartoum", "Darfur"],
    "SSD": ["South Sudan"], "ETH": ["Ethiopia", "Ethiopian"], "SOM": ["Somalia", "Somali", "al-Shabaab"], "LBY": ["Libya", "Libyan"],
    "EGY": ["Egypt", "Egyptian", "Cairo"], "MLI": ["Mali", "Malian"], "BFA": ["Burkina Faso"], "NER": ["Niger"],
    "NGA": ["Nigeria", "Nigerian"], "COD": ["Congo", "Congolese", "M23"], "AFG": ["Afghanistan", "Afghan", "Taliban"],
    "PAK": ["Pakistan", "Pakistani", "Islamabad"], "IND": ["India", "Indian", "New Delhi"], "MMR": ["Myanmar", "Burmese"],
    "CHN": ["China", "Chinese", "Beijing"], "TWN": ["Taiwan", "Taiwanese", "Taipei"], "PRK": ["North Korea", "Pyongyang"],
    "KOR": ["South Korea", "Seoul"], "PHL": ["Philippines", "Philippine", "Manila"], "VEN": ["Venezuela", "Venezuelan", "Caracas"],
    "HTI": ["Haiti", "Haitian"], "COL": ["Colombia", "Colombian"], "MEX": ["Mexico", "Mexican"], "ARM": ["Armenia", "Armenian"],
    "AZE": ["Azerbaijan", "Azerbaijani", "Baku"], "SRB": ["Serbia", "Serbian", "Belgrade"],
    "USA": ["United States", "U.S.", "Washington", "Pentagon"],
}

CHOKEPOINTS = [
    {"id": "hormuz", "name": "Strait of Hormuz", "lat": 26.57, "lon": 56.25, "countries": ["IRN", "OMN", "ARE"],
     "flows": "≈20% of global oil", "exposed": ["BZ=F", "CL=F", "INR=X", "BPCL.NS", "IOC.NS", "ASIANPAINT.NS", "INDIGO.NS"]},
    {"id": "babelmandeb", "name": "Bab-el-Mandeb", "lat": 12.6, "lon": 43.33, "countries": ["YEM", "ERI", "DJI"],
     "flows": "Red Sea ⇄ Suez route", "exposed": ["BZ=F", "EURUSD=X"]},
    {"id": "suez", "name": "Suez Canal", "lat": 30.6, "lon": 32.33, "countries": ["EGY", "ISR", "PSE"],
     "flows": "≈12% of world trade", "exposed": ["BZ=F", "^STOXX50E"]},
    {"id": "malacca", "name": "Strait of Malacca", "lat": 2.5, "lon": 101.2, "countries": ["MYS", "IDN", "SGP"],
     "flows": "China/Japan/Korea energy lifeline", "exposed": ["BZ=F", "^N225", "^KS11", "CNY=X"]},
    {"id": "taiwan", "name": "Taiwan Strait", "lat": 24.4, "lon": 119.6, "countries": ["TWN", "CHN"],
     "flows": "≈90% of leading-edge chips", "exposed": ["TSM", "NVDA", "^TWII", "^CNXIT", "AAPL"]},
    {"id": "bosporus", "name": "Bosporus", "lat": 41.12, "lon": 29.07, "countries": ["TUR", "UKR", "RUS"],
     "flows": "Black Sea grain & oil", "exposed": ["ZW=F", "ZC=F", "BZ=F"]},
    {"id": "panama", "name": "Panama Canal", "lat": 9.08, "lon": -79.68, "countries": ["PAN"],
     "flows": "US Gulf ⇄ Asia LNG & grain", "exposed": ["NG=F", "ZS=F"]},
    {"id": "gibraltar", "name": "Strait of Gibraltar", "lat": 35.95, "lon": -5.6, "countries": ["ESP", "MAR"],
     "flows": "Atlantic ⇄ Mediterranean", "exposed": ["BZ=F"]},
    {"id": "hsinchu", "name": "Hsinchu Science Park", "lat": 24.78, "lon": 120.99, "countries": ["TWN"],
     "flows": "TSMC fabs", "exposed": ["TSM", "NVDA", "AVGO", "AAPL"]},
    {"id": "abqaiq", "name": "Abqaiq / Ras Tanura", "lat": 26.3, "lon": 49.9, "countries": ["SAU"],
     "flows": "Saudi crude processing & export", "exposed": ["BZ=F", "CL=F"]},
    {"id": "jamnagar", "name": "Jamnagar Refinery", "lat": 22.35, "lon": 69.85, "countries": ["IND"],
     "flows": "World's largest refining complex", "exposed": ["RELIANCE.NS"]},
    {"id": "rotterdam", "name": "Port of Rotterdam", "lat": 51.95, "lon": 4.14, "countries": ["NLD"],
     "flows": "Europe's largest port", "exposed": ["^AEX", "^STOXX50E"]},
]

# Proved oil reserves, bn barrels (OPEC/EIA, approx. 2023) & official gold holdings, tonnes (WGC, approx. 2025)
OIL_RESERVES = {"VEN": 303, "SAU": 267, "CAN": 168, "IRN": 157, "IRQ": 145, "RUS": 107, "KWT": 101,
                "ARE": 97, "USA": 68, "LBY": 48, "NGA": 37, "KAZ": 30, "CHN": 26, "QAT": 25, "BRA": 13,
                "DZA": 12, "NOR": 8, "AGO": 8, "IND": 4.6, "MEX": 6}
GOLD_RESERVES = {"USA": 8133, "DEU": 3351, "ITA": 2452, "FRA": 2437, "RUS": 2333, "CHN": 2279, "CHE": 1040,
                 "JPN": 846, "IND": 880, "NLD": 612, "TUR": 595, "PRT": 383, "POL": 448, "UZB": 365,
                 "SAU": 323, "GBR": 310, "KAZ": 284, "ESP": 282, "AUT": 280, "THA": 234}


class Geo:
    def __init__(self):
        saved = store.kv_get("geo:conflict", {})
        scores = saved.get("scores", {})
        if any("confidence" not in v or v.get("method") == "headlines" for v in scores.values()):
            scores, saved = {}, {}  # discard readings from the old raw-volume method (coverage-biased)
        self.conflict: dict = scores
        self.conflict_asof = saved.get("asof")
        self.sweep_progress = saved.get("progress", 0.0) if self.conflict else 0.0
        self.quakes: list = store.kv_get("geo:quakes", [])
        self.events: list = store.kv_get("geo:events", [])
        self.choke: list = []
        self._alerted: dict = {}

    # ------------------------------------------------------------ GDELT
    GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"

    async def _gdelt_series(self, c, query) -> list[float]:
        """GDELT allows ~1 request / 5s per IP; a 429 means wait and retry, not failure."""
        for attempt in range(2):
            r = await c.get(self.GDELT, params={"query": query, "mode": "timelinevolraw", "timespan": "7d", "format": "json"},
                            timeout=httpx.Timeout(40, connect=20))
            if r.status_code == 429 or not r.text.lstrip().startswith("{"):
                await asyncio.sleep(10)
                continue
            return [float(p["value"]) for p in r.json()["timeline"][0]["data"]]
        raise RuntimeError("GDELT rate-limited")

    async def _gdelt(self, c, qname) -> dict:
        """Conflict SHARE of a country's coverage — removes the bias toward countries
        that simply get more news (a raw count makes the US look like a war zone)."""
        conflict = await self._gdelt_series(c, f'"{qname}" {CONFLICT_TERMS} sourcelang:english')
        await asyncio.sleep(6)
        total = await self._gdelt_series(c, f'"{qname}" sourcelang:english')
        await asyncio.sleep(6)
        n = min(len(conflict), len(total))
        conflict, total = conflict[-n:], total[-n:]
        day = max(1, n // 7)
        return {
            "share": sum(conflict) / max(1.0, sum(total)),
            "share24": sum(conflict[-day:]) / max(1.0, sum(total[-day:])),
            "share_prior": sum(conflict[:-day]) / max(1.0, sum(total[:-day])),
            "volume": sum(conflict), "coverage": sum(total),
        }

    async def _headlines(self, c, qname) -> int:
        q = f'intitle:"{qname}" ({GN_TERMS}) -stocks -shares -deal -contract -exports when:1d'
        r = await c.get("https://news.google.com/rss/search", params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        return r.text.count("<item>")

    @staticmethod
    def _share_score(share: float) -> float:
        # ~2% conflict share = background noise, 35%+ = coverage dominated by conflict
        if share <= 0.02:
            return 0.0
        return round(min(1.0, math.log(share / 0.02) / math.log(0.35 / 0.02)) * 100, 1)

    async def sweep_conflict(self, health):
        items = list(CONFLICT_WATCH.items())
        scores, fails, used_gdelt = {}, 0, 0
        now_ms = int(time.time() * 1000)
        async with client(45) as c:
            for n, (iso, (name, qname)) in enumerate(items, 1):
                prev = self.conflict.get(iso, {})
                row = None
                if fails < 3:
                    try:
                        g = await self._gdelt(c, qname)
                        fails, used_gdelt = 0, used_gdelt + 1
                        esc = g["share24"] / g["share_prior"] if g["share_prior"] > 0 else 1.0
                        row = {"score": self._share_score(g["share"]), "share": round(g["share"] * 100, 1),
                               "share24": round(g["share24"] * 100, 1), "escalation": finite(esc, 2),
                               "volume": int(g["volume"]), "coverage": int(g["coverage"]), "method": "gdelt",
                               "confidence": "high" if g["coverage"] >= 300 else "medium", "asof": now_ms}
                        if esc >= 1.6 and g["share24"] >= 0.1 and row["score"] >= 45:
                            bus.emit("GEOPOLITICS", f"Escalation signal: conflict share of {name} coverage "
                                     f"{g['share24'] * 100:.0f}% in 24h vs {g['share_prior'] * 100:.0f}% prior "
                                     f"({esc:.1f}×, intensity {row['score']:.0f}/100)",
                                     tier="HEAVY" if esc >= 2.2 else "SIGNIFICANT", asset=iso)
                    except Exception as e:
                        fails += 1
                        log.debug("gdelt %s: %s", iso, e)
                if row is None and prev.get("method") == "gdelt" and now_ms - prev.get("asof", 0) < 48 * 3600e3:
                    row = {**prev, "stale": True}  # keep the last trustworthy reading rather than degrade it
                if row is None:
                    # share of this country's stories on the Finverse wire that are about armed conflict
                    from .news import news
                    mentions, hits = news.country_share(ALIASES.get(iso, [name]))
                    if mentions >= 6:
                        share = hits / mentions
                        score = round(100 * max(0.0, min(1.0, (share - 0.08) / 0.62)) ** 0.8, 1)
                        row = {"score": score, "share": round(share * 100, 1), "mentions": mentions, "escalation": None,
                               "method": "wire", "confidence": "low", "asof": now_ms}
                    else:
                        row = {"score": None, "mentions": mentions, "method": "wire", "confidence": "none", "asof": now_ms}
                if row:
                    scores[iso] = {**row, "name": name, "prev": prev.get("score")}
                self.sweep_progress = round(n / len(items), 3)
                health.ok(f"conflict sweep {n}/{len(items)} · GDELT {used_gdelt}")
        scored = {k: v for k, v in scores.items() if v.get("score") is not None}
        if len(scored) < 5:
            raise RuntimeError("conflict sweep returned too little data")
        self.conflict, self.conflict_asof = scores, now_ms
        store.kv_set("geo:conflict", {"scores": scores, "asof": now_ms, "progress": 1.0})
        self.compute_chokepoints()
        bus.publish("geo", self.snapshot())
        health.ok(f"{len(scored)} countries scored · GDELT {used_gdelt}/{len(items)}")
        # degraded sweep (GDELT unreachable): come back in 30 minutes instead of 6 hours
        return 1800 if used_gdelt < len(items) // 2 else None

    # ------------------------------------------------------------ hazards
    async def refresh_hazards(self, health):
        async with client(25) as c:
            q = (await c.get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson")).json()
            ev = (await c.get("https://eonet.gsfc.nasa.gov/api/v3/events",
                              params={"status": "open", "days": 20, "limit": 120})).json()
        self.quakes = [{
            "id": f["id"], "mag": f["properties"]["mag"], "place": f["properties"]["place"],
            "t": f["properties"]["time"], "lon": f["geometry"]["coordinates"][0],
            "lat": f["geometry"]["coordinates"][1], "tsunami": f["properties"].get("tsunami", 0),
        } for f in q.get("features", [])]
        events = []
        for e in ev.get("events", []):
            geo = (e.get("geometry") or [])[-1:] or []
            if not geo or geo[0].get("type") != "Point":
                continue
            lon, lat = geo[0]["coordinates"][:2]
            events.append({"id": e["id"], "title": e["title"], "cat": (e.get("categories") or [{}])[0].get("title", ""),
                           "lat": lat, "lon": lon, "t": geo[0].get("date")})
        self.events = events
        store.kv_set("geo:quakes", self.quakes)
        store.kv_set("geo:events", self.events)
        for qk in self.quakes:
            if qk["mag"] >= 6.5 and time.time() * 1000 - qk["t"] < 6 * 3600e3 and qk["id"] not in self._alerted:
                self._alerted[qk["id"]] = time.time()
                bus.emit("HAZARD", f"M{qk['mag']:.1f} earthquake — {qk['place']}" + (" · tsunami flag" if qk["tsunami"] else ""),
                         tier="CRITICAL" if qk["mag"] >= 7 else "HEAVY", asset="USGS", lat=qk["lat"], lon=qk["lon"])
        self.compute_chokepoints()
        bus.publish("geo", self.snapshot())
        health.ok(f"{len(self.quakes)} quakes · {len(self.events)} events")

    # ------------------------------------------------------- chokepoint radar
    def compute_chokepoints(self):
        out = []
        now = time.time() * 1000
        for cp in CHOKEPOINTS:
            hazard, drivers = 0.0, []
            for qk in self.quakes:
                d = haversine_km(cp["lat"], cp["lon"], qk["lat"], qk["lon"])
                if d < 600:
                    w = (qk["mag"] - 4) ** 2 * (1 - d / 600) * (0.5 if now - qk["t"] > 3 * 86400e3 else 1)
                    hazard += w * 4
                    if w > 1:
                        drivers.append(f"M{qk['mag']:.1f} quake {int(d)} km away")
            for e in self.events:
                d = haversine_km(cp["lat"], cp["lon"], e["lat"], e["lon"])
                if d < 400:
                    hazard += 12 * (1 - d / 400)
                    drivers.append(f"{e['cat'] or 'Event'}: {e['title'][:48]} ({int(d)} km)")
            conflict = max([self.conflict.get(i, {}).get("score") or 0 for i in cp["countries"]] + [0])
            esc = max([self.conflict.get(i, {}).get("escalation") or 1 for i in cp["countries"]] + [1])
            if conflict >= 50:
                drivers.append(f"Adjacent conflict intensity {conflict:.0f}/100" + (f", escalating {esc:.1f}×" if esc >= 1.5 else ""))
            risk = min(100, hazard + conflict * 0.6 + max(0, esc - 1) * 18)
            status = "CRITICAL" if risk >= 70 else ("ELEVATED" if risk >= 40 else "NORMAL")
            prev = next((c["status"] for c in self.choke if c["id"] == cp["id"]), None)
            if prev and prev != status and status != "NORMAL":
                bus.emit("CHOKEPOINT", f"{cp['name']} risk {prev} → {status}: {'; '.join(drivers[:2])}",
                         tier="CRITICAL" if status == "CRITICAL" else "HEAVY", asset=cp["id"].upper())
            out.append({**cp, "risk": round(risk, 1), "status": status, "drivers": drivers[:4]})
        out.sort(key=lambda c: -c["risk"])
        self.choke = out

    def snapshot(self) -> dict:
        return {
            "conflict": self.conflict, "conflict_asof": self.conflict_asof, "sweep": self.sweep_progress,
            "quakes": self.quakes[:120], "events": self.events, "chokepoints": self.choke,
            "oil": OIL_RESERVES, "gold": GOLD_RESERVES,
            "sources": {"conflict": "Conflict share of each country's news coverage · GDELT 7d (fallback: Finverse wire, low confidence)", "oil": "Proved reserves, bn bbl (OPEC/EIA ≈2023)",
                        "gold": "Official holdings, tonnes (WGC ≈2025)", "quakes": "USGS M4.5+ (7d)",
                        "events": "NASA EONET open events"},
        }


geo = Geo()
