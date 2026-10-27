AURIX AI Assistant
AURIX is a Windows-first Python terminal voice assistant. It accepts speech through a microphone, routes supported desktop and browser commands to local handlers, and sends ordinary conversation to an OpenAI-compatible chat API. Responses are printed in the terminal; optional text-to-speech uses the local voice provided by pyttsx3.

This repository is not a web application: it contains no React frontend, package.json, or browser-based chat UI. Milestone 5 adds an optional Alpha Vantage daily-equity-data integration with source metadata, freshness checks, deterministic calculations, and separately labeled AI commentary; it does not provide live quotes.
Current capabilities
- Voice input using SpeechRecognition with Google's online speech-recognition endpoint.
- AI conversation through an OpenAI-compatible Chat Completions API. The example configuration uses Groq's endpoint and openai/gpt-oss-120b.
- Bounded, in-memory conversation history. History is lost when AURIX exits; it is not persisted to a database or file.
- Optional local text-to-speech through pyttsx3.
- Windows-first application discovery and launching from Start Menu shortcuts, Windows' Get-StartApps inventory, registered application paths, selected known installation locations, and PATH.
- Explicit website mappings opened through the operating system's default browser.
- Separate application-versus-website intent: say "open Chrome app" to launch an installed app or "open Google website" to open a website.
- Configured Jio website mapping: https://www.jio.com/.
- YouTube search and web search through the default browser.
- Explicit market-data commands such as `stock IBM` or `market data AAPL`, backed by Alpha Vantage daily end-of-day data, validation, freshness metadata, calculations, and separately labeled optional AI commentary.
- Guardrails that reject direct executable/script paths from spoken input and avoid passing voice commands to a shell.
Requirements and setup
The documented setup targets Windows, PowerShell, and Python 3.13. A working microphone, microphone permission, internet access, and a compatible audio input device are needed for voice input. PyAudio installation may depend on your Python and Windows environment.

From the repository root, run:
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
Add your own provider API key to the local .env file. Keep this file private and never commit API keys. The .env file is ignored by Git; .env.example contains placeholders and safe defaults.

Start AURIX:
.\.venv\Scripts\python.exe -m aurix.main
Stop it with Ctrl+C or say exit, quit, shutdown, stop listening, or stop aurix when the recognizer understands the phrase.

Run the offline unit tests:
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
These tests mock most desktop/browser operations; they do not prove that every installed application launches correctly on every Windows machine.
Configuration
Set these values in .env as needed:
Variable	Default in .env.example	Purpose
AI_API_KEY	Empty	API key for the configured provider. The code also accepts GROQ_API_KEY or OPENAI_API_KEY as fallback names.
AI_BASE_URL	https://api.groq.com/openai/v1	OpenAI-compatible API base URL.
OPENAI_MODEL	openai/gpt-oss-120b	Model identifier supported by the chosen provider. AI_MODEL is a legacy fallback name.
AURIX_SPEECH_LANGUAGE	en-US	Locale passed to Google's speech-recognition endpoint. It is not an offline recognizer.
AURIX_REQUIRE_WAKE_WORD	false	If false, recognized speech can be sent to the assistant without a wake word. If true, the configured wake word must be detected, with a short conversation window after activation.
AURIX_WAKE_WORD	aurix	Wake word used by the current ASCII/Latin-script wake-word matcher.
AURIX_CONVERSATION_WINDOW_SECONDS	30	How long follow-up speech is accepted after activation when wake-word mode is enabled.
AURIX_TTS_ENABLED	true	Enables or disables local pyttsx3 speech output.
AURIX_MAX_HISTORY_TURNS	8	Maximum number of user/assistant turn pairs retained in memory.
AURIX_REQUEST_TIMEOUT_SECONDS	25	AI API request timeout.
AURIX_MAX_API_RETRIES	1	Maximum retries for selected transient API failures.
| ALPHA_VANTAGE_API_KEY | Empty | Optional key for Alpha Vantage daily market data. |
| AURIX_MARKET_DATA_BASE_URL | https://www.alphavantage.co/query | Alpha Vantage endpoint; HTTPS is required. |
| AURIX_MARKET_DATA_TIMEOUT_SECONDS | 8 | Market-data request timeout. |
| AURIX_MARKET_DATA_CACHE_TTL_SECONDS | 300 | Bounded in-memory cache duration; set to 0 to disable. |
| AURIX_MARKET_DATA_MAX_AGE_DAYS | 7 | Calendar-day age threshold for daily observations. |
| AURIX_MARKET_DATA_MAX_RETRIES | 1 (capped at 3) | Bounded retries for transient network/server failures; no retries for provider quota notices. |


