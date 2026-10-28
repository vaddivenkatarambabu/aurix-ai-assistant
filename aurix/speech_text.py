"""Convert display text (may contain Markdown) into text that is safe to speak.

The readable answer is shown unchanged; only the copy passed to text-to-speech is
normalised. Rules are deliberately conservative: formatting syntax is removed, but
words, numbers, hyphens, "C#", "#1" and snake_case names are preserved, and simple
arithmetic or LaTeX is turned into words ("2*3=6" -> "2 times 3 equals 6").
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_FENCE = re.compile(
    r"(?ms)^[ \t]*(```|~~~)[^\n]*\n.*?^[ \t]*\1[ \t]*$|^[ \t]*(```|~~~)[^\n]*\n.*\Z"
)
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)\s]*(?:\s+\"[^\"]*\")?\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)\s]*(?:\s+\"[^\"]*\")?\)")
_URL = re.compile(r"https?://[^\s<>()\[\]]+", re.I)
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", re.S)
_ITALIC_STAR = re.compile(r"(?<![\w*])\*(?=[^\s*])([^*\n]+?)(?<=[^\s*])\*(?![\w*])")
_ITALIC_UNDER = re.compile(r"(?<!\w)_(?=[^\s_])([^_\n]+?)(?<=[^\s_])_(?!\w)")
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_INLINE_CODE = re.compile(r"`+([^`\n]+?)`+")
_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.*?)[ \t]*#*[ \t]*$")
_BULLET = re.compile(r"^[ \t]*[-*+•][ \t]+(.*)$")
_NUMBERED = re.compile(r"^[ \t]*(\d{1,3})[.)][ \t]+(.*)$")
_QUOTE = re.compile(r"^[ \t]*>+[ \t]?")
_RULE = re.compile(r"^[ \t]*(?:[-*_][ \t]*){3,}$")
_TABLE_SEP = re.compile(r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(?:\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*$")


_LATEX_SPAN = re.compile(r"\$([^$\n]*[\\^_{}][^$\n]*)\$")
_FRAC = re.compile(r"\\frac\{([^{}]*)\}\{([^{}]*)\}")
_SQRT = re.compile(r"\\sqrt\{([^{}]*)\}")
_LATEX_WORDS = {
    r"\times": " times ",
    r"\cdot": " times ",
    r"\pm": " plus or minus ",
    r"\leq": " less than or equal to ",
    r"\le": " less than or equal to ",
    r"\geq": " greater than or equal to ",
    r"\ge": " greater than or equal to ",
    r"\neq": " not equal to ",
    r"\pi": " pi ",
}
_POWER = re.compile(r"(?<=[\w)])\s*\^\s*(-?\d+)")
_OPERATORS = (
    (re.compile(r"(?<=\d)\s*[*\u00d7]\s*(?=\d)"), " times "),
    (re.compile(r"(?<=\d)\s*\+\s*(?=\d)"), " plus "),
    (re.compile(r"(?<=\d)\s+[-\u2212]\s+(?=\d)"), " minus "),
    (re.compile(r"(?<=[\w)])\s*(?:<=|\u2264)\s*(?=[\w(-])"), " is less than or equal to "),
    (re.compile(r"(?<=[\w)])\s*(?:>=|\u2265)\s*(?=[\w(-])"), " is greater than or equal to "),
    (re.compile(r"(?<=[\w)])\s*(?:!=|\u2260)\s*(?=[\w(-])"), " is not equal to "),
    (re.compile(r"(?<=[\w)])\s*=\s*(?=[\w(-])"), " equals "),
    (re.compile(r"(?<=\d)\s*%"), " percent"),
)


def _latex_to_words(match: re.Match[str]) -> str:
    inner = match.group(1)
    inner = _FRAC.sub(lambda m: f"{m.group(1)} over {m.group(2)}", inner)
    inner = _SQRT.sub(lambda m: f"square root of {m.group(1)}", inner)
    for token, words in sorted(_LATEX_WORDS.items(), key=lambda kv: -len(kv[0])):
        inner = inner.replace(token, words)
    return inner.replace("\\", "").replace("{", "").replace("}", "")


def _speak_power(match: re.Match[str]) -> str:
    exponent = match.group(1)
    return {"2": " squared", "3": " cubed"}.get(exponent, f" to the power of {exponent}")


def _speak_math(text: str) -> str:
    text = _LATEX_SPAN.sub(_latex_to_words, text)
    text = _POWER.sub(_speak_power, text)
    for pattern, words in _OPERATORS:
        text = pattern.sub(words, text)
    return text


def _speak_url(match: re.Match[str]) -> str:
    full = match.group(0)
    raw = full.rstrip(".,;:!?")
    trailing = full[len(raw) :]
    host = (urlparse(raw).hostname or "").removeprefix("www.")
    return (host or "a link") + trailing


def _end_sentence(line: str) -> str:
    line = line.strip()
    if line and line[-1] not in ".!?:;,":
        line += "."
    return line


def to_speech_text(display_text: str) -> str:
    """Return a plain-prose version of ``display_text`` for text-to-speech."""
    if not isinstance(display_text, str) or not display_text.strip():
        return ""

    text = display_text.replace("\r\n", "\n").replace("\r", "\n")
    text = _FENCE.sub("\n(A code example is shown on screen.)\n", text)
    text = _IMAGE.sub(lambda m: m.group(1).strip(), text)
    text = _LINK.sub(lambda m: m.group(1), text)
    text = _URL.sub(_speak_url, text)

    lines: list[str] = []
    for line in text.split("\n"):
        if _RULE.match(line) or _TABLE_SEP.match(line):
            continue
        line = _QUOTE.sub("", line)
        heading = _HEADING.match(line)
        if heading:
            line = _end_sentence(heading.group(1))
        else:
            numbered = _NUMBERED.match(line)
            bullet = _BULLET.match(line)
            if numbered:
                line = _end_sentence(f"{numbered.group(1)}. {numbered.group(2)}")
            elif bullet:
                line = _end_sentence(bullet.group(1))
            elif "|" in line and line.strip().startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|") if c.strip()]
                line = _end_sentence(", ".join(cells))
        lines.append(line)
    text = "\n".join(lines)

    text = _INLINE_CODE.sub(r"\1", text)
    text = _BOLD.sub(r"\2", text)
    text = _STRIKE.sub(r"\1", text)
    text = _ITALIC_STAR.sub(r"\1", text)
    text = _ITALIC_UNDER.sub(r"\1", text)

    text = _speak_math(text)

    paragraphs = [" ".join(chunk.split()) for chunk in re.split(r"\n+", text)]
    return " ".join(p for p in paragraphs if p)
