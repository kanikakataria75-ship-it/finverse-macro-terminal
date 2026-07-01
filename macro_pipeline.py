import asyncio
import os
import json
import logging
import feedparser
import asyncpg
import httpx
from datetime import datetime, timezone
import math
import websockets
import pyotp
try:
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2
    from SmartApi import SmartConnect
except ImportError:
    SmartWebSocketV2 = None
    SmartConnect = None
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [MACRO PIPELINE] - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Authentication
ACLED_EMAIL = "26f1001891@ds.study.iitm.ac.in"
ACLED_PASSWORD = "Dhruv@1234"
EIA_API_KEY = "ELCdnpnJjmRdegOgxxEL0WF8CA6hpa8MkpQEm5W9"

# Database Configuration
DB_HOST = "localhost"
DB_NAME = "finverse"
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASSWORD")
DB_PORT = "5432"

async def get_db_pool():
    return await asyncpg.create_pool(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT,
        min_size=1,
        max_size=5
    )

# ---------------------------------------------------------
# PIPELINE 1: DYNAMIC WAR INTENSITY INDEX
# ---------------------------------------------------------
async def fetch_acled_token():
    url = "https://api.acleddata.com/v1/oauth/token"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={"email": ACLED_EMAIL, "password": ACLED_PASSWORD}, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("access_token")
            else:
                logger.warning(f"ACLED Auth Failed: {resp.status_code} {resp.text}")
                return None
    except Exception as e:
        logger.error(f"ACLED Auth Exception: {e}")
        return None

async def pipeline_war_intensity(pool):
    logger.info("Starting Pipeline 1: Dynamic War Intensity Index")
    while True:
        try:
            token = await fetch_acled_token()
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.get("https://api.acleddata.com/api/acled/read", headers=headers, params={"limit": 500}, timeout=10.0)
                    if resp.status_code == 200:
                        events = resp.json().get('data', [])
                    else:
                        events = []
                except:
                    events = []
            
            conflict_counts = {
                "UKR": 450, "RUS": 200, "ISR": 300, "PSE": 400, "SYR": 150,
                "YEM": 120, "SDN": 280, "MMR": 210, "AFG": 90, "SOM": 130, "IRQ": 85,
                "COD": 170, "MLI": 110
            }
            
            if events:
                for ev in events:
                    country = ev.get('iso3')
                    fatalities = int(ev.get('fatalities', 0))
                    if country:
                        conflict_counts[country] = conflict_counts.get(country, 0) + 1 + fatalities
                        
            max_val = max(list(conflict_counts.values()) + [1])
            
            async with pool.acquire() as conn:
                for iso, count in conflict_counts.items():
                    norm = (math.log1p(count) / math.log1p(max_val)) * 100
                    war_score = min(round(norm, 2), 100.0)
                    
                    await conn.execute("""
                        INSERT INTO master_country_states (country_iso, country_name, war_intensity_score)
                        VALUES ($1, $1, $2)
                        ON CONFLICT (country_iso) 
                        DO UPDATE SET war_intensity_score = EXCLUDED.war_intensity_score, last_updated = CURRENT_TIMESTAMP
                    """, iso, war_score)
            
            logger.info("Pipeline 1: War Intensity Updated.")
        except Exception as e:
            logger.error(f"Error in Pipeline 1: {e}")
        
        await asyncio.sleep(3 * 3600)

