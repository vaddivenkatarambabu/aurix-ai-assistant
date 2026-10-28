# AURIX AI Assistant

AURIX is a Windows-first, terminal-based **voice assistant** written in Python. You speak, it
understands, it answers on screen **and out loud**, and it can open apps, websites and searches
for you.

```
You: hello                      →  AURIX: Hello! How can I help?        (printed and spoken)
You: what is software engineering →  AURIX: Software engineering is...   (printed and spoken)
You: open notepad               →  AURIX: Opening installed application: Notepad.
You: stock IBM                  →  AURIX: Market data — IBM (daily end-of-day)...
```

## Features

- **Voice input** through your microphone, with Google's online recognizer (default) or an
  optional local, offline Whisper model.
- **AI conversation** through any OpenAI-compatible chat API (the example config uses Groq and
  `openai/gpt-oss-120b`). Short in-memory conversation history; nothing is stored on disk.
- **Spoken replies for every answer** using the Windows speech voice (pyttsx3). Markdown is
  stripped before speaking, so you hear natural sentences, not "asterisk asterisk".
- **Desktop and browser actions**: open installed apps, known websites or any URL, search the
  web, search YouTube. Natural phrasing such as "I need to use Chrome" is understood through a
  validated AI classifier. See [docs/SPEECH_AND_ACTIONS.md](docs/SPEECH_AND_ACTIONS.md).
- **Market data** (optional): `stock IBM` returns daily end-of-day data with freshness checks and
  clearly separated AI commentary. See [docs/MARKET_DATA.md](docs/MARKET_DATA.md).
- **Safety by design**: speech never reaches a shell; executable paths and scripts are rejected;
  the AI can only choose from five harmless actions.
- **Optional wake word** ("Aurix, ..."), spoken confirmation for low-confidence commands, and
  light multilingual command patterns (English, Spanish, French, Hindi, Telugu).

## Quick start (Windows)

You need **Windows 10/11, Python 3.10 or newer, a microphone, and an internet connection**.

```powershell
cd path\to\aurix-ai-assistant
.\scripts\setup.ps1        # creates .venv, installs everything, creates .env
notepad .env               # paste your key after AI_API_KEY=
.\scripts\run.ps1          # start AURIX
```

