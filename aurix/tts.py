"""Reliable spoken output for AURIX.

Why every reply is spoken by a fresh process
--------------------------------------------
AURIX used to create one ``pyttsx3`` engine at start-up and call ``say()`` /
``runAndWait()`` on it for every reply. On Windows (SAPI5) that engine only completes its
first utterance: later ``runAndWait()`` calls return immediately without making a sound and
without raising, so the first answer was heard and every later one was silent.

The fix is to stop reusing the engine. :class:`Speaker` hands each utterance to a short-lived
child process (``python -m aurix.tts_worker``) that creates a brand-new engine, speaks, and
exits. Every utterance therefore behaves exactly like the first one, a hung speech driver can
be killed after a timeout, and Ctrl+C stops speech immediately.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MAX_CONSECUTIVE_FAILURES = 3
_MIN_TIMEOUT_SECONDS = 20.0
_SECONDS_PER_CHARACTER = 0.12  # slow-speech allowance so long answers are not cut off

Runner = Callable[..., Any]


class Speaker:
    """Speak text aloud; never raises, and disables itself if speech keeps failing."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        rate: int = 175,
        runner: Runner | None = None,
        notify: Callable[[str], None] | None = None,
    ) -> None:
        self.enabled = enabled
        self.rate = rate
        self._runner = runner or subprocess.run
        self._notify = notify or (lambda message: print(message, flush=True))
        self._failures = 0

    def _command(self) -> list[str]:
        return [sys.executable, "-m", "aurix.tts_worker", str(self.rate)]

    def speak(self, text: str) -> bool:
        """Speak ``text`` and block until finished. Returns True if the worker succeeded."""
        text = (text or "").strip()
        if not self.enabled or not text:
            return False

        timeout = max(_MIN_TIMEOUT_SECONDS, len(text) * _SECONDS_PER_CHARACTER)
        options: dict[str, Any] = {
            "input": text.encode("utf-8"),
            "capture_output": True,
            "timeout": timeout,
            "cwd": str(_PROJECT_ROOT),
            "check": False,
        }
        if sys.platform == "win32":
            options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            completed = self._runner(self._command(), **options)
        except subprocess.TimeoutExpired:
            return self._failed("the speech engine did not finish in time")
        except OSError as exc:
            return self._failed(f"could not start the speech process ({exc})")

        if completed.returncode != 0:
            detail = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
            return self._failed(detail.splitlines()[-1] if detail else "speech engine error")

        self._failures = 0
        return True

    def _failed(self, reason: str) -> bool:
        self._failures += 1
        logger.warning("Speech output failed: %s", reason)
        self._notify(f"[TTS Notice] Could not speak the response: {reason}")
        if self._failures >= _MAX_CONSECUTIVE_FAILURES:
            self.enabled = False
            self._notify(
                "[TTS Notice] Speech output turned off after repeated failures. "
                "Run 'python scripts/diagnose.py tts' to test it; replies stay visible on screen."
            )
        return False
