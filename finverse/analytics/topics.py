"""Topic answers for Oracle/VEDA: rates & central banks, inflation, jobs, bonds, news, calendar,
sentiment, crypto — plus greetings, help and thanks. Each returns (answer, spoken)."""
import re
import time
from datetime import date

from ..providers.crypto import crypto
from ..providers.macro import macro
from ..providers.markets import markets
from ..providers.news import news
from ..providers.rhetoric import rhetoric
from . import quant
from .speech import clean, headline, pct, pick

TOPICS = [  # order matters: first match wins
    ("thanks", r"\b(thank you|thanks|thankyou|great job|good job|shukriya|dhanyavaad|dhanyavad)\b"),
    ("help", r"\b(who are you|what can you do|what do you do|your name|introduce yourself|how do i use|help me)\b"),
    ("greet", r"^\s*(hi|hello|hey|namaste|good (morning|afternoon|evening))\b[\s!.?]*$"),
    ("calendar", r"\b(calendar|coming up|this week|next week|upcoming|schedule|events?|when is|next (fed|fomc|meeting|cpi|payrolls?|jobs report))\b"),
    ("rates", r"\b(fed|federal reserve|fomc|powell|interest rates?|rate (cut|hike)s?|policy rates?|repo( rate)?|rbi|reserve bank|ecb|central banks?|monetary policy)\b"),
    ("inflation", r"\b(inflation|cpi|consumer prices?|price rise|core prices?)\b"),
    ("jobs", r"\b(jobs?|payrolls?|nfp|unemployment|labou?r market|employment|hiring|wages?)\b"),
    ("bonds", r"\b(bonds?|treasur(y|ies)|yields?|yield curve|ten.year|10.year|two.year|2s10s|curve)\b"),
    ("sentiment", r"\b(sentiment|fear|greed|mood|pulse|panic|euphoria|risk appetite)\b"),
    ("crypto", r"\b(crypto|cryptocurrenc(y|ies)|altcoins?|liquidations?|funding rates?|coins?)\b"),
    ("news", r"\b(news|headlines?|top stor(y|ies)|what('s| is) (happening|going on)|latest)\b"),
]
_RX = [(k, re.compile(v, re.I)) for k, v in TOPICS]


def detect(text: str) -> str | None:
    for k, rx in _RX:
        if rx.search(text):
            return k
    return None


def _day(iso: str) -> str:
    d = date.fromisoformat(iso)
    delta = (d - date.today()).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return d.strftime("%A, %B ") + str(d.day)


def answer(topic: str, q: str) -> tuple[dict, str]:
    return globals()[f"_{topic}"](q)


# ------------------------------------------------------------------ small talk
def _thanks(q):
    return {"title": "You're welcome", "sections": []}, pick("You're welcome.", "Anytime.", "Happy to help.")


def _greet(q):
    h = time.localtime().tm_hour
    hello = "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"
    return {"title": hello, "sections": []}, f"{hello}. Ask me about any market, a region like the Gulf, the Fed, inflation, or a what-if."


def _help(q):
    tips = ["Any market or stock: “how is Reliance doing?”, “why is gold rising?”",
            "Regions: “what's the situation in the Gulf?”, “Taiwan”, “Russia and Ukraine”",
            "Macro: the Fed, RBI, inflation, jobs, bonds and the yield curve",
            "What-ifs: “what if Brent rises 20 percent?” · comparisons: “gold versus bitcoin”",
            "The day: top news, what's coming up this week, market mood, crypto"]
    return ({"title": "I'm VEDA, the voice of Finverse", "sections": [{"h": "Try asking", "bullets": tips}]},
            "I'm Veda, the voice of Finverse. Ask me about any market or stock, a region like the Gulf, the Fed or inflation, "
            "today's news, what's coming up this week, or a what-if like: what if oil rises twenty percent.")


