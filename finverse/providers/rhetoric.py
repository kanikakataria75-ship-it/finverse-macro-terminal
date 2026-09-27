"""Rhetoric Radar: political + central-bank communication, scored and put in context.

TRUMP : trumpstruth.org public mirror (real status IDs; no more 60s force-push spam)
FED / RBI / ECB : official press-release RSS, scored hawkish/dovish
Every post is paired with what history says: the corrected 4-year event study.
"""
import asyncio
import json
import logging
import re
import time
from collections import deque
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
from bs4 import BeautifulSoup

from ..analytics import nlp
from ..bus import bus
from ..config import STATIC_DATA
from ..store import store
from ..util import clean_text, client

log = logging.getLogger("finverse.rhetoric")

MIRROR = "https://www.trumpstruth.org/"
BANK_FEEDS = {
    "FED": ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    "RBI": ("Reserve Bank of India", "https://www.rbi.org.in/pressreleases_rss.xml"),
    "ECB": ("European Central Bank", "https://www.ecb.europa.eu/rss/press.html"),
}
POLICY_RX = re.compile(r"(monetary policy|fomc statement|federal open market committee|policy rate|"
                       r"repo rate|interest rate decision|monetary policy decisions|mpc)", re.I)
RATE_RX = re.compile(r"(repo rate|deposit facility rate|federal funds rate)[^.%]{0,80}?(\d+(?:\.\d+)?)\s*(?:per cent|%)", re.I)

# map research topics -> our topic codes
STUDY_TOPIC = {
    "TARIFFS": "Tariffs and trade", "CHINA": "China", "FED": "Federal Reserve and interest rates",
    "INFLATION": "Inflation", "ENERGY": "Oil and energy", "GEOPOLITICS": "War, sanctions and geopolitics",
    "EARNINGS": "Companies and individual stocks", "CRYPTO": "Cryptocurrency",
    "FISCAL": "Fiscal policy and government spending",
}
MARKET_TOPICS = set(STUDY_TOPIC)


def _load_study():
    p = STATIC_DATA / "rhetoric_study.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"summary": {}, "rows": []}


