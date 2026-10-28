# Release checklist

A clean start-up alone is not a release sign-off.

## Source and review

- [ ] The intended diff is small and understood; `git diff --check` is clean.
- [ ] No `.env`, API keys, tokens, transcripts, logs, virtual environments or local backups are staged.
- [ ] The maintainer has chosen the version and release notes; update `CHANGELOG.md`.

## Quality gates

- [ ] `.\scripts\verify_release.ps1` passes (compile, tests, lint, format, `pip check`, `pip-audit`).
- [ ] Findings from `pip-audit` are reviewed; any exception is narrow and documented.
- [ ] Dependency licences are reviewed for the intended distribution.
- [ ] GitHub Actions passes on the exact commit (Python 3.10 and 3.13).

## On a real Windows machine (what CI cannot check)

- [ ] Fresh `.venv` from `requirements.txt`; missing AI/market keys fail with a clear message.
- [ ] `scripts\diagnose.py tts` is **heard three times**.
- [ ] A live conversation: three questions in a row are each printed **and spoken**.
- [ ] `diagnose.py model` and `diagnose.py apps` look right; one app launches end to end.
- [ ] Ctrl+C and "exit" stop AURIX cleanly.

## Functional and data safety

- [ ] Arbitrary shell execution remains impossible; executable paths and scripts are rejected.
- [ ] Market data is labelled end-of-day; facts, calculations and AI commentary stay separate.
- [ ] Logs hold no credentials, transcripts or raw provider payloads.

## Release and recovery

- [ ] README, configuration table and troubleshooting match the code.
- [ ] Remaining limitations are documented.
- [ ] Rollback is understood: revert the release commit or redeploy the previous reviewed one.
- [ ] Publishing is done manually, after explicit approval.
