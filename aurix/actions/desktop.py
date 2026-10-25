"""Windows-first, safe desktop discovery and browser/content launching for AURIX.

Applications are resolved from Start Menu shortcuts, Windows' installed Start Apps
inventory, App Paths registry entries, known standard locations, and PATH. Voice text
is never passed to a shell. Unknown targets fail closed unless a known website fallback
exists.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus, urlparse
import webbrowser

logger = logging.getLogger(__name__)

_OPEN_PATTERNS = (
    re.compile(
        r"^\s*(?:(?:aurix)[,\s]+)?(?:(?:please|can you|could you|would you)\s+)?"
        r"(?:open|launch|start|show|run)\s+(?:up\s+)?(.+?)\s*[.!?]*\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(?:abre|abrir|inicia|iniciar|lanza|lanzar|ejecuta|ejecutar)\s+(?:(?:el|la|los|las)\s+)?(.+?)\s*[.!?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:ouvre|ouvrir|lance|lancer)\s+(?:(?:le|la|les)\s+)?(.+?)\s*[.!?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:abre|abrir|inicie|iniciar)\s+(?:(?:o|a)\s+)?(.+?)\s*[.!?]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:खोलो|खोलिए|शुरू करो)\s+(.+?)\s*[.!?]*\s*$"),
    re.compile(r"^\s*(.+?)\s*(?:తెరువు|తెరవండి|తెరవు|ఓపెన్ చేయి|ఓపెన్ చెయ్యి)\s*[.!?]*\s*$"),
    re.compile(r"^\s*(.+?)\s*(?:खोलो|खोलिए)\s*[.!?]*\s*$"),
)

_VIDEO_PATTERNS = (
    re.compile(r"^\s*(?:play|watch|find)\s+(?:(?:the|a|an)\s+)?(?:video|song|music|clip)\s+(?:called\s+|named\s+|about\s+)?(?P<q>.+?)(?:\s+on\s+(?:youtube|you\s*tube))?\s*[.!?]*\s*$", re.I),
    re.compile(r"^\s*(?:play|watch)\s+(.+?)\s+on\s+(?:youtube|you\s*tube)\s*[.!?]*\s*$", re.I),
    re.compile(r"^\s*(?:search|find)\s+(?:youtube|you\s*tube)\s+for\s+(.+?)\s*[.!?]*\s*$", re.I),
    re.compile(r"^\s*(?:open|play|watch)\s+(?:(?:the|a|an)\s+)?video\s+(?:called\s+|named\s+)?(.+?)\s*[.!?]*\s*$", re.I),
    re.compile(r"^\s*(?:reproduce|ver)\s+(?:el\s+)?(?:video|canción|musica)\s+(?:llamado\s+|llamada\s+)?(.+?)\s*(?:en\s+youtube)?\s*[.!?]*\s*$", re.I),
)

# Known web counterparts are fallback destinations, not the first choice. If the
# desktop application is present, it is launched first.
_WEBSITES: dict[str, tuple[str, str]] = {
    "youtube": ("YouTube", "https://www.youtube.com/"),
    "google": ("Google", "https://www.google.com/"),
    "github": ("GitHub", "https://github.com/"),
    "gmail": ("Gmail", "https://mail.google.com/"),
    "chatgpt": ("ChatGPT", "https://chatgpt.com/"),
    "wikipedia": ("Wikipedia", "https://www.wikipedia.org/"),
    "stack overflow": ("Stack Overflow", "https://stackoverflow.com/"),
    "spotify": ("Spotify", "https://open.spotify.com/"),
    "whatsapp": ("WhatsApp", "https://web.whatsapp.com/"),
    "outlook": ("Outlook", "https://outlook.office.com/"),
    "brave browser": ("Brave Browser", "https://brave.com/download/"),
    "brave": ("Brave Browser", "https://brave.com/download/"),
    "google chrome": ("Google Chrome", "https://www.google.com/chrome/"),
    "chrome": ("Google Chrome", "https://www.google.com/chrome/"),
    "firefox": ("Firefox", "https://www.mozilla.org/firefox/new/"),
    "mozilla firefox": ("Firefox", "https://www.mozilla.org/firefox/new/"),
    "microsoft edge": ("Microsoft Edge", "https://www.microsoft.com/edge/download"),
    "edge": ("Microsoft Edge", "https://www.microsoft.com/edge/download"),
    "visual studio code": ("Visual Studio Code", "https://vscode.dev/"),
    "vs code": ("Visual Studio Code", "https://vscode.dev/"),
    "vscode": ("Visual Studio Code", "https://vscode.dev/"),
    "visual studio": ("Visual Studio", "https://visualstudio.microsoft.com/vs/"),
}

_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("visual studio code", "vs code", "vscode", "code", "code editor"),
    ("visual studio", "visual studio 2022", "visual studio 2019", "visual studio community", "visual studio community 2022", "visual studio professional 2022", "visual studio enterprise 2022", "devenv"),
    ("brave", "brave browser"),
    ("chrome", "google chrome", "chrome browser"),
    ("firefox", "mozilla firefox", "firefox browser"),
    ("edge", "microsoft edge", "edge browser"),
    ("notepad", "notepad editor", "bloc de notas", "bloc-notes", "नोटपैड", "నోట్‌ప్యాడ్", "నోట్ ప్యాడ్"),
    ("calculator", "calc", "windows calculator", "calculadora", "calculatrice", "गणक", "క్యాలిక్యులేటర్"),
    ("paint", "microsoft paint", "mspaint", "pintura"),
    ("file explorer", "explorer", "windows explorer", "explorador de archivos", "explorateur de fichiers"),
    ("powershell", "windows powershell", "power shell"),
    ("command prompt", "cmd", "cmd prompt"),
    ("windows terminal", "terminal", "wt"),
    ("task manager", "taskmgr", "administrador de tareas"),
    ("control panel", "panel de control"),
    ("settings", "windows settings", "system settings", "ajustes", "configuración", "सेटिंग्स", "సెట్టింగ్స్"),
    ("device manager", "administrador de dispositivos"),
    ("registry editor", "regedit"),
    ("spotify", "spotify music"),
    ("whatsapp", "whatsapp desktop", "whatsapp application", "वाट्सऐप", "व्हाट्सएप", "వాట్సాప్"),
    ("chatgpt", "chat gpt", "चैटजीपीटी"),
    ("youtube", "you tube", "यूट्यूब", "యూట్యూబ్"),
    ("google", "गूगल", "గూగుల్"),
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
_SYSTEM_URIS = {"settings": "ms-settings:"}
_GENERIC_WORDS = {"browser", "application", "app", "desktop", "installed", "desktop app"}
_ACTION_MESSAGES = {
    "en": {
        "default_browser": "Opening your default browser.",
        "default_browser_fail": "I couldn't open your default browser. Check the Windows default-browser setting.",
        "opening_app": "Opening installed application: {name}.",
        "launch_fail": "I found {name}, but Windows could not launch it. Check its shortcut or installation.",
        "website_fallback": "I couldn't find the installed desktop app '{target}'. Opening {label} in your browser instead.",
        "website_fail": "I couldn't find the installed desktop app '{target}', and the website fallback could not be opened.",
        "not_found": "'{target}' was not found in Windows' app inventory or registered paths. No command was executed.",
        "unsafe": "For safety, tell me the application name (for example, 'open Command Prompt'). I won't launch a direct executable path or shell script from speech.",
        "invalid_url": "That website URL is invalid or could not be opened.",
        "opening_url": "Opening the requested website.",
        "video_search": "Searching YouTube for '{query}'.",
        "video_fail": "I couldn't open YouTube search. Check your browser and internet connection.",
        "web_search": "Searching the web for '{query}'.",
        "web_search_fail": "I couldn't open web search. Check your browser and internet connection.",
        "empty_target": "Please name the application, website, or video you want to open.",
    },
    "es": {
        "default_browser": "Abriendo tu navegador predeterminado.",
        "default_browser_fail": "No pude abrir tu navegador predeterminado. Revisa la configuración de Windows.",
        "opening_app": "Abriendo la aplicación instalada: {name}.",
        "launch_fail": "Encontré {name}, pero Windows no pudo iniciarla. Revisa su acceso directo o instalación.",
        "website_fallback": "No encontré la aplicación de escritorio '{target}'. Abriré {label} en el navegador.",
        "website_fail": "No encontré la aplicación '{target}' y tampoco pude abrir su sitio web.",
        "not_found": "No encontré '{target}' entre las aplicaciones instaladas ni sus rutas registradas. No ejecuté ningún comando.",
        "unsafe": "Por seguridad, di el nombre de la aplicación. No ejecutaré rutas ejecutables ni scripts de shell dictados por voz.",
        "invalid_url": "La dirección del sitio no es válida o no se pudo abrir.",
        "opening_url": "Abriendo el sitio web solicitado.",
        "video_search": "Buscando '{query}' en YouTube.",
        "video_fail": "No pude abrir la búsqueda de YouTube. Revisa tu navegador y conexión.",
        "web_search": "Buscando '{query}' en la web.",
        "web_search_fail": "No pude abrir la búsqueda web. Revisa tu navegador y conexión.",
        "empty_target": "Di el nombre de la aplicación, sitio web o vídeo que quieres abrir.",
    },
    "te": {
        "default_browser": "మీ డిఫాల్ట్ బ్రౌజర్‌ను తెరుస్తున్నాను.",
        "default_browser_fail": "మీ డిఫాల్ట్ బ్రౌజర్‌ను తెరవలేకపోయాను. Windows సెట్టింగ్‌లను తనిఖీ చేయండి.",
        "opening_app": "ఇన్‌స్టాల్ చేసిన యాప్‌ను తెరుస్తున్నాను: {name}.",
        "launch_fail": "{name} కనుగొన్నాను, కానీ Windows దాన్ని తెరవలేకపోయింది. షార్ట్‌కట్ లేదా ఇన్‌స్టాలేషన్‌ను తనిఖీ చేయండి.",
        "website_fallback": "'{target}' డెస్క్‌టాప్ యాప్ దొరకలేదు. దానికి బదులుగా బ్రౌజర్‌లో {label} తెరుస్తున్నాను.",
        "website_fail": "'{target}' యాప్ దొరకలేదు; దాని వెబ్‌సైట్‌ను కూడా తెరవలేకపోయాను.",
        "not_found": "'{target}' ఇన్‌స్టాల్ చేసిన యాప్‌లలో లేదా రిజిస్టర్ చేసిన మార్గాల్లో కనబడలేదు. ఎలాంటి కమాండ్ అమలు చేయలేదు.",
        "unsafe": "భద్రత కోసం యాప్ పేరును చెప్పండి. వాయిస్ ద్వారా ఇచ్చిన executable మార్గాలు లేదా shell స్క్రిప్ట్‌లను నేరుగా అమలు చేయను.",
        "invalid_url": "ఈ వెబ్ చిరునామా చెల్లదు లేదా తెరవలేకపోయాను.",
        "opening_url": "మీరు కోరిన వెబ్‌సైట్‌ను తెరుస్తున్నాను.",
        "video_search": "YouTubeలో '{query}' కోసం వెతుకుతున్నాను.",
        "video_fail": "YouTube శోధనను తెరవలేకపోయాను. బ్రౌజర్ మరియు ఇంటర్నెట్‌ను తనిఖీ చేయండి.",
        "web_search": "వెబ్‌లో '{query}' కోసం వెతుకుతున్నాను.",
        "web_search_fail": "వెబ్ శోధనను తెరవలేకపోయాను. బ్రౌజర్ మరియు ఇంటర్నెట్‌ను తనిఖీ చేయండి.",
        "empty_target": "మీరు తెరవాలనుకుంటున్న యాప్, వెబ్‌సైట్ లేదా వీడియో పేరు చెప్పండి.",
    },
    "hi": {
        "default_browser": "आपका डिफ़ॉल्ट ब्राउज़र खोल रहा हूँ।",
        "default_browser_fail": "डिफ़ॉल्ट ब्राउज़र नहीं खुल सका। Windows सेटिंग जाँचें।",
        "opening_app": "इंस्टॉल किया गया ऐप खोल रहा हूँ: {name}।",
        "launch_fail": "{name} मिला, लेकिन Windows उसे खोल नहीं सका। शॉर्टकट या इंस्टॉलेशन जाँचें।",
        "website_fallback": "'{target}' डेस्कटॉप ऐप नहीं मिला। इसके बजाय ब्राउज़र में {label} खोल रहा हूँ।",
        "website_fail": "'{target}' ऐप नहीं मिला और उसकी वेबसाइट भी नहीं खुल सकी।",
        "not_found": "'{target}' इंस्टॉल किए गए ऐप्स या पंजीकृत पथों में नहीं मिला। कोई कमांड नहीं चलाई गई।",
        "unsafe": "सुरक्षा के लिए ऐप का नाम बताएं। मैं आवाज़ से दिए गए executable paths या shell scripts नहीं चलाऊँगा।",
        "invalid_url": "वेबसाइट का पता अमान्य है या खुल नहीं सका।",
        "opening_url": "अनुरोधित वेबसाइट खोल रहा हूँ।",
        "video_search": "YouTube पर '{query}' खोज रहा हूँ।",
        "video_fail": "YouTube खोज नहीं खुल सकी। ब्राउज़र और इंटरनेट जाँचें।",
        "web_search": "वेब पर '{query}' खोज रहा हूँ।",
        "web_search_fail": "वेब खोज नहीं खुल सकी। ब्राउज़र और इंटरनेट जाँचें।",
        "empty_target": "बताएँ कि कौन-सा ऐप, वेबसाइट या वीडियो खोलना है।",
    },
    "fr": {
        "default_browser": "J’ouvre votre navigateur par défaut.",
        "opening_app": "Ouverture de l’application installée : {name}.",
        "website_fallback": "L’application '{target}' est introuvable. J’ouvre {label} dans le navigateur.",
        "video_search": "Recherche de '{query}' sur YouTube.",
        "web_search": "Recherche de '{query}' sur le Web.",
    },
}


def _response_language(text: str, language: str | None = None) -> str:
    if language:
        code = language.casefold().split("-")[0]
        if code in _ACTION_MESSAGES:
            return code
    if re.search(r"[\u0c00-\u0c7f]", text):
        return "te"
    if re.search(r"[\u0900-\u097f]", text):
        return "hi"
    lowered = text.casefold()
    if re.search(r"\b(abre|abrir|inicia|iniciar|lanza|reproduce|cambia|idioma|español)\b|[áéíóúñ¿¡]", lowered):
        return "es"
    if re.search(r"\b(ouvre|ouvrir|lance|langue)\b|[àâçèéêëîïôûùüÿœ]", lowered):
        return "fr"
    return "en"


def _message(key: str, language: str, **values: str) -> str:
    template = _ACTION_MESSAGES.get(language, {}).get(key) or _ACTION_MESSAGES["en"].get(key, key)
    return template.format(**values)


_LOCALIZED_TARGETS = {
    "el navegador": "browser", "navegador": "browser", "web browser": "browser",
    "explorador": "file explorer", "explorador de archivos": "file explorer",
    "abre whatsapp": "whatsapp", "whatsapp app": "whatsapp",
    "వాట్సాప్": "whatsapp", "వాట్సాప్ అప్లికేషన్": "whatsapp",
    "నోట్‌ప్యాడ్": "notepad", "నోట్ ప్యాడ్": "notepad",
    "యూట్యూబ్": "youtube", "గూగుల్": "google", "సెట్టింగ్స్": "settings",
    "व्हाट्सएप": "whatsapp", "वाट्सऐप": "whatsapp", "नोटपैड": "notepad",
    "यूट्यूब": "youtube", "गूगल": "google", "सेटिंग्स": "settings",
    "bloc de notas": "notepad", "calculadora": "calculator",
}


def _plain(value: str) -> str:
    """Normalize a phrase while preserving Unicode letters and combining marks."""
    value = value.casefold().strip()
    value = unicodedata.normalize("NFKC", value)
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
    # Keep English names as ASCII for registry/executable comparisons.
    words = re.findall(r"[a-z0-9]+", value.replace("&", " and "))
    while words and words[-1] in _GENERIC_WORDS:
        words.pop()
    return " ".join(words)


def _canonical_target(target: str) -> str:
    # Preserve explicit URLs exactly so URL validation can handle them later.
    if target.strip().lower().startswith(("http://", "https://")):
        return target.strip()
    plain = _plain(target)
    return _LOCALIZED_TARGETS.get(plain, plain)


def _candidate_names(target: str) -> set[str]:
    normalized = _key(_canonical_target(target))
    names = {normalized} if normalized else set()
    for group in _ALIAS_GROUPS:
        group_keys = {_key(item) for item in group}
        if normalized in group_keys:
            names.update(group_keys)
            break
    # Target names in non-Latin scripts are mapped via _LOCALIZED_TARGETS first.
    return {name for name in names if name}


def parse_open_request(text: str) -> str | None:
    """Extract an explicit open request in supported command languages."""
    raw = (text or "").strip()
    for pattern in _OPEN_PATTERNS:
        match = pattern.match(raw)
        if match:
            target = match.group(1).strip().strip(" \t\r\n.,!?;:")
            target = re.sub(r"^(?:the|my|el|la|los|las|le|les|mi|mon|ma)\s+", "", target, flags=re.IGNORECASE).strip()
            return _LOCALIZED_TARGETS.get(_plain(target), target) or None
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
            query = re.sub(r"^(?:of|about|for|de|sobre)\s+", "", query, flags=re.IGNORECASE)
            if query:
                return query
    return None


@dataclass(frozen=True)
class InstalledApp:
    name: str
    kind: str  # shortcut, appid, executable, system_uri
    target: str


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
    """Read per-user and all-users Start Menu shortcuts once per run."""
    found: list[Path] = []
    extensions = {".lnk", ".appref-ms"}
    for root in _start_menu_roots():
        try:
            for path in root.rglob("*"):
                try:
                    if path.is_file() and path.suffix.casefold() in extensions:
                        found.append(path)
                except OSError:
                    continue
        except OSError:
            continue
    return tuple(found)


def _find_start_menu_shortcut(target: str) -> Path | None:
    wanted = _candidate_names(target)
    shortcuts = _start_menu_shortcuts()
    # Exact name match comes first.
    for path in shortcuts:
        if _key(path.stem) in wanted:
            return path
    # Versioned Visual Studio shortcuts are common; don't match its installer.
    if _key(target) == "visual studio":
        for path in shortcuts:
            name = _key(path.stem)
            if name.startswith("visual studio ") and "installer" not in name and re.search(r"\b20\d{2}\b", name):
                return path
    return None


@lru_cache(maxsize=1)
def _windows_start_apps() -> tuple[tuple[str, str], ...]:
    """Discover packaged apps via the fixed, read-only Get-StartApps query."""
    if sys.platform != "win32":
        return ()
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return ()
    # The script is a fixed constant; no user/voice text is interpolated into it.
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
        result: list[tuple[str, str]] = []
        for item in data if isinstance(data, list) else []:
            name, app_id = item.get("Name"), item.get("AppID")
            if isinstance(name, str) and isinstance(app_id, str) and name.strip() and app_id.strip():
                result.append((name.strip(), app_id.strip()))
        return tuple(result)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        logger.debug("Could not enumerate Windows Start Apps.", exc_info=True)
        return ()


def _find_start_app_id(target: str) -> tuple[str, str] | None:
    wanted = _candidate_names(target)
    items = _windows_start_apps()
    for name, app_id in items:
        if _key(name) in wanted:
            return name, app_id
    if _key(target) == "visual studio":
        for name, app_id in items:
            normalized = _key(name)
            if normalized.startswith("visual studio ") and "installer" not in normalized and re.search(r"\b20\d{2}\b", normalized):
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
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
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


def _display_icon_executable(raw_value: object) -> Path | None:
    """Extract only a real executable path from a registered DisplayIcon value."""
    raw = os.path.expandvars(str(raw_value or "").strip())
    if not raw:
        return None
    if raw.startswith('"'):
        match = re.match(r'^"([^"\r\n]+\.exe)"', raw, re.IGNORECASE)
        candidate = match.group(1) if match else ""
    else:
        match = re.match(r'^(.*?\.exe)(?:,\s*-?\d+)?$', raw, re.IGNORECASE)
        candidate = match.group(1).strip() if match else raw
    if not candidate:
        return None
    path = Path(candidate)
    if not path.is_file() or path.suffix.casefold() != ".exe":
        return None
    stem = _key(path.stem)
    if any(word in stem for word in ("installer", "uninstall", "setup", "updater", "crashpad")):
        return None
    return path


def _registry_installed_programs() -> tuple[tuple[str, Path], ...]:
    """Read installed-program display names and launchable DisplayIcon executables."""
    if sys.platform != "win32":
        return ()
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows only
        return ()

    locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
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
                            try:
                                display_icon, _ = winreg.QueryValueEx(child, "DisplayIcon")
                            except OSError:
                                continue
                        if not isinstance(display_name, str) or not display_name.strip():
                            continue
                        path = _display_icon_executable(display_icon)
                        if path is not None:
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
    publisher_prefixes = ("microsoft ", "google ", "mozilla ", "spotify ", "adobe ")
    for display_name, executable in _registered_installed_programs():
        display_key = _key(display_name)
        normalized_names = {display_key}
        for prefix in publisher_prefixes:
            if display_key.startswith(prefix):
                normalized_names.add(display_key[len(prefix):])
        if normalized_names.intersection(wanted):
            return display_name, executable
    return None


def _common_executable_paths(target: str) -> tuple[Path, ...]:
    wanted = _candidate_names(target)
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    paths: list[Path] = []
    group_paths: dict[str, tuple[Path, ...]] = {
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
        "firefox": (Path(pf) / "Mozilla Firefox/firefox.exe", Path(pf86) / "Mozilla Firefox/firefox.exe"),
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
    for canonical, candidates in group_paths.items():
        if wanted.intersection(_candidate_names(canonical)):
            paths.extend(candidates)
    return tuple(path for path in paths if path.is_file())


def _find_visual_studio() -> Path | None:
    """Use Microsoft's installed vswhere utility to find devenv.exe."""
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
        devenv = Path(install) / "Common7" / "IDE" / "devenv.exe" if proc.returncode == 0 and install else None
        return devenv if devenv and devenv.is_file() else None
    except (OSError, subprocess.SubprocessError):
        return None


