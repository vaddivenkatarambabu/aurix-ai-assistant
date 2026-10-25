"""Entry point for the AURIX AI Assistant."""

from aurix.voice import run_voice_loop


def main() -> None:
    """Start AURIX."""
    print("=" * 48)
    print("             AURIX AI ASSISTANT")
    print("=" * 48)
    print("Starting voice pipeline...")

    run_voice_loop()


if __name__ == "__main__":
    main()
