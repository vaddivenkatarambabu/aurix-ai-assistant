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


## Dynamic applications, video search, and multilingual voice

## What this patch adds

- Windows installed-app discovery through Start Menu shortcuts, the read-only `Get-StartApps` inventory, App Paths registry entries, known install locations, and executable paths already on `PATH`.
- Visual Studio resolution through Microsoft's installed `vswhere.exe` utility, plus VS Code and common browser install locations.
- Desktop application priority: installed app first, known web counterpart second. If the desktop app isn't found, AURIX tells you and opens its known website fallback when one exists.
- Direct YouTube search for phrases such as `play lofi on YouTube`, `open video Naatu Naatu`, or `search YouTube for Python tutorial`.
- English, Telugu, Spanish, Hindi, Tamil, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Urdu, Portuguese, French, German, Italian, Dutch, Russian, Japanese, Korean, Chinese, Arabic, Turkish, Indonesian, Vietnamese, Thai, Polish, Ukrainian, Swedish, and Hebrew speech-language profiles. More BCP-47 codes can be passed with `--language`.
- Runtime language switching through supported spoken commands, and multilingual TTS using Edge voices when available, with matching local Windows voices as fallback.
- Safe launching: voice text is not put into a shell. Arbitrary `.exe`, `.cmd`, `.bat`, or PowerShell text is rejected. A known, resolved application or validated web destination is required.

## Install and run

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m aurix.main
```

Start in Telugu or Spanish directly:

```powershell
.\.venv\Scripts\python.exe -m aurix.main --language te-IN
.\.venv\Scripts\python.exe -m aurix.main --language es-ES
```

Or use the default locale from `.env`, then say `switch language to Telugu` or `cambia el idioma a español`. Speech recognition needs internet access for the current Google recognizer. Edge TTS also uses an online speech service; if that is unavailable, AURIX tries an installed local voice and always prints answers in the terminal.

## Behavior and limitations

- App inventories and exact program paths vary across Windows PCs. AURIX can only launch an app when Windows exposes a shortcut, registered path, Start Apps identity, or known installation path.
- If an app with a known web counterpart isn't installed, AURIX will say so and open the web counterpart. Apps with no known website return a not-found result.
- `Open Browser` opens the system default browser. `Open Brave Browser` tries to launch the installed Brave app first.
- `Open Visual Studio` resolves Visual Studio IDE; `Open Visual Studio Code` resolves VS Code. These are different applications.
- Video commands open a YouTube search results page for the requested title, not a guessed single video URL.
- This is still a Python terminal application; it does not add a web/React frontend, and npm is not needed.
