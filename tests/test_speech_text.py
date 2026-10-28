"""Offline tests for Markdown-to-speech normalisation."""

import unittest

from aurix.speech_text import to_speech_text


class TestSpeechText(unittest.TestCase):
    def test_markdown_markers_are_not_spoken(self):
        spoken = to_speech_text("# Title\n**Bold** and _italic_ and `code`.\n- one\n- two")
        for marker in ("#", "**", "`", "_italic_"):
            self.assertNotIn(marker, spoken)
        self.assertIn("Bold and italic and code.", spoken)
        self.assertIn("one. two.", spoken)

    def test_meaningful_symbols_are_preserved(self):
        text = "C# and C++ use snake_case_name, well-known terms, and #1 rankings."
        self.assertEqual(to_speech_text(text), text)

    def test_simple_arithmetic_is_spoken_as_words(self):
        self.assertEqual(to_speech_text("2*3=6"), "2 times 3 equals 6")
        self.assertEqual(to_speech_text("10 + 5 = 15"), "10 plus 5 equals 15")
        self.assertEqual(
            to_speech_text("x^2 grows, 50% of 8-12 apples"),
            "x squared grows, 50 percent of 8-12 apples",
        )

    def test_latex_is_spoken_and_prices_are_untouched(self):
        self.assertEqual(
            to_speech_text(r"Use $\frac{a}{b}$ and $\sqrt{x}$."),
            "Use a over b and square root of x.",
        )
        self.assertEqual(to_speech_text("It costs $5 and $10."), "It costs $5 and $10.")

    def test_links_and_urls(self):
        spoken = to_speech_text(
            "See [the docs](https://docs.python.org/3/) or https://www.python.org/x."
        )
        self.assertEqual(spoken, "See the docs or python.org.")

    def test_code_block_is_summarised_not_read(self):
        spoken = to_speech_text("Run this:\n```python\nprint('hi')\n```\nDone.")
        self.assertNotIn("print", spoken)
        self.assertIn("code example", spoken)
        self.assertTrue(spoken.endswith("Done."))

    def test_numbered_list_keeps_numbers(self):
        self.assertEqual(to_speech_text("1. Plan\n2. Build"), "1. Plan. 2. Build.")

    def test_empty_and_non_string_inputs(self):
        self.assertEqual(to_speech_text(""), "")
        self.assertEqual(to_speech_text(None), "")

    def test_original_text_is_not_mutated(self):
        original = "**Bold**"
        to_speech_text(original)
        self.assertEqual(original, "**Bold**")


if __name__ == "__main__":
    unittest.main()
