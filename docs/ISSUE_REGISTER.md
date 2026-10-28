# Issue register

Findings from repository inspection, the supplied Windows logs and the automated tests. This is
not a claim that every possible defect has been found. "Verified" means covered by an
automated test; items marked *needs your laptop* depend on hardware or live services.

## Fixed

| ID | Severity | Finding | Root cause | Fix and verification |
|---|---|---|---|---|
| AURIX-010 | **High** | Only the first reply after start-up was spoken; later replies appeared on screen but were silent, with no error. | One `pyttsx3` engine was created at start-up and reused. On Windows (SAPI5) such an engine only completes its first `runAndWait()`; later calls return immediately without sound or exception. | `aurix/tts.py` speaks each reply in a fresh worker process (`aurix/tts_worker.py`). Verified: `tests/test_tts.py` runs the real worker three times against a stand-in engine that reproduces the bug (old design speaks 1 of 3, new design 3 of 3); `tests/test_voice.py` checks every reply is spoken. *Needs your laptop:* `scripts\diagnose.py tts` to confirm with real speakers. |
| AURIX-011 | Medium | Chat such as "show me a joke" or "start over" was answered "'me a joke' was not found in Windows' app inventory" and never reached the AI. | The open-command parser accepts open/start/run/show plus any words as an app name. | Unresolved targets that read like sentences fall through to the AI; short unknown names still say "not found". Verified in `tests/test_desktop_actions.py`. |
| AURIX-012 | Medium | Every action-like request made two AI calls; the first always failed with HTTP 400 (seen in `logs/aurix.log`). | JSON mode is rejected by the configured Groq model and the rejection was not remembered. | The rejection is cached per model; later requests go straight to plain text. Verified in `tests/test_intent.py`. |
| AURIX-013 | Low | "Listening..." printed every second while idle. | Printed on every one-second listen timeout. | Printed once per idle period. |
| AURIX-014 | Low | The log file filled with `httpx`/`comtypes` INFO lines; the log folder depended on the start-up directory. | Third-party loggers inherited INFO; relative `logs` path. | Chatty loggers limited to warnings; default log folder is anchored to the project. |
| AURIX-015 | Low | AURIX could hear its own voice after speaking. | Microphone audio buffered during speech was processed afterwards. | Buffered input is discarded after each spoken reply (best effort). *Needs your laptop* to judge in a quiet/loud room. |
| AURIX-016 | Low | Start-up did not say that the AI key was missing; a Telugu/Hindi transcript could crash a legacy-codepage console. | No check; strict console encoding. | Start-up warning; console output is made non-crashing. |
| AURIX-017 | Low | Duplicate retry/error code in the AI engine and repeated launch/response code in the desktop router; unused `psutil` dependency; empty `browser.py`; stray backup and patch files; Python 3.13-only tooling although Python 3.10 was in use. | Organic growth. | Shared helpers, dead code removed, project made 3.10-compatible, whole tree formatted and linted, CI runs 3.10 and 3.13. |

## Open or informational

| ID | Severity | Finding | Status |
|---|---|---|---|
| AURIX-001 | Info | Natural-language action phrasing relies on a live AI classifier. | Validated and tested offline; live behaviour depends on your provider. |
| AURIX-005 | Info | Runtime dependencies use lower bounds, not a hash-locked lockfile. | Documented follow-up. |
| AURIX-006 | Info | Recognized speech is printed in the terminal. | Not written to the log. |
| AURIX-007 | Info | Market data is daily end-of-day; AI commentary is not verified claim by claim. | Documented limitation. |
| AURIX-018 | Info | The uploaded project contained a real API key in `.env`. | The key was not copied into the cleaned project. Revoke it at your provider and create a new one. |
