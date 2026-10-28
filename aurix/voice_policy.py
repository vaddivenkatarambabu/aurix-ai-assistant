"""Pure decision helpers for the voice loop: when to confirm a heard command."""

from __future__ import annotations

import re

from aurix.actions.desktop import parse_open_request, parse_video_search
from aurix.intent import should_attempt_desktop_interpretation

_SEARCH = re.compile(
    r"^\s*(?:aurix[, ]+)?(?:search|look)\s+(?:the\s+)?(?:web|internet|google)\s+for\s+\S", re.I
)
_YES = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "correct",
    "right",
    "sure",
    "confirm",
    "do it",
    "go ahead",
    "that's right",
    "thats right",
    "ok",
    "okay",
}
_NO = {"no", "nope", "nah", "cancel", "stop", "wrong", "never mind", "nevermind", "don't", "dont"}


def vocabulary_prompt(limit: int = 40) -> str:
    """Hint text listing known app/site names so Whisper spells them correctly."""
    from aurix.actions.registry import _ALIAS_GROUPS, _WEBSITES

    names: list[str] = []
    for group in _ALIAS_GROUPS:
        if group[0].isascii() and group[0] not in names:
            names.append(group[0])
    for label, _url in _WEBSITES.values():
        if label not in names:
            names.append(label)
    return "AURIX commands: open " + ", ".join(names[:limit]) + "."


def is_action_like(command: str) -> bool:
    """True when the command may open an app/site or search, i.e. cause a desktop action."""
    return bool(
        parse_open_request(command) is not None
        or parse_video_search(command) is not None
        or _SEARCH.match(command)
        or should_attempt_desktop_interpretation(command)
    )


def needs_confirmation(confidence: float | None, action_like: bool, threshold: float) -> bool:
    """Ask before acting only when the engine reported a confidence below the threshold."""
    return bool(action_like and confidence is not None and confidence < threshold)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z' ]", "", text.casefold()).strip()


def is_yes(text: str) -> bool:
    return _norm(text) in _YES


def is_no(text: str) -> bool:
    return _norm(text) in _NO
