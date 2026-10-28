"""AURIX voice assistant entry point: ``python -m aurix.main``."""

import sys

from aurix.config import AI_API_KEY
from aurix.observability import configure_logging
from aurix.voice import run_voice_loop


def _make_console_safe() -> None:
    """Never crash on a character the console cannot display (e.g. Telugu in a legacy codepage)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def main() -> None:
    _make_console_safe()
    configure_logging()
    print("=" * 48, flush=True)
    print("             AURIX AI ASSISTANT", flush=True)
    print("=" * 48, flush=True)
    if not AI_API_KEY:
        print(
            "[Setup] AI_API_KEY is not set in .env, so AI answers will not work. "
            "Copy .env.example to .env and add your key.",
            flush=True,
        )
    print("Starting voice pipeline...", flush=True)
    run_voice_loop()


if __name__ == "__main__":
    main()
