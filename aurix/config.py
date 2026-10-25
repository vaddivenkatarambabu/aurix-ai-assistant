"""Configuration loading for AURIX."""

import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")

AURIX_LOG_LEVEL = os.getenv("AURIX_LOG_LEVEL", "INFO")

AURIX_WAKE_WORD = os.getenv("AURIX_WAKE_WORD", "aurix").strip().lower()

AURIX_SPEECH_LANGUAGE = os.getenv(
    "AURIX_SPEECH_LANGUAGE",
    "en-US",
).strip()
