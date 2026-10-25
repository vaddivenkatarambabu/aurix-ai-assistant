"""Microphone input, optional wake-word gating, and visible responses."""

import re
import time
from typing import Any

import speech_recognition as sr

from aurix.assistant import handle_command
from aurix.config import (
    AURIX_CONVERSATION_WINDOW_SECONDS,
    AURIX_REQUIRE_WAKE_WORD,
    AURIX_SPEECH_LANGUAGE,
    AURIX_TTS_ENABLED,
    AURIX_WAKE_WORD,
)


def extract_wake_command(
    transcript: str,
    wake_word: str = AURIX_WAKE_WORD,
) -> tuple[bool, str]:
    """Detect the wake word at the beginning of a recognized utterance."""
    text_words = re.sub(r"[^a-z0-9\s]", " ", transcript.casefold()).split()
    wake_words = re.sub(r"[^a-z0-9\s]", " ", wake_word.casefold()).split()

    if not text_words or not wake_words:
        return False, ""

    start = 1 if text_words[0] in {"hey", "okay", "ok"} else 0
    if text_words[start : start + len(wake_words)] != wake_words:
        return False, ""

    command = " ".join(text_words[start + len(wake_words) :]).strip()
    return True, command


def _make_speaker() -> Any | None:
    """Create optional text-to-speech without making it a startup dependency."""
    if not AURIX_TTS_ENABLED:
        return None
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", 175)
        return engine
    except Exception as exc:  # TTS must not prevent the text conversation from working.
        print(f"[TTS Notice] Speech output is unavailable: {exc}", flush=True)
        return None


def _respond(text: str, speaker: Any | None) -> None:
    """Display every response; speak it when TTS is available."""
    print(f"\nAURIX: {text}\n", flush=True)
    if speaker is not None:
        try:
            speaker.say(text)
            speaker.runAndWait()
        except Exception as exc:
            print(f"[TTS Notice] Could not speak the response: {exc}", flush=True)


def run_voice_loop() -> None:
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8
    speaker = _make_speaker()

    try:
        microphone = sr.Microphone()
    except (AttributeError, OSError) as exc:
        print(
            f"[Microphone Error] {exc}\n"
            "Check PyAudio, the selected input device, and Windows microphone permissions.",
            flush=True,
        )
        return

    print("\nCalibrating microphone for background noise...", flush=True)
    try:
        with microphone as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.8)
            print("\nAURIX is ready.", flush=True)
            if AURIX_REQUIRE_WAKE_WORD:
                print(
                    f"Say '{AURIX_WAKE_WORD.upper()}' first; conversation stays active "
                    f"for {AURIX_CONVERSATION_WINDOW_SECONDS} seconds after a response.",
                    flush=True,
                )
            else:
                print(
                    "Conversational mode is enabled: recognized speech is sent to the AI. "
                    "Set AURIX_REQUIRE_WAKE_WORD=true in .env to require the wake word.",
                    flush=True,
                )
            print("Say 'exit' or press Ctrl+C to stop.\n", flush=True)

            awake_until = 0.0
            while True:
                try:
                    print("Listening...", flush=True)
                    audio = recognizer.listen(
                        source,
                        timeout=1,
                        phrase_time_limit=8,
                    )
                except sr.WaitTimeoutError:
                    continue

                try:
                    transcript = recognizer.recognize_google(
                        audio,
                        language=AURIX_SPEECH_LANGUAGE,
                    ).strip()
                except sr.UnknownValueError:
                    print("[Voice] Speech was not understood; try speaking closer to the mic.", flush=True)
                    continue
                except sr.RequestError as exc:
                    print(
                        f"[Speech Service Error] Recognition failed: {exc}. "
                        "Check your internet connection.",
                        flush=True,
                    )
                    time.sleep(1)
                    continue

                if not transcript:
                    continue

                print(f"You: {transcript}", flush=True)
                detected, wake_command = extract_wake_command(transcript)
                now = time.monotonic()

                if detected and not wake_command:
                    awake_until = now + AURIX_CONVERSATION_WINDOW_SECONDS
                    _respond("Yes, I'm listening.", speaker)
                    continue

                if detected and wake_command:
                    command = wake_command
                elif AURIX_REQUIRE_WAKE_WORD and now > awake_until:
                    print(
                        f"[AURIX] No response because '{AURIX_WAKE_WORD}' was not detected. "
                        "Say the wake word or set AURIX_REQUIRE_WAKE_WORD=false in .env.",
                        flush=True,
                    )
                    continue
                else:
                    command = transcript

                command = command.strip()
                if not command:
                    continue

                if command.casefold() in {
                    "exit", "quit", "shutdown", "stop listening", "stop aurix"
                }:
                    print("[AURIX] Shutting down.", flush=True)
                    break

                # Show what will be sent to the AI so ignored/misheard speech is visible.
                if command.casefold() != transcript.casefold():
                    print(f"You asked: {command}", flush=True)

                response = handle_command(command)
                _respond(response, speaker)
                if AURIX_REQUIRE_WAKE_WORD:
                    # Keep a short conversation window open for follow-up questions.
                    awake_until = time.monotonic() + AURIX_CONVERSATION_WINDOW_SECONDS

    except KeyboardInterrupt:
        print("\n[AURIX] Stopped by user.", flush=True)
    except OSError as exc:
        print(
            f"[Microphone Error] {exc}\n"
            "Check your input device and Windows microphone permissions.",
            flush=True,
        )
