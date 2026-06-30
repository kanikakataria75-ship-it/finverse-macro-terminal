# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-06-30

### Added
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