Voice privacy and limitations
- Speech recognition sends audio to Google's online recognition service. An internet connection is required, and recognized words may be sent to the configured AI provider.
- AURIX_REQUIRE_WAKE_WORD=false can cause background speech to be sent to the AI and consume API quota. Enable wake-word mode if you want recognized speech ignored until the wake word is detected.
- The current wake-word matcher operates on ASCII/Latin characters; it is not a multilingual or offline wake-word detector.
- pyttsx3 uses the local system TTS engine and its installed/default voice at the configured speech rate. The current code does not implement automatic per-language voice selection or Edge TTS voice switching.
- Recognition language, AI response language, action-command parsing, localized action messages, and the Windows TTS voice are separate things. Setting AURIX_SPEECH_LANGUAGE does not enable full runtime language switching.
Supported desktop and browser commands
Commands are routed by the explicit parser in aurix/actions/desktop.py. Common examples include:
Open WhatsApp
Open browser
Open YouTube
Open Visual Studio Code
Open https://example.com
Search the web for Python decorators
Search YouTube for Python tutorial
Play lofi hip hop on YouTube
The parser also contains selected command patterns in Spanish, French, Hindi, and Telugu, for example abre WhatsApp, ouvre Firefox, व्हाट्सएप खोलो, and వాట్సాప్ తెరువు. This is limited command-pattern coverage, not complete multilingual support.

Known service names such as Google, Jio, ChatGPT, YouTube, GitHub, and WhatsApp open their configured URL in the operating system's default browser. Say "open Chrome app" or "open Spotify app" when you specifically want to launch an installed desktop application instead. Unknown names are not guessed into website URLs; provide an explicit domain such as "open example.com" or name a configured website. Open browser opens a blank tab in the default browser. YouTube commands open a YouTube search results page, not a guaranteed specific video.

Application discovery varies by Windows installation, app packaging, Start Menu shortcuts, registration, and permissions. AURIX may not be able to discover every installed app. For safety, direct executable paths, shell scripts, and arbitrary commands spoken as text are rejected rather than executed through a shell.
Language support: what is and is not implemented
- General AI answers are prompted to respond in the language of the latest message when possible; quality depends on the configured model.
- The desktop-action response templates currently include English, Spanish, Telugu, Hindi, and French. Language detection and command patterns are heuristic and cover only selected phrases.
- Speech recognition uses the single locale configured by AURIX_SPEECH_LANGUAGE for a run.
- There is no implemented --language command-line option, no complete spoken runtime language-switch command, and no automatic TTS voice switching in the current code.
Error handling and conversation behavior
The AI client uses a configured request timeout, bounded retries for selected transient errors, and explicit messages for missing API keys, authentication failures, rate limits, and provider errors. Conversation history is stored only in the current process. The application has no database, user accounts, durable memory, or web backend in this repository.
Not implemented yet
- Intraday/realtime or 15-minute-delayed quotes, verified exchange-calendar status, durable market-data persistence, and live-provider validation without credentials.
- A web UI, React frontend, REST backend, database, or persistent conversation history.
- Full multilingual speech recognition, multilingual wake-word detection, full runtime language switching, and per-language TTS voice selection.
- Guaranteed discovery or launch of every third-party application on Windows.
Market-data work should be implemented as a separate integration with a documented provider, response validation, explicit source and timestamp metadata, deterministic calculations, stale-data handling, and tests before AURIX presents market information as fact.
## Market-data integration (Milestone 5)

