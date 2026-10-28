"""Speak one utterance and exit. Run by :mod:`aurix.tts` as ``python -m aurix.tts_worker RATE``.

The text arrives on stdin (UTF-8), never on the command line, so no quoting, length limit or
shell is involved. Exit codes: 0 spoken (or nothing to say), 2 speech engine unavailable.
"""

from __future__ import annotations

import sys

EXIT_OK = 0
EXIT_ENGINE_ERROR = 2


def speak(text: str, rate: int) -> None:
    import pyttsx3

    engine = pyttsx3.init()
    engine.setProperty("rate", rate)
    engine.say(text)
    engine.runAndWait()


def main(argv: list[str]) -> int:
    try:
        rate = int(argv[1]) if len(argv) > 1 else 175
    except ValueError:
        rate = 175
    text = sys.stdin.buffer.read().decode("utf-8", errors="replace").strip()
    if not text:
        return EXIT_OK
    try:
        speak(text, rate)
    except Exception as exc:  # engine/driver errors differ per platform
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ENGINE_ERROR
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