def _find_executable(target: str) -> Path | None:
    wanted = _candidate_names(target)
    for group in _ALIAS_GROUPS:
        group_keys = {_key(item) for item in group}
        if wanted.intersection(group_keys):
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
    if canonical in {"visual studio", "visual studio 2022", "visual studio community", "visual studio community 2022", "visual studio professional 2022", "visual studio enterprise 2022", "devenv"}:
        found_vs = _find_visual_studio()
        if found_vs:
            return found_vs
    for path in _common_executable_paths(target):
        return path
    app_paths = _registered_app_paths()
    for candidate in wanted:
        if candidate in app_paths:
            return app_paths[candidate]
    # Do not pass a command line through a shell; allow only exact executable names.
    if re.fullmatch(r"[A-Za-z0-9_. -]{1,80}", target):
        found = shutil.which(target)
        if found:
            path = Path(found)
            if path.is_file() and path.suffix.casefold() in {".exe", ".com"}:
                return path
    return None


def _launch_app(app: InstalledApp) -> bool:
    if app.kind == "system_uri":
        if sys.platform != "win32":
            return False
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            return False
        startfile(app.target)
        return True
    if app.kind == "shortcut":
        if sys.platform != "win32":
            return False
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            return False
        startfile(app.target)
        return True
    if app.kind == "appid":
        if sys.platform != "win32":
            return False
        explorer = shutil.which("explorer.exe") or str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe")
        if not Path(explorer).is_file():
            return False
        # App ID was read from Windows' own Start Apps inventory, not voice text.
        subprocess.Popen([explorer, f"shell:AppsFolder\\{app.target}"], shell=False)
        return True
    if app.kind == "executable":
        path = Path(app.target)
        if path.suffix.casefold() not in {".exe", ".com", ".msc"} or not path.is_file():
            return False
        if path.suffix.casefold() == ".msc":
            # Launch MMC snap-ins through their registered file association.
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                return False
            startfile(str(path))
            return True
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if sys.platform == "win32" else 0
        subprocess.Popen([str(path)], shell=False, creationflags=flags)
        return True
    return False


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
        display_name, executable_path = registered
        return InstalledApp(display_name, "executable", str(executable_path))
    return None


