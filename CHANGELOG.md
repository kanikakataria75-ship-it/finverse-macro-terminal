# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-07-01

### Added
- **Dynamic Geopolitical Radar Heatmap**: Replaced the static world map with a fully data-driven SVG TopoJSON rendering engine. Added map toggles for `[WAR ZONES]`, `[OIL RESERVES]`, and `[GOLD RESERVES]` that apply live min-max color scaling.
- **ACLED Conflict Mapping**: Expanded the `d3ToIso` frontend dictionary to support TopoJSON mapping for major ACLED conflict regions (Syria, Yemen, Sudan, Myanmar, Afghanistan, etc.).
- **Live Marquee Hydration**: Hooked up the top scrolling ticker bar to pull real-time asset pricing from the `/api/macro-metrics` polling loop instead of static HTML.

### Changed
- **Pipeline Consolidation (`macro_pipeline.py`)**: Deprecated `ticker_pipeline.py` and merged all async data ingestions (Angel One WebSocket, Binance Liquidations, ACLED War Data, yFinance) into a single, unified `macro_pipeline.py` worker script.
- **Frontend Map Engine**: Upgraded `GeopoliticsRadar` class to continuously poll `/api/macro/map-state` every 10 seconds.
- **SVG Styling Override**: Swapped D3's `.attr("fill")` to `.style("fill")` to correctly override the `cyber-wireframe` CSS class and enable vibrant data-driven color coding.

### Fixed
- Javascript map color scale crashes caused by falsy `0` evaluations on null reserve metrics.
- Database authentication locking and multi-threading deadlocks caused by stray port 8000 `uvicorn` processes.

## [Phase 2] - 2026-06-30
- **Live Text Intel Feed Engine**: Coalesced multi-stream asynchronous pipeline successfully integrated via FastAPI WebSockets.
- **Background Ingestion Tasks**:
  - `[SYSTEM]`: Server status and heartbeat tracking.
  - `[VOLATILITY]`: High-frequency delta surging tracker.
  - `[MACRO]`: RSS pipeline for global structural news (Reuters/Bloomberg mock).
  - `[LIQUIDATION]`: Native Binance WebSocket `!forceOrder@arr` integration handling >$5M blocks.
  - `[DIVERGENCE]`: Hourly correlation checks.
  - `[INSTITUTIONAL]`: Angel One SmartAPI Level 2 depth monitoring for domestic NSE stocks.
- **3-Tier Whale Categorization Algorithm**: Dynamically tags massive blocks into `[SIGNIFICANT]`, `[HEAVY DESK]`, and `[SYSTEMIC WHALE]` based on aggregate value.
- **Frontend Live Feed UI**: Fully interactive scroll container rendering color-coded logs natively via WebSockets without external dependencies.
- **Phase 2 Governance Architecture**: Generated `SYSTEM_MAP.md` mapping current data flows and logging the 'Live NSE Option Activity' tracker to the backlog.

### Changed
- Re-architected `server.py` to support `uvicorn` background `asyncio` task scheduling parallel to the FastAPI thread.
- Overhauled `<div id="live-feed-log">` inside `index.html` to accept parsed JSON payloads directly from `/ws/intel`.

### Fixed
- Stripped experimental properties off the Video Console Iframe natively to bypass YouTube Error 153 definitively.
