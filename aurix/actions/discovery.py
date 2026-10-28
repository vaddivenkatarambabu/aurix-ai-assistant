"""Windows application discovery: finds verified launch targets, never launches anything."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from aurix.actions.registry import (
    _ALIAS_GROUPS,
    _SYSTEM_EXECUTABLES,
    _candidate_names,
    _canonical_target,
    _key,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstalledApp:
    """An app whose target was found from trusted system metadata."""

    name: str
    kind: str
    target: str


def _start_menu_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    if os.environ.get("APPDATA"):
        roots.append(
            Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        )
    if os.environ.get("PROGRAMDATA"):
        roots.append(
            Path(os.environ["PROGRAMDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        )
    return tuple(root for root in roots if root.is_dir())


@lru_cache(maxsize=1)
def _start_menu_shortcuts() -> tuple[Path, ...]:
    found: list[Path] = []
    for root in _start_menu_roots():
        try:
            for path in root.rglob("*"):
                try:
                    if path.is_file() and path.suffix.casefold() in {".lnk", ".appref-ms"}:
                        found.append(path)
                except OSError:
                    continue
        except OSError:
            continue
    return tuple(found)


def _find_start_menu_shortcut(target: str) -> Path | None:
    wanted = _candidate_names(target)
    for path in _start_menu_shortcuts():
        if _key(path.stem) in wanted:
            return path
    if _key(target) == "visual studio":
        for path in _start_menu_shortcuts():
            name = _key(path.stem)
            if (
                name.startswith("visual studio ")
                and "installer" not in name
                and re.search(r"\b20\d{2}\b", name)
            ):
                return path
    return None


@lru_cache(maxsize=1)
def _windows_start_apps() -> tuple[tuple[str, str], ...]:
    """Read Windows' fixed Get-StartApps inventory command; no voice text is injected."""
    if sys.platform != "win32":
        return ()
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return ()
    script = "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
    try:
        proc = subprocess.run(
            [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            shell=False,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return ()
        data = json.loads(proc.stdout)
        if isinstance(data, dict):
            data = [data]
        return tuple(
            (item["Name"].strip(), item["AppID"].strip())
            for item in data
            if isinstance(item, dict)
            and isinstance(item.get("Name"), str)
            and item["Name"].strip()
            and isinstance(item.get("AppID"), str)
            and item["AppID"].strip()
        )
    except (
        OSError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
        ValueError,
        KeyError,
        TypeError,
    ):
        logger.debug("Could not enumerate Windows Start Apps.", exc_info=True)
        return ()


def _find_start_app_id(target: str) -> tuple[str, str] | None:
    wanted = _candidate_names(target)
    for name, app_id in _windows_start_apps():
        if _key(name) in wanted:
            return name, app_id
    if _key(target) == "visual studio":
        for name, app_id in _windows_start_apps():
            normalized = _key(name)
            if (
                normalized.startswith("visual studio ")
                and "installer" not in normalized
                and re.search(r"\b20\d{2}\b", normalized)
            ):
                return name, app_id
    return None


def _registry_app_paths() -> dict[str, Path]:
    if sys.platform != "win32":
        return {}
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return {}
    result: dict[str, Path] = {}
    locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
        ),
    )
    for hive, key_path in locations:
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
                        path = Path(os.path.expandvars(str(value).strip().strip('"')))
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


def _display_icon_executable(raw_value: object) -> Path | None:
    raw = os.path.expandvars(str(raw_value or "").strip())
    if not raw:
        return None
    match = (
        re.match(r'^"([^"\r\n]+\.exe)"', raw, re.I)
        if raw.startswith('"')
        else re.match(r"^(.*?\.exe)(?:,\s*-?\d+)?$", raw, re.I)
    )
    candidate = match.group(1).strip() if match else ""
    if not candidate:
        return None
    path = Path(candidate)
    if not path.is_file() or path.suffix.casefold() != ".exe":
        return None
    if any(
        word in _key(path.stem)
        for word in ("installer", "uninstall", "setup", "updater", "crashpad")
    ):
        return None
    return path


def _registry_installed_programs() -> tuple[tuple[str, Path], ...]:
    if sys.platform != "win32":
        return ()
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return ()
    locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
    )
    entries: list[tuple[str, Path]] = []
    for hive, key_path in locations:
        try:
            with winreg.OpenKey(hive, key_path) as root:
                index = 0
                while True:
                    try:
                        child_name = winreg.EnumKey(root, index)
                        index += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(root, child_name) as child:
                            display_name, _ = winreg.QueryValueEx(child, "DisplayName")
                            display_icon, _ = winreg.QueryValueEx(child, "DisplayIcon")
                        if isinstance(display_name, str) and display_name.strip():
                            path = _display_icon_executable(display_icon)
                            if path:
                                entries.append((display_name.strip(), path))
                    except OSError:
                        continue
        except OSError:
            continue
    return tuple(entries)


@lru_cache(maxsize=1)
def _registered_installed_programs() -> tuple[tuple[str, Path], ...]:
    return _registry_installed_programs()