Market-data commands use the Alpha Vantage `TIME_SERIES_DAILY` endpoint and therefore return raw, unadjusted **daily end-of-day** equity bars, not a real-time or 15-minute-delayed quote. See the [official API documentation](https://www.alphavantage.co/documentation/#daily). The API returns a compact window (up to the latest 100 daily observations) in this implementation.

Configure the optional `ALPHA_VANTAGE_API_KEY` in the local `.env` file. Example commands are `stock IBM`, `market data AAPL`, `quote TSLA`, and `what is the stock price of SHOP.TO`. Market-data fetching does not require the AI API key; if AI commentary is unavailable, AURIX still displays the source facts and deterministic calculations.

The result keeps `source_facts`, `derived_metrics`, and `generated_analysis` separate. The source facts include provider/reference, date-only observation semantics, UTC provider-retrieval time, data/adjustment status, and freshness status. Percentage change is calculated from the two latest provider observations using `((latest_close - previous_close) / previous_close) * 100`, rounded to two decimal places. It is not represented as a provider-reported fact. Missing currencies and exchange identifiers remain unknown rather than being guessed. A bounded five-minute in-memory cache is enabled by default; cached results retain the original provider retrieval timestamp and recompute the freshness age on cache hits. Set `AURIX_MARKET_DATA_CACHE_TTL_SECONDS=0` to disable it.

The endpoint does not verify an exchange calendar or provide a live quote timestamp, so the implementation cannot determine whether an older bar is caused by a market holiday, a provider outage, or a missing trading observation. Freshness is an age-threshold check, not proof that a market is open. Alpha Vantage currently documents 25 requests/day for its standard free stock API service, with unlimited requests for verified open-source or educational projects; US real-time and 15-minute-delayed quote access is premium. Confirm the current provider plan and data licensing terms for your intended use before commercial use. No live-provider test was executed without credentials.


Troubleshooting
- Missing API key: add a valid key to .env and check AI_BASE_URL and OPENAI_MODEL for the provider.
- Microphone/PyAudio error: confirm Windows microphone permission, select a working recording device, and verify PyAudio installation in the active .venv.
- Speech recognition errors: check internet connectivity and the configured AURIX_SPEECH_LANGUAGE locale.
- Application not found: verify the app appears in the Windows Start Menu or is registered with Windows. Some packaged apps cannot be launched by a simple executable path.
- No spoken response: set AURIX_TTS_ENABLED=true and confirm Windows has a working installed speech voice. The text response should still be printed in the terminal.
## Production hardening (Milestone 6)

AURIX uses standard-library logging with console output and bounded rotating diagnostic logs. Local quality checks and release-readiness guidance are documented in [`docs/PRODUCTION_HARDENING.md`](docs/PRODUCTION_HARDENING.md) and [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md). Install the pinned development tools with `python -m pip install -r requirements-dev.txt`; run `.\scripts\verify_release.ps1` from PowerShell. GitHub Actions runs automated tests and quality/security gates for pushes and pull requests.


## Natural-language intent understanding

Action-like requests that are not resolved by deterministic rules may be classified by the configured AI provider into a small, validated action schema. Only application opening, website opening, web search, YouTube search, clarification, or no-action outcomes are accepted. The classifier cannot return executable shell commands or launch arguments. Accepted actions are translated back through the existing desktop/browser router, which retains URL validation and no-shell execution safeguards. The feature requires the configured AI service and does not cover every phrasing; failures fall back to ordinary assistant handling. See [`docs/NATURAL_LANGUAGE_INTENTS.md`](docs/NATURAL_LANGUAGE_INTENTS.md).
