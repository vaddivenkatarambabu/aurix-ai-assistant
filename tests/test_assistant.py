"""Offline unit tests for the AURIX conversation engine."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from aurix.assistant import AIConfigurationError, AurixAssistant


class TestAurixAssistant(unittest.TestCase):
    def test_response_is_returned_and_history_is_preserved(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Hello, I am AURIX."))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="You said your favorite color is blue."))]),
        ]
        assistant = AurixAssistant(
            client=client,
            model="test-model",
            max_history_turns=4,
            max_api_retries=0,
        )

        first = assistant.ask("Introduce yourself.")
        second = assistant.ask("What is my favorite color? I said blue.")

        self.assertEqual(first, "Hello, I am AURIX.")
        self.assertIn("blue", second)
        messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
        self.assertEqual(messages[1], {"role": "user", "content": "Introduce yourself."})
        self.assertEqual(messages[2], {"role": "assistant", "content": "Hello, I am AURIX."})

    def test_empty_prompt_does_not_call_api(self):
        client = Mock()
        assistant = AurixAssistant(client=client, model="test-model")
        self.assertIn("Please tell me", assistant.ask("  "))
        client.chat.completions.create.assert_not_called()

    def test_missing_key_is_clear(self):
        assistant = AurixAssistant(api_key="", model="test-model")
        with self.assertRaises(AIConfigurationError):
            assistant.ask("Hello")

    def test_history_is_bounded(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f"answer {n}"))])
            for n in range(5)
        ]
        assistant = AurixAssistant(
            client=client, model="test-model", max_history_turns=2, max_api_retries=0
        )
        for n in range(5):
            assistant.ask(f"question {n}")
        self.assertEqual(len(assistant.history), 4)

    def test_clear_history(self):
        assistant = AurixAssistant(client=Mock(), model="test-model")
        assistant.history = [{"role": "user", "content": "Hello"}]
        assistant.clear_history()
        self.assertEqual(assistant.history, [])


if __name__ == "__main__":
    unittest.main()
