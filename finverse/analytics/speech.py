"""VEDA's narrator: turns Oracle's facts into natural, spoken English.

Rules: round like a person would, name units the way traders say them, put numbers in context
("a normal move" vs "a big move"), vary phrasing a little, never invent a fact.
"""
import random
import re

from ..providers.markets import markets
from ..universe import BY_SYM, meta

_rng = random.Random()

SPOKEN_NAME = {
    "^NSEI": "the Nifty", "^BSESN": "the Sensex", "^NSEBANK": "Bank Nifty", "^CNXIT": "Nifty IT", "^GSPC": "the S&P 500",
    "^IXIC": "the Nasdaq", "^DJI": "the Dow", "^N225": "Japan's Nikkei", "^HSI": "Hong Kong's Hang Seng",
    "^FTSE": "the FTSE", "^GDAXI": "Germany's DAX", "^VIX": "the VIX", "^INDIAVIX": "India VIX",
    "BZ=F": "Brent crude", "CL=F": "WTI crude", "NG=F": "natural gas", "GC=F": "gold", "SI=F": "silver",
    "HG=F": "copper", "BTC-USD": "Bitcoin", "ETH-USD": "Ether", "DX-Y.NYB": "the dollar index",
    "INR=X": "dollar-rupee", "JPY=X": "dollar-yen", "EURUSD=X": "the euro", "GBPUSD=X": "sterling", "CNY=X": "dollar-yuan", "^TNX": "the US ten-year yield",
    "000001.SS": "Shanghai stocks", "^KS11": "Korea's Kospi", "^TWII": "Taiwan stocks",
    "PL=F": "platinum", "ZW=F": "wheat", "ZC=F": "corn", "ZS=F": "soybeans", "KC=F": "coffee", "SB=F": "sugar",
    "TCS.NS": "TCS", "BPCL.NS": "BPCL", "IOC.NS": "Indian Oil", "INDIGO.NS": "IndiGo", "ASIANPAINT.NS": "Asian Paints",
    "RELIANCE.NS": "Reliance", "HDFCBANK.NS": "HDFC Bank", "SBIN.NS": "SBI",
}


def cap(t: str) -> str:
    return t[:1].upper() + t[1:]


def headline(t: str) -> str:
    return t.rstrip(" .?!:;") + "."


def rupee(q: dict) -> str:
    """USD/INR falling means the rupee strengthened — say it the way a person would."""
    x = q.get("pct")
    if x is None or abs(x) < 0.15:
        mood = "steady"
    else:
        size = "a touch " if abs(x) < 0.4 else "about half a percent " if abs(x) < 0.75 else f"about {abs(x):.1f} percent "
        mood = size + ("weaker" if x > 0 else "stronger")
    return f"The rupee is at {q.get('price', 0):.1f} to the dollar, {mood} today"


def name(sym: str) -> str:
    if sym in SPOKEN_NAME:
        return SPOKEN_NAME[sym]
    m = meta(sym)
    n = m["name"].split(" (")[0]
    n = re.sub(r"\b(limited|ltd\.?|inc\.?|corporation|corp\.?|plc|co\.?)$", "", n, flags=re.I).strip(" ,")
    return n.title() if n.isupper() and len(n) > 4 else n


def pct(x: float | None, horizon: str = "") -> str:
    """'up about 2 percent', 'down a touch', 'roughly flat'."""
    if x is None:
        return "unchanged"
    a, d = abs(x), ("up" if x > 0 else "down")
    if a < 0.15:
        return "roughly flat" + (f" {horizon}" if horizon else "")
    if a < 0.4:
        s = f"{d} a touch"
    elif a < 0.75:
        s = f"{d} about half a percent"
    elif a < 1.25:
        s = f"{d} about 1 percent"
    elif a < 3:
        s = f"{d} about {round(a * 2) / 2:g} percent"
    else:
        s = f"{d} about {round(a):.0f} percent"
    return s + (f" {horizon}" if horizon else "")


def price(sym: str, p: float | None) -> str:
    if p is None:
        return ""
    inst = BY_SYM.get(sym)
    cls = inst.cls if inst else "equity"
    if sym == "INR=X":
        return f"{p:.1f} rupees to the dollar"
    if cls == "fx":
        return f"{p:.3g}" if p < 10 else f"{p:.1f}"
    if cls == "rate":
        return f"{p:.2f} percent"
    rounded = f"{p:,.0f}" if p >= 100 else f"{p:.1f}" if p >= 10 else f"{p:.2f}"
    if sym in ("BZ=F", "CL=F"):
        return f"{rounded} dollars a barrel"
    if sym in ("GC=F", "SI=F", "PL=F"):
        return f"{rounded} dollars an ounce"
    if cls == "crypto":
        return f"{rounded} dollars"
    if cls in ("index", "sector", "vol"):
        return rounded
    ccy = inst.ccy if inst else ("INR" if sym.endswith(".NS") else "USD")
    return f"{rounded} {'rupees' if ccy == 'INR' else 'dollars'}"


