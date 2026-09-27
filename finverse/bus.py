"""In-process pub/sub. Replaces the old Postgres LISTEN/NOTIFY hop: providers publish,
the WebSocket gateway fans out to every connected terminal."""
import asyncio
import itertools
import logging
import time
from collections import deque

from .store import store
from .util import now_ms

log = logging.getLogger("finverse.bus")

TIERS = ("INFO", "SIGNIFICANT", "HEAVY", "CRITICAL")


class Bus:
    def __init__(self):
        self._subs: set[asyncio.Queue] = set()
        self.intel: deque = deque(maxlen=400)
        self._stamps: deque = deque()
        self._seq = itertools.count()
        self._listeners: list = []  # sync callbacks (alerts engine) on intel events

    # subscriptions -------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subs.discard(q)

    @property
    def clients(self) -> int:
        return len(self._subs)

    def publish(self, channel: str, data):
        msg = {"ch": channel, "data": data}
        for q in list(self._subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                # slow client: drop the oldest message rather than blocking producers
                try:
                    q.get_nowait()
                    q.put_nowait(msg)
                except Exception:
                    pass

    def on_intel(self, fn):
        self._listeners.append(fn)

    # intel events --------------------------------------------------------------
    def tape_speed(self) -> int:
        """Events per minute (the old 'APM' metric, now deduplicated)."""
        cutoff = time.time() - 60
        while self._stamps and self._stamps[0] < cutoff:
            self._stamps.popleft()
        return len(self._stamps)

    def emit(self, tag: str, message: str, tier: str = "INFO", asset: str = "", **extra) -> dict:
        tier = tier if tier in TIERS else "INFO"
        ev = {
            "id": f"{now_ms()}-{next(self._seq)}",
            "ts": now_ms(),
            "tag": tag.upper(),
            "tier": tier,
            "asset": asset,
            "message": message,
            **extra,
        }
        self.intel.append(ev)
        self._stamps.append(time.time())
        try:
            store.intel_add(ev)
        except Exception as e:  # persistence must never break the stream
            log.warning("intel persist failed: %s", e)
        speed = self.tape_speed()
        self.publish("intel", {**ev, "tape_speed": speed})
        for fn in self._listeners:
            try:
                fn(ev)
            except Exception as e:
                log.warning("intel listener failed: %s", e)
        return ev

    def load_history(self):
        for ev in store.intel_recent(250):
            self.intel.append(ev)


bus = Bus()
