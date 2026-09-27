"""Finverse Macro Terminal — one command to run everything.

    python run.py            start engine + UI, open the browser
    python run.py --no-open  start without opening a browser
"""
import logging
import sys
import threading
import webbrowser

import uvicorn

from finverse.config import HOST, PORT, ROOT

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_DIR / "finverse.log", encoding="utf-8")],
)
for noisy in ("httpx", "yfinance", "websockets", "peewee", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

if __name__ == "__main__":
    url = f"http://{HOST}:{PORT}"
    print(f"\n  FINVERSE MACRO TERMINAL  ·  {url}\n")
    if "--no-open" not in sys.argv:
        threading.Timer(2.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("finverse.api:app", host=HOST, port=PORT, log_level="warning")
