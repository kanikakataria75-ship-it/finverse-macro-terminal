import os
import sys
import logging
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict
import macro_pipeline
from macro_pipeline import LIVE_TICKER_CACHE, LIVE_TICKER_LOCK, pipeline_angel_one_ws

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
    import asyncpg
    import uvicorn
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Error: Missing dependency. {e}")
    sys.exit(1)

import httpx

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [GATEWAY] - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Finverse Macro Bridge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_HOST = "localhost"
DB_NAME = "finverse"
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASSWORD")
DB_PORT = "5432"

class IngestPayload(BaseModel):
    post_id: str
    timestamp: str
    raw_text: str
    source: str = "TRUTH_SOCIAL"
    published_at: str = "Unknown"
    is_new: bool = True

# ---------------------------------------------------------
# CACHE & APM STATE
# ---------------------------------------------------------
memory_cache = {
    "macro_map_state": [],
    "last_updated": None
}

# LIVE_TICKER_CACHE is now globally imported from macro_pipeline
apm_tracker: List[datetime] = []
active_connections: List[WebSocket] = []

async def get_db_pool():
    return await asyncpg.create_pool(
        host=DB_HOST, database=DB_NAME, user=DB_USER,
        password=DB_PASS, port=DB_PORT, min_size=1, max_size=10
    )

pool = None

@app.on_event("startup")
async def startup_event():
    global pool
    pool = await get_db_pool()
    macro_pipeline.MAIN_LOOP = asyncio.get_running_loop()
    asyncio.create_task(pipeline_angel_one_ws(pool))
    asyncio.create_task(cache_refresh_loop())
    asyncio.create_task(listen_to_pg_notify())

@app.on_event("shutdown")
async def shutdown_event():
    if pool:
        await pool.close()

# ---------------------------------------------------------
# BACKGROUND TASKS
# ---------------------------------------------------------
async def cache_refresh_loop():
    """Rapid <15ms memory cache updater for the map state"""
    while True:
        try:
            if pool:
                async with pool.acquire() as conn:
                    rows = await conn.fetch("""
                        SELECT country_iso, country_name, war_intensity_score, 
                               oil_reserves_barrels, gold_reserves_tonnes, composite_risk_score
                        FROM master_country_states
                    """)
                    memory_cache["macro_map_state"] = [dict(r) for r in rows]
                    memory_cache["last_updated"] = datetime.now().isoformat()
        except Exception as e:
            logger.error(f"Cache Refresh Error: {e}")
        
        await asyncio.sleep(5)  # Refresh cache every 5s

async def listen_to_pg_notify():
    """Listens for intel_channel events from macro_pipeline and broadcasts via WS"""
    if not pool:
        return
        
    async with pool.acquire() as conn:
        def on_notify(connection, pid, channel, payload):
            asyncio.create_task(broadcast_intel(payload))
            
        await conn.add_listener('intel_channel', on_notify)
        
        # Keep connection open for notifications
        while True:
            await asyncio.sleep(3600)

async def broadcast_intel(payload: str):
    """Broadcasts to all connected WS clients and tracks APM"""
    global apm_tracker
    
    # Clean up old APM tracking
    now = datetime.now()
    apm_tracker = [t for t in apm_tracker if (now - t).total_seconds() < 60]
    apm_tracker.append(now)
    
    # Calculate APM and check volatility surge
    apm = len(apm_tracker)
    data = json.loads(payload)
    data["current_apm"] = apm
                
    if apm > 15:
        data["volatility_surge"] = True
    
    packet = json.dumps(data)
    for ws in active_connections:
        try:
            await ws.send_text(packet)
        except:
            pass

# ---------------------------------------------------------
# REST ENDPOINTS
# ---------------------------------------------------------
@app.get("/api/macro-metrics")
async def get_macro_metrics():
    """Fetches real-time ticker data for the frontend Liquidity Matrix"""
    if not pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch("SELECT asset_name, ticker, current_price, delta_1d, baseline_1w, baseline_1m FROM macro_assets")
            return [dict(r) for r in rows]
        except asyncpg.exceptions.UndefinedTableError:
            return []

@app.get("/api/macro/map-state")
async def get_map_state():
    """Ultra-fast memory cache response for Map initial load (<15ms)"""
    return memory_cache

