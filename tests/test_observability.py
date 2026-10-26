"""Tests for AURIX logging configuration and secret redaction."""

from __future__ import annotations

import logging
from contextlib import contextmanager
import tempfile
import unittest
from pathlib import Path

from aurix.observability import (
    SecretRedactionFormatter,
    configure_logging,
    reset_logging_for_tests,
)


class TestSecretRedactionFormatter(unittest.TestCase):
    def setUp(self) -> None:
        self.formatter = SecretRedactionFormatter("%(levelname)s %(message)s")

    def test_redacts_environment_style_api_key_and_bearer_token(self) -> None:
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            "AI_API_KEY=sk-private, Authorization: Bearer very-secret-token",
            (),
            None,
        )
        rendered = self.formatter.format(record)
        self.assertNotIn("sk-private", rendered)
        self.assertNotIn("very-secret-token", rendered)
        self.assertIn("AI_API_KEY=[REDACTED]", rendered)
        self.assertIn("Authorization: [REDACTED]", rendered)

    def test_redacts_secret_url_query_parameters(self) -> None:
        record = logging.LogRecord(
            "test",
            logging.INFO,
            __file__,
            1,
            "request failed at https://example.test/?apikey=private-value&symbol=IBM",
            (),
            None,
        )
        rendered = self.formatter.format(record)
        self.assertNotIn("private-value", rendered)
        self.assertIn("apikey=[REDACTED]", rendered)
        self.assertIn("symbol=IBM", rendered)


class TestLoggingConfiguration(unittest.TestCase):
    @contextmanager
    def _temporary_logging_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            try:
                yield directory
            finally:
                reset_logging_for_tests()

    def tearDown(self) -> None:
        reset_logging_for_tests()

    def test_writes_timestamped_operational_log_and_console_handler(self) -> None:
        with self._temporary_logging_directory() as directory:
            configure_logging(level="INFO", log_dir=directory, force=True)
            logger = logging.getLogger("aurix.test")
            logger.info("test event")
            for handler in logging.getLogger().handlers:
                handler.flush()

            output = Path(directory, "aurix.log").read_text(encoding="utf-8")
            self.assertIn("INFO [aurix.test] test event", output)
            self.assertRegex(output, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
            self.assertTrue(
                any(
                    isinstance(handler, logging.StreamHandler)
                    for handler in logging.getLogger().handlers
                )
            )

    def test_invalid_log_level_falls_back_without_raising(self) -> None:
        with self._temporary_logging_directory() as directory:
            configure_logging(level="NOT_A_LEVEL", log_dir=directory, force=True)
            self.assertEqual(logging.getLogger().level, logging.INFO)
            logging.getLogger("aurix.test").warning("configuration continues")

    def test_repeated_configuration_does_not_duplicate_handlers(self) -> None:
        with self._temporary_logging_directory() as directory:
            configure_logging(level="INFO", log_dir=directory, force=True)
            root = logging.getLogger()
            handler_count = len(root.handlers)
            configure_logging(level="INFO", log_dir=directory)
            self.assertEqual(len(root.handlers), handler_count)

    def test_log_file_rotates_and_retention_is_bounded(self) -> None:
        with self._temporary_logging_directory() as directory:
            configure_logging(
                level="INFO", log_dir=directory, max_bytes=180, backup_count=1, force=True
            )
            logger = logging.getLogger("aurix.rotation")
            for index in range(12):
                logger.info("event %s %s", index, "x" * 60)
            for handler in logging.getLogger().handlers:
                handler.flush()
            log_path = Path(directory, "aurix.log")
            backup_path = Path(directory, "aurix.log.1")
            self.assertTrue(log_path.exists())
            self.assertTrue(backup_path.exists())
            self.assertFalse(Path(directory, "aurix.log.2").exists())


if __name__ == "__main__":
    unittest.main()
