"""AURIX voice assistant entry point."""

from aurix.observability import configure_logging
from aurix.voice import run_voice_loop


def main() -> None:
    configure_logging()
    print("=" * 48, flush=True)
    print("             AURIX AI ASSISTANT", flush=True)
    print("=" * 48, flush=True)
    print("Starting voice pipeline...", flush=True)
    run_voice_loop()


if __name__ == "__main__":
    main()