@app.get("/api/macro/country/{iso}")
async def get_country_history(iso: str):
    """Fetches historical snapshots for the Glassmorphic Drawer"""
    if not pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
        
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT metric_name, metric_value, timestamp
            FROM country_macro_history
            WHERE country_iso = $1
            ORDER BY timestamp ASC
        """, iso.upper())
        
        state = await conn.fetchrow("""
            SELECT * FROM master_country_states WHERE country_iso = $1
        """, iso.upper())
        
        if not rows and not state:
            raise HTTPException(status_code=404, detail="Country not found")
            
        history = [dict(r) for r in rows]
        # Group by metric
        chart_data = {}
        for r in history:
            m = r['metric_name']
            if m not in chart_data:
                chart_data[m] = []
            chart_data[m].append({"val": float(r['metric_value']), "time": r['timestamp'].isoformat()})
            
        return {
            "current_state": dict(state) if state else None,
            "historical_charts": chart_data
        }

@app.post("/api/macro/ingest")
async def ingest_macro_signal(payload: IngestPayload):
    """
    Ingest a raw signal (e.g., from Truth Social), apply intent classification
    and fiscal contextual filters to compute an Impact Score.
    """
    text = payload.raw_text.lower()
    
    # ---------------------------------------------------------
    # STAGE 1: INTENT CLASSIFIER
    # ---------------------------------------------------------
    classification = "[POLICY_SIGNAL]"  # Default for demonstration
    
    if any(kw in text for kw in ["happy", "great day", "check out", "follow", "social"]):
        classification = "[SOCIAL/PROMOTIONAL]"
    elif any(kw in text for kw in ["pray", "thoughts", "humanitarian aid", "sending our prayers"]):
        classification = "[HUMANITARIAN/EMERGENCY_RESPONSE]"
    elif any(kw in text for kw in ["ultimatum", "military", "brics", "existential", "threat"]):
        classification = "[GEOPOLITICAL_SIGNAL]"
    elif any(kw in text for kw in ["tariff", "growth", "stimulus", "tax", "funding", "recovery", "repair"]):
        classification = "[POLICY_SIGNAL]"

    # If classified as SOCIAL or HUMANITARIAN, immediately bypass sentiment engine and drop the signal
    if classification in ["[SOCIAL/PROMOTIONAL]", "[HUMANITARIAN/EMERGENCY_RESPONSE]"]:
        return {
            "post_id": payload.post_id,
            "timestamp": payload.timestamp,
            "classification": classification,
            "metrics": {
                "base_sentiment": 0.0,
                "intent_factor_phi": 0.0,
                "source_weight": 0.0,
                "final_impact_score": 0.0
            },
            "sentiment_state": "NEUTRAL/STABILIZING",
            "terminal_action": "NO_DASHBOARD_TRIGGER"
        }

    # ---------------------------------------------------------
    # STAGE 2: SENTIMENT ENGINE WITH FISCAL CONTEXTUAL FILTERS
    # ---------------------------------------------------------
    # Mock Base Sentiment extraction (would typically be an LLM or NLP model call)
    base_sentiment = 0.8 if any(kw in text for kw in ["growth", "stimulus", "tremendous", "opportunity"]) else -0.5
    
    # Determine IntentFactor (phi) based on specific rules
    phi = 1.0
    sub_classification = classification
    
    if classification == "[POLICY_SIGNAL]":
        if any(kw in text for kw in ["recovery", "repair funding", "disaster recovery"]):
            # Dampened heavily to ensure "reactive repair capital" isn't misclassified as bullish economic growth
            phi = 0.2
            sub_classification = "POLICY_SIGNAL/RECOVERY"
        elif any(kw in text for kw in ["threat", "regulatory risk"]):
            phi = 0.8
            sub_classification = "POLICY_SIGNAL/THREAT"
        else:
            # Growth, Direct Stimulus, or Bilateral Trade Signals
            phi = 1.0
            sub_classification = "POLICY_SIGNAL"
            
    elif classification == "[GEOPOLITICAL_SIGNAL]":
        sub_classification = "GEOPOLITICAL_SIGNAL"
        phi = 0.9  # Geopolitical Ultimatums or Sector Threats (0.8 to 1.0)
        
    # Weights Setup
    w_source = 2.0 if "ultimatum" in text else 1.5
    t_decay = 1.0
    
    # Impact Score Calculation (Impact_Score = W_source * S_w * T_decay)
    s_w = base_sentiment * phi
    impact_score = w_source * s_w * t_decay
    
    # ---------------------------------------------------------
    # STAGE 3: STRUCTURED PAYLOAD OUTPUT (Determine State/Action)
    # ---------------------------------------------------------
    if impact_score >= 0.5:
        sentiment_state = "BULLISH"
    elif impact_score <= -0.5:
        sentiment_state = "BEARISH/INTERVENTIONIST"
    else:
        sentiment_state = "NEUTRAL/STABILIZING"
        
    if "existential" in text or "ultimatum" in text:
        sentiment_state = "CRITICAL"
        
    terminal_action = "MARKET_ALERT" if abs(impact_score) >= 0.5 else "REGIONAL_MONITORING"
    
    response_payload = {
        "post_id": payload.post_id,
        "timestamp": payload.timestamp,
        "classification": sub_classification,
        "metrics": {
            "base_sentiment": base_sentiment,
            "intent_factor_phi": phi,
            "source_weight": w_source,
            "final_impact_score": round(impact_score, 4)
        },
        "sentiment_state": sentiment_state,
        "terminal_action": terminal_action
    }
    
    # Log the output
    logger.info(f"Processed Signal Output: {json.dumps(response_payload)}")
    
    # Broadcast to websocket clients so the UI updates
    broadcast_data = {
        "tag": "[TRUTH_SOCIAL]",
        "tier": f"[{sentiment_state}]",
        "asset": "TRUMP",
        "message": payload.raw_text,
        "classification": sub_classification,
        "metrics": response_payload["metrics"],
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "published_at": payload.published_at,
        "is_new": payload.is_new
    }
    asyncio.create_task(broadcast_intel(json.dumps(broadcast_data)))
    
    return response_payload

# ---------------------------------------------------------
# DYNAMIC SEARCH & TIME-SERIES ENGINE
# ---------------------------------------------------------
@app.get("/api/search")
async def search_assets(q: str):
    """Searches master_financial_assets for matching tickers or names"""
    if not pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    if not q or len(q) < 1:
        return []

    async with pool.acquire() as conn:
        try:
            query = """
                SELECT ticker_symbol, asset_name, fas_score 
                FROM master_financial_assets 
                WHERE ticker_symbol ILIKE $1 OR asset_name ILIKE $1
                LIMIT 10
            """
            search_term = f"%{q}%"
            rows = await conn.fetch(query, search_term)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Search API Error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

def calculate_fas_score(ticker: str, history: list) -> str:
    """Quantitative FAS Score Engine"""
    if not history or len(history) < 2:
        return "N/A"
        
    try:
        # [F]undamental Volume Delta
        vol_today = history[-1].get("volume", 1)
        vol_prev = history[-2].get("volume", 1)
        if vol_prev == 0: vol_prev = 1
        vol_delta = (vol_today - vol_prev) / vol_prev
        
        # [A]lert Severity Momentum
        price_today = history[-1].get("price_close", 1)
        price_prev = history[-2].get("price_close", 1)
        price_delta = abs((price_today - price_prev) / price_prev) * 100
        
        # [S]entiment Vector Input (Mock mapping)
        sentiment = 1.2 if price_today > price_prev else 0.8
        
        aggregate_scalar = (vol_delta * 0.4) + (price_delta * 0.4) + (sentiment * 0.2)
        
        if aggregate_scalar > 1.5: return "AAA+"
        elif aggregate_scalar > 0.8: return "AA"
        elif aggregate_scalar > 0.3: return "A"
        elif aggregate_scalar > 0: return "BBB+"
        elif aggregate_scalar > -0.5: return "BBB-"
        else: return "C"
    except Exception as e:
        logger.error(f"FAS Score Error: {e}")
        return "N/A"

@app.get("/api/asset/{ticker_symbol}/history")
async def get_asset_history(ticker_symbol: str):
    """Fetches multi-asset analysis using yfinance and outputs Institutional FAS payload"""
    clean_ticker = ticker_symbol.replace(" ", "").upper()
    
    # EXPLICIT SYMBOL MAPPER UTILITY FOR YFINANCE
    yf_symbol = clean_ticker
    if clean_ticker in ["NIFTY50", "NIFTY"]:
        yf_symbol = "^NSEI"
    elif clean_ticker == "RELIANCE":
        yf_symbol = "RELIANCE.NS"
    elif "BTC" in clean_ticker or "USDT" in clean_ticker:
        yf_symbol = "BTC-USD"
        
    meta_dict = {
        "asset_name": clean_ticker,
        "fas_score": 0,
        "support_level": 0.0,
        "resistance_level": 0.0,
        "range_status": "Neutral",
        "financials_analysis": "Gathering historical momentum...",
        "events_analysis": "Processing multi-session volatility profiles...",
        "price_correlation": "Analyzing trajectory vs Past Vectors..."
    }
    
    try:
        import yfinance as yf
        # yfinance operations are blocking, run in executor if necessary, but for simplicity here we block briefly
        ticker_obj = yf.Ticker(yf_symbol)
        
        # Fetch 1 month of daily data for structural bounds
        df = ticker_obj.history(period="1mo", interval="1d")
        
        if df.empty:
            # Fallback mock generator
            import random
            base_price = 24350.00 if "NIFTY" in clean_ticker else (60000.00 if "BTC" in clean_ticker else 150.00)
            meta_dict["support_level"] = round(base_price * 0.95, 2)
            meta_dict["resistance_level"] = round(base_price * 1.05, 2)
            meta_dict["fas_score"] = 45
            meta_dict["range_status"] = "Neutral"
        else:
            current_close = float(df['Close'].iloc[-1])
            absolute_high = float(df['High'].max())
            absolute_low = float(df['Low'].min())
            
            meta_dict["support_level"] = round(absolute_low, 2)
            meta_dict["resistance_level"] = round(absolute_high, 2)
            
            # FAS EQUATION ENGINE
            # 1. Fundamental Weight (40%): Derive via historical proxy (average volume vs current volume)
            avg_vol = df['Volume'].mean()
            curr_vol = df['Volume'].iloc[-1]
            fund_ratio = (curr_vol / avg_vol) if avg_vol > 0 else 1.0
            fund_score = min(max(fund_ratio * 20, 0), 40) # Scale 0 to 40
            
            # 2. Algorithmic Weight (35%): ((Current_Close - Absolute_Low) / (Absolute_High - Absolute_Low)) * 35
            range_diff = absolute_high - absolute_low
            algo_ratio = ((current_close - absolute_low) / range_diff) if range_diff > 0 else 0.5
            algo_score = min(max(algo_ratio * 35, 0), 35) # Scale 0 to 35
            
            # 3. Sentiment Weight (25%): Map divergence trends (close vs 1mo avg)
            avg_close = df['Close'].mean()
            sent_ratio = (current_close / avg_close) if avg_close > 0 else 1.0
            sent_score = min(max((sent_ratio - 0.9) * 125, 0), 25) # Scale 0 to 25
            
            total_fas = round(fund_score + algo_score + sent_score)
            meta_dict["fas_score"] = total_fas
            
            if total_fas > 70:
                meta_dict["range_status"] = "Overvalued"
            elif total_fas < 30:
                meta_dict["range_status"] = "Undervalued"
            else:
                meta_dict["range_status"] = "Neutral"
                
            # Populate text blocks dynamically based on state
            meta_dict["financials_analysis"] = f"Algorithmic variance mapped at {round(algo_ratio*100, 1)}% of rolling range. Volume momentum multiplier at {round(fund_ratio, 2)}x."
            meta_dict["events_analysis"] = "Session high bounded resistance tested. Structurally intact liquidity zone found at support."
            meta_dict["price_correlation"] = f"Asset maintains a {meta_dict['range_status'].lower()} matrix state relative to macro indicators."

        return {
            "metadata": meta_dict
        }
    except Exception as e:
        logger.error(f"History API Error: {e}")
        # Return fallback on complete failure
        return {"metadata": meta_dict}

# ---------------------------------------------------------
# WEBSOCKETS
# ---------------------------------------------------------
@app.websocket("/ws/intel")
async def websocket_intel(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # We are just broadcasting TO the client, keep it alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception as e:
        if websocket in active_connections:
            active_connections.remove(websocket)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