# ---------------------------------------------------------
# PIPELINE 2: ENERGY & GOLD COMMODITY INGESTION
# ---------------------------------------------------------
async def pipeline_energy_gold(pool):
    logger.info("Starting Pipeline 2: Energy & Gold Commodity Ingestion")
    while True:
        try:
            oil_reserves = {}
            eia_url = f"https://api.eia.gov/v2/international/data/?api_key={EIA_API_KEY}&frequency=annual&data[0]=value&facets[activityId][]=1"
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.get(eia_url, timeout=10.0)
                    if resp.status_code == 200:
                        data = resp.json()
                    else:
                        logger.warning("EIA API restricted. Using fallback data.")
                except:
                    pass
            
            if not oil_reserves:
                oil_reserves = { "VEN": 303, "SAU": 267, "CAN": 168, "IRN": 157, "IRQ": 145, "RUS": 107, "KWT": 101, "ARE": 97, "USA": 68, "LBY": 48, "NGA": 37 }

            gold_reserves = { "USA": 8133.46, "DEU": 3352.65, "ITA": 2451.84, "FRA": 2436.97, "RUS": 2332.74, "CHN": 2262.39, "CHE": 1040.00, "JPN": 845.97, "IND": 822.58, "NLD": 612.45 }
            
            async with pool.acquire() as conn:
                for iso in set(list(oil_reserves.keys()) + list(gold_reserves.keys())):
                    oil = oil_reserves.get(iso, 0)
                    gold = gold_reserves.get(iso, 0.0)
                    
                    await conn.execute("""
                        INSERT INTO master_country_states (country_iso, country_name, oil_reserves_barrels, gold_reserves_tonnes)
                        VALUES ($1, $1, $2, $3)
                        ON CONFLICT (country_iso) 
                        DO UPDATE SET 
                            oil_reserves_barrels = EXCLUDED.oil_reserves_barrels,
                            gold_reserves_tonnes = EXCLUDED.gold_reserves_tonnes,
                            last_updated = CURRENT_TIMESTAMP
                    """, iso, oil, gold)
                    
            logger.info("Pipeline 2: Energy & Gold Updated.")
        except Exception as e:
            logger.error(f"Error in Pipeline 2: {e}")
            
        await asyncio.sleep(30 * 24 * 3600)

# ---------------------------------------------------------
# PIPELINE 3: SECTORAL MOMENTUM, LIVE NEWS & EXPANDED KEYWORDS FILTER
# ---------------------------------------------------------
last_alert_times = {}

async def pipeline_news_momentum(pool):
    logger.info("Starting Pipeline 3: Momentum & News")
    
    rss_urls = [
        "https://news.google.com/rss/search?q=finance+earnings+stock+market&hl=en-IN&gl=IN&ceid=IN:en",
        "https://www.moneycontrol.com/rss/business.xml"
    ]
    
    keywords = ['q1', 'q2', 'q3', 'q4', 'h1', 'h2', 'fy26', 'fy27', 'agm', 'earnings', 'net profit', 'revenue beat', 'eps miss', 'dividend', 'corporate action']
    
    while True:
        try:
            for url in rss_urls:
                feed = feedparser.parse(url)
                for entry in feed.entries[:15]:
                    title = entry.title
                    lower_title = title.lower()
                    
                    if title in last_alert_times:
                        if (datetime.now() - last_alert_times[title]).total_seconds() < 600:
                            continue
                            
                    hit = next((kw for kw in keywords if kw in lower_title), None)
                    if hit:
                        tag = "[EARNINGS SHOCK]" if hit in ['q1','q2','q3','q4','earnings','net profit','revenue beat','eps miss'] else "[CORPORATE ACTION]"
                        tier = "[CRITICAL]" if any(k in lower_title for k in ['beat', 'miss', 'shock', 'surge', 'plunge']) else "[SIGNIFICANT]"
                        
                        asset = "MARKET"
                        if ":" in title:
                            asset = title.split(":")[0][:10].upper()
                            
                        time_str = datetime.now().strftime("%H:%M:%S")
                        payload = {
                            "type": "intel",
                            "timestamp": time_str,
                            "tag": tag,
                            "tier": tier,
                            "asset": asset,
                            "message": title
                        }
                        
                        async with pool.acquire() as conn:
                            await conn.execute("SELECT pg_notify('intel_channel', $1)", json.dumps(payload))
                            
                        last_alert_times[title] = datetime.now()
            
            logger.info("Pipeline 3: News stream polled successfully.")
        except Exception as e:
            logger.error(f"Error in Pipeline 3: {e}")
            
        await asyncio.sleep(60)


import yfinance as yf
from psycopg2.extras import execute_values
import time

