"""ORACLE — the terminal's analyst. Answers questions from live terminal data only.

Pipeline: intent + entity detection -> gather grounded facts from every engine ->
deterministic narrative (always) -> optional local LLM polish via Ollama (free, offline).
Every answer lists the facts it used, so nothing is invented.
"""
import asyncio
import json
import logging
import re
import time

import httpx

from ..config import OLLAMA_MODEL, OLLAMA_URL
from ..providers.geo import geo
from ..providers.macro import macro
from ..providers.markets import markets
from ..providers.news import news
from ..providers.rhetoric import rhetoric
from ..universe import BY_SYM, DRIVERS, EXTRA_NAMES, INDIA_TARGETS, UNIVERSE, meta, resolve
from . import quant, regions, speech, topics

log = logging.getLogger("finverse.oracle")
_ollama_state = {"checked": 0, "ok": False, "models": []}


def _f(v, d=2, sign=True):
    if v is None:
        return "n/a"
    return f"{v:+.{d}f}" if sign else f"{v:.{d}f}"


def find_entities(text: str) -> list[str]:
    """Longest alias match first ('nifty it' beats 'nifty'), then single tokens."""
    found, low = [], " " + re.sub(r"[^a-z0-9&^=.\- ]", " ", text.lower()) + " "
    names = sorted(((a, i.sym) for i in UNIVERSE for a in [i.name.lower(), *i.aliases, i.code.lower()] if len(a) > 2),
                   key=lambda x: -len(x[0]))
    pos = {}
    original = low
    for a, sym in names:
        if f" {a} " in low and sym not in found:
            found.append(sym)
            pos[sym] = original.find(f" {a} ")
            low = low.replace(f" {a} ", " ")
    for tok in re.findall(r"[A-Za-z0-9^=.\-&]+", text):
        s = resolve(tok)
        if s and s not in found and tok.lower() in low:
            found.append(s)
            pos[s] = original.lower().find(tok.lower())
    found.sort(key=lambda x: pos.get(x, 999))
    return found[:4]


def _px(v):
    if v is None:
        return "n/a"
    return f"{v:,.2f}" if abs(v) >= 100 else f"{v:,.4g}"


def _movers(cls_set, n=3):
    rows = [q for s, q in markets.quotes.items() if BY_SYM.get(s) and BY_SYM[s].cls in cls_set and q.get("pct") is not None]
    rows.sort(key=lambda q: q["pct"])
    return rows[:n], rows[-n:][::-1]