# ------------------------------------------------------------------ macro
def _rates(q):
    f, banks = macro.fed, rhetoric.banks
    cal = [e for e in macro.calendar(60) if e["event"].startswith("FOMC")]
    b, spoken = [], []
    if f.get("target_to") is not None:
        b.append(f"Fed funds target {f['target_from']:.2f}–{f['target_to']:.2f}%, effective rate {f['effr']}% ({f['date']}).")
        spoken.append(f"The Fed's target range is {f['target_from']:g} to {f['target_to']:g} percent, with the effective rate at {f['effr']:g}.")
    if cal:
        b.append(f"Next FOMC decision: {cal[0]['date']}.")
        spoken.append(f"The next Fed decision is on {_day(cal[0]['date'])}.")
    rbi, ecb = banks.get("RBI", {}), banks.get("ECB", {})
    if rbi.get("rate") is not None:
        b.append(f"RBI repo rate {rbi['rate']:.2f}% ({rbi.get('rate_src') or 'press'}).")
        spoken.append(f"In India, the RBI repo rate is {rbi['rate']:g} percent.")
    if ecb.get("rate") is not None:
        b.append(f"ECB rate {ecb['rate']:.2f}% ({ecb.get('rate_src') or 'press'}).")
        spoken.append(f"The ECB is at {ecb['rate']:g} percent.")
    for code in ("FED", "RBI", "ECB"):
        st = banks.get(code, {}).get("stance")
        if st is not None and abs(st) >= 0.25:
            spoken.append(f"Recent {code if code != 'FED' else 'Fed'} communication reads {'hawkish' if st > 0 else 'dovish'}.")
            break
    c = macro.curve
    if c.get("now", {}).get("10Y") is not None:
        s = c.get("spreads", {}).get("2s10s")
        b.append(f"US 10Y {c['now']['10Y']:.2f}%, 2s10s {s:+.0f}bp.")
        spoken.append(f"The US ten-year yield is {c['now']['10Y']:.2f} percent.")
    return {"title": "Rates & central banks", "sections": [{"h": "Policy rates", "bullets": b}]}, clean(" ".join(spoken) or "I don't have central bank data yet.")


def _inflation(q):
    bls = macro.bls
    cpi, core = bls.get("cpi"), bls.get("core_cpi")
    if not cpi:
        return {"title": "Inflation", "sections": []}, "US inflation data is still loading."
    trend = "rising" if cpi["value"] > cpi["prev"] else "easing" if cpi["value"] < cpi["prev"] else "steady"
    b = [f"US CPI {cpi['value']}% YoY in {cpi['period']} (prior {cpi['prev']}%)."]
    spoken = [f"US inflation was {cpi['value']:g} percent in {cpi['period']}, {trend} from {cpi['prev']:g} percent the month before."]
    if core:
        b.append(f"Core CPI {core['value']}% YoY.")
        spoken.append(f"Core inflation, excluding food and energy, is {core['value']:g} percent.")
    reg = quant.regime()
    if reg.get("ready"):
        infl = reg["inflation"]
        spoken.append("Market-based inflation signals are running hot." if infl > 0.5 else
                      "Market-based inflation signals are cooling." if infl < -0.5 else "Market-based inflation signals are fairly neutral.")
    nxt = next((e for e in macro.calendar(45) if "CPI" in e["event"] and e["region"] == "US"), None)
    if nxt:
        spoken.append(f"The next US CPI print is expected around {_day(nxt['date'])}.")
    return {"title": "Inflation", "sections": [{"h": "Latest", "bullets": b}]}, clean(" ".join(spoken))


def _jobs(q):
    bls = macro.bls
    p, u, w = bls.get("payrolls"), bls.get("unemployment"), bls.get("wages")
    if not p:
        return {"title": "Jobs", "sections": []}, "Jobs data is still loading."
    b = [f"Non-farm payrolls {p['value']:+,}K in {p['period']} (prior {p['prev']:+,}K)."]
    spoken = [f"The US economy added {p['value']:,} thousand jobs in {p['period']}, versus {p['prev']:,} thousand the month before."]
    if u:
        b.append(f"Unemployment {u['value']}%.")
        spoken.append(f"Unemployment is {u['value']:g} percent.")
    if w:
        b.append(f"Average hourly earnings {w['value']}% YoY.")
        spoken.append(f"Wages are growing {w['value']:g} percent a year.")
    return {"title": "US labour market", "sections": [{"h": "Latest", "bullets": b}]}, clean(" ".join(spoken))


def _bonds(q):
    c = macro.curve
    now, m1, sp = c.get("now", {}), c.get("m1", {}), c.get("spreads", {})
    if now.get("10Y") is None:
        return {"title": "Bonds", "sections": []}, "Treasury data is still loading."
    b = [f"3M {now.get('3M')}% · 2Y {now.get('2Y')}% · 10Y {now.get('10Y')}% · 30Y {now.get('30Y')}% ({c.get('asof')})",
         f"2s10s {sp.get('2s10s'):+.0f}bp · 3m10y {sp.get('3m10y'):+.0f}bp"]
    d10 = (now["10Y"] - m1.get("10Y", now["10Y"])) * 100
    shape = "upward sloping" if sp.get("2s10s", 0) > 10 else "inverted" if sp.get("2s10s", 0) < -10 else "fairly flat"
    spoken = [f"The US ten-year yield is {now['10Y']:.2f} percent, "
              f"{'up' if d10 > 0 else 'down'} about {abs(d10):.0f} basis points over the past month." if abs(d10) >= 3 else
              f"The US ten-year yield is {now['10Y']:.2f} percent, little changed over the past month.",
              f"The two-year is at {now.get('2Y'):.2f} percent, so the curve is {shape}."]
    return {"title": "US Treasury curve", "sections": [{"h": "Curve", "bullets": b}]}, clean(" ".join(spoken))


