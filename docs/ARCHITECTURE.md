# AURIX architecture

## The path of one spoken request

```
microphone ──► SpeechRecognition ──► speech engine (google | whisper) ──► Transcript(text, confidence)
                                                                              │
                                                                  aurix/voice.py  Conversation.process
                                                   wake word? exit? low-confidence action? ──► confirm by voice
                                                                              │
                                                              aurix/assistant.py  handle_command
                          1. local desktop/browser command  (aurix/actions/desktop.py)
                          2. market-data command            (aurix/integrations/market_data.py)
                          3. AI action classifier           (aurix/intent.py) ─► back through step 1
                          4. ordinary AI conversation       (AurixAssistant.ask)
                                                                              │
                              printed on screen  +  to_speech_text()  ──►  aurix/tts.py  Speaker.speak
                                                                              │
                                                    child process: aurix/tts_worker.py (new pyttsx3 engine)
```

Order matters: cheap, deterministic, local handlers go first, so ordinary commands such as
"open Notepad" never cost an AI call, and a sentence like "show me a joke" is passed on to the
AI instead of being mistaken for an app name.

## Why spoken output uses a child process

`pyttsx3` on Windows (SAPI5) plays only the **first** utterance of a given engine object: every
later `runAndWait()` returns at once with no sound and no error. AURIX originally created one
engine at start-up and reused it, so the first reply was spoken and all later ones were
silent (they were still printed).

`aurix/tts.py` therefore never reuses an engine. Each reply is sent over stdin to
`python -m aurix.tts_worker`, a tiny process that creates a fresh engine, speaks, and exits.
Every utterance behaves like the first one. Side benefits: a stuck speech driver is killed after
a timeout, Ctrl+C stops speech immediately, and after three consecutive failures speech turns
itself off with a clear notice instead of failing silently. After each spoken reply the voice
loop also discards microphone audio buffered while AURIX was talking, so it does not hear
itself.

The cost is a short start-up pause (the worker imports the speech library) before each reply is spoken.

## Source files

### Application (`aurix/`)

| File | Responsibility |
|---|---|
| `main.py` | Entry point (`python -m aurix.main`): console safety, logging, start-up banner |
| `config.py` | Reads `.env` / environment variables into typed settings with safe defaults |
| `voice.py` | Microphone loop and `Conversation` (wake word, exit, confirmation, reply + speech) |
| `voice_policy.py` | Pure helpers: is a command action-like, should we confirm, yes/no parsing, Whisper hint text |
| `stt.py` | Speech-to-text engines (`GoogleEngine`, `WhisperEngine`) returning `Transcript` |
| `stt_eval.py` | Word-error-rate and command-intent scoring used by `scripts/eval_stt.py` |
| `tts.py` | `Speaker`: reliable spoken output, one worker process per reply |
| `tts_worker.py` | The worker: reads text on stdin, speaks it with a fresh pyttsx3 engine, exits |
| `speech_text.py` | Converts Markdown/LaTeX answers into plain sentences for speaking |
| `assistant.py` | AI client with bounded retries, conversation history, request routing (`handle_command`) |
| `intent.py` | AI action classifier with strict JSON validation and an allow-list of five actions |
| `observability.py` | Logging setup: console + rotating file, secret redaction, quiet third-party loggers |

### Desktop actions (`aurix/actions/`)

| File | Responsibility |
|---|---|
| `desktop.py` | Parses "open / search / play" commands, decides app vs website, validates URLs, launches without a shell |
| `discovery.py` | Finds verified Windows launch targets (Start Menu, AppsFolder, registry, known paths); never launches |
| `registry.py` | Data only: website URLs, alias groups, system executables, name normalisation. **Add apps and sites here** |
| `messages.py` | Localized response strings (en, es, te, hi, fr) and language detection |

### Integrations (`aurix/integrations/`)

| File | Responsibility |
|---|---|
| `market_data.py` | Alpha Vantage daily-bar client: validation, caching, freshness, deterministic calculations, formatting |

### Tests (`tests/`)

| File | Covers |
|---|---|
| `test_voice.py` | Conversation flow incl. the "every reply is spoken" regression, wake word, confirmation |
| `test_tts.py` | `Speaker` unit tests and a real worker process driven against a stand-in speech engine |
| `test_assistant.py` | AI engine: history, errors, token budget, routing |
| `test_intent.py` | Action classifier validation and provider compatibility |
| `test_desktop_actions.py` | App/website resolution and safety rules (no real launches) |
| `test_stt.py` | Speech engines, confirmation policy, WER scoring |
| `test_speech_text.py` | Markdown-to-speech conversion |
| `test_market_data.py` | Market-data parsing, validation, retries, cache, formatting |
| `test_observability.py` | Logging configuration and secret redaction |

### Scripts (`scripts/`)

| File | Purpose |
|---|---|
| `setup.ps1` | One-time setup: `.venv`, dependencies, `.env` |
| `run.ps1` | Starts AURIX |
| `diagnose.py` | `tts`, `audio`, `model`, `apps` checks for things tests cannot verify |
| `eval_stt.py` | Measure speech-recognition accuracy on your own recordings |
| `verify_release.ps1` | Runs every local quality gate |

### Project files

`requirements.txt` (runtime), `requirements-dev.txt` (tests and tooling),
`requirements-whisper.txt` (optional offline recognition), `pyproject.toml` (Ruff settings),
`.env.example`, `.gitignore`, `.github/workflows/ci.yml`, `.github/dependabot.yml`, `LICENSE`,
`CHANGELOG.md`, `docs/`.

## Design rules

- **No shell, ever.** Launches use argument lists, `os.startfile` or the Windows shell
  `AppsFolder`; spoken text is never executed.
- **The AI proposes, local code decides.** Classifier output is validated against a schema and
  an allow-list, then re-enters the same safe router as typed commands.
- **Fail visibly and keep going.** Provider, microphone and speech failures print a clear
  message; they do not stop the loop. Text is always printed even if speech fails.
- **Python 3.10 compatible.** No syntax newer than 3.10.
