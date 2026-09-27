"""Local, transparent NLP: finance sentiment, hawk/dove stance, topic + entity tagging.

No model downloads, no API keys. The lexicons are compact, auditable and tuned for
headlines (Loughran-McDonald-inspired polarity + market-specific verbs).
"""
import re

from ..universe import UNIVERSE

POS = set("""
beat beats surge surges surged soar soars soared rally rallies rallied gain gains gained jump jumps jumped
climb climbs climbed rise rises rose record high highs upgrade upgrades upgraded boost boosts boosted
strong stronger strength robust growth grow grows expand expands expansion recover recovers recovery
rebound rebounds rebounded outperform outperforms profit profits profitable optimism optimistic bullish
breakthrough approve approves approved approval deal deals agreement ceasefire truce peace easing ease
eases stimulus win wins won accelerate accelerates beat-estimates upbeat positive resilient
agree agrees agreed
""".split())

NEG = set("""
miss misses missed plunge plunges plunged crash crashes crashed tumble tumbles tumbled slump slumps slumped
fall falls fell drop drops dropped sink sinks sank slide slides slid decline declines declined loss losses
downgrade downgrades downgraded weak weaker weakness recession slowdown contraction contract default defaults
bankruptcy bankrupt fraud probe investigation lawsuit sued sanction sanctions tariff tariffs war wars attack
attacks attacked strike strikes missile missiles invasion invade conflict crisis turmoil selloff sell-off
fear fears panic warn warns warning layoffs layoff inflation inflationary shortage disruption
disrupted halt halts halted ban bans banned threat threatens threatened escalate escalates escalation
job-cuts
bearish volatile volatility risk risks downturn collapse collapsed hawkish shutdown deficit
""".split())

NEGATORS = {"not", "no", "never", "without", "fails", "failed", "lack", "hardly"}
INTENSIFIERS = {"sharply": 1.6, "massive": 1.6, "record": 1.4, "biggest": 1.5, "steep": 1.4, "huge": 1.5,
                "historic": 1.4, "severe": 1.5, "tremendous": 1.3, "total": 1.2, "very": 1.2}

HAWK = set("""
hike hikes hiking tighten tightening restrictive inflation vigilant vigilance elevated persistent upside
withdrawal accommodation-withdrawal hawkish higher-for-longer overheating tight firm firmly curb curbing
reduce-balance-sheet quantitative-tightening
""".split())
DOVE = set("""
cut cuts cutting ease easing accommodative accommodation support supportive stimulus lower dovish pause
patient patience slowdown softening weaken weakening downside unemployment liquidity injection
growth-concerns moderate moderating disinflation
""".split())

URGENT = re.compile(r"\b(breaking|urgent|flash|just in|emergency|halted|crash|plunges?|soars?|record|"
                    r"default|war|invasion|missile|sanctions?|rate (hike|cut)|surprise|shock|collapse)\b", re.I)

TOPICS = {
    "TARIFFS": r"\b(tariffs?|trade war|duties|import tax|usmca|wto)\b",
    "CHINA": r"\b(china|chinese|beijing|xi jinping|yuan|pboc)\b",
    "FED": r"\b(fed|federal reserve|powell|fomc|rate cut|rate hike|interest rates?)\b",
    "RBI": r"\b(rbi|reserve bank of india|repo rate|mpc|malhotra)\b",
    "INFLATION": r"\b(inflation|cpi|ppi|prices|cost of living)\b",
    "ENERGY": r"\b(oil|crude|brent|opec|gas|lng|energy|gasoline|refiner)\b",
    "GEOPOLITICS": r"\b(war|sanctions?|military|missile|ukraine|russia|israel|gaza|iran|nato|taiwan|houthi|strike)\b",
    "EARNINGS": r"\b(earnings|profit|revenue|q[1-4]|quarterly|results|guidance|eps)\b",
    "CRYPTO": r"\b(crypto|bitcoin|btc|ethereum|stablecoin|etf inflows?)\b",
    "FISCAL": r"\b(budget|deficit|debt ceiling|stimulus|tax cuts?|spending bill|fiscal)\b",
    "INDIA": r"\b(india|indian|sensex|nifty|rupee|sebi|modi)\b",
    "TECH": r"\b(ai|chip|chips|semiconductor|nvidia|openai|data center)\b",
}
_TOPIC_RE = {k: re.compile(v, re.I) for k, v in TOPICS.items()}

# entity dictionary built from the instrument universe (aliases + names)
_AMBIGUOUS = {"real", "energy", "tech", "consumer", "auto", "autos", "banks", "media", "metal", "metals",
              "financials", "yields", "franc", "won", "peso", "rand", "lira", "loonie", "aussie", "meta",
              "cable", "treasury", "volatility", "sol", "eth", "itc", "ioc", "tips", "pharma", "realty",
              "psu bank", "hcl", "titan", "indigo", "corn", "sugar", "coffee", "wheat", "euro"}
_ENTITY: list[tuple[re.Pattern, str]] = []
for inst in UNIVERSE:
    names = {a for a in inst.aliases if len(a) >= 3 and a not in _AMBIGUOUS}
    if len(inst.name) > 4 and inst.cls != "etf":
        names.add(inst.name.lower())
    for n in names:
        _ENTITY.append((re.compile(r"\b" + re.escape(n) + r"\b", re.I), inst.sym))

_WORD = re.compile(r"[a-z][a-z\-']+")


def sentiment(text: str) -> float:
    """Polarity in [-1, 1]."""
    words = _WORD.findall(text.lower())
    score, hits = 0.0, 0
    for i, w in enumerate(words):
        pol = 1 if w in POS else (-1 if w in NEG else 0)
        if not pol:
            continue
        window = words[max(0, i - 3):i]
        if any(n in NEGATORS for n in window):
            pol = -pol
        mult = max([INTENSIFIERS.get(x, 1.0) for x in window] + [1.0])
        score += pol * mult
        hits += 1
    if not hits:
        return 0.0
    return max(-1.0, min(1.0, score / (hits + 1.5)))


def stance(text: str) -> float:
    """Central-bank stance: +1 hawkish, -1 dovish."""
    words = _WORD.findall(text.lower())
    h = sum(1 for w in words if w in HAWK)
    d = sum(1 for w in words if w in DOVE)
    if "unchanged" in words or "hold" in words or "holds" in words:
        d += 0.25
        h += 0.25
    if h + d == 0:
        return 0.0
    return round((h - d) / (h + d), 3)


def topics(text: str) -> list[str]:
    return [k for k, rx in _TOPIC_RE.items() if rx.search(text)]


def entities(text: str) -> list[str]:
    out = []
    for rx, sym in _ENTITY:
        if sym not in out and rx.search(text):
            out.append(sym)
    return out[:6]


def urgency(text: str) -> int:
    return len(URGENT.findall(text))


def intensity(text: str) -> float:
    """Rhetorical intensity 0..1 from CAPS ratio, exclamations and absolutes."""
    letters = [c for c in text if c.isalpha()]
    caps = sum(1 for c in letters if c.isupper()) / max(1, len(letters))
    excl = min(text.count("!"), 5) / 5
    absolutes = len(re.findall(r"\b(never|always|total|complete|biggest|worst|best|ever|immediately)\b", text, re.I))
    return round(min(1.0, caps * 1.2 + excl * 0.35 + min(absolutes, 4) * 0.08), 3)
