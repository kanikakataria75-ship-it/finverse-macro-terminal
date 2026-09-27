# Changelog

All notable changes to this project will be documented in this file.

## [4.2.1] - 2026-09-27

### Fixed
- VEDA now starts listening when Finverse turns on (opt-out on the power-on screen) instead of waiting for a click.
- Wake word recognises the many ways speech engines spell "Veda" (vada, vedas, wada, bheda, वेदा…) plus near-misses; "Finverse" also works.
- Clap detection is attack-based and tolerant of room echo, quiet laptop mics and noisy rooms.
- Questions are no longer cut off at the first pause; VEDA waits for a real pause before answering.
- Oracle answers far more questions directly — Fed/RBI/ECB, inflation, jobs, bonds, news, calendar ("when is the next Fed meeting"), market mood, crypto, greetings/help — looks up any company by name, and understands natural what-ifs ("what if the rupee falls 5 percent").

## [4.2.0 · Terrain] - 2026-09-27

### Added
- **Macro Terrain**: the Global Macro Radar is now a 3D extruded map — each country's height and colour encode the active metric, with a west-to-east rise when switching modes, hover lift + tooltip, click-through drawer, quake rings with light beams, floating chokepoint beacons, live labels on the biggest movers, orbit/zoom/reset, shadows and selective bloom. The flat map remains one click away (3D | 2D).
- Maximize any panel (⤢ or double-click its title bar; Esc restores).

### Fixed
- Map tooltip/drawer crashed for countries whose conflict score is "insufficient coverage".

## [4.1.0 · VEDA] - 2026-09-27

### Added
- **VEDA**, the voice of Finverse: wake by saying "Veda" (always-on recogniser, one-breath commands, barge-in with "Veda, stop"), by clapping twice, the V key or the mic button; optional auto-start from the power-on screen.
- Natural neural voices (Microsoft Edge Read Aloud via `edge-tts`, free) served by `/api/voice/tts` with an on-disk cache and pre-rendered acknowledgements; browser voices as fallback.
- Narrator (`analytics/speech.py`): conversational scripts built from Oracle facts — rounded numbers, trader units, context, correct currency-pair semantics.
- Region situation reports in Oracle (Gulf, Middle East, Red Sea, Russia–Ukraine, Taiwan, India–Pakistan, Africa, Korea).
- Particle avatar (`web/js/three/avatar.js`): a human bust assembled from neon dust with hologram lighting, audio-driven jaw, thinking halo and dissolve.

### Fixed
- Liquidations aggregate OKX + Bybit + Binance (Binance futures streams are silent on some networks); OKX contract specs fetched from whichever regional host answers.
- Conflict Intensity Index measures the conflict *share* of each country's coverage (raw counts painted big-news countries as war zones).

## [4.0.0 · Obsidian] - 2026-09-27

A ground-up rebuild: new engine, new analytics, new interface. The v3 code is preserved in `legacy/`.

### Security & correctness fixes
- **Removed hardcoded ACLED credentials and EIA API key** from source (they had been pushed to a public repo — rotate them).
- Fixed stored-XSS path: feed text was injected with `innerHTML`; every string is now rendered as text.
- Removed the unauthenticated `/api/macro/ingest` endpoint; server binds to `127.0.0.1`; no wildcard CORS.
- Angel One: started once (was launched twice → double login, duplicate alerts); opt-in via `ANGEL_ENABLED`; a failed login is never retried.
- Liquidations now use the correct futures streams (the spot host never carried `!forceOrder@arr`), aggregated across OKX, Bybit and Binance.
- Truth Social feed uses real status IDs and post timestamps; no more re-broadcasting the same post every 60s.
- Removed every simulated value: random 1W/1M toggles, hardcoded Fed/CPI/NFP/"Market Mood" tiles, war-score baselines added on top of real data, discarded EIA responses, canned "intelligence" text.
- Research: `key_findings.md` was empty because the study filtered `^GSPC` while the data used `SPY`; recomputed with bootstrap CIs (`tools/build_rhetoric_study.py`).

### Engine
- One command (`python run.py`), no Postgres: supervised asyncio feeds, in-process pub/sub, SQLite storage, live feed health.
- New free data: US Treasury curve, NY Fed rates, BLS macro, 18-feed news wire with cross-source confirmation, Fed/RBI/ECB press, USGS & NASA EONET hazards, GDELT conflict share, Binance funding/OI/long-short, crypto Fear & Greed, CoinGecko global.

### Analytics
- Regime Compass, Global & India Pulse, σ-outlier detection, correlation matrix + break detector.
- India Transmission Model with implied open, Scenario Simulator, portfolio stress tests.
- Event Study Lab (15y, declustered, abnormal returns, bootstrap CIs).
- Chokepoint Radar, Conflict Intensity Index (coverage share, bias-corrected).
- Oracle analyst (explain / compare / scenario / regime / region situation reports) with optional local LLM.
- Alerts engine (price, % move, σ, keyword, liquidation size, rhetoric heat) with browser + Telegram delivery.
- Portfolio: live ₹ P&L across Indian and global assets, VaR/CVaR, beta, drawdown.

### Interface
- Cinematic Three.js intro, 3D globe home with day/night terminator and live exchange beacons.
- Obsidian design system; seven F-key workspaces; command line with autocomplete; ticker & news tapes.
- Security page with candles, fundamentals, macro betas and options analytics; 3D yield-curve surface.
- **Finverse Voice**: clap twice → ask → spoken answer.

## [Phase 3] - 2026-07-03

### Added
- **Truth Social State Persistence Pipeline**: Configured scraper in `truth_scraper.py` to cache the latest post and force push it to the backend every 60 seconds to maintain visual terminal state even if no new posts are parsed.
- **Real-Time Post Timestamp Extraction**: Scraper now parses the actual post timestamp directly from the HTML and forwards it down the pipeline.
- **Interactive Manual Pinning Subsystem**: Replaced auto-pinning with a manual client-side JS pin/unpin handler, allowing operators to pin logs to the top header section.
- **Trump Profile Avatar**: Integrated local asset `image_feb74e.jpg` with standard 50% circular clipping, face centering, and gold-themed neon glowing border circles.

### Changed
- **Rhetoric Radar UI Overhaul**: Upgraded component to "TRUMP METER" with glowing monospace neon-amber styling, deleted the simulation button, and restructured the raw text readout box with word-wrap protections.
- **FastAPI Payload Schema**: Updated `IngestPayload` and WS broadcasts in `server.py` to support `published_at` and `is_new` payload fields.

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
