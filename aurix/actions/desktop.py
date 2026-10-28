"""Safe Windows-first desktop application and website launching for AURIX."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from aurix.actions.discovery import (  # noqa: F401  (re-exported for callers and tests)
    InstalledApp,
    _find_installed_app,
    _find_start_app_id,
)
from aurix.actions.messages import _message, _response_language
from aurix.actions.registry import (
    _DESKTOP_CLIENT_BRANDS,
    _LOCALIZED_TARGETS,
    _WEBSITES,
    _candidate_names,
    _canonical_target,
    _key,
    _plain,
)

logger = logging.getLogger(__name__)

_OPEN_PATTERNS = (
    re.compile(
        r"^\s*(?:(?:aurix)[,\s]+)?(?:(?:please|can you|could you|would you)\s+)?(?:open|launch|start|show|run)\s+(?:up\s+)?(.+?)\s*[.!?]*\s*$",
        re.I,
    ),
    re.compile(
        r"^\s*(?:abre|abrir|inicia|iniciar|lanza|lanzar|ejecuta|ejecutar)\s+(?:(?:el|la|los|las)\s+)?(.+?)\s*[.!?]*\s*$",
        re.I,
    ),
    re.compile(
        r"^\s*(?:ouvre|ouvrir|lance|lancer)\s+(?:(?:le|la|les)\s+)?(.+?)\s*[.!?]*\s*$", re.I
    ),
    re.compile(r"^\s*(?:abre|abrir|inicie|iniciar)\s+(?:(?:o|a)\s+)?(.+?)\s*[.!?]*\s*$", re.I),
    re.compile(r"^\s*(?:खोलो|खोलिए|शुरू करो)\s+(.+?)\s*[.!?]*\s*$"),
    re.compile(
        r"^\s*(.+?)\s*(?:\u0c24\u0c46\u0c30\u0c41\u0c35\u0c41|\u0c24\u0c46\u0c30\u0c35\u0c02\u0c21\u0c3f|\u0c24\u0c46\u0c30\u0c35\u0c41|\u0c12\u0c2a\u0c46\u0c28\u0c4d \u0c1a\u0c47\u0c2f\u0c3f|\u0c12\u0c2a\u0c46\u0c28\u0c4d \u0c1a\u0c46\u0c2f\u0c4d\u0c2f\u0c3f)\s*[.!?]*\s*$"
    ),
    re.compile(r"^\s*(.+?)\s*(?:खोलो|खोलिए)\s*[.!?]*\s*$"),
)
_VIDEO_PATTERNS = (
    re.compile(
        r"^\s*(?:play|watch|find)\s+(?:(?:the|a|an)\s+)?(?:video|song|music|clip)\s+(?:called\s+|named\s+|about\s+)?(?P<q>.+?)(?:\s+on\s+(?:youtube|you\s*tube))?\s*[.!?]*\s*$",
        re.I,
    ),
    re.compile(r"^\s*(?:play|watch)\s+(.+?)\s+on\s+(?:youtube|you\s*tube)\s*[.!?]*\s*$", re.I),
    re.compile(r"^\s*(?:search|find)\s+(?:youtube|you\s*tube)\s+for\s+(.+?)\s*[.!?]*\s*$", re.I),
    re.compile(
        r"^\s*(?:open|play|watch)\s+(?:(?:the|a|an)\s+)?video\s+(?:called\s+|named\s+)?(.+?)\s*[.!?]*\s*$",
        re.I,
    ),
    re.compile(
        r"^\s*(?:reproduce|ver)\s+(?:el\s+)?(?:video|canción|musica)\s+(?:llamado\s+|llamada\s+)?(.+?)\s*(?:en\s+youtube)?\s*[.!?]*\s*$",
        re.I,
    ),
)


def parse_open_request(text: str) -> str | None:
    """Extract a direct open request from supported language patterns."""
    raw = (text or "").replace("\u200c", "").replace("\u200d", "").strip()
    # Speech transcription may render Telugu transliteration of "website" with
    # minor spelling variation. Normalize only the known service-intent token.
    raw = re.sub(r"వెబ్\s*సైట్|వెబ్సైట్", "website", raw, flags=re.I)
    for pattern in _OPEN_PATTERNS:
        match = pattern.match(raw)
        if match:
            target = match.group(1).strip().strip(" \t\r\n.,!?;:")
            target = target.replace("\u200c", " ").replace("\u200d", " ")
            # Keep common intent suffixes but strip punctuation/formatting first.
            target = re.sub(
                r"^(?:the|my|el|la|los|las|le|les|mi|mon|ma)\s+", "", target, flags=re.I
            ).strip()
            normalized = _plain(target)
            # Keep explicit intent suffixes for the resolver (e.g. "WhatsApp app").
            if normalized.endswith(
                (
                    "desktop app",
                    "desktop application",
                    "application",
                    "app",
                    "website",
                    "web site",
                    "site",
                    "web page",
                )
            ):
                return target or None
            return _LOCALIZED_TARGETS.get(normalized, target) or None
    return None


def parse_video_search(text: str) -> str | None:
    """Return a requested video/music title for YouTube search, or None."""
    raw = (text or "").strip()
    for pattern in _VIDEO_PATTERNS:
        match = pattern.match(raw)
        if match:
            query = match.group("q") if "q" in match.groupdict() else match.group(1)
            query = re.sub(r"\s+on\s+(?:youtube|you\s*tube)\s*$", "", query, flags=re.I)
            query = query.strip(" \t\r\n.,!?;:")
            query = re.sub(r"^(?:of|about|for|de|sobre)\s+", "", query, flags=re.I)
            if query:
                return query
    return None


def _launch_app(app: InstalledApp) -> bool:
    if app.kind in {"system_uri", "shortcut"}:
        if sys.platform != "win32":
            return False
        startfile = getattr(os, "startfile", None)
        if not startfile:
            return False
        startfile(app.target)
        return True
    if app.kind == "appid":
        if sys.platform != "win32":
            return False
        explorer = shutil.which("explorer.exe") or str(
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe"
        )
        if not Path(explorer).is_file():
            return False
        subprocess.Popen([explorer, f"shell:AppsFolder\\{app.target}"], shell=False)
        return True
    if app.kind == "executable":
        path = Path(app.target)
        if path.suffix.casefold() not in {".exe", ".com", ".msc"} or not path.is_file():
            return False
        if path.suffix.casefold() == ".msc":
            startfile = getattr(os, "startfile", None)
            if not startfile:
                return False
            startfile(str(path))
            return True
        subprocess.Popen(
            [str(path)],
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            if sys.platform == "win32"
            else 0,
        )
        return True
    return False


def _is_valid_web_url(url: str) -> bool:
    """Validate only absolute HTTP(S) URLs with hostname and no credentials."""
    try:
        parsed = urlparse(url)
        return bool(
            parsed.scheme.lower() in {"http", "https"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not any(ord(ch) < 32 for ch in url)
        )
    except (TypeError, ValueError):
        return False


def _open_url(url: str) -> bool:
    """Open a validated URL via the OS default browser."""
    if not _is_valid_web_url(url):
        return False
    try:
        return bool(webbrowser.open_new_tab(url))
    except Exception:
        logger.warning("Browser open failed.", exc_info=True)
        return False


def _website_fallback(target: str) -> tuple[str, str] | None:
    """Resolve configured website aliases or an explicitly supplied domain."""
    key = _key(_canonical_target(target))
    if key in _WEBSITES:
        return _WEBSITES[key]
    for alias, data in _WEBSITES.items():
        if _key(alias) in _candidate_names(target):
            return data
    cleaned = target.strip()
    if cleaned.lower().startswith(("http://", "https://")):
        return (cleaned, cleaned) if _is_valid_web_url(cleaned) else None
    if re.fullmatch(
        r"(?i)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9]){0,62})+(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?",
        cleaned,
    ):
        url = "https://" + cleaned
        return (cleaned, url) if _is_valid_web_url(url) else None
    return None


def _default_browser_request(target: str) -> bool:
    return _plain(target) in {
        "browser",
        "default browser",
        "internet browser",
        "web browser",
        "navegador",
        "el navegador",
    }


def _search_youtube(query: str) -> bool:
    return bool(query.strip()) and _open_url(
        "https://www.youtube.com/results?search_query=" + quote_plus(query.strip())
    )


def _search_web(query: str) -> bool:
    return bool(query.strip()) and _open_url(
        "https://www.google.com/search?q=" + quote_plus(query.strip())
    )


# Words that start ordinary conversation ("show me a joke", "start over", "run it again"),
# not the name of an application.
_CONVERSATIONAL_START = frozenset(
    "me us you him her it that this these those a an some any all how what why when where who "
    "over again up down out off on in to for with about my our your".split()
)


def _looks_like_conversation(target: str) -> bool:
    """True for an unresolved target that reads like a sentence rather than an app name."""
    words = target.casefold().split()
    if not words:
        return False
    return (
        len(words) > 3
        or words[0] in _CONVERSATIONAL_START
        or (len(words) >= 2 and words[0].endswith("ing"))
    )


def _open_site_response(label: str, url: str, language: str, target: str) -> str:
    if _open_url(url):
        return _message("opening_site", language, label=label)
    return _message("website_fail", language, target=target)


def _launch_response(app: InstalledApp, language: str) -> str:
    if _launch_app(app):
        return _message("opening_app", language, name=app.name)
    return _message("launch_fail", language, name=app.name)


def try_handle_desktop_command(text: str, language: str | None = None) -> str | None:
    """Handle explicit app/browser/content commands or return None for normal chat."""
    raw = (text or "").strip()
    if not raw:
        return None
    response_language = _response_language(raw, language)
    video_query = parse_video_search(raw)
    if video_query is not None:
        return (
            _message("video_search", response_language, query=video_query)
            if _search_youtube(video_query)
            else _message("video_fail", response_language)
        )
    search_match = re.match(
        r"^\s*(?:aurix[, ]+)?(?:search|look)\s+(?:the\s+)?(?:web|internet|google)\s+for\s+(.+?)\s*[.!?]*\s*$",
        raw,
        re.I,
    )
    if search_match:
        query = search_match.group(1).strip()
        return (
            _message("web_search", response_language, query=query)
            if _search_web(query)
            else _message("web_search_fail", response_language)
        )
    target = parse_open_request(raw)
    if target is None:
        return None

    # Pull intent markers from the original phrase before localized-name mapping.
    explicit_website = bool(re.search(r"\b(?:website|web site|site|web page)\b", target, re.I))
    explicit_app = bool(
        re.search(r"\b(?:desktop app|desktop application|app|application)\b", target, re.I)
    )
    target = re.sub(
        r"\b(?:website|web site|site|web page|desktop app|desktop application|application|app)\b",
        " ",
        target,
        flags=re.I,
    )
    target = " ".join(target.split()).strip()

    # Reject explicit non-web URL schemes (javascript:, file:, mailto:, etc.).
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) and not target.lower().startswith(
        ("http://", "https://")
    ):
        return _message("invalid_url", response_language)

    # Resolve a direct URL only after validating scheme/host/userinfo.
    if target.lower().startswith(("http://", "https://")):
        if _open_url(target):
            return _message("opening_url", response_language)
        return _message("invalid_url", response_language)

    # Direct executable paths and scripts are never accepted from speech.
    if (
        "\\" in target
        or "/" in target
        or re.search(r"(?i)\.(?:exe|com|cmd|bat|ps1|msi|dll)$", target.strip())
    ):
        return _message("unsafe", response_language)

    target = _canonical_target(target)
    key = _key(target)
    if not key and not _plain(target):
        return _message("empty_target", response_language)

    try:
        if explicit_website:
            fallback = _website_fallback(target)
            if fallback is None:
                return f"I couldn't identify the official website for '{target}'. Please provide its domain."
            label, url = fallback
            return _open_site_response(label, url, response_language, target)

        if explicit_app:
            app = _find_installed_app(target)
            if app is None:
                return f"I couldn't find {target.title()} installed on this system."
            return _launch_response(app, response_language)

        if _default_browser_request(target):
            try:
                if webbrowser.open_new_tab("about:blank"):
                    return _message("default_browser", response_language)
            except Exception:
                pass
            if _open_url("https://www.google.com/"):
                return _message("default_browser", response_language)
            return _message("default_browser_fail", response_language)

        # A known brand name normally means its configured service. Say "app"
        # when the user instead means its installed desktop client.
        website_key = key
        if website_key in _WEBSITES:
            if website_key in _DESKTOP_CLIENT_BRANDS:
                client_app = _find_installed_app(target)
                if client_app is not None:
                    return _launch_response(client_app, response_language)
            label, url = _WEBSITES[website_key]
            return _open_site_response(label, url, response_language, target)

        app = _find_installed_app(target)
        if app is not None:
            return _launch_response(app, response_language)

        fallback = _website_fallback(target)
        if fallback is not None:
            label, url = fallback
            return _open_site_response(label, url, response_language, target)
        if _looks_like_conversation(target):
            return None  # normal chat such as "show me a joke": let the AI answer it
        return _message("not_found", response_language, target=target)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Could not launch target %r: %s", target, exc)
        return f"I couldn't open '{target}'. Check that it is installed and accessible."
    except Exception:
        logger.exception("Unexpected desktop-launch error for %r", target)
        return f"I hit an error while opening '{target}'. Check the application installation and terminal log."


# Short alias used by scripts/diagnose.py and the tests.
handle_desktop_command = try_handle_desktop_command
