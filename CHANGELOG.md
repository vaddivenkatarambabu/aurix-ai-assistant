# Changelog

## 0.7.0 - Reliable voice output and cleanup

### Fixed
- **Only the first reply was spoken.** Each reply is now spoken by a fresh worker process, so
  every answer is audible. (`aurix/tts.py`, `aurix/tts_worker.py`)
- Chat starting with "show", "start", "run" or "open" (for example "show me a joke") is no
  longer mistaken for an app name.
- The action classifier remembers when a model rejects JSON mode instead of failing on every
  request.
- "Listening..." is printed once per idle period instead of every second.
- Microphone audio buffered while AURIX speaks is discarded so it does not hear itself.
- Console output cannot crash on characters the console cannot show.

### Added
- `AURIX_TTS_RATE` setting; `scripts/diagnose.py tts`; `scripts/setup.ps1`; `scripts/run.ps1`.
- Start-up warning when `AI_API_KEY` is missing.
- Tests for the voice loop, spoken output (real worker process) and the fixes above (140 total).
- `docs/ARCHITECTURE.md`, `docs/TROUBLESHOOTING.md`, `docs/MARKET_DATA.md`,
  `docs/DEVELOPMENT.md`; README and the other documents rewritten.

### Changed
- Python 3.10 or newer is supported and tested (CI: 3.10 and 3.13).
- Voice loop split into a testable `Conversation` class; AI retry/error handling shared;
  desktop responses deduplicated and localized.
- Third-party loggers limited to warnings; the log folder is anchored to the project.
- Whole tree is formatted with Ruff; import order is linted.

### Removed
- Unused `psutil` dependency, empty `aurix/actions/browser.py`, unused message keys, the
  `OPENAI_API_KEY` module alias, `tests/test_smoke.py` (merged into `tests/test_voice.py`).
- Stray files from the working copy: a backup of `assistant.py`, a pasted Git patch,
  `__pycache__`, `.ruff_cache`, and the local log file.
