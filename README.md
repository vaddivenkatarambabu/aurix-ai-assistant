# AURIX AI Assistant

AURIX is currently a **Python terminal application**. There is no `package.json`, React app, or browser chat UI in this repository, so `npm install` is not part of the current setup. AI responses are displayed in the terminal; optional Windows text-to-speech reads them aloud.

## Windows setup

Use Python 3.13 and PowerShell from the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Set a real API key from your chosen provider in the local `.env`. This sample uses Groq's OpenAI-compatible endpoint and the `openai/gpt-oss-120b` model. Keep `.env` private and never commit it.

Start AURIX:

```powershell
.\.venv\Scripts\python.exe -m aurix.main
```

Run offline unit tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Voice behavior

- `AURIX_REQUIRE_WAKE_WORD=false` lets recognized speech such as “Hello” reach the assistant without a wake word. This can send background speech to the cloud model and use API quota, so use this mode intentionally.
- Set `AURIX_REQUIRE_WAKE_WORD=true` to require “AURIX”. Once activated, follow-up turns are accepted for the configured conversation window.
- Speech recognition currently uses `SpeechRecognition`'s Google recognition endpoint and requires internet access. This is not an offline wake-word detector.
- Every assistant response is printed to the terminal. `pyttsx3` speech output is optional and can be disabled with `AURIX_TTS_ENABLED=false`.
- Browser launching and market-data operations are not implemented yet. The AI is instructed not to claim those actions were performed.

## API and conversation behavior

The application passes an explicit bounded message history to the OpenAI-compatible Chat Completions endpoint. History lasts only while the process is running. The client timeout and retry count are bounded, and API errors are returned as visible user-facing messages.

## Current scope

This repository does not contain an npm-based frontend. A web chat interface is a separate feature requiring a frontend and a backend API; do not put provider API keys in browser JavaScript.
