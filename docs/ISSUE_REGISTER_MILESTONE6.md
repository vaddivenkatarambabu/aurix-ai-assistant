# AURIX issue register — current repository audit snapshot

Statuses here describe findings supported by repository inspection and the supplied Windows test logs. They are not a claim that every possible defect has been found.

| ID | Severity | Finding / evidence | Root cause | Status / verification |
|---|---|---|---|---|
| AURIX-001 | Medium | Several natural-language paraphrases such as “I need to use Google Chrome” are not directly represented by deterministic open-command patterns. | The desktop router recognizes selected action phrase patterns rather than using a general intent classifier. | A bounded, schema-validated intent classifier is added as an optional pre-conversation fallback; offline tests cover action-cue and response validation. Live provider behavior remains unverified. |
| AURIX-002 | Medium | New logging tests initially failed on Windows while `TemporaryDirectory` attempted to delete an open rotating log file. | Test fixture cleanup ran after directory cleanup. | Fixed in the supplied Milestone 6 local patch. Uploaded Windows output shows all 6 observability tests passing and all 61 tests passing after this repair. |
| AURIX-003 | Low | Ruff lint found two E702 statements in `aurix/actions/desktop.py`. | Registry iteration and index increment were written on one line. | Fixed in local working copy; uploaded output shows `ruff check aurix tests` passing. The latest GitHub `main` already contains the split statements. |
| AURIX-004 | Low | Ruff formatting check failed on `aurix/main.py`, `aurix/observability.py`, and `tests/test_observability.py` in the local working copy. | Local file formatting differs from the successfully CI-checked repository revision. | The installer runs Ruff formatting on these files. Verify locally using `ruff format --check` and the release script before committing. |
| AURIX-005 | Informational | Runtime dependencies use lower bounds, not a platform-resolved hash-locked lockfile. | Project is a Windows-first script application without a packaging/lockfile workflow. | Documented follow-up; do not change dependency pins without tests. |
| AURIX-006 | Informational | Voice recognition prints recognized speech to the interactive terminal. | Existing interactive behavior. | Diagnostic logger does not intentionally record transcripts. Terminal display remains a privacy consideration. |
| AURIX-007 | Informational | Market-data integration is daily end-of-day, not a live quote, and AI analysis is not verified claim-by-claim. | Alpha Vantage daily endpoint and prompt-based commentary design. | Documented limitation; automated tests use mocked provider data. No live provider result is claimed. |

## Required verification before merge

1. Run `..venv\Scripts\python.exe -m unittest discover -s tests -v`.
2. Run `..venv\Scripts\python.exe -m ruff check aurix tests` and `..venv\Scripts\python.exe -m ruff format --check aurix\main.py aurix\observability.py tests\test_observability.py`.
3. Run `.scripts\verify_release.ps1` and confirm every gate completes.
4. Review `git status --short`, `git diff --check`, and the full staged diff.
5. Confirm remote CI for the exact commit that contains the changes.
