"""Regional situation reports ("What's the situation in the Gulf?") and ear-friendly summaries.

A report fuses: conflict readings for the region's countries, chokepoint status, a market
read-through (prices + a first-order oil/FX shock through the India transmission betas),
the latest headlines and any rhetoric that mentions the region. Every line is sourced data.
"""
import re
import time

from ..providers.geo import geo
from ..providers.markets import markets
from ..providers.news import news
from ..providers.rhetoric import rhetoric
from ..universe import meta
from . import quant

REGIONS = {
    "gulf": {
        "name": "the Gulf and the Strait of Hormuz",
        "kw": r"\b(gulf|hormuz|persian gulf|iran|iranian|saudi|uae|emirates|qatar|kuwait|oman|opec)\b",
        "countries": ["IRN", "IRQ", "SAU", "YEM"], "chokepoints": ["hormuz", "abqaiq", "babelmandeb"],
        "assets": ["BZ=F", "CL=F", "NG=F", "GC=F", "INR=X", "BPCL.NS", "IOC.NS", "ONGC.NS"],
        "news": ["Hormuz", "Gulf", "Iran", "Saudi", "OPEC", "Houthi", "Qatar", "UAE"], "shock": {"BZ=F": 10},
        "speak": ["BZ=F", "INR=X"],
    },
    "middleeast": {
        "name": "the Middle East",
        "kw": r"\b(middle east|israel|israeli|gaza|lebanon|hezbollah|hamas|west bank|syria)\b",
        "countries": ["ISR", "PSE", "LBN", "SYR", "IRN"], "chokepoints": ["suez", "babelmandeb"],
        "assets": ["BZ=F", "GC=F", "^TA125.TA", "DX-Y.NYB", "^VIX"],
        "news": ["Israel", "Gaza", "Lebanon", "Hezbollah", "Syria", "Hamas"], "shock": {"BZ=F": 8, "GC=F": 3},
    },
    "redsea": {
        "name": "the Red Sea and Suez",
        "kw": r"\b(red sea|suez|houthi|houthis|bab.el.mandeb|yemen)\b",
        "countries": ["YEM", "EGY"], "chokepoints": ["babelmandeb", "suez"],
        "assets": ["BZ=F", "EURUSD=X", "^STOXX50E", "GC=F"],
        "news": ["Red Sea", "Suez", "Houthi", "Yemen", "shipping"], "shock": {"BZ=F": 6},
    },
    "ukraine": {
        "name": "Russia and Ukraine",
        "kw": r"\b(ukraine|ukrainian|russia|russian|kyiv|moscow|black sea|donbas|kremlin)\b",
        "countries": ["UKR", "RUS"], "chokepoints": ["bosporus"],
        "assets": ["ZW=F", "ZC=F", "NG=F", "BZ=F", "^GDAXI", "EURUSD=X"],
        "news": ["Ukraine", "Russia", "Black Sea", "Kremlin", "Kyiv"], "shock": {"BZ=F": 6, "GC=F": 2},
    },
    "taiwan": {
        "name": "the Taiwan Strait",
        "kw": r"\b(taiwan|taiwanese|tsmc|south china sea|taipei)\b",
        "countries": ["TWN", "CHN"], "chokepoints": ["taiwan", "hsinchu", "malacca"],
        "assets": ["TSM", "NVDA", "^TWII", "CNY=X", "^CNXIT", "^IXIC"],
        "news": ["Taiwan", "TSMC", "South China Sea", "Beijing"], "shock": {"^IXIC": -8},
        "speak": ["TSM", "^TWII"],
    },
    "southasia": {
        "name": "India and Pakistan",
        "kw": r"\b(pakistan|pakistani|kashmir|line of control|india.pakistan|border tension)\b",
        "countries": ["IND", "PAK", "AFG"], "chokepoints": [],
        "assets": ["^NSEI", "^INDIAVIX", "INR=X", "^NSEBANK"],
        "news": ["Pakistan", "Kashmir", "Line of Control"], "shock": {"INR=X": 2},
        "speak": ["^NSEI", "^INDIAVIX"],
    },
    "africa": {
        "name": "the Sahel and the Horn of Africa",
        "kw": r"\b(sudan|sahel|mali|niger|burkina|somalia|ethiopia|congo|africa)\b",
        "countries": ["SDN", "SSD", "ETH", "SOM", "MLI", "BFA", "NER", "COD"], "chokepoints": ["babelmandeb"],
        "assets": ["GC=F", "HG=F", "BZ=F"],
        "news": ["Sudan", "Sahel", "Somalia", "Ethiopia", "Congo", "Mali"], "shock": {},
    },
    "korea": {
        "name": "the Korean Peninsula",
        "kw": r"\b(north korea|pyongyang|korean peninsula|kim jong)\b",
        "countries": ["PRK", "KOR"], "chokepoints": [],
        "assets": ["^KS11", "KRW=X", "JPY=X", "GC=F"],
        "news": ["North Korea", "Pyongyang", "Seoul"], "shock": {},
    },
}
_RX = {k: re.compile(v["kw"], re.I) for k, v in REGIONS.items()}


