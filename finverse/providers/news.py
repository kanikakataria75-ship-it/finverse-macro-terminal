"""Multi-source news wire: 18 free RSS feeds -> dedup -> tag -> score -> stream.

Stories confirmed by several outlets are merged and gain importance ("confirmations").
Only plain text leaves this module; links are passed through for click-out.
"""
import asyncio
import hashlib
import logging
import re
import time
from collections import deque
from email.utils import parsedate_to_datetime

import feedparser

from ..analytics import nlp
from ..bus import bus
from ..util import clean_text, client, jaccard, tokens

log = logging.getLogger("finverse.news")

JUNK = re.compile(r"(fund info|direct plan|regular plan|\(g\)|\bnav\b|horoscope|lottery|recipe|quiz|photos:|in pics|watch:)", re.I)
CONFLICT_RX = re.compile(r"\b(airstrikes?|air strikes?|shelling|militants?|insurgents?|rebels?|clash(es)?|killed|bomb(s|ing|ings)?|"
                         r"offensive|troops|missiles?|drone strikes?|attacks?|war|ceasefire|hostages?|gunmen|fighting|invasion)\b", re.I)
G = "https://news.google.com/rss/search?hl=en-IN&gl=IN&ceid=IN:en&q="
FEEDS = [
    # (source, url, tier weight, region)
    ("ET Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", 1.0, "IN"),
    ("ET Economy", "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms", 0.9, "IN"),
    ("Livemint", "https://www.livemint.com/rss/markets", 0.9, "IN"),
    ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss", 0.9, "IN"),
    ("BusinessLine", "https://www.thehindubusinessline.com/markets/feeder/default.rss", 0.8, "IN"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", 1.0, "US"),
    ("CNBC Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html", 0.9, "US"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", 0.9, "US"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex", 0.7, "US"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", 0.9, "GL"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", 0.8, "GL"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", 0.8, "GL"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", 0.8, "CRYPTO"),
    ("Reuters (GN)", G + "site:reuters.com+markets+when:1d", 1.0, "GL"),
    ("GN: Central Banks", G + "(fed+OR+rbi+OR+ecb)+interest+rates+when:1d", 0.8, "GL"),
    ("GN: Oil", G + "crude+oil+OR+opec+when:1d", 0.8, "GL"),
    ("GN: Geopolitics", G + "sanctions+OR+military+OR+ceasefire+markets+when:1d", 0.7, "GL"),
    ("GN: India Markets", G + "sensex+OR+nifty+when:1d", 0.8, "IN"),
]


class News:
    def __init__(self):
        self.items: deque = deque(maxlen=600)
        self.feed_health: dict = {}
        self._seen: set = set()
        self._warm = False

    async def _fetch(self, c, name, url):
        t0 = time.time()
        try:
            r = await c.get(url)
            r.raise_for_status()
            parsed = await asyncio.to_thread(feedparser.parse, r.content)
            self.feed_health[name] = {"ok": True, "n": len(parsed.entries), "ms": int((time.time() - t0) * 1000),
                                      "at": int(time.time())}
            return name, parsed.entries[:30]
        except Exception as e:
            self.feed_health[name] = {"ok": False, "err": str(e)[:80], "at": int(time.time())}
            return name, []

    async def poll(self, health):
        async with client(20) as c:
            results = await asyncio.gather(*(self._fetch(c, n, u) for n, u, *_ in FEEDS))
        meta = {n: (w, reg) for n, _, w, reg in FEEDS}
        fresh = []
        for name, entries in results:
            w, reg = meta[name]
            for e in entries:
                item = self._build(name, w, reg, e)
                if item:
                    fresh.append(item)
        fresh.sort(key=lambda x: x["ts"])
        new_items = []
        for it in fresh:
            merged = self._merge(it)
            if merged is None:
                self.items.append(it)
                new_items.append(it)
        ok = sum(1 for v in self.feed_health.values() if v.get("ok"))
        health.ok(f"{ok}/{len(FEEDS)} feeds · {len(self.items)} stories")
        if new_items:
            bus.publish("news", new_items[-40:])
            if not self._warm:  # first poll only primes the wire; don't flood the intel feed
                self._warm = True
                return
            for it in new_items:
                if it["importance"] >= 70 and time.time() * 1000 - it["ts"] < 3 * 3600e3:
                    tier = "CRITICAL" if it["importance"] >= 88 else ("HEAVY" if it["importance"] >= 80 else "SIGNIFICANT")
                    bus.emit("NEWS", it["title"], tier=tier, asset=(it["entities"] or [""])[0],
                             source=it["source"], link=it["link"], sentiment=it["sentiment"])

    def _build(self, source, weight, region, e):
        title = clean_text(e.get("title"), 220)
        if not title or len(title) < 12:
            return None
        if " - " in title and source.startswith(("GN", "Reuters")):
            title, _, outlet = title.rpartition(" - ")
            source = f"{outlet.strip()[:24]}"
        if JUNK.search(title):
            return None
        key = hashlib.sha1(title.lower().encode()).hexdigest()[:16]
        if key in self._seen:
            return None
        self._seen.add(key)
        ts = time.time()
        for fld in ("published", "updated"):
            if e.get(fld):
                try:
                    ts = parsedate_to_datetime(e[fld]).timestamp()
                    break
                except Exception:
                    pass
        if time.time() - ts > 36 * 3600:
            return None
        summary = clean_text(e.get("summary"), 320)
        text = f"{title}. {summary}"
        sent = round(nlp.sentiment(text), 3)
        tps = nlp.topics(text)
        ents = nlp.entities(title)
        urg = nlp.urgency(title)
        age_h = max(0.0, (time.time() - ts) / 3600)
        importance = (
            46 * weight + 14 * min(urg, 2) + 6 * min(len(ents), 3) + 5 * min(len(tps), 3)
            + 14 * abs(sent) - 2 * min(age_h, 8)
        )
        return {
            "id": key, "ts": int(ts * 1000), "title": title, "summary": summary, "source": source,
            "link": e.get("link", ""), "region": region, "sentiment": sent, "topics": tps,
            "entities": ents, "importance": int(max(0, min(100, importance))), "confirmations": 1,
            "_tok": tokens(title),
        }

    def _merge(self, it):
        for old in reversed(self.items):
            if abs(old["ts"] - it["ts"]) > 12 * 3600e3:
                continue
            if jaccard(old["_tok"], it["_tok"]) >= 0.55:
                if it["source"] not in old.get("also", []) and it["source"] != old["source"]:
                    old.setdefault("also", []).append(it["source"])
                    old["confirmations"] += 1
                    old["importance"] = min(100, old["importance"] + 8)
                return old
        return None

    def latest(self, n=80, q: str | None = None, topic: str | None = None, sym: str | None = None) -> list[dict]:
        rows = list(self.items)
        if q:
            ql = q.lower()
            rows = [r for r in rows if ql in r["title"].lower() or ql in r["summary"].lower()]
        if topic:
            rows = [r for r in rows if topic.upper() in r["topics"]]
        if sym:
            rows = [r for r in rows if sym in r["entities"]]
        rows.sort(key=lambda r: r["ts"], reverse=True)
        return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows[:n]]

    def top(self, n=12) -> list[dict]:
        cutoff = time.time() * 1000 - 18 * 3600e3
        rows = [r for r in self.items if r["ts"] >= cutoff]
        rows.sort(key=lambda r: (r["importance"], r["ts"]), reverse=True)
        return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows[:n]]

    def country_share(self, aliases: list[str], hours: int = 36) -> tuple[int, int]:
        """(stories mentioning the country, of which about armed conflict) over the wire."""
        rx = re.compile(r"\b(" + "|".join(re.escape(a) for a in aliases) + r")\b", re.I)
        cutoff = time.time() * 1000 - hours * 3600e3
        mentions = conflict = 0
        for r in self.items:
            if r["ts"] < cutoff:
                continue
            text = f"{r['title']} {r['summary']}"
            if rx.search(text):
                mentions += 1
                if CONFLICT_RX.search(text):
                    conflict += 1
        return mentions, conflict

    def topic_heat(self) -> dict:
        cutoff = time.time() * 1000 - 24 * 3600e3
        heat: dict = {}
        for r in self.items:
            if r["ts"] < cutoff:
                continue
            for t in r["topics"]:
                h = heat.setdefault(t, {"n": 0, "sent": 0.0})
                h["n"] += 1
                h["sent"] += r["sentiment"]
        return {k: {"n": v["n"], "sent": round(v["sent"] / v["n"], 3)} for k, v in
                sorted(heat.items(), key=lambda kv: -kv[1]["n"])}


news = News()
