# Development guide

## Environment

Python **3.10 or newer** (CI runs 3.10 and 3.13 on Windows). Keep code compatible with 3.10.

```powershell
.\scripts\setup.ps1
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v     # offline tests
.\.venv\Scripts\python.exe -m ruff check aurix tests scripts     # lint (incl. import order)
.\.venv\Scripts\python.exe -m ruff format aurix tests scripts    # auto-format
.\scripts\verify_release.ps1                                     # everything, incl. pip-audit
```

The tests mock paid or external services, desktop launches and the microphone. Spoken output is
tested by running the real `tts_worker` process against a stand-in `pyttsx3`, so they pass
without speakers. They do **not** show that your speakers, microphone, every installed app or a
live AI request work; use `scripts/diagnose.py` for those.

## Adding things

- **An app or website**: edit `aurix/actions/registry.py` only (data, no logic).
- **A response language**: add a block to `aurix/actions/messages.py`.
- **A new AI-triggered action**: it must be an explicit validated tool with its own tests and
  authorization; do not widen the five-action allow-list in `aurix/intent.py` casually.
- **A setting**: add it in `aurix/config.py`, `.env.example` and the README table.

## Logging

Standard-library logging writes to the console and to `logs/aurix.log` in the project folder,
rotating at `AURIX_LOG_MAX_BYTES` and keeping `AURIX_LOG_BACKUP_COUNT` backups. File logging is
best-effort: an unwritable folder never stops AURIX. Chatty libraries (`httpx`, `openai`,
`comtypes`, ...) are limited to warnings. A formatter redacts labelled credentials and URL
query secrets as a second line of defence; do not log keys, request bodies or transcripts in
the first place. The voice loop prints transcripts to the terminal only.

## Continuous integration

`.github/workflows/ci.yml` compiles, tests, lints, format-checks, runs `pip check` and
`pip-audit` on Windows for Python 3.10 and 3.13. Third-party actions are pinned to commit SHAs;
Dependabot proposes weekly updates, which should be reviewed rather than auto-merged.

## Known limitations

- Runtime dependencies use lower bounds, not a hash-locked lockfile.
- CI audits vulnerabilities but does not judge licence compatibility.
- This is a script application, not a signed installer or wheel.
- The log redaction filter is a safety net, not a guarantee.