def size_of(z: float | None) -> str:
    if z is None:
        return ""
    a = abs(z)
    if a >= 3:
        return f"That's an unusually large move, around {a:.0f} standard deviations, so it really stands out."
    if a >= 2:
        return "That's a big move by its own standards, about two standard deviations."
    if a >= 1:
        return "That's a noticeable but not unusual move."
    return "That's well within its normal daily range."


def pick(*opts):
    return _rng.choice(opts)


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(\d)\s?%", r"\1 percent", text)
    text = text.replace("&", " and ").replace(" · ", ", ").replace("—", ", ").replace("–", " to ")
    return re.sub(r"\s+", " ", text)


# ------------------------------------------------------------------ intents
def explain(sym: str, facts: dict) -> str:
    q = facts.get("quote") or markets.quotes.get(sym) or {}
    n = name(sym)
    inst = BY_SYM.get(sym)
    if sym == "INR=X":
        out = [f"{rupee(q)}."]
    elif inst and inst.cls == "rate" and q.get("chg") is not None:
        bp = q["chg"] * 100
        move = "roughly unchanged" if abs(bp) < 1 else f"{'up' if bp > 0 else 'down'} about {abs(bp):.0f} basis points"
        out = [f"{cap(n)} is {move} today, at {q.get('price'):.2f} percent."]
    else:
        out = [f"{cap(n)} is {pct(q.get('pct'))} today, at {price(sym, q.get('price'))}."]
    if q.get("z") is not None:
        out.append(size_of(q.get("z")))
    tx = facts.get("transmission")
    if tx:
        top = sorted(tx["contrib_pct"].items(), key=lambda kv: -abs(kv[1] or 0))[:2]
        drivers = " and ".join(name(d) for d, c in top if c and abs(c) >= 0.03)
        imp, act = tx.get("implied_pct") or 0, tx.get("actual_pct") or 0
        if drivers and abs(imp) >= 0.1:
            if imp * act > 0 and abs(imp) >= 0.5 * abs(act):
                out.append(f"Overnight global moves, mainly {drivers}, account for most of that.")
            elif imp * act > 0:
                out.append(f"Overnight global moves, mainly {drivers}, explain part of it; the rest looks stock-specific.")
            else:
                out.append(f"Interestingly, overnight global moves, mainly {drivers}, pointed the other way, "
                           f"{pct(imp)}, so this looks driven by local factors.")
    elif facts.get("correlates_raw"):
        other, c, oq = facts["correlates_raw"][0]
        rel = "usually moves the opposite way" if c < -0.3 else "usually moves in step with it" if c > 0.3 else "is loosely linked"
        out.append(f"The closest link right now is {name(other)}, which is {pct(oq)} and {rel}.")
    if q.get("m1") is not None:
        if sym == "INR=X":
            m = q["m1"]
            out.append("Over the past month the rupee has held steady." if abs(m) < 0.15 else
                       f"Over the past month the rupee is about {abs(m):.1f} percent {'weaker' if m > 0 else 'stronger'}.")
        else:
            out.append(f"Over the past month it's {pct(q.get('m1'))}.")
    if facts.get("news_top"):
        out.append(f"{pick('On the news front', 'In the headlines', 'The latest headline')}: {headline(facts['news_top'])}")
    return clean(" ".join(out))


def overview(facts: dict) -> str:
    p = facts.get("pulse") or {}
    g, i = p.get("global") or {}, p.get("india") or {}
    out = [pick("Here's the big picture.", "Here's where markets stand.", "Quick read on the markets.")]
    if g.get("value") is not None and i.get("value") is not None:
        out.append(f"Global sentiment is {g['label'].lower()}, at {g['value']:.0f} out of 100, "
                   f"while India is in {i['label'].lower()} territory at {i['value']:.0f}.")
    reg = facts.get("regime")
    if reg:
        out.append(f"We're in a {reg.lower()} regime.")
    movers = facts.get("movers") or []
    if len(movers) >= 2:
        (s1, p1), (s2, p2) = movers[0], movers[-1]
        out.append(f"Among the big movers, {name(s1)} is {pct(p1)}, while {name(s2)} is {pct(p2)}.")
    if facts.get("headline"):
        out.append(f"Top story: {headline(facts['headline'])}")
    return clean(" ".join(out))


