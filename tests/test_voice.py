"""Tests for the voice conversation logic (no microphone or speech hardware needed)."""

import contextlib
import io
import unittest
from unittest.mock import Mock, patch

import speech_recognition as sr

from aurix import voice
from aurix.stt import Transcript
from aurix.voice import EXIT_PHRASES, Conversation, _discard_buffered_audio, extract_wake_command


class FakeSpeaker:
    def __init__(self, succeed=True):
        self.spoken = []
        self.succeed = succeed

    def speak(self, text):
        self.spoken.append(text)
        return self.succeed


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def heard(text, confidence=None):
    return Transcript(text, confidence, "test")


class ConversationTestCase(unittest.TestCase):
    def build(self, handler=None, confirm=None, **kwargs):
        self.speaker = FakeSpeaker()
        self.handler = handler or Mock(side_effect=lambda command: f"Answer to {command}.")
        self.confirm = confirm or Mock(return_value=True)
        self.after_speech = Mock()
        self.clock = FakeClock()
        kwargs.setdefault("require_wake_word", False)
        return Conversation(
            self.speaker,
            confirm=self.confirm,
            handler=self.handler,
            on_spoken=self.after_speech,
            clock=self.clock,
            **kwargs,
        )

    def say(self, conversation, text, confidence=None):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            keep_going = conversation.process(heard(text, confidence))
        return keep_going, out.getvalue()


class TestEverySpokenReply(ConversationTestCase):
    def test_second_and_later_replies_are_spoken_too(self):
        """Regression: only the first reply after start-up used to be spoken."""
        conversation = self.build()
        for text in ("hello", "what is python", "tell me a joke", "thank you"):
            keep_going, shown = self.say(conversation, text)
            self.assertTrue(keep_going)
            self.assertIn(f"Answer to {text}.", shown)
        self.assertEqual(
            self.speaker.spoken,
            [f"Answer to {t}." for t in ("hello", "what is python", "tell me a joke", "thank you")],
        )
        self.assertEqual(self.after_speech.call_count, 4)

    def test_markdown_is_removed_from_speech_but_kept_on_screen(self):
        conversation = self.build(handler=Mock(return_value="**Bold** answer with `code`."))
        _, shown = self.say(conversation, "explain")
        self.assertIn("**Bold** answer with `code`.", shown)
        self.assertEqual(self.speaker.spoken, ["Bold answer with code."])

    def test_failed_speech_still_shows_the_answer(self):
        conversation = self.build()
        self.speaker.succeed = False
        _, shown = self.say(conversation, "hello")
        self.assertIn("Answer to hello.", shown)
        self.after_speech.assert_not_called()

    def test_blank_transcript_is_ignored(self):
        conversation = self.build()
        keep_going, shown = self.say(conversation, "   ")
        self.assertTrue(keep_going)
        self.assertEqual((shown, self.speaker.spoken), ("", []))
        self.handler.assert_not_called()


class TestExit(ConversationTestCase):
    def test_exit_phrases_stop_the_loop_silently(self):
        for phrase in EXIT_PHRASES:
            conversation = self.build()
            keep_going, _ = self.say(conversation, phrase)
            self.assertFalse(keep_going, phrase)
        self.assertEqual(self.speaker.spoken, [])
        self.handler.assert_not_called()


class TestWakeWordMode(ConversationTestCase):
    def test_speech_without_wake_word_is_ignored(self):
        conversation = self.build(require_wake_word=True, window_seconds=30)
        _, shown = self.say(conversation, "what time is it")
        self.assertIn("not detected", shown)
        self.handler.assert_not_called()

    def test_wake_word_alone_opens_a_conversation_window(self):
        conversation = self.build(require_wake_word=True, window_seconds=30)
        self.say(conversation, "Aurix")
        self.assertEqual(self.speaker.spoken, ["Yes, I'm listening."])
        self.clock.now += 10
        self.say(conversation, "what time is it")
        self.handler.assert_called_once_with("what time is it")

    def test_window_extends_after_each_answer_and_then_expires(self):
        conversation = self.build(require_wake_word=True, window_seconds=30)
        self.say(conversation, "Aurix hello")
        self.clock.now += 25
        self.say(conversation, "and another")
        self.clock.now += 25  # 50s after start, but only 25s after the last answer
        self.say(conversation, "one more")
        self.assertEqual(self.handler.call_count, 3)
        self.clock.now += 31
        self.say(conversation, "too late")
        self.assertEqual(self.handler.call_count, 3)

    def test_wake_word_with_command_runs_the_command(self):
        conversation = self.build(require_wake_word=True)
        self.say(conversation, "Hey Aurix, open youtube")
        self.handler.assert_called_once_with("open youtube")


