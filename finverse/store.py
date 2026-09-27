"""SQLite persistence (WAL). Zero setup, single file at data/finverse.db."""
import json
import sqlite3
import threading
import time
from typing import Any

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY, value TEXT NOT NULL, updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS intel (
    id TEXT PRIMARY KEY, ts INTEGER NOT NULL, tag TEXT, tier TEXT, body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intel_ts ON intel(ts);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, rule TEXT NOT NULL, enabled INTEGER DEFAULT 1,
    created REAL NOT NULL, last_fired REAL DEFAULT 0, fire_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY, added REAL NOT NULL, note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, qty REAL NOT NULL,
    cost REAL NOT NULL, added REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, body TEXT NOT NULL, created REAL NOT NULL
);
"""


class Store:
    def __init__(self, path=DB_PATH):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(SCHEMA)
        self._db.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._db.execute(sql, params)
            self._db.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, params).fetchall()]

    # key/value cache ---------------------------------------------------------
    def kv_set(self, key: str, value: Any):
        self.execute(
            "INSERT INTO kv(key,value,updated) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
            (key, json.dumps(value, default=str), time.time()),
        )

    def kv_get(self, key: str, default=None, max_age: float | None = None):
        rows = self.query("SELECT value, updated FROM kv WHERE key=?", (key,))
        if not rows:
            return default
        if max_age is not None and time.time() - rows[0]["updated"] > max_age:
            return default
        return json.loads(rows[0]["value"])

    # intel log ---------------------------------------------------------------
    def intel_add(self, ev: dict):
        self.execute(
            "INSERT OR IGNORE INTO intel(id,ts,tag,tier,body) VALUES(?,?,?,?,?)",
            (ev["id"], ev["ts"], ev.get("tag"), ev.get("tier"), json.dumps(ev)),
        )

    def intel_recent(self, limit=250) -> list[dict]:
        rows = self.query("SELECT body FROM intel ORDER BY ts DESC LIMIT ?", (limit,))
        return [json.loads(r["body"]) for r in rows][::-1]

    def intel_prune(self, keep_days=14):
        cutoff = int((time.time() - keep_days * 86400) * 1000)
        self.execute("DELETE FROM intel WHERE ts < ?", (cutoff,))


store = Store()
