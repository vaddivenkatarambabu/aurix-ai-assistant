"""Evaluate AURIX speech recognition on your own recordings.

Usage (from the repo root, with the venv active):
    python scripts/eval_stt.py samples/manifest.csv --engine google
    python scripts/eval_stt.py samples/manifest.csv --engine whisper

manifest.csv columns: audio_path,reference_text   (WAV files, any accent/speed/noise you want
to measure). Prints per-file results plus mean WER and command-intent accuracy. Record the same
phrases in different conditions (quiet/noisy, slow/fast, different speakers) to compare engines.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import speech_recognition as sr  # noqa: E402

from aurix.config import AURIX_SPEECH_LANGUAGE  # noqa: E402
from aurix.stt import SpeechServiceError, build_engine  # noqa: E402
from aurix.stt_eval import intent_matches, word_error_rate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--engine", default="google", choices=["google", "whisper", "auto"])
    parser.add_argument("--whisper-model", default="small")
    args = parser.parse_args()

    recognizer = sr.Recognizer()
    engine = build_engine(
        args.engine, recognizer=recognizer, sr_module=sr, whisper_model=args.whisper_model
    )
    with open(args.manifest, newline="", encoding="utf-8") as manifest:
        rows = list(csv.DictReader(manifest))
    wers: list[float] = []
    intents: list[bool] = []
    for row in rows:
        path = Path(args.manifest).parent / row["audio_path"]
        with sr.AudioFile(str(path)) as source:
            audio = recognizer.record(source)
        try:
            result = engine.transcribe(audio, AURIX_SPEECH_LANGUAGE)
        except SpeechServiceError as exc:
            print(f"{path.name}: ENGINE ERROR {exc}")
            continue
        heard = result.text if result else ""
        wer = word_error_rate(row["reference_text"], heard)
        ok = intent_matches(row["reference_text"], heard)
        wers.append(wer)
        intents.append(ok)
        conf = "n/a" if not result or result.confidence is None else f"{result.confidence:.2f}"
        print(f"{path.name}: WER={wer:.2f} intent_ok={ok} conf={conf} heard={heard!r}")
    if wers:
        print(
            f"\nfiles={len(wers)} mean_WER={sum(wers) / len(wers):.3f} "
            f"intent_accuracy={sum(intents) / len(intents):.3f} engine={args.engine}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