class TestConfirmation(ConversationTestCase):
    def test_low_confidence_action_asks_and_declined_action_is_not_run(self):
        conversation = self.build(confirm=Mock(return_value=False))
        self.say(conversation, "open chrome", confidence=0.4)
        self.handler.assert_not_called()
        self.assertIn("Should I do that?", self.speaker.spoken[0])
        self.assertIn("won't do that", self.speaker.spoken[1])

    def test_confirmed_action_runs(self):
        conversation = self.build(confirm=Mock(return_value=True))
        self.say(conversation, "open chrome", confidence=0.4)
        self.handler.assert_called_once_with("open chrome")

    def test_confident_or_unscored_actions_and_plain_chat_never_ask(self):
        conversation = self.build()
        self.say(conversation, "open chrome", confidence=0.95)
        self.say(conversation, "open chrome", confidence=None)
        self.say(conversation, "what is python", confidence=0.2)
        self.confirm.assert_not_called()
        self.assertEqual(self.handler.call_count, 3)


class TestWakeCommandParsing(unittest.TestCase):
    def test_wake_word_and_command(self):
        self.assertEqual(extract_wake_command("Aurix, open YouTube!"), (True, "open youtube"))

    def test_hey_aurix(self):
        self.assertEqual(
            extract_wake_command("Hey, AURIX, tell me the time."), (True, "tell me the time")
        )

    def test_wake_word_alone(self):
        self.assertEqual(extract_wake_command("AURIX"), (True, ""))

    def test_unrelated_speech_has_no_wake_word(self):
        self.assertEqual(extract_wake_command("Open YouTube"), (False, ""))

    def test_custom_wake_word(self):
        self.assertEqual(extract_wake_command("jarvis open mail", "jarvis"), (True, "open mail"))


class TestDiscardBufferedAudio(unittest.TestCase):
    def test_reads_and_drops_whatever_is_waiting(self):
        stream = Mock()
        stream.get_read_available.return_value = 512
        source = Mock(stream=Mock(pyaudio_stream=stream))
        _discard_buffered_audio(source)
        stream.read.assert_called_once_with(512, exception_on_overflow=False)

    def test_nothing_waiting_does_not_read(self):
        stream = Mock()
        stream.get_read_available.return_value = 0
        _discard_buffered_audio(Mock(stream=Mock(pyaudio_stream=stream)))
        stream.read.assert_not_called()

    def test_missing_stream_or_device_errors_are_swallowed(self):
        _discard_buffered_audio(object())
        stream = Mock()
        stream.get_read_available.side_effect = OSError("device lost")
        _discard_buffered_audio(Mock(stream=Mock(pyaudio_stream=stream)))


class TestRunVoiceLoopEndToEnd(unittest.TestCase):
    """Drive the real loop with a fake microphone: three questions, each spoken, then exit."""

    def test_every_answer_is_spoken_and_exit_ends_the_loop(self):
        script = [
            "hello",
            None,  # one second of silence
            "what is python",
            "tell me a joke",
            "exit",
        ]

        class FakeRecognizer:
            def __init__(self):
                self.queue = list(script)

            def adjust_for_ambient_noise(self, source, duration=0):
                pass

            def listen(self, source, timeout=None, phrase_time_limit=None):
                item = self.queue.pop(0)
                if item is None:
                    raise sr.WaitTimeoutError()
                return item

        class FakeMicrophone:
            stream = None

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeEngine:
            def transcribe(self, audio, language):
                return Transcript(audio, None, "fake")

        speaker = FakeSpeaker()
        answers = iter(["Hi there.", "Python is a language.", "Why did the chicken cross?"])
        with (
            patch.object(voice.sr, "Recognizer", FakeRecognizer),
            patch.object(voice.sr, "Microphone", FakeMicrophone),
            patch.object(voice, "build_engine", return_value=FakeEngine()),
            patch.object(voice, "Speaker", return_value=speaker),
            patch.object(voice, "handle_command", side_effect=lambda command: next(answers)),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            voice.run_voice_loop()

        self.assertEqual(
            speaker.spoken,
            ["Hi there.", "Python is a language.", "Why did the chicken cross?"],
        )
        self.assertIn("Shutting down", out.getvalue())
        # Printed before each fresh listen, but not again for the silent second.
        self.assertEqual(out.getvalue().count("Listening..."), 4)


if __name__ == "__main__":
    unittest.main()
