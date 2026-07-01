# Finverse World Macro Terminal - System Map

## Architecture Overview

**1. Frontend (`index.html`)**
- Single-page application built with HTML, Vanilla JS, and Tailwind CSS runtime.
- High-density, zero-padding trading floor aesthetic.
- Components: Macro Asset Ticker Panel, Dynamic SVG Geopolitical Heatmap (D3.js), Live Video Console, Live Text Intel Feed, Ingestion Stream Status.

**2. Backend Engine (`server.py`)**
- FastAPI server running on Uvicorn.
- **REST API (`/api/macro-metrics`)**: Serves asset data (price, 1d, 1w, 1m deltas) from PostgreSQL.
- **WebSocket (`/ws/intel`)**: Publishes multi-stream data from background ingestion tasks.

**3. Data Pipeline (`macro_pipeline.py`)**
- Unified asynchronous worker replacing previous independent scripts.
- Consolidates `yfinance` baseline ingestion, Angel One WebSockets, Binance Liquidations, and ACLED Geopolitical map metrics.
- Stores data and historical baselines into a local PostgreSQL database (`finverse.macro_assets` and `finverse.macro_map_state`).

## Live Text Intel Feed Data Streams

- **[SYSTEM]**: Generates server status and database heartbeat pulses.
- **[VOLATILITY]**: Real-time monitor tracking delta surges in major indices (NIFTY, GOLD, SILVER, BTC).
- **[MACRO]**: Pulls active headlines via RSS feed parsing (Reuters/Bloomberg mock).
- **[LIQUIDATION]**: Connects directly to Binance `!forceOrder@arr` websocket. Filters block trades > $5M.
- **[DIVERGENCE]**: Rolling hourly check on inter-market macro divergences (DXY vs GOLD, etc.).
- **[INSTITUTIONAL]**: SmartAPI Level 2 Depth anomalies for mega-cap NSE stocks.

## 3-Tier Whale Categorization Algorithm
- **Tier 1 [SIGNIFICANT]**: Normal institutional rebalancing.
- **Tier 2 [HEAVY DESK]**: Aggressive position loading.
- **Tier 3 [SYSTEMIC WHALE]**: Massive liquidity shock block > $10,000,000.

## DEFERRED WORKFLOWS & BACKLOG
| Feature | Priority | Status |
|---|---|---|
| Live NSE Option Activity & OI Delta Tracker | High | Deferred to Phase 3 |
| Advanced Portfolio Position Manager | Low | Backlog |
| Advanced Portfolio Position Manager | Low | Backlog |
