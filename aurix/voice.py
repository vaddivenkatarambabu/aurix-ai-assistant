"""Microphone input and wake-word handling for AURIX."""

import re
import time

import speech_recognition as sr

from aurix.assistant import handle_command
from aurix.config import AURIX_SPEECH_LANGUAGE, AURIX_WAKE_WORD


def extract_wake_command(
    transcript: str,
    wake_word: str = AURIX_WAKE_WORD,
) -> tuple[bool, str]:
    """Return whether the wake word was detected and its following command.

    Supported examples:
        "Aurix"
        "Aurix, open YouTube"
        "Hey Aurix, open YouTube"
        "Okay Aurix, open YouTube"
    """
    text_words = re.sub(
        r"[^a-z0-9\s]",
        " ",
        transcript.casefold(),
    ).split()

    wake_words = re.sub(
        r"[^a-z0-9\s]",
        " ",
        wake_word.casefold(),
    ).split()

    if not text_words or not wake_words:
        return False, ""

    start = 0

    if text_words[0] in {"hey", "okay", "ok"}:
        start = 1

    found_words = text_words[start : start + len(wake_words)]

    if found_words != wake_words:
        return False, ""

    command = " ".join(text_words[start + len(wake_words) :])

    return True, command.strip()


def run_voice_loop() -> None:
    """Listen for speech and process commands after activation."""
    recognizer = sr.Recognizer()

    # Adjust these values later if your microphone is too sensitive.
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.7

    try:
        microphone = sr.Microphone()
    except (AttributeError, OSError) as exc:
        print(
            f"[Microphone Error] {exc}\n"
            "Check PyAudio, microphone availability, and Windows "
            "microphone permissions."
        )
        return

    print("\nCalibrating microphone for background noise...")

    try:
        with microphone as source:
            recognizer.adjust_for_ambient_noise(
                source,
                duration=0.8,
            )

            print("\nAURIX is ready.")
            print("Say 'AURIX' to activate the assistant.")
            print("Say 'AURIX, exit' or press Ctrl+C to stop.")

            # A wake word alone activates an 8-second command window.
            awake_until = 0.0

            while True:
                try:
                    print("\nListening...")

                    audio = recognizer.listen(
                        source,
                        timeout=1,
                        phrase_time_limit=8,
                    )

                except sr.WaitTimeoutError:
                    # No speech detected during this short listening window.
                    continue

                try:
                    transcript = recognizer.recognize_google(
                        audio,
                        language=AURIX_SPEECH_LANGUAGE,
                    ).strip()

                except sr.UnknownValueError:
                    print("[Voice] Speech was not understood.")
                    continue

                except sr.RequestError as exc:
                    print(
                        "[Speech Service Error] Recognition failed. "
                        "Check your internet connection and try again."
                    )
                    print(f"Details: {exc}")
                    time.sleep(1)
                    continue

                if not transcript:
                    continue

                print(f"You said: {transcript}")

                detected, command = extract_wake_command(transcript)
                now = time.monotonic()

                if detected and not command:
                    awake_until = now + 8
                    print("[AURIX] Yes, I'm listening.")
                    continue

                if not detected:
                    if now > awake_until:
                        # Ignore speech until AURIX is activated.
                        continue

                    # Accept one command within the active listening window.
                    command = transcript

                # One command is processed per activation.
                awake_until = 0.0
                command = command.strip()

                if not command:
                    continue

                if command.casefold() in {
                    "exit",
                    "quit",
                    "shutdown",
                    "stop listening",
                }:
                    print("[AURIX] Shutting down.")
                    break

                response = handle_command(command)
                print(f"\n[AURIX] {response}")

    except KeyboardInterrupt:
        print("\n[AURIX] Stopped by user.")

    except OSError as exc:
        print(
            f"[Microphone Error] {exc}\n"
            "Check your input device and Windows microphone permissions."
        )
