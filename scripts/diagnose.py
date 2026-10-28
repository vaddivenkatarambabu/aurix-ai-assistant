"""Verify the things that cannot be checked offline. Run on your Windows machine:

    python scripts/diagnose.py model      # Groq 400s, token budget, JSON mode
    python scripts/diagnose.py apps       # which apps AURIX can discover (launches nothing)
    python scripts/diagnose.py apps --launch notepad   # actually launch one app end to end
    python scripts/diagnose.py audio      # microphones and the configured speech engine
    python scripts/diagnose.py tts        # speaks three sentences in a row (spoken-output test)

Output never prints your API key.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _describe_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", "?")
    body = getattr(exc, "body", None)
    message = (
        body.get("error", {}).get("message")
        if isinstance(body, dict) and isinstance(body.get("error"), dict)
        else str(exc)
    )
    return f"{type(exc).__name__} status={status}: {message}"


def diagnose_model() -> int:
    from openai import OpenAI

    from aurix.config import AI_API_KEY, AI_BASE_URL, OPENAI_MODEL
    from aurix.intent import _SYSTEM_PROMPT

    if not AI_API_KEY:
        print("AI_API_KEY is empty in .env")
        return 1
    client = OpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL or None, timeout=40, max_retries=0)
    print(f"model={OPENAI_MODEL} base_url={AI_BASE_URL or '(default)'}\n")
    question = [{"role": "user", "content": "What is software engineering? Explain simply."}]
    probes = [
        ("plain, 350 tokens (old limit)", dict(messages=question, max_completion_tokens=350)),
        ("plain, 1200 tokens (new default)", dict(messages=question, max_completion_tokens=1200)),
        (
            "JSON mode, 200 tokens (old intent)",
            dict(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": '{"request": "Open Chrome"}'},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=200,
            ),
        ),
        (
            "JSON mode, 600 tokens (new intent)",
            dict(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": '{"request": "Open Chrome"}'},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=600,
            ),
        ),
        (
            "no JSON mode, 600 tokens (fallback)",
            dict(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": '{"request": "Open Chrome"}'},
                ],
                max_completion_tokens=600,
            ),
        ),
    ]
    for label, kwargs in probes:
        try:
            result = client.chat.completions.create(model=OPENAI_MODEL, **kwargs)
        except Exception as exc:  # report every provider error verbatim (minus secrets)
            print(f"[FAIL] {label}\n       {_describe_error(exc)}")
            continue
        choice = result.choices[0]
        usage = getattr(result, "usage", None)
        details = getattr(usage, "completion_tokens_details", None)
        reasoning = getattr(details, "reasoning_tokens", None)
        text = (choice.message.content or "").strip()
        print(
            f"[ OK ] {label}\n       finish_reason={choice.finish_reason} chars={len(text)} "
            f"completion_tokens={getattr(usage, 'completion_tokens', '?')} reasoning_tokens={reasoning}"
        )
    print(
        "\nInterpretation: finish_reason=length with chars=0 means the budget was spent on reasoning."
    )
    return 0


def diagnose_apps(launch: str | None) -> int:
    from aurix.actions import desktop

    names = [
        "notepad",
        "calculator",
        "chrome",
        "brave",
        "firefox",
        "edge",
        "vs code",
        "spotify",
        "whatsapp",
        "outlook",
    ]
    for name in names:
        app = desktop._find_installed_app(name)
        print(f"{name:12} -> {'NOT FOUND' if app is None else f'{app.kind}: {app.name}'}")
    if launch:
        print(f"\nLaunching '{launch}' through the real router...")
        print(desktop.handle_desktop_command(f"open {launch}"))
        print("Check that the window actually appeared; AURIX can only confirm the launch request.")
    return 0


def diagnose_audio() -> int:
    import speech_recognition as sr

    from aurix.config import AURIX_STT_ENGINE, AURIX_WHISPER_MODEL

    for index, name in enumerate(sr.Microphone.list_microphone_names()):
        print(f"[{index}] {name}")
    print(f"\nConfigured engine: {AURIX_STT_ENGINE} (whisper model: {AURIX_WHISPER_MODEL})")
    try:
        import faster_whisper  # noqa: F401

        print("faster-whisper: installed")
    except ImportError:
        print("faster-whisper: not installed (pip install faster-whisper)")
    return 0


def diagnose_tts() -> int:
    from aurix.config import AURIX_TTS_RATE
    from aurix.tts import Speaker

    sentences = [
        "This is the first test sentence.",
        "This is the second one. If you can hear it, spoken replies work every time.",
        "And this is the third.",
    ]
    speaker = Speaker(enabled=True, rate=AURIX_TTS_RATE)
    failures = 0
    for number, sentence in enumerate(sentences, 1):
        spoken = speaker.speak(sentence)
        print(f"[{'OK' if spoken else 'FAIL'}] sentence {number}")
        failures += 0 if spoken else 1
    if failures:
        print("\nSpeech failed; see the [TTS Notice] lines above for the reason.")
        return 1
    print("\nAll three sentences were handed to the speech engine successfully.")
    print("You should have HEARD all three. If not, check Windows volume and the default")
    print("output device, and that a voice is installed (Settings > Time & language > Speech).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=["model", "apps", "audio", "tts"])
    parser.add_argument("--launch")
    args = parser.parse_args()
    if args.check == "model":
        return diagnose_model()
    if args.check == "apps":
        return diagnose_apps(args.launch)
    if args.check == "tts":
        return diagnose_tts()
    return diagnose_audio()


if __name__ == "__main__":
    raise SystemExit(main())
