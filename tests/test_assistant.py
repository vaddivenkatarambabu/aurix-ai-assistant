"""Offline unit tests for the AURIX conversation engine."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from aurix.assistant import AIConfigurationError, AurixAssistant


class TestAurixAssistant(unittest.TestCase):
    def test_response_is_returned_and_history_is_preserved(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Hello, I am AURIX."))]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="You said your favorite color is blue.")
                    )
                ]
            ),
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
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"answer {n}"))]
            )
            for n in range(5)
        ]
        assistant = AurixAssistant(
            client=client, model="test-model", max_history_turns=2, max_api_retries=0
        )
        for n in range(5):
            assistant.ask(f"question {n}")
        self.assertEqual(len(assistant.history), 4)

    def test_market_analysis_uses_only_source_data_and_does_not_mutate_history(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="The supplied observations show a positive change."
                    )
                )
            ]
        )
        assistant = AurixAssistant(client=client, model="test-model", max_api_retries=0)
        assistant.history = [{"role": "user", "content": "UNRELATED_PRIVATE_CONTEXT"}]
        original_history = list(assistant.history)
        payload = {
            "source_facts": {"symbol": "IBM", "ohlcv": {"close": "100"}},
            "derived_metrics": {"close_to_close_change_percent": {"value": "25.00"}},
            "generated_analysis": {"status": "not_generated", "text": None},
        }

        answer = assistant.analyze_market_data(payload)

        self.assertIn("positive change", answer)
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(len(messages), 2)
        self.assertIn("source_facts", messages[1]["content"])
        self.assertIn("derived_metrics", messages[1]["content"])
        self.assertNotIn("generated_analysis", messages[1]["content"])
        self.assertNotIn("UNRELATED_PRIVATE_CONTEXT", str(messages))
        self.assertIn("Do not give buy/sell/hold recommendations", messages[0]["content"])
        self.assertEqual(assistant.history, original_history)

    def test_clear_history(self):
        assistant = AurixAssistant(client=Mock(), model="test-model")
        assistant.history = [{"role": "user", "content": "Hello"}]
        assistant.clear_history()
        self.assertEqual(assistant.history, [])

    def test_response_token_budget_is_configurable_and_used(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="Fine."), finish_reason="stop")
            ]
        )
        assistant = AurixAssistant(
            client=client, model="m", max_api_retries=0, max_response_tokens=777
        )
        assistant.ask("Hello")
        self.assertEqual(
            client.chat.completions.create.call_args.kwargs["max_completion_tokens"], 777
        )

    def test_empty_answer_at_length_limit_gets_specific_error_and_no_history(self):
        from aurix.assistant import AIServiceError

        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=""), finish_reason="length")]
        )
        assistant = AurixAssistant(client=client, model="m", max_api_retries=0)
        with self.assertRaises(AIServiceError) as ctx:
            assistant.ask("What is software engineering?")
        self.assertIn("AURIX_MAX_RESPONSE_TOKENS", str(ctx.exception))
        self.assertEqual(assistant.history, [])

    def test_action_like_chat_triggers_one_intent_call_not_three(self):
        from unittest.mock import patch

        import aurix.assistant as module

        fake = Mock()
        fake.interpret_desktop_intent.return_value = None
        fake.ask.return_value = "ok"
        with (
            patch.object(module, "_assistant", fake),
            patch.object(module, "try_handle_desktop_command", return_value=None),
            patch.object(module, "extract_market_data_symbol", return_value=None),
        ):
            self.assertEqual(module.handle_command("can you start explaining python"), "ok")
        self.assertEqual(fake.interpret_desktop_intent.call_count, 1)


if __name__ == "__main__":
    unittest.main()
