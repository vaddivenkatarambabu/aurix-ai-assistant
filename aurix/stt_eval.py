"""Word-error-rate and command-intent scoring for speech-recognition evaluation."""

from __future__ import annotations

import re

from aurix.actions.desktop import parse_open_request


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s']", " ", text.casefold()).split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein word edit distance divided by reference length (0.0 is perfect)."""
    ref, hyp = _words(reference), _words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i]
        for j, h in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return previous[-1] / len(ref)


def command_target(text: str) -> str | None:
    """The application/site target the launcher would extract from ``text``."""
    target = parse_open_request(text)
    return " ".join(target.casefold().strip(" .!?").split()) if target else None


def intent_matches(reference: str, hypothesis: str) -> bool:
    """True when both transcripts resolve to the same open-target (or both to none)."""
    return command_target(reference) == command_target(hypothesis)
