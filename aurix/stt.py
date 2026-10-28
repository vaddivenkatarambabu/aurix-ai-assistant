"""Speech-to-text engines for AURIX.

Two interchangeable engines return a :class:`Transcript` (text plus an optional 0-1
confidence). ``google`` is the free web endpoint behind ``recognize_google``;
``whisper`` is a local faster-whisper model (offline, no per-request cost, audio stays
on the machine). Neither is claimed to handle every accent: measure with
``scripts/eval_stt.py`` on your own recordings.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class SpeechServiceError(RuntimeError):
    """The recognition backend failed (network, model load, or runtime error)."""


@dataclass(frozen=True)
class Transcript:
    text: str
    confidence: float | None  # None means the engine gave no usable signal
    engine: str


class SpeechEngine(Protocol):
    name: str

    def transcribe(self, audio: Any, language: str) -> Transcript | None:
        """Return a transcript, or None when no speech was understood."""


def _clamp01(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and 0.0 <= value <= 1.0 else None


class GoogleEngine:
    name = "google"

    def __init__(self, recognizer: Any, sr_module: Any) -> None:
        self._recognizer = recognizer
        self._sr = sr_module

    def transcribe(self, audio: Any, language: str) -> Transcript | None:
        try:
            result = self._recognizer.recognize_google(audio, language=language, show_all=True)
        except self._sr.UnknownValueError:
            return None
        except self._sr.RequestError as exc:
            raise SpeechServiceError(f"Google speech request failed: {exc}") from exc
        alternatives = result.get("alternative") if isinstance(result, dict) else None
        if not alternatives:
            return None
        best = alternatives[0]
        text = str(best.get("transcript", "")).strip()
        return Transcript(text, _clamp01(best.get("confidence")), self.name) if text else None


class WhisperEngine:
    """Local faster-whisper recognition with hallucination and low-confidence filtering."""

    name = "whisper"

    def __init__(
        self,
        model_size: str = "small",
        *,
        vocabulary_prompt: str = "",
        max_no_speech_prob: float = 0.6,
        model: Any | None = None,
    ) -> None:
        self._prompt = vocabulary_prompt or None
        self._max_no_speech = max_no_speech_prob
        if model is not None:  # injected in tests
            self._model = model
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SpeechServiceError(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            ) from exc
        try:
            self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
        except Exception as exc:  # download/IO/runtime errors vary by platform
            raise SpeechServiceError(f"Could not load Whisper model '{model_size}': {exc}") from exc

    def transcribe(self, audio: Any, language: str) -> Transcript | None:
        try:
            import numpy as np

            pcm = np.frombuffer(
                audio.get_raw_data(convert_rate=16000, convert_width=2), dtype=np.int16
            )
            samples = pcm.astype(np.float32) / 32768.0
            segments, _info = self._model.transcribe(
                samples,
                language=(language or "en").split("-")[0].lower(),
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=self._prompt,
            )
            kept: list[str] = []
            logprobs: list[float] = []
            for segment in segments:
                if getattr(segment, "no_speech_prob", 0.0) > self._max_no_speech:
                    continue  # silence/noise that Whisper may "hear" as text
                text = segment.text.strip()
                if text:
                    kept.append(text)
                    logprobs.append(float(getattr(segment, "avg_logprob", -1.0)))
        except SpeechServiceError:
            raise
        except Exception as exc:
            raise SpeechServiceError(f"Whisper transcription failed: {exc}") from exc
        if not kept:
            return None
        confidence = _clamp01(math.exp(sum(logprobs) / len(logprobs)))
        return Transcript(" ".join(kept), confidence, self.name)


def build_engine(
    name: str,
    *,
    recognizer: Any,
    sr_module: Any,
    whisper_model: str = "small",
    vocabulary_prompt: str = "",
) -> SpeechEngine:
    """Create the configured engine; ``auto`` prefers Whisper when it is installed."""
    choice = (name or "google").strip().lower()
    if choice == "auto":
        try:
            import faster_whisper  # noqa: F401

            choice = "whisper"
        except ImportError:
            choice = "google"
    if choice == "whisper":
        return WhisperEngine(whisper_model, vocabulary_prompt=vocabulary_prompt)
    if choice == "google":
        return GoogleEngine(recognizer, sr_module)
    raise SpeechServiceError(f"Unknown AURIX_STT_ENGINE '{name}'. Use google, whisper or auto.")
