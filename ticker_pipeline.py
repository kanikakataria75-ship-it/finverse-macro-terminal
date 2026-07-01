import time
import logging
import psycopg2
from psycopg2.extras import execute_values
import sys
import os
from dotenv import load_dotenv

load_dotenv()
try:
    import yfinance as yf
    import requests
except ImportError:
    print("Error: yfinance or requests is not installed.")
    print("Please install by running: pip install yfinance requests")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Database connection parameters
DB_HOST = "localhost"
DB_NAME = "finverse"
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASSWORD")
DB_PORT = "5432"

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
    {"name": "Nifty Bank", "ticker": "^NSEBANK"},
    {"name": "Finnifty", "ticker": "NIFTY_FIN_SERVICE.NS"},
    {"name": "Nifty IT", "ticker": "^CNXIT"},
    {"name": "Nifty Pharma", "ticker": "^CNXPHARMA"},
    {"name": "Nifty Auto", "ticker": "^CNXAUTO"},
    {"name": "Nifty FMCG", "ticker": "^CNXFMCG"},
    {"name": "Nifty Metal", "ticker": "^CNXMETAL"},
    {"name": "Nifty Realty", "ticker": "^CNXREALTY"},
    {"name": "Nifty Media", "ticker": "^CNXMEDIA"}
]

# Stateful alert debouncing dictionaries
last_alert_values = {}
last_alert_times = {}

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
        logger.error(f"Failed to connect to database: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            # DDL to create the macro_assets table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS macro_assets (
                    ticker VARCHAR(50) PRIMARY KEY,
                    asset_name VARCHAR(100) NOT NULL,
                    current_price NUMERIC(12, 4) NOT NULL,
                    delta_1d NUMERIC(12, 4) NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                ALTER TABLE macro_assets
                ADD COLUMN IF NOT EXISTS baseline_1w NUMERIC(12, 4),
                ADD COLUMN IF NOT EXISTS baseline_1m NUMERIC(12, 4);
            """)
        conn.commit()
        logger.info("Table 'macro_assets' initialized or verified successfully in database 'finverse'.")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize table: {e}")
        return False
    finally:
        conn.close()

def fetch_and_update_data():
    conn = get_db_connection()
    if not conn:
        return
    
    logger.info(f"Fetching data for {len(ASSETS)} assets from yFinance...")
    records = []
    
    for asset in ASSETS:
        ticker = asset["ticker"]
        asset_name = asset["name"]
        
        try:
            stock = yf.Ticker(ticker)
            # Fetch 1 month to ensure we have enough trading days for historical baselines
            hist = stock.history(period="1mo")
            
            if len(hist) < 2:
                logger.warning(f"Not enough historical data for {ticker} to calculate delta.")
                continue
                
            current_price = float(hist['Close'].iloc[-1])
            prev_price = float(hist['Close'].iloc[-2])
            
            baseline_1w = float(hist['Close'].iloc[-6]) if len(hist) >= 6 else prev_price
            baseline_1m = float(hist['Close'].iloc[0]) if len(hist) > 0 else prev_price
            
            # Calculate 1D percentage change
            delta_1d = ((current_price - prev_price) / prev_price) * 100
            
            # Intel Spam Filtering & Debouncing Check
            now_ts = time.time()
            last_delta = last_alert_values.get(ticker, 0.0)
            last_time = last_alert_times.get(ticker, 0)
            
            # Only trigger if delta is significant
            if abs(delta_1d) >= 1.5:
                # Trigger if absolute additional 0.5% move OR 10 minutes (600s) have passed
                if abs(delta_1d - last_delta) >= 0.5 or (now_ts - last_time) >= 600:
                    last_alert_values[ticker] = delta_1d
                    last_alert_times[ticker] = now_ts
                    
                    tier = "[CRITICAL]" if abs(delta_1d) >= 3.0 else "[SIGNIFICANT]"
                    direction = "BREAKOUT" if delta_1d > 0 else "PLUNGE"
                    try:
                        requests.post("http://127.0.0.1:8000/api/intel/broadcast", json={
                            "tag": "[VOLATILITY]",
                            "tier": tier,
                            "asset": asset_name,
                            "message": f"Sudden structural {direction} detected. Delta: {delta_1d:+.2f}%"
                        }, timeout=2)
                    except Exception as e:
                        logger.warning(f"Could not broadcast alert for {ticker}: {e}")
            
            records.append((ticker, asset_name, current_price, delta_1d, baseline_1w, baseline_1m))
            logger.info(f"Processed {asset_name} ({ticker}): {current_price:.2f} ({delta_1d:+.2f}%)")
        except Exception as e:
            logger.error(f"Error processing {ticker}: {e}")
    
    if records:
        try:
            with conn.cursor() as cur:
                # Upsert query
                upsert_query = """
                    INSERT INTO macro_assets (ticker, asset_name, current_price, delta_1d, baseline_1w, baseline_1m)
                    VALUES %s
                    ON CONFLICT (ticker) DO UPDATE SET
                        asset_name = EXCLUDED.asset_name,
                        current_price = EXCLUDED.current_price,
                        delta_1d = EXCLUDED.delta_1d,
                        baseline_1w = EXCLUDED.baseline_1w,
                        baseline_1m = EXCLUDED.baseline_1m,
                        last_updated = CURRENT_TIMESTAMP;
                """
                execute_values(cur, upsert_query, records)
            conn.commit()
            logger.info("Database updated successfully with latest macro values.")
        except Exception as e:
            logger.error(f"Error updating database: {e}")
    
    conn.close()

if __name__ == "__main__":
    if init_db():
        logger.info("Starting Finverse yFinance Ingestion Pipeline...")
        # Run indefinitely, pulling every 60 seconds
        while True:
            fetch_and_update_data()
            logger.info("Sleeping for 60 seconds before next ingestion cycle...")
            time.sleep(60)
    else:
        logger.error("Pipeline initialization failed. Check PostgreSQL credentials and ensure database exists. Exiting.")