def detect(text: str) -> str | None:
    hits = [(k, len(rx.findall(text))) for k, rx in _RX.items()]
    hits = [h for h in hits if h[1]]
    return max(hits, key=lambda x: x[1])[0] if hits else None


def _px(v):
    return "n/a" if v is None else (f"{v:,.2f}" if abs(v) >= 100 else f"{v:,.4g}")


def report(key: str) -> dict:
    R = REGIONS[key]
    sections, facts = [], {"region": key, "syms": R.get("speak", R["assets"][:2])}

    # 1 · conflict readings
    rows = []
    for iso in R["countries"]:
        c = geo.conflict.get(iso)
        if not c or c.get("score") is None:
            continue
        esc = c.get("escalation")
        line = f"{c['name']}: conflict intensity {c['score']:.0f}/100"
        if c.get("share") is not None:
            line += f" ({c['share']:.0f}% of its coverage is about armed conflict)"
        if esc and esc >= 1.4:
            line += f", escalating {esc:.1f}× in the last 24h"
        if c.get("confidence") == "low":
            line += " · low-confidence reading"
        rows.append((c["score"], line))
    rows.sort(key=lambda r: -r[0])
    if rows:
        sections.append({"h": "Conflict readings", "bullets": [r[1] for r in rows]})
    facts["conflict"] = rows

    # 2 · chokepoints
    cps = [c for c in geo.choke if c["id"] in R["chokepoints"]]
    if cps:
        sections.append({"h": "Chokepoints", "bullets": [
            f"{c['name']} is {c['status'].lower()} (risk {c['risk']:.0f}/100) — carries {c['flows']}"
            + (f"; {c['drivers'][0]}" if c["drivers"] else "") for c in cps]})
    facts["chokepoints"] = [(c["name"], c["status"]) for c in cps]

    # 3 · market read-through
    mk = []
    for sym in R["assets"]:
        q = markets.quotes.get(sym)
        if not q or q.get("price") is None:
            continue
        m = meta(sym)
        mk.append(f"{m['name']} {_px(q['price'])} ({q['pct']:+.2f}% today, {q.get('m1') or 0:+.1f}% over a month)")
    if R["shock"]:
        sc = quant.scenario(R["shock"])
        imp = [r for r in sc["impacts"] if r["impact_pct"] is not None]
        if imp:
            shock_txt = ", ".join(f"{meta(s)['code']} {v:+g}%" for s, v in R["shock"].items())
            worst, best = imp[:3], imp[-2:][::-1]
            mk.append(f"If {shock_txt}: India most exposed — " + ", ".join(f"{r['code']} {r['impact_pct']:+.1f}%" for r in worst)
                      + "; relative winners — " + ", ".join(f"{r['code']} {r['impact_pct']:+.1f}%" for r in best) + " (β model).")
            facts["shock"] = {"worst": worst, "best": best, "shock": R["shock"]}
    if mk:
        sections.append({"h": "Market read-through", "bullets": mk})
    facts["markets"] = mk

    # 4 · headlines
    rx = re.compile(r"\b(" + "|".join(re.escape(w) for w in R["news"]) + r")\b", re.I)
    heads = [n for n in news.latest(300) if rx.search(n["title"])]
    heads.sort(key=lambda n: (n["importance"] + 6 * n.get("confirmations", 1), n["ts"]), reverse=True)
    if heads:
        sections.append({"h": "Latest on the wire", "bullets": [f"{n['source']}: {n['title']}" for n in heads[:5]]})
    facts["headlines"] = [n["title"] for n in heads[:3]]

    # 5 · rhetoric that touches the region
    cutoff = time.time() * 1000 - 48 * 3600e3
    posts = [p for p in rhetoric.posts if p["seen_at"] >= cutoff and _RX[key].search(p["text"])]
    if posts:
        sections.append({"h": "Rhetoric", "bullets": [f"Trump ({p['published']}): {p['text'][:180]}" for p in posts[:2]]})

    if not sections:
        sections.append({"h": "No signal", "bullets": ["No scored conflict, chokepoint or headline data for this region yet."]})
    return {"title": f"Situation report · {R['name'].replace('the ', '').title()}", "sections": sections,
            "facts": facts, "region": R["name"]}


