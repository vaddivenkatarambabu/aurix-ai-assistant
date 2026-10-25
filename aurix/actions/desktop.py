"""Safe desktop and website launcher for AURIX.

This module launches only a resolved Start Menu shortcut, a resolved executable,
a small set of explicit Windows system tools, or a validated HTTP(S) website.
It never passes voice text to a shell and never uses shell=True.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import webbrowser
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

_OPEN_RE = re.compile(
    r"^\s*(?:(?:aurix)[,\s]+)?(?:(?:please|can you|could you|would you)\s+)?"
    r"(?:open|launch|start|show)\s+(?:up\s+)?(.+?)\s*[.!?]*\s*$",
    re.IGNORECASE,
)

# Sites are fallbacks: if a matching application shortcut is installed, AURIX
# opens the app first. Only normal HTTPS pages are opened as URLs.
_WEBSITES: dict[str, str] = {
    "youtube": "https://www.youtube.com/",
    "google": "https://www.google.com/",
    "github": "https://github.com/",
    "gmail": "https://mail.google.com/",
    "chatgpt": "https://chatgpt.com/",
    "wikipedia": "https://www.wikipedia.org/",
    "stack overflow": "https://stackoverflow.com/",
    "spotify": "https://open.spotify.com/",
    "whatsapp": "https://web.whatsapp.com/",
    "outlook": "https://outlook.office.com/",
}

# Aliases are used to match human names to Start Menu shortcuts or executable
# names. They are not shell commands and are never concatenated into a command
# line. Add aliases here when a specific installed app needs a better name.
_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("vs code", "visual studio code", "vscode", "code", "code editor"),
    ("brave", "brave browser"),
    ("chrome", "google chrome", "chrome browser"),
    ("firefox", "mozilla firefox", "firefox browser"),
    ("edge", "microsoft edge", "edge browser"),
    ("notepad", "notepad editor"),
    ("calculator", "calc", "windows calculator"),
    ("paint", "microsoft paint"),
    ("file explorer", "explorer", "windows explorer"),
    ("powershell", "windows powershell", "power shell"),
    ("command prompt", "cmd", "cmd prompt"),
    ("windows terminal", "terminal", "wt"),
    ("task manager", "taskmgr"),
    ("control panel",),
    ("settings", "windows settings", "system settings"),
    ("device manager",),
    ("registry editor", "regedit"),
    ("spotify", "spotify music"),
    ("whatsapp", "whatsapp desktop"),
    ("chatgpt", "chat gpt"),
)

# Explicitly supported system tools. We launch executable files directly; we do
# not interpret command-line text spoken by the user.
_SYSTEM_EXECUTABLES: dict[str, tuple[str, ...]] = {
    "notepad": ("notepad.exe",),
    "calculator": ("calc.exe",),
    "paint": ("mspaint.exe",),
    "file explorer": ("explorer.exe",),
    "powershell": ("powershell.exe", "pwsh.exe"),
    "command prompt": ("cmd.exe",),
    "windows terminal": ("wt.exe",),
    "task manager": ("taskmgr.exe",),
    "control panel": ("control.exe",),
    "registry editor": ("regedit.exe",),
    "device manager": ("devmgmt.msc",),
}

_SYSTEM_URIS: dict[str, str] = {
    "settings": "ms-settings:",
}

_GENERIC_WORDS = {"browser", "application", "app", "desktop"}


def _key(value: str) -> str:
    """Normalize a display name for safe exact matching."""
    value = value.casefold().strip()
    value = re.sub(r"\.(lnk|url|appref-ms|exe|com|msc)$", "", value)
    value = value.replace("&", " and ")
    words = re.findall(r"[a-z0-9]+", value)
    while words and words[-1] in _GENERIC_WORDS:
        words.pop()
    return " ".join(words)


def _candidate_names(target: str) -> set[str]:
    normalized = _key(target)
    names = {normalized}
    for group in _ALIAS_GROUPS:
        group_keys = {_key(item) for item in group}
        if normalized in group_keys:
            names.update(group_keys)
            break
    return {name for name in names if name}


def parse_open_request(text: str) -> str | None:
    """Extract a target only from an explicit open/launch/start/show request.

    Returning None means this is ordinary conversation and should be sent to
    the AI engine. This function does not support arbitrary shell commands.
    """
    match = _OPEN_RE.match(text or "")
    if not match:
        return None

    target = match.group(1).strip().strip(" \t\r\n.,!?;:")
    target = re.sub(r"^(?:the|my)\s+", "", target, flags=re.IGNORECASE).strip()
    return target or None


def _start_menu_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    if appdata:
        roots.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if programdata:
        roots.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return tuple(root for root in roots if root.is_dir())


@lru_cache(maxsize=1)
def _start_menu_shortcuts() -> tuple[Path, ...]:
    """Index normal Start Menu shortcuts once per process."""
    results: list[Path] = []
    extensions = {".lnk", ".url", ".appref-ms"}
    for root in _start_menu_roots():
        try:
            for path in root.rglob("*"):
                try:
                    if path.is_file() and path.suffix.casefold() in extensions:
                        results.append(path)
                except OSError:
                    continue
        except OSError:
            continue
    return tuple(results)


def _find_start_menu_shortcut(target: str) -> Path | None:
    wanted = _candidate_names(target)
    # Do not use fuzzy matching for executable launches: a close but wrong
    # application is more dangerous than a clear not-found message.
    for path in _start_menu_shortcuts():
        if _key(path.stem) in wanted:
            return path
    return None


def _common_executable_paths(target: str) -> tuple[Path, ...]:
    """Return known install locations for apps not always registered on PATH."""
    names = _candidate_names(target)
    local = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    candidates: list[Path] = []

    if names & {_key(x) for x in ("vs code", "visual studio code", "vscode", "code", "code editor")}:
        candidates.extend(
            [
                Path(local) / "Programs" / "Microsoft VS Code" / "Code.exe",
                Path(program_files) / "Microsoft VS Code" / "Code.exe",
                Path(program_files_x86) / "Microsoft VS Code" / "Code.exe",
            ]
        )
    if names & {_key(x) for x in ("brave", "brave browser")}:
        candidates.extend(
            [
                Path(local) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
                Path(program_files) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
                Path(program_files_x86) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            ]
        )
    if names & {_key(x) for x in ("chrome", "google chrome", "chrome browser")}:
        candidates.extend(
            [
                Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe",
            ]
        )
    if names & {_key(x) for x in ("firefox", "mozilla firefox", "firefox browser")}:
        candidates.extend(
            [
                Path(program_files) / "Mozilla Firefox" / "firefox.exe",
                Path(program_files_x86) / "Mozilla Firefox" / "firefox.exe",
            ]
        )
    if names & {_key(x) for x in ("edge", "microsoft edge", "edge browser")}:
        candidates.extend(
            [
                Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(program_files_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            ]
        )

    return tuple(path for path in candidates if path.is_file())


def _registry_app_paths() -> dict[str, Path]:
    """Read Windows App Paths registration without changing the registry."""
    if sys.platform != "win32":
        return {}
    try:
        import winreg
    except ImportError:  # pragma: no cover - only relevant on Windows
        return {}

    result: dict[str, Path] = {}
    registry_locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
    )
    for hive, key_path in registry_locations:
        try:
            with winreg.OpenKey(hive, key_path) as root:
                index = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(root, index)
                        index += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(root, subkey_name) as subkey:
                            value, _ = winreg.QueryValueEx(subkey, None)
                        # Registry entries normally contain just a path. Reject
                        # values with extra command-line arguments.
                        value = str(value).strip().strip('"')
                        path = Path(value)
                        if path.is_file() and path.suffix.casefold() in {".exe", ".com"}:
                            result[_key(subkey_name)] = path
                    except OSError:
                        continue
        except OSError:
            continue
    return result


@lru_cache(maxsize=1)
def _registered_app_paths() -> dict[str, Path]:
    return _registry_app_paths()


def _find_executable(target: str) -> Path | None:
    wanted = _candidate_names(target)

    # First look for explicit aliases for a small set of Windows system tools.
    for alias_group in _ALIAS_GROUPS:
        if wanted.intersection({_key(item) for item in alias_group}):
            canonical = _key(alias_group[0])
            for executable in _SYSTEM_EXECUTABLES.get(canonical, ()):
                found = shutil.which(executable)
                if found:
                    path = Path(found)
                    if path.suffix.casefold() in {".exe", ".com", ".msc"}:
                        return path
                # System tools may not be present in PATH even though Windows
                # ships them. Resolve them from the Windows directory explicitly.
                if executable.lower().endswith((".exe", ".msc")):
                    system_root = os.environ.get("WINDIR", r"C:\Windows")
                    known = Path(system_root) / "System32" / executable
                    if known.is_file():
                        return known
                    if executable.lower() == "devmgmt.msc":
                        known_msc = Path(system_root) / "System32" / executable
                        if known_msc.is_file():
                            return known_msc

    # Common install paths, then the registered App Paths keys.
    for path in _common_executable_paths(target):
        return path

    app_paths = _registered_app_paths()
    for candidate in wanted:
        if candidate in app_paths:
            return app_paths[candidate]

    # Allow an explicitly named executable only if Windows resolves it to a
    # real .exe/.com. Never invoke .bat/.cmd/.ps1 through a shell.
    if re.fullmatch(r"[A-Za-z0-9_. -]{1,80}", target):
        found = shutil.which(target)
        if found:
            path = Path(found)
            if path.is_file() and path.suffix.casefold() in {".exe", ".com"}:
                return path
    return None


def _launch_path(path: Path) -> bool:
    """Launch one resolved Start Menu shortcut or executable safely."""
    suffix = path.suffix.casefold()
    if suffix in {".lnk", ".url", ".appref-ms", ".msc"}:
        if sys.platform == "win32":
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                return False
            startfile(str(path))
            return True
        if suffix == ".url":
            return webbrowser.open_new_tab(path.as_uri())
        return False

    if suffix not in {".exe", ".com"}:
        return False

    # shell=False is deliberate: recognized speech is never interpreted as
    # PowerShell, CMD, a batch file, or arbitrary shell syntax.
    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if sys.platform == "win32" else 0
    subprocess.Popen([str(path)], shell=False, creationflags=creationflags)
    return True


def _open_url(url: str) -> bool:
    """Open a validated HTTP(S) URL in the default browser."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    try:
        return bool(webbrowser.open_new_tab(url))
    except Exception:
        return False