# ------------------------------------------------------------------ intents
def explain(sym: str) -> dict:
    m = meta(sym)
    q = markets.quotes.get(sym, {})
    sections, facts = [], {}
    if not q:
        return {"title": f"{m['name']}", "sections": [{"h": "No data", "bullets": ["This instrument is not in the live universe yet — open it with its symbol to load it."]}], "facts": {}}
    facts["quote"] = {k: q.get(k) for k in ("price", "pct", "z", "w1", "m1", "ytd", "hi52", "lo52", "vol")}
    move = [f"{m['name']} is {_f(q.get('pct'))}% on the session at {_px(q.get('price'))}"
            + (f" ({_f(q.get('z'), 1)}σ vs its 60-day volatility)." if q.get("z") is not None else ".")]
    if q.get("hi52") and q.get("lo52"):
        pos = (q["price"] - q["lo52"]) / (q["hi52"] - q["lo52"]) * 100 if q["hi52"] != q["lo52"] else 50
        move.append(f"Trend: 1W {_f(q.get('w1'))}%, 1M {_f(q.get('m1'))}%, YTD {_f(q.get('ytd'))}%; "
                    f"sits at {pos:.0f}% of its 52-week range.")
    sections.append({"h": "What moved", "bullets": move})

    drivers = []
    if sym in INDIA_TARGETS:
        tx = next((t for t in quant.transmission()["targets"] if t["sym"] == sym), None)
        if tx:
            facts["transmission"] = tx
            top = sorted(tx["contrib_pct"].items(), key=lambda kv: -abs(kv[1] or 0))[:3]
            drivers.append(f"Transmission model (R² {tx['r2']:.2f}) implies {_f(tx['implied_pct'])}% from global drivers; "
                           f"actual {_f(tx['actual_pct'])}% → idiosyncratic residual {_f(tx['residual_pct'])}%.")
            for d, c in top:
                if c:
                    drivers.append(f"{meta(d)['code']} contributed {_f(c)}% (β {tx['betas'][d]['b']:+.2f}).")
    else:
        rets = markets.returns([sym] + quant.CORR_SET, n=60)
        if sym in rets:
            corr = rets.corr(min_periods=20)[sym].drop(sym, errors="ignore").dropna()
            raw = []
            for other, c in corr.reindex(corr.abs().sort_values(ascending=False).index).head(3).items():
                oq = markets.quotes.get(other, {})
                drivers.append(f"{meta(other)['code']} ({_f(oq.get('pct'))}% today) has a 60-day correlation of {c:+.2f}.")
                raw.append((other, float(c), oq.get("pct")))
            facts["correlates"] = drivers
            facts["correlates_raw"] = raw
    if drivers:
        sections.append({"h": "Likely drivers", "bullets": drivers})

    related = news.latest(n=5, sym=sym) or news.latest(n=4, q=m["name"].split(" (")[0])
    if related:
        facts["news"] = [r["title"] for r in related]
        strong = [r for r in related if r.get("importance", 0) >= 50]
        if strong:
            facts["news_top"] = strong[0]["title"]
        sections.append({"h": "On the wire", "bullets": [f"{r['source']}: {r['title']}" for r in related[:4]]})
    reg = quant.regime()
    if reg.get("ready"):
        sections.append({"h": "Macro backdrop", "bullets": [
            f"Regime: {reg['regime']} ({reg['description'].lower()}), risk appetite {reg['risk_label']}.",
            reg["playbook"]]})
    return {"title": f"{m['code']} · {m['name']}", "sections": sections, "facts": facts, "entities": [sym]}


def overview() -> dict:
    p = quant.pulse()
    reg = quant.regime()
    sections = []
    pulse_b = []
    for k, label in (("global", "Global"), ("india", "India")):
        if p.get(k, {}).get("value") is not None:
            pulse_b.append(f"{label} Pulse {p[k]['value']:.0f}/100 — {p[k]['label']}.")
    if reg.get("ready"):
        pulse_b.append(f"Regime {reg['regime']} · risk appetite {reg['risk_label']} · {reg['playbook']}")
    sections.append({"h": "State of the market", "bullets": pulse_b})
    mv = []
    for cls, label in (({"index"}, "Indices"), ({"fx"}, "FX"), ({"commodity"}, "Commodities"), ({"crypto"}, "Crypto")):
        lo, hi = _movers(cls, 2)
        if hi:
            mv.append(f"{label}: leaders {', '.join(f'{q['code']} {_f(q['pct'])}%' for q in hi)}; "
                      f"laggards {', '.join(f'{q['code']} {_f(q['pct'])}%' for q in lo)}.")
    sections.append({"h": "Cross-asset movers", "bullets": mv})
    an = quant.anomalies(2.0)[:4]
    if an:
        sections.append({"h": "Statistical outliers", "bullets": [f"{a['code']} {_f(a['pct'])}% = {_f(a['z'], 1)}σ move." for a in an]})
    top = news.top(5)
    if top:
        sections.append({"h": "Top stories", "bullets": [f"{t['source']}: {t['title']}" for t in top]})
    risk = [c for c in geo.choke if c["status"] != "NORMAL"][:3]
    if risk:
        sections.append({"h": "Chokepoint radar", "bullets": [f"{c['name']} {c['status']} ({c['risk']:.0f}) — {'; '.join(c['drivers'][:2])}" for c in risk]})
    cal = macro.calendar(10)[:4]
    if cal:
        sections.append({"h": "Coming up", "bullets": [f"{e['date']} {e['time']} · {e['region']} {e['event']}" + (" (est.)" if e["est"] else "") for e in cal]})
    pool = [q for sym, q in markets.quotes.items() if BY_SYM.get(sym) and BY_SYM[sym].cls in ("index", "commodity", "crypto")
            and q.get("pct") is not None]
    pool.sort(key=lambda q: q["pct"], reverse=True)
    movers = [(pool[0]["sym"], pool[0]["pct"]), (pool[-1]["sym"], pool[-1]["pct"])] if len(pool) >= 2 else []
    return {"title": "Market overview", "sections": sections,
            "facts": {"pulse": p, "regime": reg.get("regime"), "movers": movers, "headline": top[0]["title"] if top else None}}


