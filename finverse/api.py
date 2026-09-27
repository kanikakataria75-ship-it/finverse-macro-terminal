"""HTTP + WebSocket gateway. Serves the terminal UI from /web and the API under /api.

Security posture (fixes from the audit):
- binds to 127.0.0.1 by default, no wildcard CORS (UI is same-origin)
- no unauthenticated ingest endpoint (scrapers run in-process now)
- all inputs validated; the UI renders every string as text, never HTML
"""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from . import voice as veda
from .analytics import oracle, quant
from .analytics.alerts import alerts, describe, parse
from .bus import bus
from .config import WEB_DIR
from .engine import engine
from .providers.crypto import crypto
from .providers.geo import geo
from .providers.macro import macro
from .providers.markets import RANGES, markets
from .providers.news import news
from .providers.rhetoric import rhetoric
from .store import store
from .universe import DRIVERS, MATRIX, all_meta, meta, resolve

log = logging.getLogger("finverse.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await engine.start()
    yield
    await engine.stop()


app = FastAPI(title="Finverse Macro Terminal", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def no_stale_assets(request, call_next):
    """Revalidate UI assets on every load so upgrades are picked up (ETags keep it cheap)."""
    resp = await call_next(request)
    path = request.url.path
    if not path.startswith("/api") and not path.startswith("/vendor"):
        resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp


def _sym(raw: str) -> str:
    s = resolve(raw) or raw.strip().upper()
    if not s or len(s) > 24 or any(c in s for c in " /\\?#"):
        raise HTTPException(400, "invalid symbol")
    return s


# ---------------------------------------------------------------- snapshot
@app.get("/api/health")
def health():
    return {"version": __version__, **engine.health_snapshot()}


@app.get("/api/snapshot")
def snapshot():
    """Everything the terminal needs to paint its first frame."""
    return {
        "version": __version__, "universe": all_meta(), "matrix": MATRIX, "drivers": DRIVERS,
        "quotes": markets.snapshot(), "macro": macro.snapshot(), "analytics": engine.analytics,
        "rhetoric": rhetoric.snapshot(), "geo": geo.snapshot(), "news": news.latest(80), "top": news.top(10),
        "topics": news.topic_heat(), "intel": list(bus.intel)[-200:], "crypto": crypto.snapshot(),
        "health": engine.health_snapshot(), "server_time": int(time.time() * 1000),
    }


@app.get("/api/quotes")
def quotes():
    return markets.snapshot()


# ------------------------------------------------------------- securities
@app.get("/api/search")
async def search(q: str = Query(..., min_length=1, max_length=40)):
    return await markets.search(q)


@app.get("/api/chart/{sym}")
async def chart(sym: str, range: str = "1Y"):
    if range not in RANGES:
        raise HTTPException(400, "bad range")
    return await markets.chart(_sym(sym), range)


@app.get("/api/security/{sym}")
async def security(sym: str):
    s = _sym(sym)
    q = await markets.quote_one(s)
    try:
        prof = await asyncio.wait_for(markets.profile(s), 12)
    except Exception:
        prof = {}
    fit = await asyncio.to_thread(quant.betas_for, s) if s in markets.closes else None
    betas = None
    if fit:
        coef, se, r2, n, _ = fit
        betas = {"r2": round(r2, 3), "n": n, "betas": {d: {"code": meta(d)["code"], "b": round(float(coef[k + 1]), 4)}
                                                        for k, d in enumerate([d for d in DRIVERS if d in markets.closes])}}
    m = meta(s)
    rel = news.latest(12, sym=s) or news.latest(8, q=(prof.get("shortName") or m["name"]).split(" ")[0])
    return {"meta": m, "quote": q, "profile": prof, "macro_betas": betas, "news": rel}


@app.get("/api/options/{sym}")
async def options(sym: str, expiry: str | None = None):
    try:
        return await markets.options(_sym(sym), expiry)
    except Exception as e:
        return {"sym": sym, "error": f"Options unavailable: {e}"[:160], "expiries": []}


# ------------------------------------------------------------------ feeds
@app.get("/api/news")
def get_news(q: str | None = None, topic: str | None = None, sym: str | None = None, n: int = 80, top: bool = False):
    if top:
        return news.top(min(n, 50))
    return news.latest(min(n, 300), q=q, topic=topic, sym=sym)


@app.get("/api/news/health")
def news_health():
    return news.feed_health


@app.get("/api/intel")
def intel(limit: int = 200):
    return list(bus.intel)[-min(limit, 400):]


@app.get("/api/macro")
def get_macro():
    return macro.snapshot()


@app.get("/api/curve/surface")
def curve_surface():
    return macro.surface()


@app.get("/api/geo")
def get_geo():
    return geo.snapshot()


@app.get("/api/crypto")
def get_crypto():
    return crypto.snapshot()


@app.get("/api/rhetoric")
def get_rhetoric():
    return rhetoric.snapshot()


@app.get("/api/rhetoric/study")
def rhetoric_study():
    return rhetoric.study


# --------------------------------------------------------------- analytics
@app.get("/api/analytics")
def analytics():
    return engine.analytics


@app.get("/api/correlation")
async def correlation(syms: str | None = None, short: int = 60, long: int = 250):
    lst = [_sym(s) for s in syms.split(",")][:24] if syms else None
    return await asyncio.to_thread(quant.correlation, lst, max(20, min(short, 250)), max(60, min(long, 500)))


class ScenarioIn(BaseModel):
    shocks: dict[str, float] = Field(default_factory=dict)


@app.post("/api/scenario")
async def scenario(body: ScenarioIn):
    shocks = {k: max(-80.0, min(300.0, v)) for k, v in body.shocks.items() if k in DRIVERS}
    return await asyncio.to_thread(quant.scenario, shocks)


@app.get("/api/eventstudy")
async def eventstudy(trigger: str, target: str, threshold: float, op: str = "gt", decluster: int = 5):
    if op not in ("gt", "lt"):
        raise HTTPException(400, "op must be gt|lt")
    return await asyncio.to_thread(quant.event_study, _sym(trigger), op, threshold, _sym(target),
                                   (1, 5, 20), max(1, min(decluster, 30)))


class AskIn(BaseModel):
    q: str = Field(..., min_length=2, max_length=400)


@app.post("/api/oracle")
async def ask(body: AskIn):
    return await oracle.ask(body.q)


@app.get("/api/briefing")
async def briefing():
    return await asyncio.to_thread(oracle.briefing)


@app.get("/api/briefing.md", response_class=PlainTextResponse)
async def briefing_md():
    b = await asyncio.to_thread(oracle.briefing)
    return PlainTextResponse(b["markdown"], headers={"Content-Disposition": 'attachment; filename="finverse-brief.md"'})


# ------------------------------------------------------------------ voice
@app.get("/api/voice/config")
def voice_config():
    return veda.config()


class TTSIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=600)
    voice: str | None = Field(None, max_length=60)
    rate: str = Field("+2%", pattern=r"^[+-]\d{1,2}%$")
    pitch: str = Field("-1Hz", pattern=r"^[+-]\d{1,2}Hz$")


@app.post("/api/voice/tts")
async def voice_tts(body: TTSIn):
    try:
        audio = await asyncio.wait_for(veda.synth(body.text, body.voice, body.rate, body.pitch), 25)
    except Exception as e:
        raise HTTPException(503, f"neural voice unavailable: {type(e).__name__}")
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})