def _open_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    try:
        return bool(webbrowser.open_new_tab(url))
    except Exception:
        logger.warning("Browser open failed.", exc_info=True)
        return False


def _website_fallback(target: str) -> tuple[str, str] | None:
    key = _key(_canonical_target(target))
    if key in _WEBSITES:
        return _WEBSITES[key]
    wanted = _candidate_names(target)
    for alias, data in _WEBSITES.items():
        if _key(alias) in wanted:
            return data
    cleaned = target.strip()
    if cleaned.lower().startswith(("http://", "https://")):
        parsed = urlparse(cleaned)
        if parsed.hostname and not parsed.username and not parsed.password:
            return cleaned, cleaned
    if re.fullmatch(r"(?i)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9]){0,62})+(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?", cleaned):
        return cleaned, "https://" + cleaned
    return None


def _default_browser_request(target: str) -> bool:
    return _plain(target) in {"browser", "default browser", "internet browser", "web browser", "navegador", "el navegador"}


def _search_youtube(query: str) -> bool:
    if not query.strip():
        return False
    return _open_url("https://www.youtube.com/results?search_query=" + quote_plus(query.strip()))


def _search_web(query: str) -> bool:
    if not query.strip():
        return False
    return _open_url("https://www.google.com/search?q=" + quote_plus(query.strip()))