def _as_website(target: str) -> str | None:
    key = _key(target)
    if key in _WEBSITES:
        return _WEBSITES[key]

    # Accept a bare public-looking domain, but never infer non-web schemes.
    if re.fullmatch(
        r"(?i)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?",
        target.strip(),
    ):
        return "https://" + target.strip()

    if target.strip().lower().startswith(("http://", "https://")):
        parsed = urlparse(target.strip())
        if parsed.hostname and not parsed.username and not parsed.password:
            return target.strip()
    return None


def _plain_key(value: str) -> str:
    """Normalize words without removing generic suffixes such as browser."""
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _is_default_browser_request(target: str) -> bool:
    return _plain_key(target) in {
        "browser",
        "default browser",
        "internet browser",
        "web browser",
    }


def try_handle_desktop_command(text: str) -> str | None:
    """Handle explicit open/launch requests; return None for normal AI chat.

    The result string is the user-facing response. An unknown launch target
    fails closed with instructions rather than executing a guessed command.
    """
    target = parse_open_request(text)
    if target is None:
        return None

    key = _key(target)

    try:
        if _is_default_browser_request(target):
            try:
                if webbrowser.open_new_tab("about:blank"):
                    return "Opening your default browser."
            except Exception:
                pass
            if _open_url("https://www.google.com/"):
                return "Opening your default browser."
            return "I couldn't open your default browser. Check your browser settings."

        if not key:
            return "What application or website should I open?"

        # Use the Windows Settings URI for settings pages; do not invoke a shell.
        if key in {"settings", "windows settings", "system settings"}:
            uri = _SYSTEM_URIS[key]
            if sys.platform == "win32":
                startfile = getattr(os, "startfile", None)
                if startfile is None:
                    return "Windows Settings could not be launched on this platform."
                startfile(uri)
                return "Opening Windows Settings."
            return "Windows Settings is available only on Windows."

        shortcut = _find_start_menu_shortcut(target)
        if shortcut is not None and _launch_path(shortcut):
            return f"Opening {target}."

        executable = _find_executable(target)
        if executable is not None and _launch_path(executable):
            return f"Opening {target}."

        website = _as_website(target)
        if website and _open_url(website):
            return f"Opening {target} in your default browser."

        return (
            f"I couldn't find an installed application or supported website named '{target}'. "
            "Check its Windows Start Menu shortcut or use the full website domain. "
            "I did not execute a shell command."
        )
    except Exception as exc:
        # Keep the voice loop alive and return an actionable, user-facing error.
        return f"I couldn't open '{target}': {exc}"

# Backward-compatible name used by aurix.assistant.
handle_desktop_command = try_handle_desktop_command
