"""Tests for spoken output: every reply must be spoken, not only the first one."""

import functools
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from aurix import tts_worker
from aurix.tts import Speaker

# A stand-in for pyttsx3 that reproduces the Windows bug behind "only the first answer is
# spoken": within one process, an engine only makes sound for its first runAndWait().
FAKE_PYTTSX3 = textwrap.dedent(
    """
    import os

    _state = {"used": False}

    class _Engine:
        def setProperty(self, name, value):
            self.rate = value

        def say(self, text):
            self.text = text

        def runAndWait(self):
            if _state["used"]:
                return  # silent, exactly like the real bug
            _state["used"] = True
            with open(os.environ["FAKE_TTS_LOG"], "a", encoding="utf-8") as log:
                log.write(self.text + "\\n")

    def init():
        return _Engine()
    """
)

FAILING_PYTTSX3 = "def init():\n    raise RuntimeError('no SAPI voice installed')\n"


def completed(returncode=0, stderr=b""):
    return SimpleNamespace(returncode=returncode, stderr=stderr)


class TestSpeakerUnit(unittest.TestCase):
    def make(self, runner, **kwargs):
        notices = []
        speaker = Speaker(runner=runner, notify=notices.append, **kwargs)
        return speaker, notices

    def test_each_utterance_gets_its_own_worker_process(self):
        runner = Mock(return_value=completed())
        speaker, _ = self.make(runner, rate=160)
        for text in ("Hello there.", "Second answer.", "Third answer."):
            self.assertTrue(speaker.speak(text))
        self.assertEqual(runner.call_count, 3)
        first_call = runner.call_args_list[0]
        self.assertEqual(first_call.args[0][1:], ["-m", "aurix.tts_worker", "160"])
        self.assertEqual(
            [call.kwargs["input"] for call in runner.call_args_list],
            [b"Hello there.", b"Second answer.", b"Third answer."],
        )

    def test_unicode_text_is_sent_as_utf8(self):
        runner = Mock(return_value=completed())
        speaker, _ = self.make(runner)
        speaker.speak("నమస్కారం")
        self.assertEqual(runner.call_args.kwargs["input"], "నమస్కారం".encode("utf-8"))

    def test_disabled_or_empty_never_starts_a_process(self):
        runner = Mock()
        speaker, _ = self.make(runner, enabled=False)
        self.assertFalse(speaker.speak("Hello"))
        speaker.enabled = True
        self.assertFalse(speaker.speak("   "))
        runner.assert_not_called()

    def test_long_text_gets_a_longer_timeout(self):
        runner = Mock(return_value=completed())
        speaker, _ = self.make(runner)
        speaker.speak("Hi.")
        short = runner.call_args.kwargs["timeout"]
        speaker.speak("word " * 1000)
        self.assertGreater(runner.call_args.kwargs["timeout"], short)

    def test_failure_is_reported_not_raised(self):
        runner = Mock(return_value=completed(2, b"RuntimeError: no voice\n"))
        speaker, notices = self.make(runner)
        self.assertFalse(speaker.speak("Hello"))
        self.assertIn("no voice", notices[0])

    def test_timeout_and_start_errors_are_reported(self):
        for error in (subprocess.TimeoutExpired("tts", 1), OSError("cannot start")):
            speaker, notices = self.make(Mock(side_effect=error))
            self.assertFalse(speaker.speak("Hello"))
            self.assertEqual(len(notices), 1)

    def test_repeated_failures_turn_speech_off_and_success_resets_the_count(self):
        runner = Mock(return_value=completed(2, b"boom"))
        speaker, notices = self.make(runner)
        speaker.speak("one")
        speaker.speak("two")
        runner.return_value = completed()
        self.assertTrue(speaker.speak("three"))  # success resets the failure count
        runner.return_value = completed(2, b"boom")
        for _ in range(3):
            speaker.speak("again")
        self.assertFalse(speaker.enabled)
        self.assertIn("turned off", notices[-1])
        calls = runner.call_count
        speaker.speak("silent now")
        self.assertEqual(runner.call_count, calls)


class TestSpeakerWithRealWorkerProcess(unittest.TestCase):
    """Run the real worker in a real child process against the fake pyttsx3 above."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name, "spoken.txt")

    def speaker_with(self, pyttsx3_source):
        Path(self.tmp.name, "pyttsx3.py").write_text(pyttsx3_source, encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": self.tmp.name, "FAKE_TTS_LOG": str(self.log)}
        notices = []
        speaker = Speaker(runner=functools.partial(subprocess.run, env=env), notify=notices.append)
        return speaker, notices

    def test_every_reply_is_spoken_not_only_the_first(self):
        speaker, notices = self.speaker_with(FAKE_PYTTSX3)
        replies = ["Hello! How can I help?", "Python is a language.", "Goodbye for now."]
        for reply in replies:
            self.assertTrue(speaker.speak(reply))
        self.assertEqual(self.log.read_text(encoding="utf-8").splitlines(), replies)
        self.assertEqual(notices, [])

    def test_missing_speech_voice_is_reported_with_the_real_reason(self):
        speaker, notices = self.speaker_with(FAILING_PYTTSX3)
        self.assertFalse(speaker.speak("Hello"))
        self.assertIn("no SAPI voice installed", notices[0])


class TestWorkerMain(unittest.TestCase):
    def test_empty_input_exits_cleanly_without_speech_engine(self):
        original = sys.stdin
        try:
            sys.stdin = SimpleNamespace(buffer=SimpleNamespace(read=lambda: b"  \n"))
            self.assertEqual(tts_worker.main(["tts_worker", "175"]), tts_worker.EXIT_OK)
        finally:
            sys.stdin = original

    def test_bad_rate_falls_back_to_default(self):
        spoken = []
        original_speak, original_stdin = tts_worker.speak, sys.stdin
        try:
            tts_worker.speak = lambda text, rate: spoken.append((text, rate))
            sys.stdin = SimpleNamespace(buffer=SimpleNamespace(read=lambda: b"Hi"))
            self.assertEqual(tts_worker.main(["tts_worker", "fast"]), tts_worker.EXIT_OK)
        finally:
            tts_worker.speak, sys.stdin = original_speak, original_stdin
        self.assertEqual(spoken, [("Hi", 175)])


if __name__ == "__main__":
    unittest.main()
