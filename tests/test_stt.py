"""Offline tests for speech engines, confirmation policy, and WER scoring (no audio hardware)."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from aurix.stt import GoogleEngine, SpeechServiceError, WhisperEngine, build_engine
from aurix.stt_eval import intent_matches, word_error_rate
from aurix.voice_policy import is_action_like, is_no, is_yes, needs_confirmation, vocabulary_prompt


class FakeSR:
    class UnknownValueError(Exception):
        pass

    class RequestError(Exception):
        pass


class FakeAudio:
    def get_raw_data(self, convert_rate=None, convert_width=None):
        return b"\x00\x10" * 1600


class TestGoogleEngine(unittest.TestCase):
    def test_returns_text_and_confidence(self):
        rec = Mock()
        rec.recognize_google.return_value = {
            "alternative": [{"transcript": "open chrome", "confidence": 0.91}]
        }
        result = GoogleEngine(rec, FakeSR).transcribe(object(), "en-US")
        self.assertEqual((result.text, result.confidence), ("open chrome", 0.91))

    def test_missing_confidence_is_none_not_invented(self):
        rec = Mock()
        rec.recognize_google.return_value = {"alternative": [{"transcript": "open chrome"}]}
        self.assertIsNone(GoogleEngine(rec, FakeSR).transcribe(object(), "en-US").confidence)

    def test_not_understood_and_empty_results(self):
        rec = Mock()
        rec.recognize_google.side_effect = FakeSR.UnknownValueError
        self.assertIsNone(GoogleEngine(rec, FakeSR).transcribe(object(), "en-US"))
        rec.recognize_google.side_effect = None
        rec.recognize_google.return_value = []
        self.assertIsNone(GoogleEngine(rec, FakeSR).transcribe(object(), "en-US"))

    def test_service_failure_is_wrapped(self):
        rec = Mock()
        rec.recognize_google.side_effect = FakeSR.RequestError("offline")
        with self.assertRaises(SpeechServiceError):
            GoogleEngine(rec, FakeSR).transcribe(object(), "en-US")


class TestWhisperEngine(unittest.TestCase):
    def _engine(self, segments):
        model = Mock()
        model.transcribe.return_value = (iter(segments), SimpleNamespace())
        return WhisperEngine(model=model, vocabulary_prompt="AURIX commands: open Chrome."), model

    def test_text_confidence_and_vocabulary_prompt(self):
        seg = SimpleNamespace(text=" Open Brave ", no_speech_prob=0.01, avg_logprob=-0.1)
        engine, model = self._engine([seg])
        result = engine.transcribe(FakeAudio(), "en-US")
        self.assertEqual(result.text, "Open Brave")
        self.assertAlmostEqual(result.confidence, 0.905, places=2)
        kwargs = model.transcribe.call_args.kwargs
        self.assertEqual(kwargs["language"], "en")
        self.assertEqual(kwargs["initial_prompt"], "AURIX commands: open Chrome.")
        self.assertTrue(kwargs["vad_filter"])

    def test_silence_hallucination_is_dropped(self):
        seg = SimpleNamespace(text="Thank you.", no_speech_prob=0.95, avg_logprob=-0.2)
        engine, _ = self._engine([seg])
        self.assertIsNone(engine.transcribe(FakeAudio(), "en-US"))

    def test_runtime_failure_is_wrapped(self):
        model = Mock()
        model.transcribe.side_effect = RuntimeError("boom")
        with self.assertRaises(SpeechServiceError):
            WhisperEngine(model=model).transcribe(FakeAudio(), "en-US")

    def test_unknown_engine_name_is_rejected(self):
        with self.assertRaises(SpeechServiceError):
            build_engine("nope", recognizer=Mock(), sr_module=FakeSR)


class TestConfirmationPolicy(unittest.TestCase):
    def test_low_confidence_action_requires_confirmation(self):
        self.assertTrue(needs_confirmation(0.5, True, 0.8))

    def test_confident_unknown_or_non_action_does_not(self):
        self.assertFalse(needs_confirmation(0.95, True, 0.8))
        self.assertFalse(needs_confirmation(None, True, 0.8))
        self.assertFalse(needs_confirmation(0.2, False, 0.8))

    def test_action_detection(self):
        self.assertTrue(is_action_like("open chrome"))
        self.assertTrue(is_action_like("Could you bring up Chrome?"))
        self.assertFalse(is_action_like("What is software engineering?"))

    def test_yes_no_parsing_is_strict(self):
        self.assertTrue(is_yes("Yes."))
        self.assertTrue(is_no("No, cancel"[:2]))
        self.assertFalse(is_yes("yes but not really"))
        self.assertFalse(is_yes(""))

    def test_vocabulary_prompt_lists_known_apps(self):
        prompt = vocabulary_prompt()
        self.assertIn("visual studio code", prompt)
        self.assertIn("Spotify", prompt)


class TestWordErrorRate(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(word_error_rate("open google chrome", "open google chrome"), 0.0)
        self.assertAlmostEqual(word_error_rate("open google chrome", "open google crown"), 1 / 3)
        self.assertEqual(word_error_rate("open chrome", ""), 1.0)
        self.assertEqual(word_error_rate("", ""), 0.0)

    def test_intent_match_uses_resolved_target(self):
        self.assertTrue(intent_matches("open chrome", "Open Chrome."))
        self.assertFalse(intent_matches("open chrome", "open crone"))


if __name__ == "__main__":
    unittest.main()
