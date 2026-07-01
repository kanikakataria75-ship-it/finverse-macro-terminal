import os
import sys
import logging
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import asyncpg
    import uvicorn
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Error: Missing dependency. {e}")
    sys.exit(1)

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

# ---------------------------------------------------------
# CACHE & APM STATE
# ---------------------------------------------------------
memory_cache = {
    "macro_map_state": [],
    "last_updated": None
}

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