def compare(a: str, b: str) -> dict:
    qa, qb = markets.quotes.get(a, {}), markets.quotes.get(b, {})
    rets = markets.returns([a, b], n=250)
    bullets = []
    for s, q in ((a, qa), (b, qb)):
        bullets.append(f"{meta(s)['code']}: {_f(q.get('pct'))}% today, 1M {_f(q.get('m1'))}%, YTD {_f(q.get('ytd'))}%, vol {_f(q.get('vol'), 1, False)}%.")
    if a in rets and b in rets:
        c60 = rets.tail(60).corr().loc[a, b]
        c250 = rets.corr().loc[a, b]
        bullets.append(f"Correlation 60d {c60:+.2f} vs 250d {c250:+.2f}" + (" — a correlation break." if abs(c60 - c250) > 0.4 else "."))
    c60 = float(rets.tail(60).corr().loc[a, b]) if a in rets and b in rets else None
    return {"title": f"{meta(a)['code']} vs {meta(b)['code']}", "sections": [{"h": "Head to head", "bullets": bullets}],
            "facts": {"a": a, "b": b, "corr60": c60}}


SCEN_RX = re.compile(r"([+\-−]?\d+(?:\.\d+)?)\s*(%|percent|per cent|bp|bps|basis points?)", re.I)
DRIVER_WORDS = [  # spoken driver names -> (symbol, sign flip for "rupee"-style inverted quotes)
    (r"brent|oil|crude", "BZ=F", 1), (r"dollar index|dxy|the dollar|dollar", "DX-Y.NYB", 1),
    (r"yields?|treasur(?:y|ies)|10.year|ten.year|us10y|bond", "^TNX", 1), (r"rupee|inr", "INR=X", -1),
    (r"nasdaq|tech stocks|tech", "^IXIC", 1), (r"gold", "GC=F", 1),
]
DOWN_WORDS = re.compile(r"\b(falls?|fell|drops?|dropped|declines?|crash(?:es)?|plunges?|tumbles?|slumps?|sinks?|weakens?|down|lower|cuts?)\b", re.I)


def what_if(text: str) -> dict | None:
    """'what if Brent rises 20%', 'what if the rupee falls 5 percent and yields jump 50bp', 'Brent +20%'."""
    low = text.lower().replace("−", "-")
    shocks = {}
    clauses = re.split(r"\band\b|,|;", low)
    for clause in clauses:
        m = SCEN_RX.search(clause)
        if not m:
            continue
        val = float(m.group(1))
        unit = m.group(2)
        for pat, sym, flip in DRIVER_WORDS:
            if re.search(r"\b(" + pat + r")\b", clause):
                if DOWN_WORDS.search(clause) and val > 0:
                    val = -val
                if sym == "^TNX" and not unit.startswith("b"):
                    val = val * 100 if abs(val) <= 3 else val  # "yields rise 1%" -> 100bp
                shocks[sym] = val * flip  # rupee falls 5% == USD/INR +5%
                break
    if not shocks:
        return None
    res = quant.scenario(shocks)
    imp = res["impacts"]
    bullets = [f"{r['code']}: {_f(r['impact_pct'])}%" for r in imp[:4]] + ["…"] + [f"{r['code']}: {_f(r['impact_pct'])}%" for r in imp[-4:]]
    desc = ", ".join(f"{meta(s)['code']} {v:+g}{'bp' if s == '^TNX' else '%'}" for s, v in shocks.items())
    return {"title": f"Scenario · {desc}", "sections": [
        {"h": "Most hurt → most helped (India)", "bullets": bullets},
        {"h": "Method", "bullets": ["Propagated through 250-day multivariate betas of each sector on the global drivers. First-order, linear, no feedback loops."]}],
        "facts": res, "scenario": res}


