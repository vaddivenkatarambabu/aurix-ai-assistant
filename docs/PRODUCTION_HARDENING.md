# Production hardening notes (Milestone 6)

## Logging

AURIX configures standard-library logging during startup. It writes concise timestamped messages to the console and to `logs/aurix.log`, rotating at the configured size and retaining a bounded number of backups. Set `AURIX_LOG_LEVEL` to `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`; `AURIX_LOG_DIR`, `AURIX_LOG_MAX_BYTES`, and `AURIX_LOG_BACKUP_COUNT` control file logging. File logging is best-effort, so an unwritable log directory does not prevent the assistant from starting.

The log formatter redacts common labelled credential fields and URL query credentials as defense in depth. This is not a guarantee that arbitrary secrets in free text can be detected. Do not log API keys, full request/response bodies, authorization headers, or voice transcripts in the first place. The current voice loop intentionally prints the recognized transcript to the interactive terminal; this is not copied to the diagnostic log by this change.

## Developer checks

Install the supported Python version and dependencies, then run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m compileall -q aurix tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check aurix tests
.\.venv\Scripts\python.exe -m ruff format --check aurix\main.py aurix\observability.py tests\test_observability.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\pip-audit.exe -r requirements-dev.txt
.\scripts\verify_release.ps1
```

GitHub Actions repeats compilation, tests, linting, selected formatter checks, dependency consistency, and the dependency audit on Windows/Python 3.13 for pushes, pull requests, or manual dispatch. Third-party actions are referenced by immutable commit SHA and the workflow has read-only repository contents permission. Dependabot proposes weekly dependency and GitHub Actions updates; review those pull requests rather than auto-merging them.

## Scope and known limitations

- Unit tests mock paid/external services and desktop/microphone operations; they do not establish that every physical device or live provider request works.
- Runtime requirements still use version lower bounds rather than a complete platform-resolved, hash-locked runtime lockfile. The development tool versions are pinned; runtime dependency reproducibility remains a follow-up.
- CI runs a vulnerability audit but does not automatically decide whether dependency licences are compatible with a specific distribution model. Review direct and transitive dependency licences before distributing AURIX.
- The current source tree is a Windows-first script application, not an installable wheel or signed distribution. This hardening work does not publish releases, configure deployments, or declare a production-service SLO.
- The logging redaction filter is only a secondary safeguard. Callers remain responsible for avoiding secrets and sensitive text in log messages.
- Market data is daily end-of-day from Alpha Vantage, not a real-time quote; the implementation does not infer exchange closure or validate AI prose claim by claim.
