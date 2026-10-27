"""Offline tests for schema-validated natural-language action interpretation."""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from aurix.intent import (
    ActionIntent,
    execute_action_intent,
    interpret_action_intent,
    should_attempt_desktop_interpretation,
)


def response(payload):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
    )


def intent(action, **changes):
    payload = {
        "action": action,
        "target": "Google Chrome",
        "query": None,
        "confidence": 0.96,
        "needs_clarification": False,
        "clarification_question": None,
    }
    payload.update(changes)
    return payload


class TestIntentGate(unittest.TestCase):
    def test_candidate_action_paraphrases_enter_interpreter(self):
        examples = (
            "Can you launch Chrome for me?",
            "I need to use Google Chrome.",
            "Please bring up Chrome.",
            "Take me to the Google website.",
            "I want to search something on Google.",
        )
        for phrase in examples:
            with self.subTest(phrase=phrase):
                self.assertTrue(should_attempt_desktop_interpretation(phrase))

    def test_explanatory_question_does_not_enter_interpreter(self):
        self.assertFalse(should_attempt_desktop_interpretation("How do I open Chrome?"))
        self.assertFalse(should_attempt_desktop_interpretation("Explain decorators in Python."))


class TestIntentValidation(unittest.TestCase):
    def test_application_intent_is_validated(self):
        client = Mock()
        client.chat.completions.create.return_value = response(intent("open_application"))
        parsed = interpret_action_intent(
            "I need to use Google Chrome.", client=client, model="test-model"
        )
        self.assertEqual(parsed, ActionIntent("open_application", target="Google Chrome", confidence=0.96))
        client.chat.completions.create.assert_called_once()

    def test_website_intent_is_validated(self):
        client = Mock()
        client.chat.completions.create.return_value = response(
            intent("open_website", target="Google")
        )
        parsed = interpret_action_intent("Take me to Google.", client=client, model="test-model")
        self.assertEqual(parsed.action, "open_website")
        self.assertEqual(parsed.target, "Google")

    def test_search_intent_requires_query(self):
        client = Mock()
        client.chat.completions.create.return_value = response(
            intent("search_web", target=None, query="weather tomorrow")
        )
        parsed = interpret_action_intent(
            "I want to search something on Google.", client=client, model="test-model"
        )
        self.assertEqual(parsed.action, "search_web")
        self.assertEqual(parsed.query, "weather tomorrow")

    def test_unknown_action_is_rejected(self):
        client = Mock()
        client.chat.completions.create.return_value = response(intent("run_shell"))
        self.assertIsNone(
            interpret_action_intent("Please launch Chrome", client=client, model="test-model")
        )

    def test_confidence_outside_range_is_rejected(self):
        client = Mock()
        client.chat.completions.create.return_value = response(intent("open_application", confidence=1.2))
        self.assertIsNone(
            interpret_action_intent("Please launch Chrome", client=client, model="test-model")
        )

    def test_low_confidence_requests_clarification(self):
        client = Mock()
        client.chat.completions.create.return_value = response(
            intent("open_application", confidence=0.5, clarification_question="App or website?")
        )
        parsed = interpret_action_intent("Open Chrome", client=client, model="test-model")
        self.assertEqual(parsed.action, "clarify")
        self.assertEqual(parsed.clarification_question, "App or website?")

    def test_path_and_shell_like_targets_are_rejected(self):
        for bad_target in (r"C:\\Windows\\System32", "cmd.exe", "Google; shutdown"):
            with self.subTest(target=bad_target):
                client = Mock()
                client.chat.completions.create.return_value = response(
                    intent("open_application", target=bad_target)
                )
                self.assertIsNone(
                    interpret_action_intent("Open this app", client=client, model="test-model")
                )

    def test_malformed_json_is_rejected(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
        )
        self.assertIsNone(
            interpret_action_intent("Launch Chrome", client=client, model="test-model")
        )

    def test_model_failure_returns_none(self):
        client = Mock()
        client.chat.completions.create.side_effect = TimeoutError("provider timeout")
        self.assertIsNone(
            interpret_action_intent("Launch Chrome", client=client, model="test-model")
        )


class TestSafeIntentExecution(unittest.TestCase):
    def test_application_runs_through_existing_executor(self):
        executor = Mock(return_value="Opening installed application: Google Chrome.")
        result = execute_action_intent(
            ActionIntent("open_application", target="Google Chrome", confidence=0.96),
            executor,
            language="en-US",
        )
        self.assertIn("Opening installed application", result)
        executor.assert_called_once_with("open Google Chrome app", language="en-US")

    def test_website_runs_through_existing_executor(self):
        executor = Mock(return_value="Opening Google in your default browser.")
        result = execute_action_intent(
            ActionIntent("open_website", target="Google", confidence=0.96), executor
        )
        self.assertIn("default browser", result)
        executor.assert_called_once_with("open Google website", language=None)

    def test_search_query_is_passed_to_existing_search_router(self):
        executor = Mock(return_value="Searching the web.")
        execute_action_intent(
            ActionIntent("search_web", query="latest Python release", confidence=0.94), executor
        )
        executor.assert_called_once_with("search the web for latest Python release", language=None)

    def test_no_action_never_calls_executor(self):
        executor = Mock()
        result = execute_action_intent(ActionIntent("none", confidence=0.9), executor)
        self.assertIsNone(result)
        executor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