async def _ollama(question: str, answer: dict) -> str | None:
    now = time.time()
    if now - _ollama_state["checked"] > 300:
        _ollama_state["checked"] = now
        try:
            async with httpx.AsyncClient(timeout=2) as c:
                tags = (await c.get(f"{OLLAMA_URL}/api/tags")).json()
            _ollama_state["models"] = [m["name"] for m in tags.get("models", [])]
            _ollama_state["ok"] = bool(_ollama_state["models"])
        except Exception:
            _ollama_state["ok"] = False
    if not _ollama_state["ok"]:
        return None
    model = OLLAMA_MODEL if any(m.startswith(OLLAMA_MODEL) for m in _ollama_state["models"]) else _ollama_state["models"][0]
    grounding = "\n".join(f"## {s['h']}\n" + "\n".join(f"- {b}" for b in s["bullets"]) for s in answer["sections"])
    prompt = (
        "You are ORACLE, a concise senior macro strategist inside a trading terminal. Answer the user's question "
        "using ONLY the facts below. Do not invent numbers. 4-7 sentences, plain prose, no disclaimers except that "
        "this is not investment advice if the user asks what to buy/sell.\n\n"
        f"FACTS:\n{grounding}\n\nQUESTION: {question}\nANSWER:"
    )
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{OLLAMA_URL}/api/generate", json={"model": model, "prompt": prompt, "stream": False,
                                                                  "options": {"temperature": 0.2}})
            return r.json().get("response", "").strip() or None
    except Exception as e:
        log.debug("ollama: %s", e)
        return None


def narrate(ans: dict, intent: str) -> str:
    """Spoken version for VEDA — conversational, rounded, built only from the answer's facts."""
    f = ans.get("facts", {})
    try:
        if intent == "explain" and ans.get("entities"):
            return speech.explain(ans["entities"][0], f)
        if intent == "overview":
            return speech.overview(f)
        if intent == "region":
            return speech.region(ans)
        if intent == "scenario":
            return speech.scenario(f)
        if intent == "compare":
            return speech.compare(f["a"], f["b"], f.get("corr60"))
        if intent == "regime":
            return speech.regime(f)
    except Exception as e:  # never let narration break an answer
        log.warning("narrator %s: %s", intent, e)
    return regions.spoken(ans, intent)


STOP = set("""what whats what's why how is are was were the a an of on in for to about with and or me tell show give
please veda vedha vada finverse can you could would doing today now right price prices stock stocks share shares
its it's it update latest happening going news quote chart performance performing looking look up down do does
did market markets hey hi ok okay""".split())


async def lookup(low: str) -> str | None:
    """Find a company/instrument named in free speech that isn't in the built-in universe."""
    words = [w for w in re.findall(r"[a-z0-9&.\-]+", low) if w not in STOP]
    if not 1 <= len(words) <= 4 or len(" ".join(words)) < 3:
        return None
    try:
        hits = await markets.search(" ".join(words))
    except Exception:
        return None
    hit = next((h for h in hits if h.get("cls") in ("equity", "etf", "index", "cryptocurrency", "future", "currency")), None)
    if not hit:
        return None
    sym = hit["sym"]
    if sym not in markets.quotes:
        try:
            q = await markets.quote_one(sym)
        except Exception:
            return None
        if not q or q.get("price") is None:
            return None
        markets.quotes[sym] = q
    if sym not in BY_SYM:
        EXTRA_NAMES[sym] = hit.get("name") or sym
    return sym


OVERVIEW_ASK = re.compile(r"\b(overview|summary|brief|big picture|market today|markets today|how are (the )?markets|market update)\b")