# ----------------------------------------------------- watchlist/portfolio
class WatchIn(BaseModel):
    symbol: str = Field(..., max_length=24)


@app.get("/api/watchlist")
def watchlist():
    rows = store.query("SELECT symbol, added FROM watchlist ORDER BY added")
    return [{**r, **meta(r["symbol"]), "quote": markets.quotes.get(r["symbol"])} for r in rows]


@app.post("/api/watchlist")
async def watch_add(body: WatchIn):
    s = _sym(body.symbol)
    store.execute("INSERT OR IGNORE INTO watchlist(symbol, added) VALUES(?,?)", (s, time.time()))
    return {"ok": True, "symbol": s}


@app.delete("/api/watchlist/{sym}")
def watch_del(sym: str):
    store.execute("DELETE FROM watchlist WHERE symbol=?", (sym,))
    return {"ok": True}


class HoldingIn(BaseModel):
    symbol: str = Field(..., max_length=24)
    qty: float = Field(..., gt=0, lt=1e9)
    cost: float = Field(..., gt=0, lt=1e9)


@app.get("/api/portfolio")
async def portfolio():
    rows = store.query("SELECT id, symbol, qty, cost FROM holdings ORDER BY id")
    for r in rows:
        if r["symbol"] not in markets.quotes:
            try:
                markets.quotes[r["symbol"]] = await markets.quote_one(r["symbol"])
            except Exception:
                pass
    return await asyncio.to_thread(quant.portfolio_risk, rows)


@app.post("/api/portfolio")
def holding_add(body: HoldingIn):
    s = _sym(body.symbol)
    store.execute("INSERT INTO holdings(symbol, qty, cost, added) VALUES(?,?,?,?)", (s, body.qty, body.cost, time.time()))
    return {"ok": True}


@app.delete("/api/portfolio/{hid}")
def holding_del(hid: int):
    store.execute("DELETE FROM holdings WHERE id=?", (hid,))
    return {"ok": True}


# ------------------------------------------------------------------ alerts
class AlertIn(BaseModel):
    text: str | None = Field(None, max_length=120)
    rule: dict | None = None


@app.get("/api/alerts")
def alerts_list():
    return alerts.list()


@app.post("/api/alerts")
def alerts_add(body: AlertIn):
    rule = body.rule or (parse(body.text) if body.text else None)
    if not rule:
        raise HTTPException(400, "Could not parse alert. Try: BTC > 120000 · NIFTY PCT < -1.5 · Z 3 · NEWS hormuz · LIQ 2M · HEAT 70")
    return alerts.add(rule)


@app.delete("/api/alerts/{rid}")
def alerts_del(rid: int):
    alerts.delete(rid)
    return {"ok": True}


@app.post("/api/alerts/{rid}/toggle")
def alerts_toggle(rid: int, enabled: bool = True):
    alerts.toggle(rid, enabled)
    return {"ok": True}


# --------------------------------------------------------------- websocket
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    q = bus.subscribe()

    async def pump():
        while True:
            msg = await q.get()
            await websocket.send_text(json.dumps(msg, default=str))

    sender = asyncio.create_task(pump())
    try:
        while True:
            raw = await websocket.receive_text()
            if raw == "ping":
                await websocket.send_text('{"ch":"pong"}')
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.debug("ws closed: %s", e)
    finally:
        sender.cancel()
        bus.unsubscribe(q)


# ------------------------------------------------------------------ static
@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
