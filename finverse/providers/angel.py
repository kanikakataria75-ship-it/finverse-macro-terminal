"""Optional: Angel One SmartAPI real-time NSE ticks (uses your own broker credentials from .env).

Fixes vs legacy: started exactly once (the old code launched it in both server.py and
macro_pipeline.py -> double login, duplicate alerts), no DB connection per tick, and
callbacks hop back onto the event loop thread-safely.
"""
import asyncio
import logging
import threading
import time

from ..bus import bus
from ..config import ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_ENABLED, ANGEL_MPIN, ANGEL_TOTP
from .markets import markets

log = logging.getLogger("finverse.angel")
TOKENS = {"26000": "^NSEI", "26009": "^NSEBANK", "2885": "RELIANCE.NS", "11536": "TCS.NS", "1333": "HDFCBANK.NS"}


def configured() -> bool:
    return all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_MPIN, ANGEL_TOTP])


def _mute_smartapi():
    """SmartAPI logs whole failed requests - MPIN, TOTP, API key - to the console and to
    logs/<date>/app.log, and re-enables that file log in every constructor. Switch it off."""
    try:
        import logzero
        logzero.logfile(None)
        logzero.loglevel(logging.CRITICAL, update_custom_handlers=True)
    except Exception:
        pass


_LOGIN_ATTEMPTED = False  # one login attempt per process, ever: repeated bad MPINs lock the broker account


async def run(health):
    global _LOGIN_ATTEMPTED
    if not ANGEL_ENABLED:
        health.idle("disabled — set ANGEL_ENABLED=true in .env to enable")
        await asyncio.Event().wait()
    if not configured():
        health.idle("not configured (optional)")
        await asyncio.Event().wait()
    if _LOGIN_ATTEMPTED:
        health.idle("login already attempted this session — fix credentials and restart")
        await asyncio.Event().wait()
    try:
        import pyotp
        from SmartApi import SmartConnect
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2
    except ImportError:
        health.idle("smartapi-python not installed")
        await asyncio.Event().wait()

    loop = asyncio.get_running_loop()
    obj = SmartConnect(api_key=ANGEL_API_KEY)
    _mute_smartapi()
    _LOGIN_ATTEMPTED = True
    try:
        session = await asyncio.to_thread(obj.generateSession, ANGEL_CLIENT_ID, ANGEL_MPIN, pyotp.TOTP(ANGEL_TOTP).now())
    except Exception as e:
        session = {"status": False, "message": str(e)}
    if not session or not session.get("status"):
        # never retry a failed login automatically
        health.fail(f"login rejected: {(session or {}).get('message', 'unknown')} — not retrying")
        log.error("Angel One login rejected (%s). Not retrying; fix .env and restart.", (session or {}).get("message"))
        await asyncio.Event().wait()
    feed_token = obj.getfeedToken()
    sws = SmartWebSocketV2(session["data"]["jwtToken"], ANGEL_API_KEY, ANGEL_CLIENT_ID, feed_token)
    _mute_smartapi()
    anchors: dict = {}
    pending: dict = {}

    def flush():
        if pending:
            bus.publish("quotes", dict(pending))
            pending.clear()

    def handle(token, ltp, close):
        sym = TOKENS.get(token)
        if not sym:
            return
        prev = close or (markets.quotes.get(sym) or {}).get("prev") or ltp
        pending[sym] = markets.apply_live(sym, ltp, prev, "ANGEL")
        health.ok("streaming")
        base = anchors.setdefault(token, ltp)
        move = (ltp / base - 1) * 100
        if abs(move) >= 0.5:
            anchors[token] = ltp
            bus.emit("INSTITUTIONAL", f"{sym.replace('^', '')} {move:+.2f}% impulse since last print · LTP ₹{ltp:,.2f}",
                     tier="HEAVY" if abs(move) >= 0.75 else "SIGNIFICANT", asset=sym)

    def on_data(ws, msg):
        if isinstance(msg, dict) and "last_traded_price" in msg:
            ltp = msg["last_traded_price"] / 100.0
            close = (msg.get("closed_price") or 0) / 100.0 or None
            loop.call_soon_threadsafe(handle, str(msg.get("token", "")), ltp, close)

    def on_open(ws):
        sws.subscribe("finverse", 2, [{"exchangeType": 1, "tokens": list(TOKENS)}])  # 2 = QUOTE mode
        loop.call_soon_threadsafe(health.ok, "subscribed")

    def on_error(ws, err):
        loop.call_soon_threadsafe(health.warn, f"ws error: {str(err)[:60]}")

    sws.on_open, sws.on_data, sws.on_error = on_open, on_data, on_error
    threading.Thread(target=sws.connect, daemon=True, name="angel-ws").start()
    while True:
        await asyncio.sleep(1)
        flush()