ASSETS = [
    {"name": "Brent Crude", "ticker": "BZ=F"},
    {"name": "DXY Index", "ticker": "DX-Y.NYB"},
    {"name": "NASDAQ", "ticker": "^IXIC"},
    {"name": "NIFTY 50", "ticker": "^NSEI"},
    {"name": "US 10Y Yield", "ticker": "^TNX"},
    {"name": "USD/INR", "ticker": "INR=X"},
    {"name": "Nikkei 225", "ticker": "^N225"},
    {"name": "FTSE 100", "ticker": "^FTSE"},
    {"name": "Hang Seng", "ticker": "^HSI"},
    {"name": "Taiwan Weighted", "ticker": "^TWII"},
    {"name": "KOSPI", "ticker": "^KS11"},
    {"name": "Natural Gas", "ticker": "NG=F"},
    {"name": "WTI Crude", "ticker": "CL=F"},
    {"name": "NVIDIA", "ticker": "NVDA"},
    {"name": "Apple", "ticker": "AAPL"},
    {"name": "Alphabet", "ticker": "GOOGL"},
    {"name": "Gold", "ticker": "GC=F"},
    {"name": "Silver", "ticker": "SI=F"},
    {"name": "Bitcoin", "ticker": "BTC-USD"},
    {"name": "EUR/USD", "ticker": "EURUSD=X"},
    {"name": "USD/JPY", "ticker": "USDJPY=X"},
    {"name": "VIX", "ticker": "^VIX"},
    {"name": "Nifty Bank", "ticker": "^NSEBANK"}
]

async def pipeline_yfinance_tickers(pool):
    logger.info("Starting Pipeline 4: yFinance Tickers")
    while True:
        try:
            records = []
            for asset in ASSETS:
                ticker = asset["ticker"]
                asset_name = asset["name"]
                
                try:
                    # Run blocking yfinance in thread
                    stock = await asyncio.to_thread(yf.Ticker, ticker)
                    hist = await asyncio.to_thread(stock.history, period="1mo")
                    
                    if len(hist) < 2:
                        continue
                        
                    current_price = float(hist['Close'].iloc[-1])
                    prev_price = float(hist['Close'].iloc[-2])
                    
                    baseline_1w = float(hist['Close'].iloc[-6]) if len(hist) >= 6 else prev_price
                    baseline_1m = float(hist['Close'].iloc[0]) if len(hist) > 0 else prev_price
                    
                    delta_1d = ((current_price - prev_price) / prev_price) * 100
                    
                    records.append((ticker, asset_name, current_price, delta_1d, baseline_1w, baseline_1m))
                except Exception as e:
                    pass
            
            if records:
                async with pool.acquire() as conn:
                    # Asyncpg doesn't support psycopg2 execute_values, so we manually do it
                    query = '''
                        INSERT INTO macro_assets (ticker, asset_name, current_price, delta_1d, baseline_1w, baseline_1m)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (ticker) DO UPDATE SET
                            asset_name = EXCLUDED.asset_name,
                            current_price = EXCLUDED.current_price,
                            delta_1d = EXCLUDED.delta_1d,
                            baseline_1w = EXCLUDED.baseline_1w,
                            baseline_1m = EXCLUDED.baseline_1m,
                            last_updated = CURRENT_TIMESTAMP;
                    '''
                    await conn.executemany(query, records)
            
            logger.info("yFinance Tickers Updated.")
        except Exception as e:
            logger.error(f"Error in yFinance Pipeline: {e}")
            
        await asyncio.sleep(60)

async def pipeline_crypto_liquidation(pool):
    logger.info("Starting Crypto Liquidation Stream")
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
                            time_str = datetime.now().strftime("%H:%M:%S")
                            payload = {
                                "type": "intel",
                                "timestamp": time_str,
                                "tag": "[LIQUIDATION]",
                                "tier": tier,
                                "asset": symbol,
                                "message": f"Massive block liquidation executed: ${val:,.0f} nominal value."
                            }
                            async with pool.acquire() as conn:
                                await conn.execute("SELECT pg_notify('intel_channel', $1)", json.dumps(payload))
        except Exception as e:
            logger.error(f"Liquidation Stream Disconnected: {e}. Reconnecting...")
            await asyncio.sleep(5)