class Rhetoric:
    def __init__(self):
        self.posts: deque = deque(store.kv_get("rhetoric:posts", []), maxlen=60)
        self.banks: dict = store.kv_get("rhetoric:banks", {})
        self.study = _load_study()
        self._seen = {p["id"] for p in self.posts}

    # ---------------------------------------------------------------- study
    def history_for(self, topic_codes: list[str]) -> list[dict]:
        names = {STUDY_TOPIC[t] for t in topic_codes if t in STUDY_TOPIC}
        rows = [r for r in self.study["rows"] if r["topic"] in names and r["horizon"] == "1w"]
        rows.sort(key=lambda r: (not r["significant"], -abs(r["abnormal"])))
        return rows[:4]

    # ---------------------------------------------------------------- trump
    async def poll_trump(self, health):
        async with client(25) as c:
            r = await c.get(MIRROR)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        found = []
        for el in soup.find_all("div", class_="status")[:12]:
            url = el.get("data-status-url") or ""
            pid = url.rstrip("/").rsplit("/", 1)[-1] or None
            if not pid:
                continue
            content = el.find(class_="status__content")
            text = clean_text(content.get_text(" ", strip=True)) if content else ""
            meta = [a.get_text(strip=True) for a in el.find_all(class_="status-info__meta-item")]
            published = meta[1] if len(meta) > 1 else ""
            t = el.find("time")
            ts = None
            if t and t.get("datetime"):
                try:
                    ts = int(datetime.fromisoformat(t["datetime"]).timestamp() * 1000)
                except ValueError:
                    pass
            found.append((pid, text, published, url, ts))
        first_run = not self._seen
        fresh = [f for f in found if f[0] not in self._seen]
        for pid, text, published, url, ts in reversed(fresh):
            post = self._score(pid, text, published, url, ts)
            self._seen.add(pid)
            self.posts.appendleft(post)
            if not first_run and post["relevance"] > 0:
                tier = "CRITICAL" if post["heat"] >= 75 else ("HEAVY" if post["heat"] >= 50 else "SIGNIFICANT")
                bus.emit("RHETORIC", text[:280], tier=tier, asset="TRUMP", heat=post["heat"],
                         topics=post["topics"], polarity=post["polarity"], link=url)
        store.kv_set("rhetoric:posts", list(self.posts))
        if fresh:
            bus.publish("rhetoric", self.snapshot())
        health.ok(f"{len(self.posts)} posts · {len(fresh)} new")

    def _score(self, pid, text, published, url, ts=None) -> dict:
        media_only = not text
        tps = [] if media_only else nlp.topics(text)
        market = [t for t in tps if t in MARKET_TOPICS]
        pol = 0.0 if media_only else nlp.sentiment(text)
        inten = 0.0 if media_only else nlp.intensity(text)
        relevance = min(1.0, len(market) * 0.45 + (0.2 if nlp.entities(text) else 0))
        heat = int(round(min(100, relevance * 70 + inten * 30 + abs(pol) * 15))) if relevance else int(inten * 20)
        return {
            "id": pid, "text": text or "[media post — no text]", "published": published, "url": url,
            "seen_at": ts or int(time.time() * 1000), "topics": tps, "market_topics": market,
            "polarity": round(pol, 3), "intensity": inten, "relevance": round(relevance, 2), "heat": heat,
            "history": self.history_for(market),
        }

    # ---------------------------------------------------------------- banks
    async def poll_banks(self, health):
        async with client(25) as c:
            results = await asyncio.gather(*(c.get(u) for _, u in BANK_FEEDS.values()), return_exceptions=True)
        n_new = 0
        for (code, (name, _)), res in zip(BANK_FEEDS.items(), results):
            if isinstance(res, Exception) or res.status_code != 200:
                continue
            parsed = await asyncio.to_thread(feedparser.parse, res.content)
            prev_ids = {i["id"] for i in self.banks.get(code, {}).get("items", [])}
            items = []
            for e in parsed.entries[:15]:
                title = clean_text(e.get("title"), 200)
                summ = clean_text(e.get("summary"), 400)
                ts = time.time()
                if e.get("published"):
                    try:
                        ts = parsedate_to_datetime(e["published"]).timestamp()
                    except Exception:
                        pass
                text = f"{title}. {summ}"
                policy = bool(POLICY_RX.search(text))
                item = {"id": e.get("link") or title, "title": title, "summary": summ, "link": e.get("link", ""),
                        "ts": int(ts * 1000), "stance": nlp.stance(text), "policy": policy}
                m = RATE_RX.search(text)
                if m:
                    item["rate"] = float(m.group(2))
                items.append(item)
                if prev_ids and item["id"] not in prev_ids and time.time() - ts < 86400:
                    n_new += 1
                    bus.emit("CENTRAL BANK", f"{code}: {title}", tier="CRITICAL" if policy else "INFO",
                             asset=code, link=item["link"], stance=item["stance"])
            # stance only from genuine policy communication (statements, minutes, speeches)
            scored = [i for i in items if i["policy"] or "speech" in i["title"].lower()
                      or re.match(r"^[A-Z][\w.\s]+:", i["title"])][:8]
            avg = round(sum(i["stance"] for i in scored) / len(scored), 3) if scored else None
            old = self.banks.get(code, {})
            rate = next((i["rate"] for i in items if "rate" in i), None)
            rate_info = {"rate": rate, "rate_src": "press release"} if rate is not None else                 {"rate": old.get("rate"), "rate_src": old.get("rate_src"), "rate_asof": old.get("rate_asof")}
            self.banks[code] = {"name": name, "items": items, "stance": avg, "n_policy": len(scored),
                                **rate_info, "updated": int(time.time() * 1000)}
        await self._rates_from_headlines()
        store.kv_set("rhetoric:banks", self.banks)
        bus.publish("rhetoric", self.snapshot())
        health.ok(f"{len(self.banks)} banks · {n_new} new")

    async def _rates_from_headlines(self):
        """Policy-rate levels parsed from the latest wire headlines (labelled 'headline')."""
        verbs = r"(?:keeps?|kept|holds?|held|leaves?|left|maintains?|retains?|cuts?|hikes?|raises?|raised|lowers?|lowered|reduces?|reduced)"
        queries = {
            "RBI": ("RBI repo rate", verbs + r"[^%]{0,60}?repo rate[^%]{0,30}?(?:at|to)\s*(\d{1,2}(?:\.\d{1,2})?)\s*(?:%|per ?cent)"),
            "ECB": ("ECB deposit rate", verbs + r"[^%]{0,60}?(?:deposit (?:facility )?rate|rates?)[^%]{0,30}?(?:at|to)\s*(\d(?:\.\d{1,2})?)\s*(?:%|per ?cent)"),
        }
        speculative = re.compile(r"\b(could|may|might|likely|unlikely|expected|expects?|seen|forecast|poll|should|would|economists?|analysts?|why)\b", re.I)
        async with client(20) as c:
            for code, (q, rx) in queries.items():
                if code not in self.banks or self.banks[code].get("rate_src") == "press release":
                    continue
                try:
                    r = await c.get("https://news.google.com/rss/search?hl=en-IN&gl=IN&ceid=IN:en&q="
                                    + q.replace(" ", "+") + "+when:60d")
                    feed = await asyncio.to_thread(feedparser.parse, r.content)
                    best = None
                    for e in feed.entries[:40]:
                        title = e.get("title", "")
                        m = re.search(rx, title, re.I)
                        if not m or speculative.search(title):
                            continue
                        ts = parsedate_to_datetime(e["published"]).timestamp() if e.get("published") else 0
                        if not best or ts > best[0]:
                            best = (ts, float(m.group(1)), clean_text(e.get("title"), 160))
                    if best and 0 <= best[1] <= 20:
                        self.banks[code].update(rate=best[1], rate_src="headline", rate_asof=int(best[0] * 1000),
                                                rate_headline=best[2])
                except Exception as e:
                    log.debug("rate headline %s: %s", code, e)

    # ------------------------------------------------------------- snapshot
    def meter(self) -> dict:
        """TRUMP METER: recency-weighted heat of market-relevant posts (last 24h)."""
        now = time.time() * 1000
        num = den = pol = 0.0
        for p in self.posts:
            age_h = (now - p["seen_at"]) / 3600e3
            if age_h > 24:
                continue
            w = 0.5 ** (age_h / 6)
            num += p["heat"] * w
            pol += p["polarity"] * w * (p["relevance"] or 0.1)
            den += w
        return {"heat": int(num / den) if den else 0, "polarity": round(pol / den, 3) if den else 0.0,
                "posts_24h": sum(1 for p in self.posts if (now - p["seen_at"]) < 86400e3)}

    def snapshot(self) -> dict:
        return {"posts": list(self.posts)[:25], "meter": self.meter(), "banks": self.banks,
                "study": self.study.get("summary", {})}


rhetoric = Rhetoric()
