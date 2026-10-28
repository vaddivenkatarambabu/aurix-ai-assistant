# Speech input, spoken output and desktop actions

## Speech recognition (`aurix/stt.py`)

| `AURIX_STT_ENGINE` | What it does | Trade-offs |
|---|---|---|
| `google` (default) | `recognize_google`, the free web endpoint | needs internet, no SLA, audio leaves the PC, confidence is sometimes missing |
| `whisper` | local faster-whisper (`pip install -r requirements-whisper.txt`) | offline and private; first run downloads the model; CPU time grows with `AURIX_WHISPER_MODEL` (`base` < `small` < `medium`) |
| `auto` | Whisper if installed, otherwise Google | |

Whisper receives a vocabulary hint built from the app/site registry so names such as "VS Code"
or "WhatsApp" are spelled correctly, and segments with a high no-speech probability are dropped
(this prevents "Thank you." being hallucinated from silence).

## Confirmation before acting

If a command may open an app/site or search and the engine reports a confidence below
`AURIX_STT_MIN_ACTION_CONFIDENCE` (default 0.80), AURIX asks "I heard ... Should I do that?"
and acts only on an explicit yes. When an engine gives no confidence (Google sometimes does
not) no confirmation is requested, because there is no signal to act on. Ordinary questions
are never confirmed.

## Spoken output (`aurix/tts.py`, `aurix/tts_worker.py`, `aurix/speech_text.py`)

1. The AI's answer is printed exactly as written.
2. `to_speech_text()` converts a copy to plain sentences: Markdown, links and code blocks are
   removed or summarised, URLs become their host name, simple maths becomes words
   ("2*3=6" -> "2 times 3 equals 6").
3. `Speaker.speak()` sends that text to a **new** `python -m aurix.tts_worker` process, which
   creates a fresh pyttsx3 engine, speaks, and exits. This is what makes **every** reply
   audible; see [ARCHITECTURE.md](ARCHITECTURE.md) for the reason.
4. If speech fails, a `[TTS Notice]` explains why, the answer is still on screen, and after three
   consecutive failures speech is switched off for the session.

Settings: `AURIX_TTS_ENABLED`, `AURIX_TTS_RATE`. The voice is the Windows default; there is no
automatic per-language voice selection, so non-English text is read by whatever voice you have.
Test it with `python scripts/diagnose.py tts`.

## Measuring recognition quality

Record WAV files, list them in a CSV (`audio_path,reference_text`) and run
`python scripts/eval_stt.py manifest.csv --engine google`, then again with `--engine whisper`.
Compare mean word error rate and command-intent accuracy across speakers, speeds and noise.
No accuracy figures ship with this project: they depend on your voice and microphone.

## Checking what tests cannot

`python scripts/diagnose.py tts | audio | model | apps [--launch notepad]`

## Desktop actions (`aurix/actions/`)

- `registry.py`: reviewed data only (website URLs, alias groups, system executables, name
  normalisation). **Add apps and sites here.**
- `messages.py`: localized response strings and language detection.
- `discovery.py`: finds verified Windows launch targets (Start Menu, AppsFolder IDs, registry,
  known paths); never launches anything.
- `desktop.py`: parses commands, decides app versus website, validates URLs, launches via
  argument lists (never a shell).

Rules worth knowing:

- Known brands (YouTube, GitHub, Gmail, ...) open their website; "app" forces the installed
  client and "website" forces the site. Spotify, WhatsApp and Outlook prefer an installed client.
- Unknown names are never guessed into URLs. Give a domain ("open example.com").
- Direct executable paths, scripts and non-web URL schemes are rejected.
- A short unknown name gives a clear "was not found". A phrase that reads like a sentence
  ("show me a joke", "start over") is not treated as an app name; it goes on to the AI.
- Supported command phrasing includes English, Spanish, French, Hindi and Telugu patterns. This
  is limited pattern coverage, not full multilingual support.
