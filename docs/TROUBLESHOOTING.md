# Troubleshooting

Run the matching check first; it usually names the problem:

```powershell
.\.venv\Scripts\python.exe scripts\diagnose.py tts | audio | model | apps
```

## AURIX answers on screen but I hear nothing

1. `diagnose.py tts` should speak three sentences. If you hear all three, spoken output works.
2. Hear none: check the Windows volume and default output device, and that `AURIX_TTS_ENABLED=true`.
3. Look for `[TTS Notice]` lines in the console; they give the real reason (for example
   "no voice installed"). Install a voice under **Settings > Time & language > Speech**.
4. After three failures in a row AURIX turns speech off for the session and says so. Fix the
   cause and restart AURIX.
5. A short pause before a reply is spoken is normal: each reply is spoken by a fresh process.

*Historical note:* earlier versions spoke only the first reply after start-up. That bug is
fixed; see [ISSUE_REGISTER.md](ISSUE_REGISTER.md) (AURIX-010).

## AURIX does not hear me / "Microphone Error"

- `diagnose.py audio` lists the microphones. Make sure the one you use is the Windows default
  recording device and that **Settings > Privacy > Microphone** allows desktop apps.
- `Could not find PyAudio`: run `.\.venv\Scripts\python.exe -m pip install PyAudio`. If that
  fails to build, install a prebuilt wheel for your Python version.
- "Speech was not understood": speak closer to the microphone, or lower
  `AURIX_PAUSE_THRESHOLD_SECONDS` if AURIX waits too long. For poor accents or noise try
  `AURIX_STT_ENGINE=whisper` (`pip install -r requirements-whisper.txt`).
- "Speech Service Error": the Google recognizer needs internet access.

## AI errors

| Message | Meaning and fix |
|---|---|
| `AI_API_KEY is missing` | Add your key to `.env` and restart |
| `provider rejected the API key` | Wrong or revoked key; create a new one |
| `rate-limiting` / `quota` | Wait, or check your provider's usage and billing page |
| `used its whole response budget` | Raise `AURIX_MAX_RESPONSE_TOKENS` |
| `HTTP 400/404` | Check `OPENAI_MODEL` and `AI_BASE_URL`; run `diagnose.py model` |

## Apps and websites

- "was not found": the app is not in the Start Menu or registry. Run `diagnose.py apps`. Say
  "website" to open a website instead.
- Direct paths and `.exe` names are rejected on purpose; say the application's name.
- A sentence such as "show me a joke" is treated as conversation and sent to the AI.

## Market data

- Needs `ALPHA_VANTAGE_API_KEY`; the free plan has a small daily request limit.
- Data is end-of-day, never live. See [MARKET_DATA.md](MARKET_DATA.md).

## Logs

`logs\aurix.log` (inside the project folder) holds diagnostics without keys or transcripts.
Set `AURIX_LOG_LEVEL=DEBUG` for more detail.