Prefer to do it by hand?

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe -m aurix.main
```

Say **"exit"** (or press **Ctrl+C**) to stop. If something does not work, start with
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

> **Keep your key private.** `.env` holds your API key and is ignored by Git. Never share it,
> attach it to a message, or commit it. If you ever do, revoke the key at your provider and
> create a new one.

### Check each part works (recommended once)

```powershell
.\.venv\Scripts\python.exe scripts\diagnose.py tts     # speaks 3 sentences in a row
.\.venv\Scripts\python.exe scripts\diagnose.py audio   # lists microphones, shows the speech engine
.\.venv\Scripts\python.exe scripts\diagnose.py model   # tests your AI key / model / token budget
.\.venv\Scripts\python.exe scripts\diagnose.py apps    # shows which apps AURIX can find
```

## Using AURIX

| Say | What happens |
|---|---|
| "What is machine learning?" | Answered by the AI, printed and spoken |
| "Open Visual Studio Code" / "Open WhatsApp app" | Launches the installed app |
| "Open Google website" / "Open https://example.com" | Opens the site in your default browser |
| "Search the web for Python decorators" | Opens a Google search |
| "Play lofi hip hop on YouTube" | Opens a YouTube search |
| "Stock IBM" / "Market data AAPL" | Daily end-of-day data (needs an Alpha Vantage key) |
| "Aurix" (wake-word mode) | "Yes, I'm listening." |
| "Exit", "quit", "stop listening" | Stops AURIX |

Known service names (YouTube, GitHub, Gmail, ...) open in the browser. Say "app" to force an
installed app (for example "open Spotify app") and "website" to force the website.

## Configuration

All settings live in `.env` (copy `.env.example`; every value has a sensible default except the
API key).

| Variable | Default | Purpose |
|---|---|---|
| `AI_API_KEY` | *(empty)* | Your AI provider key (`GROQ_API_KEY` / `OPENAI_API_KEY` also accepted) |
| `AI_BASE_URL` | `https://api.groq.com/openai/v1` | OpenAI-compatible endpoint |
| `OPENAI_MODEL` | `openai/gpt-oss-120b` | Model ID supported by your provider |
| `AURIX_TTS_ENABLED` | `true` | Speak replies aloud |
| `AURIX_TTS_RATE` | `175` | Speaking speed in words per minute |
| `AURIX_STT_ENGINE` | `google` | `google` (online), `whisper` (offline), or `auto` |
| `AURIX_WHISPER_MODEL` | `small` | Whisper size: `base` is fastest, `medium` is most accurate |
| `AURIX_STT_MIN_ACTION_CONFIDENCE` | `0.80` | Below this, AURIX asks "Should I do that?" before acting |
| `AURIX_SPEECH_LANGUAGE` | `en-US` | Language you speak (for example `te-IN`, `hi-IN`, `es-ES`) |
| `AURIX_REQUIRE_WAKE_WORD` | `false` | Ignore speech until the wake word is said |
| `AURIX_WAKE_WORD` | `aurix` | The wake word (Latin letters only) |
| `AURIX_CONVERSATION_WINDOW_SECONDS` | `30` | How long follow-ups are accepted after a wake-word answer |
| `AURIX_PHRASE_TIME_LIMIT_SECONDS` | `20` | Longest single spoken phrase |
| `AURIX_PAUSE_THRESHOLD_SECONDS` | `0.8` | Silence that ends a phrase |
| `AURIX_MAX_HISTORY_TURNS` | `8` | Question/answer pairs remembered |
| `AURIX_REQUEST_TIMEOUT_SECONDS` | `25` | AI request timeout |
| `AURIX_MAX_API_RETRIES` | `1` | Retries for temporary AI errors |
| `AURIX_MAX_RESPONSE_TOKENS` | `1200` | Answer budget (reasoning models spend part on thinking) |
| `AURIX_INTENT_MAX_TOKENS` | `600` | Budget for the action classifier |
| `ALPHA_VANTAGE_API_KEY` | *(empty)* | Optional, enables market data |
| `AURIX_MARKET_DATA_*` | see `.env.example` | Endpoint, timeout, cache, freshness and retries for market data |
| `AURIX_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `AURIX_LOG_DIR`, `AURIX_LOG_MAX_BYTES`, `AURIX_LOG_BACKUP_COUNT` | `logs`, `1048576`, `3` | Rotating log file (kept in the project's `logs` folder) |

## Privacy

- With the default `google` engine, **your audio is sent to Google's speech service**. Use
  `AURIX_STT_ENGINE=whisper` (after `pip install -r requirements-whisper.txt`) to keep audio on
  your PC.
- What you say (as text) is sent to your AI provider. With `AURIX_REQUIRE_WAKE_WORD=false`,
  everything AURIX recognizes is sent, including background speech; turn on the wake word if
  that matters to you.
- Logs hold diagnostics only: never your key, and not your transcripts.
- Conversation history lives in memory and disappears when AURIX exits.

## Development

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v   # 140 offline tests
.\scripts\verify_release.ps1                                  # every quality gate
```

The tests use mocks and a stand-in speech engine: they need no microphone, speakers, network or
API key. They cannot prove every Windows app launches or that your speakers work; use the
`diagnose.py` checks above for those.

## Documentation

| Document | What it covers |
|---|---|
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Fixes for no voice, microphone, PyAudio, API and app-launch problems |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How AURIX is built, every source file, and the voice-output design |
| [docs/SPEECH_AND_ACTIONS.md](docs/SPEECH_AND_ACTIONS.md) | Speech engines, confirmation, spoken output, desktop actions |
| [docs/NATURAL_LANGUAGE_INTENTS.md](docs/NATURAL_LANGUAGE_INTENTS.md) | The validated AI action classifier |
| [docs/MARKET_DATA.md](docs/MARKET_DATA.md) | The Alpha Vantage integration and its limits |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Tests, quality gates, CI, logging |
| [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) | Steps before tagging a release |
| [docs/ISSUE_REGISTER.md](docs/ISSUE_REGISTER.md) | Known issues, root causes and their status |
| [CHANGELOG.md](CHANGELOG.md) | What changed in each version |

## Limitations

- Windows only for app launching and spoken output; the Python code itself imports on other
  systems, but only the tests are exercised there.
- Not every installed program can be discovered; packaged apps vary.
- Language support is partial: Spanish, French, Hindi and Telugu command patterns exist, but
  speech recognition uses the single `AURIX_SPEECH_LANGUAGE`, the wake word is Latin-script
  only, and the speaking voice is whatever Windows voice you have installed.
- No web UI, database or persistent memory.
- Market data is daily end-of-day, never a live quote.

## License

MIT, see [LICENSE](LICENSE).
