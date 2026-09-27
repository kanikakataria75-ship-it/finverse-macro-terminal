import math
import re
import time
from datetime import datetime, timezone
from html import unescape

import httpx

from .config import USER_AGENT

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def now_ms() -> int:
    return int(time.time() * 1000)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def clean_text(s: str | None, limit: int | None = None) -> str:
    """Strip HTML and collapse whitespace. Output is plain text; the UI still escapes it."""
    if not s:
        return ""
    s = _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", s))).strip()
    if limit and len(s) > limit:
        s = s[: limit - 1].rsplit(" ", 1)[0] + "…"
    return s


def finite(x, nd=4):
    """JSON-safe float (NaN/inf -> None)."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd)


def client(timeout: float = 20.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
    )


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
