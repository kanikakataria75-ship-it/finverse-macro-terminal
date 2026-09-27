# Finverse — System Map (v4 · Obsidian)

## Runtime
One process: `python run.py` → Uvicorn → `finverse.api:app`. The FastAPI lifespan starts `engine.start()`,
which launches every feed as a supervised asyncio task. The UI is static ES modules served from `web/`.

```
          ┌────────────────────────── providers (async tasks) ──────────────────────────┐
Yahoo ───►│ markets.py   quotes 60s · 2y close matrix (data/closes.pkl) · charts · options │
Binance ─►│ crypto.py    spot ticks · funding/OI/LS · OKX/Bybit/Binance liquidations      │
Treasury ►│ macro.py     yield curve · NY Fed rates · BLS · calendar                      │
RSS ─────►│ news.py      18 feeds → dedup (Jaccard) → tags → sentiment → importance       │
Truth/CBs►│ rhetoric.py  post scoring + event-study context · hawk/dove stance · rates    │
GDELT ───►│ geo.py       conflict share · USGS/EONET hazards · chokepoint radar           │
Angel ───►│ angel.py     optional NSE ticks (opt-in, single login attempt)                │
          └───────────────┬──────────────────────────────────────────────────────────────┘
                          │ bus.publish(channel, data) / bus.emit(intel event)
                          ▼
   analytics/quant.py  regime · pulse · anomalies · correlation · transmission · scenario ·
                       event_study · portfolio_risk        (engine runs every 60s)
   analytics/alerts.py rules evaluated on quotes + intel events → ALERT (+ Telegram)
   analytics/oracle.py grounded Q&A (explain / compare / scenario / regime / region / overview)
   analytics/regions.py situation reports + speech-ready summaries
                          │
                          ▼
   bus → /ws  (channels: quotes · intel · news · macro · analytics · rhetoric · geo · crypto · liq · health · alert)
   store.py → data/finverse.db (kv cache · intel log 14d · alerts · watchlist · holdings)
```

## Supervision & health
`engine.every()` / `engine.forever()` wrap each job with exponential backoff and a `Health` record
(status, message, last success, error count). `/api/health` feeds the boot log in the intro, the feed chip
in the header and the Feed Health sheet. A job may return a number to schedule its next run sooner
(the conflict sweep retries in 30 minutes when GDELT is unreachable).

## Intel event tags
`NEWS` (importance ≥ 70) · `RHETORIC` · `CENTRAL BANK` · `SIGMA` (≥ 2.5σ) · `DIVERGENCE` (correlation break) ·
`LIQUIDATION` (≥ $250k; SIGNIFICANT / HEAVY DESK ≥ $1M / SYSTEMIC WHALE ≥ $5M) · `GEOPOLITICS` (escalation) ·
`HAZARD` (M6.5+) · `CHOKEPOINT` (status change) · `REGIME` (quadrant change) · `ALERT` · `INSTITUTIONAL` (Angel) · `SYSTEM`.
Tiers: INFO · SIGNIFICANT · HEAVY · CRITICAL. Tape speed = events/minute; > 25 triggers the systemic frame.

## Frontend (`web/`)
```
js/main.js            gate → intro → home → terminal orchestration
js/core/              util (safe DOM builder, formatting) · state (snapshot + WS) · sound · world · voice
js/three/             intro.js (particles + bloom) · globe.js (reusable globe) · surface.js (3D curve)
js/panels/            common · macro · markets · india · crypto · geo · analytics · portfolio
js/views/             terminal (shell, command line, workspaces) · home · overlays (security, brief, health, help, news)
vendor/               three r170 · d3 7.9 · topojson · lightweight-charts 4.2 · world-atlas (local, no CDN at runtime)
```
Rules: strings enter the DOM only via `textContent`; each panel paints from `S` (state) and subscribes to
bus channels; heavy renderers (globes, surface, regime canvas) run only while visible.

## VEDA (voice)
```
mic ──► AudioWorklet clap detector ─┐
mic ──► Web Speech (continuous) ────┴─► wake ("Veda" / clap×2 / V) ─► listen ─► POST /api/oracle
                                                                               │
          narrator (analytics/speech.py) ◄── facts ◄───────────────────────────┘
                │ spoken text
                ▼
   POST /api/voice/tts (edge-tts neural, data/tts cache) ─► AudioContext ─► analyser ─► avatar jaw/glow
```
Frontend: `js/core/voice.js` (state machine: off → armed → listening → thinking → speaking → linger),
`js/three/avatar.js` (particle bust). Her own voice echoing into the mic is ignored except her name or
a short "stop".

## Key API
`GET /api/snapshot` · `/api/health` · `/api/search?q=` · `/api/chart/{sym}?range=` · `/api/security/{sym}` ·
`/api/options/{sym}` · `/api/news?q=&topic=&sym=&top=` · `/api/macro` · `/api/curve/surface` · `/api/geo` ·
`/api/crypto` · `/api/rhetoric` · `/api/analytics` · `/api/correlation` · `POST /api/scenario` ·
`/api/eventstudy?trigger=&op=&threshold=&target=` · `POST /api/oracle` · `/api/briefing(.md)` ·
`/api/watchlist` · `/api/portfolio` · `/api/alerts` · `/api/voice/config` · `POST /api/voice/tts` · `WS /ws`

## Backlog
| Feature | Notes |
|---|---|
| NSE option chain / OI via Angel One | needs the SmartAPI instrument master (~40 MB) |
| FII/DII daily flows | NSE blocks scripted clients; needs a stable free source |
| Offline speech-to-text | local faster-whisper as an alternative to the browser recogniser (fully private wake word) |
| Multi-monitor desktop shell | Tauri wrapper with pop-out panels |
| Exchange holiday calendars | sessions currently model regular hours only |
