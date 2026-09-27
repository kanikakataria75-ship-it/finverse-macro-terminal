"""Runtime configuration. Every secret comes from the environment (.env), never from source."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def env(key: str, default=None):
    val = os.getenv(key)
    if val is None:
        # tolerate "KEY = value" style lines that some editors produce
        val = os.getenv(key + " ")
    return val.strip() if isinstance(val, str) and val.strip() else default


def env_int(key: str, default: int) -> int:
    try:
        return int(env(key, default))
    except (TypeError, ValueError):
        return default


HOST = env("FINVERSE_HOST", "127.0.0.1")
PORT = env_int("FINVERSE_PORT", 8777)

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "finverse.db"
WEB_DIR = ROOT / "web"
STATIC_DATA = Path(__file__).resolve().parent / "data"

# Refresh cadences (seconds)
QUOTE_INTERVAL = env_int("QUOTE_INTERVAL", 60)
HISTORY_INTERVAL = env_int("HISTORY_INTERVAL", 6 * 3600)
NEWS_INTERVAL = env_int("NEWS_INTERVAL", 90)
RHETORIC_INTERVAL = env_int("RHETORIC_INTERVAL", 90)
GDELT_INTERVAL = env_int("GDELT_INTERVAL", 6 * 3600)

# Thresholds
LIQ_FEED_MIN_USD = env_int("LIQ_FEED_MIN_USD", 250_000)
SIGMA_ALERT = float(env("SIGMA_ALERT", "2.5"))

# Optional integrations (all free)
ANGEL_API_KEY = env("API_KEY")
ANGEL_CLIENT_ID = env("CLIENT_ID")
ANGEL_MPIN = env("MPIN")
ANGEL_TOTP = env("TOTP_SECRET")
ANGEL_ENABLED = (env("ANGEL_ENABLED", "false") or "").lower() in ("1", "true", "yes")

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

OLLAMA_URL = env("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", "llama3.2")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
