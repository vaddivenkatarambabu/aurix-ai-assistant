"""Privacy-conscious logging configuration for AURIX.

Logs contain operational diagnostics only. Do not pass voice transcripts, API keys,
authorization headers, or full provider payloads to the logger.
"""

from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Anchored to the project folder so logs land in one place wherever AURIX is started from.
_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
# Libraries that log every request/COM step at INFO and drown out AURIX's own messages.
_NOISY_LOGGERS = ("httpx", "httpcore", "openai", "comtypes", "urllib3")
_DEFAULT_MAX_BYTES = 1_048_576
_DEFAULT_BACKUP_COUNT = 3

# These patterns are a defence in depth, not permission to log secrets.
_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b((?:[A-Z0-9_]*_)?(?:API[_ -]?KEY|ACCESS[_ -]?TOKEN|AUTHORIZATION|PASSWORD|SECRET|TOKEN))\b"
        r"(\s*[:=]\s*)(?:(?:Bearer|Basic)\s+)?([^\s,;&]+)"
    ),
    re.compile(r"(?i)([?&](?:apikey|api_key|access_token|token|secret|password)=)[^&\s]+"),
)


class SecretRedactionFormatter(logging.Formatter):
    """Redact common labelled secret values from the final formatted log line."""

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        for pattern in _SECRET_PATTERNS:
            if pattern.groups == 3:
                rendered = pattern.sub(r"\1\2[REDACTED]", rendered)
            else:
                rendered = pattern.sub(r"\1[REDACTED]", rendered)
        return rendered


def _positive_int(raw: str | None, default: int, *, minimum: int = 1) -> int:
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


def _log_level(raw: str | None) -> tuple[int, str | None]:
    candidate = (raw or "INFO").strip().upper()
    value = getattr(logging, candidate, None)
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if not isinstance(value, int) or candidate not in valid_levels:
        return logging.INFO, f"Invalid AURIX log level {candidate!r}; using INFO."
    return value, None


def configure_logging(
    *,
    level: str | None = None,
    log_dir: str | Path | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
    force: bool = False,
) -> None:
    """Set console logging and a bounded rotating log file.

    File logging is best-effort: if the directory cannot be created or written, AURIX
    continues with console logging. Calling this more than once is safe; pass force=True
    only when deliberately replacing handlers (for example, in an isolated test).
    """
    root = logging.getLogger()
    configured_level, level_warning = _log_level(level or os.getenv("AURIX_LOG_LEVEL"))
    root.setLevel(configured_level)

    if getattr(root, "_aurix_logging_configured", False) and not force:
        if level_warning:
            root.warning(level_warning)
        return

    if force or getattr(root, "_aurix_logging_configured", False):
        for old_handler in root.handlers[:]:
            root.removeHandler(old_handler)
            try:
                old_handler.close()
            except Exception:
                pass

    formatter = SecretRedactionFormatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    console = logging.StreamHandler()
    console.setLevel(configured_level)
    console.setFormatter(formatter)
    root.addHandler(console)

    target_dir = (
        Path(log_dir)
        if log_dir is not None
        else Path(os.getenv("AURIX_LOG_DIR") or str(_DEFAULT_LOG_DIR))
    )
    rotate_bytes = (
        max_bytes
        if max_bytes is not None
        else _positive_int(os.getenv("AURIX_LOG_MAX_BYTES"), _DEFAULT_MAX_BYTES)
    )
    retained_files = (
        backup_count
        if backup_count is not None
        else _positive_int(os.getenv("AURIX_LOG_BACKUP_COUNT"), _DEFAULT_BACKUP_COUNT, minimum=0)
    )
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            target_dir / "aurix.log",
            maxBytes=max(1, rotate_bytes),
            backupCount=max(0, retained_files),
            encoding="utf-8",
            delay=True,
        )
        file_handler.setLevel(configured_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        # Do not fail startup solely because optional diagnostic file logging is unavailable.
        root.warning(
            "File logging unavailable (%s); continuing with console logging.",
            type(exc).__name__,
        )

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(max(configured_level, logging.WARNING))

    root._aurix_logging_configured = True  # type: ignore[attr-defined]
    if level_warning:
        root.warning(level_warning)


def reset_logging_for_tests() -> None:
    """Close AURIX handlers; intended for tests, not ordinary application use."""
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    if hasattr(root, "_aurix_logging_configured"):
        delattr(root, "_aurix_logging_configured")
