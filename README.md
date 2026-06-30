
# Finverse World Macro Terminal                <img width="480" height="480" alt="Happy Stock Market GIF by shremps" src="https://github.com/user-attachments/assets/52febd0a-e03e-4239-9267-59e1f47bc6da" />



![Finverse Macro Terminal](https://img.shields.io/badge/Status-Phase%202%20Complete-neon) ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-blue) ![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-blue)

A high-density, cyberpunk-themed macro-economic terminal designed for zero-padding, ultra-compact real-time market intelligence gathering. 



<img width="3439" height="113" alt="Screenshot 2026-06-30 203259" src="https://github.com/user-attachments/assets/d9cd5b8b-9db2-4e95-9923-553968d2cdce" />
<img width="3435" height="1239" alt="Screenshot 2026-06-30 203243" src="https://github.com/user-attachments/assets/a749403c-fbbd-48e5-b764-3eca7a955bf5" />



## 🚀 Features

* **Cyberpunk Trading Floor UI**: A sleek, dark-themed HTML/JS/Tailwind CSS dashboard with neon accents, custom scrollbars, and dynamic glowing indicators.
* **Live Text Intel Feed Engine**: A real-time multi-stream asynchronous pipeline built on FastAPI WebSockets (`/ws/intel`), streaming color-coded intelligence directly to the UI.
* **6 Independent Ingestion Streams**:
  * `[SYSTEM]`: Server status and PostgreSQL mirroring heartbeat.
  * `[VOLATILITY]`: High-frequency delta surging tracker tracking anomalies > 1.5%.
  * `[MACRO]`: RSS pipeline for global structural news alerts.
  * `[LIQUIDATION]`: Native Binance WebSocket `!forceOrder@arr` integration parsing blocks > $5M.
  * `[DIVERGENCE]`: Hourly inter-market macro correlation checks (e.g., DXY vs GOLD).
  * `[INSTITUTIONAL]`: Angel One SmartAPI Level 2 depth monitoring for domestic NSE flows.
* **3-Tier Whale Categorization Algorithm**: Automatically classifies deep liquidity blocks into `[SIGNIFICANT]`, `[HEAVY DESK]`, and `[SYSTEMIC WHALE]`.
* **Live Video Console**: 7 verified global geopolitical and macro video streams (Bloomberg, NDTV Profit, Firstpost, CNA Asia, NBC, DW, Live War Feed) bypassing strict YouTube embedding configurations.
* **Macro Economic Dashboard**: A glassmorphic 4-box CSS grid tracking the Federal Reserve Rate, US NFP, CPI, and Live Market Mood.
* **Global Market Clocks**: A native, highly-optimized horizontal flex tracker indicating timezone hours (Tokyo, London, India, USA) with active/closed market status detection.
* **Asynchronous Asset Pipeline**: `yfinance` integration fetching continuous baseline deltas for 22 global assets and storing them in PostgreSQL.

## 🛠️ Tech Stack

* **Frontend**: HTML5, Vanilla JavaScript, Tailwind CSS.
* **Backend Engine**: Python, FastAPI, Uvicorn, WebSockets.
* **Data Pipeline Engine**: `yfinance`, `psycopg2`, `feedparser`.
* **Database**: PostgreSQL (`finverse`).

## ⚙️ Quickstart & Local Setup

### 1. Prerequisites
- Python 3.10+
- PostgreSQL Server 

### 2. Environment Variables
Create a `.env` file in the root directory:
```env
# Database
DB_PASSWORD=your_postgres_password

# Angel One SmartAPI (Optional for Institutional Feed)
API_KEY=your_angel_api_key
CLIENT_ID=your_client_code
MPIN=your_mpin
TOTP_SECRET=your_totp_key
```

### 3. Installation
Install the required Python packages:
```bash
pip install fastapi uvicorn psycopg2-binary yfinance python-dotenv feedparser websockets pyotp SmartApi-python
```

### 4. Running the Terminal
The application requires running two separate Python scripts and opening the UI locally.

**Terminal Window 1 - Data Ingestion:**
```bash
python ticker_pipeline.py
```

**Terminal Window 2 - Backend & WebSockets:**
```bash
python -m uvicorn server:app --reload --port 8000
```

**Browser:**
Open `index.html` directly in your browser or run it via a Live Server extension (e.g., Port 5500).

## 🗺️ Documentation

- **[CHANGELOG.md](./CHANGELOG.md)**: Track version changes and sprint logs.
- **[SYSTEM_MAP.md](./SYSTEM_MAP.md)**: Details the current architecture, data pipelines, and backlog workflows for future development (Phase 3).