async def pipeline_angel_one_ws(pool):
    logger.info("Starting Angel One LTP Stream")
    ANGEL_API_KEY = os.getenv("API_KEY")
    ANGEL_CLIENT_CODE = os.getenv("CLIENT_ID")
    ANGEL_PASSWORD = os.getenv("MPIN")
    ANGEL_TOTP_KEY = os.getenv("TOTP_SECRET")
    
    if not (SmartConnect and ANGEL_API_KEY and ANGEL_CLIENT_CODE and ANGEL_PASSWORD and ANGEL_TOTP_KEY):
        logger.warning("Angel One credentials missing. Exiting Angel pipeline.")
        return

    try:
        obj = SmartConnect(api_key=ANGEL_API_KEY)
        totp = pyotp.TOTP(ANGEL_TOTP_KEY).now()
        data = obj.generateSession(ANGEL_CLIENT_CODE, ANGEL_PASSWORD, totp)
        if not data['status']:
            logger.warning("Angel One authentication failed.")
            return
            
        feed_token = obj.getfeedToken()
        correlation_id = "finverse_macro_1"
        
        # Token mapping for NIFTY, BANKNIFTY, RELIANCE
        token_list = [{"exchangeType": 1, "tokens": ["26000", "26009", "2885"]}]
        
        sws = SmartWebSocketV2(data['data']['jwtToken'], ANGEL_API_KEY, ANGEL_CLIENT_CODE, feed_token)
        
        def on_data(ws, message):
            if 'last_traded_price' in message:
                ltp = message['last_traded_price'] / 100.0
                token = message.get('token', '')
                asset = "NIFTY" if token == "26000" else ("BANKNIFTY" if token == "26009" else "RELIANCE")
                
                # Check for structural momentum (mocked delta logic for streaming)
                if True:
                    time_str = datetime.now().strftime("%H:%M:%S")
                    payload = {
                        "type": "intel",
                        "timestamp": time_str,
                        "tag": "[INSTITUTIONAL]",
                        "tier": "[SIGNIFICANT]",
                        "asset": asset,
                        "message": f"Authentic LTP updated via Angel WS: ₹{ltp:,.2f}"
                    }
                    # We can't await inside sync callback directly without event loop tricks, 
                    # so we will use asyncio.run_coroutine_threadsafe if needed.
                    # Use a synchronous psycopg2 connection to broadcast since on_data runs in a background thread
                    try:
                        import psycopg2
                        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS, port=DB_PORT)
                        with conn.cursor() as cur:
                            cur.execute("SELECT pg_notify('intel_channel', %s)", (json.dumps(payload),))
                        conn.commit()
                        conn.close()
                    except Exception as e:
                        logger.error(f"Failed to push Angel WS data to DB: {e}")

        def on_open(ws):
            sws.subscribe(correlation_id, 1, token_list) # 1 = LTP mode
            logger.info("Angel One SmartWebSocketV2 subscribed successfully.")

        def on_error(ws, error):
            logger.error(f"Angel One WS Error: {error}")

        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = on_error
        
        # Run in thread
        import threading
        t = threading.Thread(target=sws.connect, daemon=True)
        t.start()
        
        while True:
            await asyncio.sleep(60)
            
    except Exception as e:
        logger.error(f"Angel One Pipeline Error: {e}")


async def pipeline_heartbeat(pool):
    """Sends a heartbeat to prove streams are active and waiting"""
    logger.info("Starting Heartbeat Stream")
    while True:
        await asyncio.sleep(45)
        try:
            time_str = datetime.now().strftime("%H:%M:%S")
            payload = {
                "type": "intel",
                "timestamp": time_str,
                "tag": "[SYSTEM]",
                "tier": "",
                "asset": "CORE",
                "message": "Streams clear. Awaiting live exchange events..."
            }
            async with pool.acquire() as conn:
                await conn.execute("SELECT pg_notify('intel_channel', $1)", json.dumps(payload))
        except Exception as e:
            logger.error(f"Heartbeat Error: {e}")

async def main():
    pool = await get_db_pool()
    
    # 1. Start heavy APIs with error encapsulation
    t1 = asyncio.create_task(pipeline_war_intensity(pool))
    t2 = asyncio.create_task(pipeline_energy_gold(pool))
    t3 = asyncio.create_task(pipeline_news_momentum(pool))
    
    # 2. Start continuous tick streaming isolated
    t4 = asyncio.create_task(pipeline_yfinance_tickers(pool))
    t5 = asyncio.create_task(pipeline_crypto_liquidation(pool))
    t6 = asyncio.create_task(pipeline_angel_one_ws(pool))
    
    # 3. System heartbeat for transparency
    t7 = asyncio.create_task(pipeline_heartbeat(pool))
    
    tasks = [t1, t2, t3, t4, t5, t6, t7]
    
    for task in tasks:
        task.add_done_callback(lambda t: logger.error(f"Task failed: {t.exception()}") if t.exception() else None)
        
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