# ------------------------------------------------------------------ speech
_SPOKEN = [
    # signed percentages read as moves; any other signed number (correlation, beta, sigma) as plus/minus
    (r"(?<![\w.])\+(\d[\d.,]*)\s?%", r"up \1 percent"), (r"(?<![\w.])[−-](\d[\d.,]*)\s?%", r"down \1 percent"),
    (r"(?<![\w.])\+(\d)", r"plus \1"), (r"(?<![\w.])[−-](\d)", r"minus \1"), (r"(\d)\s?%", r"\1 percent"),
    (r"(\d)\s?bp\b", r"\1 basis points"), (r"(\d)\s?pp\b", r"\1 percentage points"), (r"σ", " sigma"),
    (r"β", "beta"), (r"R²", "R squared"), (r"×", " times"), (r"→", " to "), (r"·", ","), (r"—", ","),
    (r"/100", " out of 100"), (r"\bUSD/INR\b", "the dollar-rupee rate"), (r"\bUSDINR\b", "dollar-rupee"),
    (r"\bUS10Y\b", "the US ten-year yield"), (r"\bDXY\b", "the dollar index"), (r"\bNIFTY\b", "Nifty"),
    (r"\bBRENT\b", "Brent"), (r"\bGOLD\b", "gold"), (r"\bBTC\b", "Bitcoin"), (r"\bCCMP\b", "the Nasdaq"),
    (r"\bSPX\b", "the S&P 500"), (r"\s{2,}", " "),
]


def speakify(text: str) -> str:
    for pat, rep in _SPOKEN:
        text = re.sub(pat, rep, text)
    # sentence case after substitutions ("the dollar index ..." at a sentence start)
    text = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text.strip())
    return text


def spoken(ans: dict, intent: str) -> str:
    """3-6 sentences written for the ear, built only from the answer's own facts."""
    secs = ans.get("sections", [])
    if intent == "region":
        f = ans.get("facts", {})
        out = [f"Here's the situation in {ans.get('region', 'the region')}."]
        for name, status in f.get("chokepoints", [])[:2]:
            out.append(f"The {name} is {status.lower()}.")
        for _, line in f.get("conflict", [])[:2]:
            out.append(line.split(" (")[0].replace(": ", " shows ") + ".")
        for line in f.get("markets", [])[:2]:
            out.append(line.split(" (β")[0].rstrip(".") + ".")
        if f.get("headlines"):
            out.append(f"The top headline: {f['headlines'][0]}.")
        return speakify(" ".join(out))
    out = [ans.get("title", "").split(" · ")[-1] + "."] if intent != "overview" else ["Here's the market picture."]
    for s in secs[:3]:
        if s["bullets"]:
            out.append(s["bullets"][0].rstrip(".") + ".")
    return speakify(" ".join(out))