async def ask(question: str) -> dict:
    q = question.strip()
    low = q.lower()
    ents = find_entities(q)
    topic = topics.detect(low)
    spoken = None
    if topic in ("thanks", "help", "greet"):
        (ans, spoken), intent = topics.answer(topic, q), topic
    elif re.search(r"\b(what if|what happens if|scenario|shock|suppose|imagine)\b", low) and SCEN_RX.search(low):
        ans = await asyncio.to_thread(what_if, q)
        intent = "scenario"
        if ans is None:
            ans, intent = await asyncio.to_thread(overview), "overview"
    elif len(ents) >= 2 and re.search(r"\b(vs|versus|compare|against)\b", low):
        ans, intent = await asyncio.to_thread(compare, ents[0], ents[1]), "compare"
    elif re.search(r"\b(regime|cycle|stagflation|reflation|goldilocks)\b", low):
        reg = await asyncio.to_thread(quant.regime)
        ans = {"title": f"Regime · {reg.get('regime')}", "sections": [
            {"h": "Where we are", "bullets": [reg.get("description", ""), f"Growth z {reg.get('growth')}, inflation z {reg.get('inflation')}, confidence {reg.get('confidence')}."]},
            {"h": "Components", "bullets": [f"{c['label']}: {c['z']:+.2f}σ" for part in reg.get("components", {}).values() for c in part if c["z"] is not None]},
            {"h": "Textbook playbook", "bullets": [reg.get("playbook", "")]}], "facts": reg}
        intent = "regime"
    elif (reg_key := regions.detect(low)) and not re.search(r"\b(price of|chart|stock)\b", low):
        ans, intent = await asyncio.to_thread(regions.report, reg_key), "region"
    elif ents and not OVERVIEW_ASK.search(low) and not (topic in ("bonds", "rates", "inflation", "jobs") and BY_SYM.get(ents[0]) and BY_SYM[ents[0]].cls in ("rate", "etf")):
        ans, intent = await asyncio.to_thread(explain, ents[0]), "explain"
    elif topic and not OVERVIEW_ASK.search(low) and not (topic == "news" and "market" in low):
        (ans, spoken), intent = await asyncio.to_thread(topics.answer, topic, q), topic
    elif not OVERVIEW_ASK.search(low) and (sym := await lookup(low)):
        ans, intent = await asyncio.to_thread(explain, sym), "explain"
    else:
        ans, intent = await asyncio.to_thread(overview), "overview"
        if not OVERVIEW_ASK.search(low) and len(low.split()) >= 3:
            body = narrate(ans, intent).split(". ", 1)
            spoken = "I couldn't find a specific market in that, so here's the overall picture instead. " + (body[1] if len(body) > 1 else body[0])
    llm = await _ollama(q, ans) if intent not in ("thanks", "help", "greet") else None
    speech = regions.speakify(llm) if llm else (spoken or narrate(ans, intent))
    return {"q": q, "intent": intent, **{k: v for k, v in ans.items() if k != "facts"},
            "llm": llm, "spoken": speech, "engine": f"ollama:{OLLAMA_MODEL}" if llm else "finverse-analyst",
            "disclaimer": "Analytics, not investment advice."}


def briefing() -> dict:
    ov = overview()
    reg = quant.regime()
    tx = quant.transmission()
    rh = rhetoric.snapshot()
    f = macro.fed
    lines = [f"# FINVERSE DAILY BRIEF — {time.strftime('%A %d %B %Y, %H:%M')}", ""]
    for s in ov["sections"]:
        lines += [f"## {s['h']}", *[f"- {b}" for b in s["bullets"]], ""]
    impl = sorted(tx["targets"], key=lambda t: t["implied_pct"] or 0)
    if impl:
        lines += ["## India pre-open (transmission model)",
                  *[f"- {t['code']}: implied {_f(t['implied_pct'])}% from overnight global moves" for t in impl[:3] + impl[-3:]], ""]
    if f.get("target_to") is not None:
        lines += ["## Rates", f"- Fed funds target {f['target_from']:.2f}–{f['target_to']:.2f}%, EFFR {f['effr']}%."]
        cv = macro.curve.get("spreads", {})
        if cv:
            lines.append(f"- US curve: 2s10s {cv.get('2s10s')}bp, 3m10y {cv.get('3m10y')}bp.")
        lines.append("")
    m = rh.get("meter", {})
    lines += ["## Rhetoric", f"- Trump Meter heat {m.get('heat', 0)}/100 across {m.get('posts_24h', 0)} posts (24h).",
              f"- Historical study: {rh.get('study', {}).get('verdict', 'n/a')}", ""]
    lines += ["---", "_Generated by Finverse from live public data. Analytics, not investment advice._"]
    return {"markdown": "\n".join(lines), "sections": ov["sections"], "regime": reg.get("regime")}
