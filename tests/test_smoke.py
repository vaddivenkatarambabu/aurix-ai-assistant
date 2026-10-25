"""Tests for AURIX voice activation."""

import unittest

from aurix.voice import extract_wake_command


class TestWakeWord(unittest.TestCase):
    def test_wake_word_and_command(self):
        detected, command = extract_wake_command("Aurix, open YouTube!")

        self.assertTrue(detected)
        self.assertEqual(command, "open youtube")

    def test_hey_aurix(self):
        detected, command = extract_wake_command("Hey, AURIX, tell me the time.")

        self.assertTrue(detected)
        self.assertEqual(command, "tell me the time")

    def test_wake_word_alone(self):
        detected, command = extract_wake_command("AURIX")

        self.assertTrue(detected)
        self.assertEqual(command, "")

    def test_unrelated_speech_is_ignored(self):
        detected, command = extract_wake_command("Open YouTube")

        self.assertFalse(detected)
        self.assertEqual(command, "")


if __name__ == "__main__":
    unittest.main()