def _sentiment(q):
    p = quant.pulse()
    g, i = p.get("global") or {}, p.get("india") or {}
    b, spoken = [], []
    if g.get("value") is not None:
        b.append(f"Global Pulse {g['value']:.0f}/100 — {g['label']}")
        spoken.append(f"Global sentiment is {g['label'].lower()}, at {g['value']:.0f} out of 100.")
    if i.get("value") is not None:
        b.append(f"India Pulse {i['value']:.0f}/100 — {i['label']}")
        spoken.append(f"India is in {i['label'].lower()} territory at {i['value']:.0f}.")
    if crypto.fng:
        b.append(f"Crypto Fear & Greed {crypto.fng['value']} — {crypto.fng['label']}")
        spoken.append(f"In crypto, the fear and greed index reads {crypto.fng['value']}, {crypto.fng['label'].lower()}.")
    return {"title": "Market mood", "sections": [{"h": "Pulse", "bullets": b}]}, clean(" ".join(spoken) or "Sentiment data is still loading.")


def _crypto(q):
    btc, eth = markets.quotes.get("BTC-USD", {}), markets.quotes.get("ETH-USD", {})
    b, spoken = [], []
    if btc.get("price"):
        b.append(f"BTC {btc['price']:,.0f} ({btc.get('pct', 0):+.2f}%) · ETH {eth.get('price', 0):,.0f} ({eth.get('pct', 0):+.2f}%)")
        spoken.append(f"Bitcoin is around {btc['price']:,.0f} dollars, {pct(btc.get('pct'), 'today')}, and Ether is {pct(eth.get('pct'))}.")
    if crypto.fng:
        spoken.append(f"The crypto fear and greed index is at {crypto.fng['value']}, {crypto.fng['label'].lower()}.")
    if crypto.global_.get("btc_dom"):
        b.append(f"BTC dominance {crypto.global_['btc_dom']:.1f}%")
    liq = crypto.liq_summary().get("1h", {})
    if liq.get("count"):
        tot = liq["long"] + liq["short"]
        side = "longs" if liq["long"] > liq["short"] else "shorts"
        b.append(f"Liquidations (1h): ${tot:,.0f} across {liq['count']} events, mostly {side}")
        spoken.append(f"In the last hour about {tot / 1e6:.1f} million dollars of positions were liquidated, mostly {side}." if tot >= 1e6 else
                      f"Liquidations have been light in the last hour, mostly {side}.")
    return {"title": "Crypto", "sections": [{"h": "Now", "bullets": b}]}, clean(" ".join(spoken) or "Crypto data is still loading.")


def _news(q):
    top = news.top(5)
    if not top:
        return {"title": "News", "sections": []}, "The news wire is still loading."
    spoken = ["Here are the top stories."] + [f"{n}: {headline(t['title'])}" for n, t in zip(("First", "Second", "Third"), top[:3])]
    return ({"title": "Top stories", "sections": [{"h": "On the wire", "bullets": [f"{t['source']}: {t['title']}" for t in top]}]},
            clean(" ".join(spoken)))


def _calendar(q):
    low = q.lower()
    wanted = ("FOMC" if re.search(r"\b(fed|fomc|powell|rate decision)\b", low) else
              "CPI" if re.search(r"\b(cpi|inflation)\b", low) else
              "Payrolls" if re.search(r"\b(jobs?|payrolls?|nfp|employment)\b", low) else
              "GDP" if "gdp" in low else None)
    if wanted:
        ev = next((e for e in macro.calendar(120) if wanted.lower() in e["event"].lower()), None)
        if ev:
            last = f" The last reading was {ev['last']}." if ev.get("last") else ""
            est = " That date is an estimate based on the usual release pattern." if ev["est"] else ""
            return ({"title": ev["event"], "sections": [{"h": "Next", "bullets": [f"{ev['date']} {ev['time']} · {ev['region']} {ev['event']}"]}]},
                    clean(f"The next {ev['event'].replace('(YoY)', '').replace('Rate Decision', 'rate decision').strip()} is {_day(ev['date'])}, at {ev['time']}.{last}{est}"))
    cal = macro.calendar(21)[:5]
    if not cal:
        return {"title": "Calendar", "sections": []}, "Nothing major on the calendar in the next three weeks."
    b = [f"{e['date']} {e['time']} · {e['region']} {e['event']}" + (" (est.)" if e["est"] else "") for e in cal]
    spoken = ["Here's what's coming up."] + [f"{e['event'].replace('(YoY)', '').strip()} {_day(e['date'])}." for e in cal[:4]]
    return {"title": "Coming up", "sections": [{"h": "Calendar", "bullets": b}]}, clean(" ".join(spoken))
