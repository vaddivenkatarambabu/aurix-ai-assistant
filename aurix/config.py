"""Load AURIX configuration from environment variables and .env."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _int_setting(name: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


def _float_setting(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _bool_setting(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


OPENAI_MODEL = (
    os.getenv("OPENAI_MODEL")
    or os.getenv("AI_MODEL")
    or "openai/gpt-oss-120b"
).strip()

AI_API_KEY = (
    os.getenv("AI_API_KEY")
    or os.getenv("GROQ_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or ""
).strip()

AI_BASE_URL = (
    os.getenv("AI_BASE_URL")
    or os.getenv("GROQ_BASE_URL")
    or ""
).strip()
if not AI_BASE_URL and "gpt-oss" in OPENAI_MODEL.lower():
    AI_BASE_URL = "https://api.groq.com/openai/v1"

AURIX_REQUIRE_WAKE_WORD = _bool_setting("AURIX_REQUIRE_WAKE_WORD", default=False)
AURIX_WAKE_WORD = os.getenv("AURIX_WAKE_WORD", "aurix").strip().lower()
AURIX_SPEECH_LANGUAGE = os.getenv("AURIX_SPEECH_LANGUAGE", "en-US").strip()
AURIX_CONVERSATION_WINDOW_SECONDS = _int_setting(
    "AURIX_CONVERSATION_WINDOW_SECONDS", 30, minimum=1
)
AURIX_MAX_HISTORY_TURNS = _int_setting("AURIX_MAX_HISTORY_TURNS", 8, minimum=1)
AURIX_REQUEST_TIMEOUT_SECONDS = _float_setting("AURIX_REQUEST_TIMEOUT_SECONDS", 25.0)
AURIX_MAX_API_RETRIES = _int_setting("AURIX_MAX_API_RETRIES", 1, minimum=0)
AURIX_TTS_ENABLED = _bool_setting("AURIX_TTS_ENABLED", default=True)
AURIX_LOG_LEVEL = os.getenv("AURIX_LOG_LEVEL", "INFO").upper()

# Optional Alpha Vantage daily equity market-data integration.
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
AURIX_MARKET_DATA_BASE_URL = (
    os.getenv("AURIX_MARKET_DATA_BASE_URL") or "https://www.alphavantage.co/query"
).strip()
AURIX_MARKET_DATA_TIMEOUT_SECONDS = _float_setting(
    "AURIX_MARKET_DATA_TIMEOUT_SECONDS", 8.0
)
AURIX_MARKET_DATA_CACHE_TTL_SECONDS = _int_setting(
    "AURIX_MARKET_DATA_CACHE_TTL_SECONDS", 300, minimum=0
)
AURIX_MARKET_DATA_MAX_AGE_DAYS = _int_setting(
    "AURIX_MARKET_DATA_MAX_AGE_DAYS", 7, minimum=0
)
AURIX_MARKET_DATA_MAX_RETRIES = min(
    _int_setting("AURIX_MARKET_DATA_MAX_RETRIES", 1, minimum=0), 3
)

# Backwards-compatible alias for older modules.
OPENAI_API_KEY = AI_API_KEY