def region(rep: dict) -> str:
    f = rep.get("facts", {})
    out = [pick(f"Here's where things stand in {rep['region']}.", f"Here's the situation in {rep['region']}.")]
    cps = f.get("chokepoints", [])
    def the(n):  # "the Strait of Hormuz" but "Abqaiq and Ras Tanura"
        n = n.replace(" / ", " and ")
        return ("the " + n) if n.split()[0] in ("Strait", "Suez", "Panama", "Bosporus", "Port", "Taiwan") else n
    alert = [c for c in cps if c[1] != "NORMAL"]
    if alert:
        verb = "are" if " and " in the(alert[0][0]) else "is"
        out.append(f"{cap(the(alert[0][0]))} {verb} on {alert[0][1].lower()} alert.")
    elif cps:
        out.append(f"Traffic through {the(cps[0][0])} looks normal for now.")
    conflict = f.get("conflict", [])
    if conflict:
        hot = [line.split(":")[0] for score, line in conflict if score >= 60]
        if hot:
            out.append(f"Conflict signals are running high around {' and '.join(hot[:2])}.")
        else:
            out.append("Conflict signals in the region are moderate right now.")
    for sym in f.get("syms", [])[:2]:
        q = markets.quotes.get(sym) or {}
        if q.get("price") is None:
            continue
        if sym == "INR=X":
            out.append(rupee(q) + ".")
            continue
        line = f"{cap(name(sym))} is trading around {price(sym, q['price'])}, {pct(q.get('pct'), 'today')}"
        if q.get("m1") is not None and abs(q["m1"]) >= 3:
            line += f", and {pct(q['m1'])} over the past month"
        out.append(line + ".")
    sh = f.get("shock")
    if sh and sh.get("worst"):
        worst = [name(r["sym"]) for r in sh["worst"][:3]]
        drv, mv = next(iter(sh["shock"].items()))
        what = {"BZ=F": "oil", "^IXIC": "tech stocks", "INR=X": "the dollar against the rupee", "GC=F": "gold"}.get(drv, name(drv))
        verb = "fall" if mv < 0 else "rise"
        mag = abs(sh["worst"][0]["impact_pct"])
        size = "though the estimated hit is small" if mag < 0.75 else f"with the biggest hit around {mag:.0f} percent"
        out.append(f"If {what} were to {verb} another {abs(mv):g} percent, the most exposed Indian names "
                   f"would be {', '.join(worst[:-1])} and {worst[-1]}, {size}.")
    if f.get("headlines"):
        out.append(f"The top headline: {headline(f['headlines'][0])}")
    return clean(" ".join(out))


def scenario(res: dict) -> str:
    imp = [r for r in res.get("impacts", []) if r.get("impact_pct") is not None]
    if not imp:
        return "I couldn't size that scenario."
    worst, best = imp[:3], imp[-2:][::-1]
    out = [f"In that scenario, the hardest hit in India would be {name(worst[0]['sym'])}, "
           f"{pct(worst[0]['impact_pct']).replace('down ', '')} lower, followed by "
           f"{' and '.join(name(r['sym']) for r in worst[1:])}."]
    if best and best[0]["impact_pct"] > 0:
        out.append(f"The relative winners would be {' and '.join(name(r['sym']) for r in best)}.")
    out.append("That's a first-order estimate from historical sensitivities, not a forecast.")
    return clean(" ".join(out))


def compare(a: str, b: str, corr60: float | None) -> str:
    qa, qb = markets.quotes.get(a, {}), markets.quotes.get(b, {})
    out = [f"{name(a)[0].upper() + name(a)[1:]} is {pct(qa.get('pct'), 'today')} and {pct(qa.get('m1'), 'over the month')}.",
           f"{name(b)[0].upper() + name(b)[1:]} is {pct(qb.get('pct'), 'today')} and {pct(qb.get('m1'), 'over the month')}."]
    if corr60 is not None:
        rel = "moving together" if corr60 > 0.4 else "moving in opposite directions" if corr60 < -0.4 else "moving fairly independently"
        out.append(f"Lately they've been {rel}.")
    return clean(" ".join(out))


def regime(reg: dict) -> str:
    if not reg.get("ready"):
        return "I don't have enough history to call the regime yet."
    appetite = {"RISK-ON": "healthy", "RISK-OFF": "weak", "BALANCED": "balanced"}.get(reg["risk_label"], "mixed")
    favour = reg["playbook"].split(";")[0].replace("EM", "emerging markets").rstrip(".")
    return clean(f"We're in a {reg['regime'].lower()} regime: {reg['description'].lower()}. Risk appetite is {appetite}. "
                 f"Historically, that tends to favour {favour[0].lower() + favour[1:]}.")
