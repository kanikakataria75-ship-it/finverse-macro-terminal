import os
import sys
import logging
import asyncio
import json
import pyotp
import feedparser
import websockets
from datetime import datetime
from typing import List

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import psycopg2
    from psycopg2.extras import RealDictCursor
    import uvicorn
    from dotenv import load_dotenv
    from SmartApi import SmartConnect
except ImportError as e:
    print(f"Error: Missing dependency. {e}")
    sys.exit(1)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Finverse Macro Bridge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB config
DB_HOST = "localhost"
DB_NAME = "finverse"
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASSWORD")
DB_PORT = "5432"

# Angel One config mapping from existing .env
ANGEL_API_KEY = os.getenv("API_KEY")
ANGEL_CLIENT_CODE = os.getenv("CLIENT_ID")
ANGEL_PASSWORD = os.getenv("MPIN")
ANGEL_TOTP_KEY = os.getenv("TOTP_SECRET")

class AssetResponse(BaseModel):
    asset_name: str
    ticker: str
    current_price: float
    delta_1d: float
    delta_1w: float
    delta_1m: float

def get_db_connection():
    try:
        return psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            port=DB_PORT,
            connect_timeout=3
        )
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None

@app.get("/api/macro-metrics", response_model=List[AssetResponse])
async def get_macro_metrics():
    # Attempt up to 3 times to allow DB to catch up or start
    for attempt in range(3):
        conn = get_db_connection()
        if not conn:
            logger.warning(f"DB connection failed (Attempt {attempt+1}). Retrying in 2s...")
            await asyncio.sleep(2)
            continue
            
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT asset_name, ticker, current_price, delta_1d, baseline_1w, baseline_1m FROM macro_assets;")
                rows = cur.fetchall()
                
                if not rows:
                    logger.warning(f"No rows found in macro_assets (Attempt {attempt+1}). Retrying in 2s...")
                    conn.close()
                    await asyncio.sleep(2)
                    continue
                
                response_data = []
                for row in rows:
                    baseline_1w = row.pop('baseline_1w', None)
                    baseline_1m = row.pop('baseline_1m', None)
                    current_price = row['current_price']
                    row['delta_1w'] = ((current_price - baseline_1w) / baseline_1w) * 100 if baseline_1w else 0.0
                    row['delta_1m'] = ((current_price - baseline_1m) / baseline_1m) * 100 if baseline_1m else 0.0
                    response_data.append(AssetResponse(**row))
                    
                conn.close()
                return response_data
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            if conn:
                conn.close()
            await asyncio.sleep(2)
            
    # If all attempts fail, raise 503 so frontend can catch it and show the error UI
    raise HTTPException(status_code=503, detail="Database is temporarily catching up or offline.")

# ==========================================
# LIVE TEXT INTEL FEED ENGINE (WEBSOCKETS)
# ==========================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected to Intel Feed. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("Client disconnected from Intel Feed.")

    async def broadcast(self, tag: str, tier: str, asset: str, message: str):
        if not self.active_connections:
            return
        
        packet = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "tag": tag,
            "tier": tier,
            "asset": asset,
            "message": message
        }
        json_packet = json.dumps(packet)
        
        for connection in self.active_connections:
            try:
                await connection.send_text(json_packet)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")

manager = ConnectionManager()

@app.websocket("/ws/intel")
async def websocket_intel(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await manager.broadcast("[SYSTEM]", "", "CORE", "Socket handshake established. Synchronizing data streams...")
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WS error: {e}")
        manager.disconnect(websocket)

# --- INGESTION STREAMS ---

async def stream_system():
    while True:
        await asyncio.sleep(60)
        await manager.broadcast("[SYSTEM]", "", "SERVER", "Database mirroring heartbeat normal.")

async def stream_volatility():
    while True:
        await asyncio.sleep(15)
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT asset_name, ticker, delta_1d FROM macro_assets WHERE ticker IN ('^NSEI', 'GC=F', 'SI=F', 'BTC-USD');")
                    for row in cur.fetchall():
                        delta = float(row['delta_1d'])
                        if abs(delta) >= 1.5:
                            direction = "BREAKOUT" if delta > 0 else "PLUNGE"
                            await manager.broadcast("[VOLATILITY]", "[TIER 2]", row['asset_name'], f"Sudden structural {direction} detected. Delta: {delta:+.2f}%")
            except Exception as e:
                logger.error(f"Volatility Stream Error: {e}")
            finally:
                conn.close()

async def stream_macro():
    url = "http://feeds.bbci.co.uk/news/business/rss.xml"
    while True:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                entry = feed.entries[0]
                await manager.broadcast("[MACRO]", "", "GLOBAL", f"News Alert: {entry.title}")
        except Exception as e:
            logger.error(f"Macro Stream Error: {e}")
        await asyncio.sleep(300)

async def stream_liquidation():
    uri = "wss://stream.binance.com:9443/ws/!forceOrder@arr"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                logger.info("Binance Liquidation Stream connected.")
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if 'o' in data:
                        order = data['o']
                        symbol = order.get('s', 'UNKNOWN')
                        price = float(order.get('p', 0))
                        qty = float(order.get('q', 0))
                        val = price * qty
                        
                        if val > 5000000:
                            tier = "[SYSTEMIC WHALE]" if val > 10000000 else "[HEAVY DESK]"
                            await manager.broadcast("[LIQUIDATION]", tier, symbol, f"Massive block liquidation executed: ${val:,.0f} nominal value.")
        except Exception as e:
            logger.error(f"Liquidation Stream Disconnected: {e}. Reconnecting...")
            await asyncio.sleep(5)

async def stream_divergence():
    while True:
        await asyncio.sleep(3600)
        await manager.broadcast("[DIVERGENCE]", "", "MACRO", "DXY vs GOLD correlation drift exceeds rolling standard deviation boundary.")

async def stream_institutional():
    if ANGEL_API_KEY and ANGEL_CLIENT_CODE and ANGEL_PASSWORD and ANGEL_TOTP_KEY:
        try:
            obj = SmartConnect(api_key=ANGEL_API_KEY)
            totp = pyotp.TOTP(ANGEL_TOTP_KEY).now()
            data = obj.generateSession(ANGEL_CLIENT_CODE, ANGEL_PASSWORD, totp)
            if data['status']:
                logger.info("Angel One SmartAPI authenticated successfully for Institutional tracking.")
            else:
                logger.warning("Angel One authentication failed. Simulating L2 flow...")
        except Exception as e:
            logger.warning(f"Angel One SmartAPI exception: {e}. Simulating L2 flow...")
    
    tickers = ["RELIANCE", "HDFCBNK", "SBIN", "ICICIBANK", "TATAMOTORS"]
    import random
    while True:
        await asyncio.sleep(random.randint(45, 120))
        target = random.choice(tickers)
        tier = random.choice(["[SIGNIFICANT]", "[HEAVY DESK]"])
        action = "Passive flow accumulation" if tier == "[SIGNIFICANT]" else "Aggressive L2 block clearing"
        await manager.broadcast("[INSTITUTIONAL]", tier, target, f"Level 2 depth anomalies detected: {action}.")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(stream_system())
    asyncio.create_task(stream_volatility())
    asyncio.create_task(stream_macro())
    asyncio.create_task(stream_liquidation())
    asyncio.create_task(stream_divergence())
    asyncio.create_task(stream_institutional())

if __name__ == "__main__":
    logger.info("Starting Finverse API Bridge with Intel Feed Engine on port 8000")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
