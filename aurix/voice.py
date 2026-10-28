"""Voice loop: listen, transcribe, optionally confirm, answer on screen, and speak the answer.

The decision logic lives in :class:`Conversation` and needs no audio hardware, so it is
unit-tested. :func:`run_voice_loop` only wires it to the microphone and speech engine.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable

import speech_recognition as sr

from aurix.assistant import handle_command
from aurix.config import (
    AURIX_CONVERSATION_WINDOW_SECONDS,
    AURIX_PAUSE_THRESHOLD_SECONDS,
    AURIX_PHRASE_TIME_LIMIT_SECONDS,
    AURIX_REQUIRE_WAKE_WORD,
    AURIX_SPEECH_LANGUAGE,
    AURIX_STT_ENGINE,
    AURIX_STT_MIN_ACTION_CONFIDENCE,
    AURIX_TTS_ENABLED,
    AURIX_TTS_RATE,
    AURIX_WAKE_WORD,
    AURIX_WHISPER_MODEL,
)
from aurix.speech_text import to_speech_text
from aurix.stt import SpeechServiceError, Transcript, build_engine
from aurix.tts import Speaker
from aurix.voice_policy import is_action_like, is_no, is_yes, needs_confirmation, vocabulary_prompt

logger = logging.getLogger(__name__)

EXIT_PHRASES = frozenset({"exit", "quit", "shutdown", "stop listening", "stop aurix"})


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


class Conversation:
    """Turn recognized transcripts into spoken and printed replies."""

    def __init__(
        self,
        speaker: Speaker,
        *,
        confirm: Callable[[], bool],
        handler: Callable[[str], str] | None = None,
        on_spoken: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        require_wake_word: bool = AURIX_REQUIRE_WAKE_WORD,
        wake_word: str = AURIX_WAKE_WORD,
        window_seconds: float = AURIX_CONVERSATION_WINDOW_SECONDS,
        min_action_confidence: float = AURIX_STT_MIN_ACTION_CONFIDENCE,
    ) -> None:
        self._speaker = speaker
        self._confirm = confirm
        self._handler = handler or handle_command
        self._on_spoken = on_spoken
        self._clock = clock
        self._require_wake_word = require_wake_word
        self._wake_word = wake_word
        self._window = window_seconds
        self._min_confidence = min_action_confidence
        self._awake_until = 0.0

    def respond(self, text: str) -> None:
        """Print the readable text, then speak a Markdown-free copy of it."""
        print(f"\nAURIX: {text}\n", flush=True)
        spoken = to_speech_text(text)
        if spoken and self._speaker.speak(spoken) and self._on_spoken:
            self._on_spoken()

    def process(self, result: Transcript) -> bool:
        """Handle one transcript. Returns False when the user asked AURIX to stop."""
        transcript = result.text.strip()
        if not transcript:
            return True

        print(f"You: {transcript}", flush=True)
        detected, wake_command = extract_wake_command(transcript, self._wake_word)
        now = self._clock()

        if detected and not wake_command:
            self._awake_until = now + self._window
            self.respond("Yes, I'm listening.")
            return True
        if detected:
            command = wake_command
        elif self._require_wake_word and now > self._awake_until:
            print(f"[AURIX] No response because '{self._wake_word}' was not detected.", flush=True)
            return True
        else:
            command = transcript

        command = command.strip()
        if not command:
            return True
        if command.casefold() in EXIT_PHRASES:
            print("[AURIX] Shutting down.", flush=True)
            return False
        if command.casefold() != transcript.casefold():
            print(f"You asked: {command}", flush=True)

        if needs_confirmation(result.confidence, is_action_like(command), self._min_confidence):
            self.respond(f"I heard: {command}. Should I do that? Say yes or no.")
            if not self._confirm():
                self.respond("Okay, I won't do that. Please say it again.")
                return True

        self.respond(self._handler(command))
        if self._require_wake_word:
            self._awake_until = self._clock() + self._window
        return True


def _confirmed(recognizer: Any, source: Any, engine: Any) -> bool:
    """Listen once for an explicit yes; anything else (including silence) means no."""
    try:
        audio = recognizer.listen(source, timeout=6, phrase_time_limit=4)
        answer = engine.transcribe(audio, AURIX_SPEECH_LANGUAGE)
    except (sr.WaitTimeoutError, SpeechServiceError):
        return False
    if answer is None:
        return False
    return is_yes(answer.text) and not is_no(answer.text)


def _discard_buffered_audio(source: Any) -> None:
    """Drop microphone audio captured while AURIX was speaking so it is not heard as input."""
    stream = getattr(getattr(source, "stream", None), "pyaudio_stream", None)
    try:
        waiting = stream.get_read_available() if stream is not None else 0
        if waiting:
            stream.read(waiting, exception_on_overflow=False)
    except Exception:  # best effort: an input-device quirk must never stop the loop
        logger.debug("Could not discard buffered microphone audio.", exc_info=True)


def _print_banner(language: str) -> None:
    print("\nAURIX is ready.", flush=True)
    print(f"Speech recognition language: {language}", flush=True)
    if AURIX_REQUIRE_WAKE_WORD:
        print(
            f"Say '{AURIX_WAKE_WORD.upper()}' first; conversation stays active "
            f"for {AURIX_CONVERSATION_WINDOW_SECONDS} seconds after a response.",
            flush=True,
        )
    else:
        print("Conversational mode is enabled: recognized speech is sent to the AI.", flush=True)
    print("Say 'exit' or press Ctrl+C to stop.\n", flush=True)


def run_voice_loop() -> None:
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = AURIX_PAUSE_THRESHOLD_SECONDS
    speaker = Speaker(enabled=AURIX_TTS_ENABLED, rate=AURIX_TTS_RATE)

    try:
        print(f"Preparing speech engine '{AURIX_STT_ENGINE}'...", flush=True)
        engine = build_engine(
            AURIX_STT_ENGINE,
            recognizer=recognizer,
            sr_module=sr,
            whisper_model=AURIX_WHISPER_MODEL,
            vocabulary_prompt=vocabulary_prompt(),
        )
    except SpeechServiceError as exc:
        logger.error("Speech engine setup failed (%s).", type(exc).__name__)
        print(f"[Speech Engine Error] {exc}", flush=True)
        return

    try:
        microphone = sr.Microphone()
    except (AttributeError, OSError) as exc:
        logger.error("Microphone initialization failed (%s).", type(exc).__name__)
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
            _print_banner(AURIX_SPEECH_LANGUAGE)
            conversation = Conversation(
                speaker,
                confirm=lambda: _confirmed(recognizer, source, engine),
                on_spoken=lambda: _discard_buffered_audio(source),
            )

            recognition_failures = 0
            idle = False
            while True:
                if not idle:
                    print("Listening...", flush=True)
                    idle = True
                try:
                    audio = recognizer.listen(
                        source, timeout=1, phrase_time_limit=AURIX_PHRASE_TIME_LIMIT_SECONDS
                    )
                except sr.WaitTimeoutError:
                    continue
                idle = False

                try:
                    result = engine.transcribe(audio, AURIX_SPEECH_LANGUAGE)
                except SpeechServiceError as exc:
                    logger.error("Speech recognition failed (%s).", type(exc).__name__)
                    print(f"[Speech Service Error] {exc}", flush=True)
                    recognition_failures += 1
                    time.sleep(min(2 ** min(recognition_failures, 4), 15))
                    continue
                recognition_failures = 0
                if result is None:
                    print(
                        "[Voice] Speech was not understood; try speaking closer to the mic.",
                        flush=True,
                    )
                    continue
                if not conversation.process(result):
                    break

    except KeyboardInterrupt:
        print("\n[AURIX] Stopped by user.", flush=True)
    except OSError as exc:
        logger.error("Microphone loop failed (%s).", type(exc).__name__)
        print(
            f"[Microphone Error] {exc}\n"
            "Check your input device and Windows microphone permissions.",
            flush=True,
        )