def _find_registered_program(target: str) -> tuple[str, Path] | None:
    wanted = _candidate_names(target)
    prefixes = ("microsoft ", "google ", "mozilla ", "spotify ", "adobe ")
    for display_name, executable in _registered_installed_programs():
        display_key = _key(display_name)
        names = {display_key}
        names.update(
            display_key[len(prefix) :] for prefix in prefixes if display_key.startswith(prefix)
        )
        if names.intersection(wanted):
            return display_name, executable
    return None


def _common_executable_paths(target: str) -> tuple[Path, ...]:
    wanted = _candidate_names(target)
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    paths: list[Path] = []
    candidates = {
        "vs code": (
            Path(local) / "Programs/Microsoft VS Code/Code.exe",
            Path(pf) / "Microsoft VS Code/Code.exe",
            Path(pf86) / "Microsoft VS Code/Code.exe",
        ),
        "brave": (
            Path(local) / "BraveSoftware/Brave-Browser/Application/brave.exe",
            Path(pf) / "BraveSoftware/Brave-Browser/Application/brave.exe",
            Path(pf86) / "BraveSoftware/Brave-Browser/Application/brave.exe",
        ),
        "chrome": (
            Path(local) / "Google/Chrome/Application/chrome.exe",
            Path(pf) / "Google/Chrome/Application/chrome.exe",
            Path(pf86) / "Google/Chrome/Application/chrome.exe",
        ),
        "firefox": (
            Path(pf) / "Mozilla Firefox/firefox.exe",
            Path(pf86) / "Mozilla Firefox/firefox.exe",
        ),
        "edge": (
            Path(pf) / "Microsoft/Edge/Application/msedge.exe",
            Path(pf86) / "Microsoft/Edge/Application/msedge.exe",
        ),
        "whatsapp": (
            Path(local) / "WhatsApp/WhatsApp.exe",
            Path(local) / "Programs/WhatsApp/WhatsApp.exe",
            Path(pf) / "WindowsApps/WhatsApp.exe",
        ),
        "spotify": (
            Path(local) / "Microsoft/WindowsApps/Spotify.exe",
            Path(local) / "Spotify/Spotify.exe",
            Path(pf) / "Spotify/Spotify.exe",
        ),
    }
    for canonical, paths_for_app in candidates.items():
        if wanted.intersection(_candidate_names(canonical)):
            paths.extend(paths_for_app)
    return tuple(path for path in paths if path.is_file())


def _find_visual_studio() -> Path | None:
    if sys.platform != "win32":
        return None
    pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    vswhere = Path(pf86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return None
    try:
        proc = subprocess.run(
            [str(vswhere), "-latest", "-products", "*", "-property", "installationPath"],
            shell=False,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        install = proc.stdout.strip()
        candidate = (
            Path(install) / "Common7/IDE/devenv.exe" if proc.returncode == 0 and install else None
        )
        return candidate if candidate and candidate.is_file() else None
    except (OSError, subprocess.SubprocessError):
        return None


def _find_executable(target: str) -> Path | None:
    wanted = _candidate_names(target)
    for group in _ALIAS_GROUPS:
        if wanted.intersection({_key(item) for item in group}):
            canonical = _key(group[0])
            for executable in _SYSTEM_EXECUTABLES.get(canonical, ()):
                found = shutil.which(executable)
                if found and Path(found).suffix.casefold() in {".exe", ".com", ".msc"}:
                    return Path(found)
                if executable.lower().endswith((".exe", ".msc")):
                    known = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / executable
                    if known.is_file():
                        return known
    canonical = _key(_canonical_target(target))
    if canonical in {
        "visual studio",
        "visual studio 2022",
        "visual studio community",
        "visual studio community 2022",
        "visual studio professional 2022",
        "visual studio enterprise 2022",
        "devenv",
    }:
        found_vs = _find_visual_studio()
        if found_vs:
            return found_vs
    for path in _common_executable_paths(target):
        return path
    for candidate in wanted:
        if candidate in _registered_app_paths():
            return _registered_app_paths()[candidate]
    # Bare spoken names can resolve only through PATH; shell=True is never used.
    if re.fullmatch(r"[A-Za-z0-9_. -]{1,80}", target):
        found = shutil.which(target)
        if found and Path(found).is_file() and Path(found).suffix.casefold() in {".exe", ".com"}:
            return Path(found)
    return None


def _find_installed_app(target: str) -> InstalledApp | None:
    key = _key(_canonical_target(target))
    if key in {"settings", "windows settings", "system settings"}:
        return InstalledApp("Windows Settings", "system_uri", "ms-settings:")
    shortcut = _find_start_menu_shortcut(target)
    if shortcut is not None:
        return InstalledApp(shortcut.stem, "shortcut", str(shortcut))
    start_app = _find_start_app_id(target)
    if start_app is not None:
        return InstalledApp(start_app[0], "appid", start_app[1])
    executable = _find_executable(target)
    if executable is not None:
        return InstalledApp(executable.stem, "executable", str(executable))
    registered = _find_registered_program(target)
    if registered is not None:
        return InstalledApp(registered[0], "executable", str(registered[1]))
    return None