def try_handle_desktop_command(text: str, language: str | None = None) -> str | None:
    """Handle explicit app/browser/content commands, or return None for AI chat."""
    raw = (text or "").strip()
    if not raw:
        return None
    response_language = _response_language(raw, language)

    video_query = parse_video_search(raw)
    if video_query is not None:
        if _search_youtube(video_query):
            return _message("video_search", response_language, query=video_query)
        return _message("video_fail", response_language)

    # "Search the web for ..." intentionally opens a direct results page.
    search_match = re.match(r"^\s*(?:aurix[, ]+)?(?:search|look)\s+(?:the\s+)?(?:web|internet|google)\s+for\s+(.+?)\s*[.!?]*\s*$", raw, re.I)
    if search_match:
        query = search_match.group(1).strip()
        if _search_web(query):
            return _message("web_search", response_language, query=query)
        return _message("web_search_fail", response_language)

    target = parse_open_request(raw)
    if target is None:
        return None

    target = _canonical_target(target)
    key = _key(target)
    # Allow explicit HTTP(S) links only after strict URL validation; they are not
    # executable paths and are never sent to a shell.
    if target.lower().startswith(("http://", "https://")):
        if _open_url(target):
            return _message("opening_url", response_language)
        return _message("invalid_url", response_language)
    # A spoken request should name an application, not inject a path or direct
    # executable/script. Common Windows tools remain available by friendly name.
    if ("\\" in target or "/" in target or re.search(r"(?i)\.(?:exe|com|cmd|bat|ps1|msi|dll)$", target.strip())):
        return _message("unsafe", response_language)
    if not key and not _plain(target):
        return _message("empty_target", response_language)

    try:
        if _default_browser_request(target):
            try:
                if webbrowser.open_new_tab("about:blank"):
                    return _message("default_browser", response_language)
            except Exception:
                pass
            if _open_url("https://www.google.com/"):
                return _message("default_browser", response_language)
            return _message("default_browser_fail", response_language)

        app = _find_installed_app(target)
        if app is not None:
            if _launch_app(app):
                return _message("opening_app", response_language, name=app.name)
            return _message("launch_fail", response_language, name=app.name)

        fallback = _website_fallback(target)
        if fallback is not None:
            label, url = fallback
            if _open_url(url):
                return _message("website_fallback", response_language, target=target, label=label)
            return _message("website_fail", response_language, target=target)

        return _message("not_found", response_language, target=target)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Could not launch target %r: %s", target, exc)
        return f"I couldn't open '{target}': {exc}"
    except Exception:
        logger.exception("Unexpected desktop-launch error for %r", target)
        return f"I hit an error while opening '{target}'. Check the application installation and terminal log."


# Compatibility with existing code and tests that use the previous function name.
handle_desktop_command = try_handle_desktop_command
