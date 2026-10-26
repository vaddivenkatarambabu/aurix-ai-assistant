# AURIX release-readiness checklist

Use this checklist before tagging or distributing a release. A clean startup alone is not a release sign-off.

## Source and review

- [ ] Work is on a reviewed feature branch and the intended diff is small and understood.
- [ ] No `.env`, API keys, access tokens, user transcripts, logs, virtual environments, or local backups are staged.
- [ ] Changes are reviewed for unintended edits and `git diff --check` is clean.
- [ ] Version and release notes are explicitly selected by the maintainer; this repository does not currently define a package version or publish a distributable artifact.

## Build and configuration

- [ ] Install dependencies into a fresh Python 3.13 virtual environment on supported Windows.
- [ ] Missing AI and market-data keys fail clearly without sending a request.
- [ ] AURIX starts and shuts down cleanly; microphone and optional TTS failures are reported honestly.
- [ ] No interactive microphone, desktop launch, AI request, or live market-data request is needed for unit tests.

## Quality gates

- [ ] `python -m compileall -q aurix tests` passes.
- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] `ruff check aurix tests` passes.
- [ ] `ruff format --check aurix/main.py aurix/observability.py tests/test_observability.py` passes.
- [ ] `python -m pip check` passes.
- [ ] `pip-audit -r requirements-dev.txt` completes and findings are reviewed; any exception must be explicit, narrow, and documented.
- [ ] Direct and transitive dependency licences are reviewed for the intended distribution model; the CI workflow does not automate licence compatibility decisions.
- [ ] Required GitHub Actions checks pass on the proposed commit.

## Functional and data safety

- [ ] Desktop/browser operations are mocked in unit tests and arbitrary shell execution remains blocked.
- [ ] Market-data responses retain provider provenance and separate observation dates from UTC retrieval times.
- [ ] Market data is labeled daily end-of-day, not live; stale or insufficient data is not represented as current.
- [ ] Source facts, derived metrics, and AI-generated commentary remain separate.
- [ ] Logs do not contain credentials, authorization headers, private transcripts, or raw provider payloads.

## Release and recovery

- [ ] README setup, configuration, troubleshooting, and test instructions match the code.
- [ ] Remaining compatibility limitations and unresolved security findings are documented.
- [ ] The maintainer has selected release notes and any version tag.
- [ ] Rollback is understood: revert the release commit or redeploy the previously reviewed commit; preserve configuration and secret stores.
- [ ] Publishing a release or deployment is done manually and only after explicit approval.

## PowerShell release check

From the repository root with `.venv` and `requirements-dev.txt` installed, run:

```powershell
.\scripts\verify_release.ps1
```

The script stops on the first failed check. The dependency audit requires network access to vulnerability data. A blocked audit is not a pass.
