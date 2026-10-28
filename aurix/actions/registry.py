"""Reviewed application/website registry and target-name normalisation for AURIX actions.

Add new apps or sites here (data only); the intent resolver and launcher do not change.
"""

from __future__ import annotations

import re
import unicodedata

_WEBSITES: dict[str, tuple[str, str]] = {
    "youtube": ("YouTube", "https://www.youtube.com/"),
    "you tube": ("YouTube", "https://www.youtube.com/"),
    "google": ("Google", "https://www.google.com/"),
    "github": ("GitHub", "https://github.com/"),
    "git hub": ("GitHub", "https://github.com/"),
    "gmail": ("Gmail", "https://mail.google.com/"),
    "chatgpt": ("ChatGPT", "https://chatgpt.com/"),
    "chat gpt": ("ChatGPT", "https://chatgpt.com/"),
    "wikipedia": ("Wikipedia", "https://www.wikipedia.org/"),
    "stack overflow": ("Stack Overflow", "https://stackoverflow.com/"),
    "spotify": ("Spotify", "https://open.spotify.com/"),
    "whatsapp": ("WhatsApp Web", "https://web.whatsapp.com/"),
    "whatsapp web": ("WhatsApp Web", "https://web.whatsapp.com/"),
    "outlook": ("Outlook", "https://outlook.office.com/"),
    "jio": ("Jio", "https://www.jio.com/"),
    "reliance jio": ("Jio", "https://www.jio.com/"),
    # These entries intentionally target official download pages, not browser apps.
    "brave browser website": ("Brave Browser", "https://brave.com/download/"),
    "google chrome website": ("Google Chrome", "https://www.google.com/chrome/"),
    "firefox website": ("Firefox", "https://www.mozilla.org/firefox/new/"),
    "edge website": ("Microsoft Edge", "https://www.microsoft.com/edge/download"),
    "visual studio code website": ("Visual Studio Code", "https://vscode.dev/"),
}

# Brands that have both a web service and a desktop client: prefer an installed client.
_DESKTOP_CLIENT_BRANDS = frozenset({"spotify", "whatsapp", "outlook"})

_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("visual studio code", "vs code", "vscode", "code", "code editor"),
    (
        "visual studio",
        "visual studio 2022",
        "visual studio 2019",
        "visual studio community",
        "visual studio community 2022",
        "visual studio professional 2022",
        "visual studio enterprise 2022",
        "devenv",
    ),
    ("brave", "brave browser"),
    ("chrome", "google chrome", "chrome browser"),
    ("firefox", "mozilla firefox", "firefox browser"),
    ("edge", "microsoft edge", "edge browser"),
    ("notepad", "notepad editor", "bloc de notas", "bloc-notes", "नोटपैड", "నోట్‌ప్యాడ్", "నోట్ ప్యాడ్"),
    ("calculator", "calc", "windows calculator", "calculadora", "calculatrice", "गणक", "క్యాలిక్యులేటర్"),
    ("paint", "microsoft paint", "mspaint", "pintura"),
    (
        "file explorer",
        "explorer",
        "windows explorer",
        "explorador de archivos",
        "explorateur de fichiers",
    ),
    ("powershell", "windows powershell", "power shell"),
    ("command prompt", "cmd", "cmd prompt"),
    ("windows terminal", "terminal", "wt"),
    ("task manager", "taskmgr", "administrador de tareas"),
    ("control panel", "panel de control"),
    (
        "settings",
        "windows settings",
        "system settings",
        "ajustes",
        "configuración",
        "सेटिंग्स",
        "సెట్టింగ్స్",
    ),
    ("device manager", "administrador de dispositivos"),
    ("registry editor", "regedit"),
    ("spotify", "spotify music"),
    ("whatsapp", "whatsapp desktop", "whatsapp application", "वाट्सऐप", "व्हाट्सएप", "వాట్సాప్"),
    ("chatgpt", "chat gpt", "चैटजीपीटी"),
    ("youtube", "you tube", "यूट्यूब", "యూట్యూబ్"),
    ("google", "गूगल", "గూగుల్"),
    ("jio", "reliance jio"),
)
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
_GENERIC_WORDS = {"browser", "application", "app", "desktop", "installed", "desktop app"}

_LOCALIZED_TARGETS = {
    "el navegador": "browser",
    "navegador": "browser",
    "web browser": "browser",
    "explorador": "file explorer",
    "explorador de archivos": "file explorer",
    "abre whatsapp": "whatsapp",
    "whatsapp app": "whatsapp",
    "వాట్సాప్": "whatsapp",
    "వాట్సాప్ అప్లికేషన్": "whatsapp",
    "నోట్‌ప్యాడ్": "notepad",
    "నోట్ ప్యాడ్": "notepad",
    "యూట్యూబ్": "youtube",
    "గూగుల్": "google",
    "సెట్టింగ్స్": "settings",
    "व्हाट्सएप": "whatsapp",
    "वाट्सऐप": "whatsapp",
    "नोटपैड": "notepad",
    "यूट्यूब": "youtube",
    "गूगल": "google",
    "सेटिंग्स": "settings",
    "bloc de notas": "notepad",
    "calculadora": "calculator",
}


def _plain(value: str) -> str:
    """Normalize a phrase while preserving Unicode letters and combining marks."""
    value = unicodedata.normalize("NFKC", (value or "").casefold().strip())
    kept: list[str] = []
    for char in value:
        category = unicodedata.category(char)
        if category[0] in {"L", "M", "N"} or char in {" ", "-", "."}:
            kept.append(char)
        else:
            kept.append(" ")
    return " ".join("".join(kept).split()).strip()


def _key(value: str) -> str:
    value = _plain(value)
    value = re.sub(r"\.(lnk|url|appref-ms|exe|com|msc)$", "", value)
    words = re.findall(r"[a-z0-9]+", value.replace("&", " and "))
    while words and words[-1] in _GENERIC_WORDS:
        words.pop()
    return " ".join(words)


def _canonical_target(target: str) -> str:
    if target.strip().lower().startswith(("http://", "https://")):
        return target.strip()
    return _LOCALIZED_TARGETS.get(_plain(target), _plain(target))


def _candidate_names(target: str) -> set[str]:
    normalized = _key(_canonical_target(target))
    names = {normalized} if normalized else set()
    for group in _ALIAS_GROUPS:
        group_keys = {_key(item) for item in group}
        if normalized in group_keys:
            names.update(group_keys)
            break
    return {name for name in names if name}
