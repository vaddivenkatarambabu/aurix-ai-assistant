"""Localized user-facing messages for desktop actions."""

from __future__ import annotations

import re

_ACTION_MESSAGES = {
    "en": {
        "opening_site": "Opening {label} in your default browser.",
        "default_browser": "Opening your default browser.",
        "default_browser_fail": "I couldn't open your default browser. Check the Windows default-browser setting.",
        "opening_app": "Opening installed application: {name}.",
        "launch_fail": "I found {name}, but Windows could not launch it. Check its shortcut or installation.",
        "website_fail": "I couldn't open the website for '{target}'. Check your browser and internet connection.",
        "not_found": "'{target}' was not found in Windows' app inventory or registered paths. No command was executed.",
        "unsafe": "For safety, tell me the application name. I won't launch a direct executable path or shell script from speech.",
        "invalid_url": "That website URL is invalid or could not be opened.",
        "opening_url": "Opening the requested website.",
        "video_search": "Searching YouTube for '{query}'.",
        "video_fail": "I couldn't open YouTube search. Check your browser and internet connection.",
        "web_search": "Searching the web for '{query}'.",
        "web_search_fail": "I couldn't open web search. Check your browser and internet connection.",
        "empty_target": "Please name the application, website, or video you want to open.",
    },
    "es": {
        "opening_site": "Abriendo {label} en tu navegador predeterminado.",
        "default_browser": "Abriendo tu navegador predeterminado.",
        "default_browser_fail": "No pude abrir tu navegador predeterminado. Revisa la configuración de Windows.",
        "opening_app": "Abriendo la aplicación instalada: {name}.",
        "launch_fail": "Encontré {name}, pero Windows no pudo iniciarla. Revisa su acceso directo o instalación.",
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
        "opening_site": "{label} వెబ్‌సైట్‌ను మీ డిఫాల్ట్ బ్రౌజర్‌లో తెరుస్తున్నాను.",
        "default_browser": "మీ డిఫాల్ట్ బ్రౌజర్‌ను తెరుస్తున్నాను.",
        "default_browser_fail": "మీ డిఫాల్ట్ బ్రౌజర్‌ను తెరవలేకపోయాను. Windows సెట్టింగ్‌లను తనిఖీ చేయండి.",
        "opening_app": "ఇన్‌స్టాల్ చేసిన యాప్‌ను తెరుస్తున్నాను: {name}.",
        "launch_fail": "{name} కనుగొన్నాను, కానీ Windows దాన్ని తెరవలేకపోయింది. షార్ట్‌కట్ లేదా ఇన్‌స్టాలేషన్‌ను తనిఖీ చేయండి.",
        "website_fail": "'{target}' యాప్ దొరకలేదు; దాని వెబ్‌సైట్‌ను కూడా తెరవలేకపోయాను.",
        "not_found": "'{target}' ఇన్‌స్టాల్ చేసిన యాప్‌లలో లేదా రిజిస్టర్ చేసిన మార్గాల్లో కనబడలేదు. ఎలాంటి కమాండ్ అమలు చేయలేదు.",
        "unsafe": "భద్రత కోసం యాప్ పేరును చెప్పండి. వాయిస్ ద్వారా ఇచ్చిన executable మార్గాలు లేదా shell స్క్రిప్ట్‌లను నేరుగా అమలు చేయను.",
        "invalid_url": "ఈ వెబ్ చిరునామా చెల్లదు లేదా తెరవలేకపోయాను.",
        "opening_url": "మీరు కోరిన వెబ్‌సైట్‌ను తెరుస్తున్నాను.",
        "video_search": "YouTubeలో '{query}' కోసం వెతుకుతున్నాను.",
        "video_fail": "YouTube శోధనను తెరువలేకపోయాను. బ్రౌజర్ మరియు ఇంటర్నెట్‌ను తనిఖీ చేయండి.",
        "web_search": "వెబ్‌లో '{query}' కోసం వెతుకుతున్నాను.",
        "web_search_fail": "వెబ్ శోధనను తెరువలేకపోయాను. బ్రౌజర్ మరియు ఇంటర్నెట్‌ను తనిఖీ చేయండి.",
        "empty_target": "మీరు తెరవాలనుకుంటున్న యాప్, వెబ్‌సైట్ లేదా వీడియో పేరు చెప్పండి.",
    },
    "hi": {
        "opening_site": "{label} आपके डिफ़ॉल्ट ब्राउज़र में खोल रहा हूँ।",
        "default_browser": "आपका डिफ़ॉल्ट ब्राउज़र खोल रहा हूँ।",
        "default_browser_fail": "डिफ़ॉल्ट ब्राउज़र नहीं खुल सका। Windows सेटिंग जाँचें।",
        "opening_app": "इंस्टॉल किया गया ऐप खोल रहा हूँ: {name}।",
        "launch_fail": "{name} मिला, लेकिन Windows उसे खोल नहीं सका। शॉर्टकट या इंस्टॉलेशन जाँचें।",
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
        "opening_site": "J’ouvre {label} dans votre navigateur par défaut.",
        "default_browser": "J’ouvre votre navigateur par défaut.",
        "opening_app": "Ouverture de l’application installée : {name}.",
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
    if re.search(
        r"\b(abre|abrir|inicia|iniciar|lanza|reproduce|cambia|idioma|español)\b|[áéíóúñ¿¡]", lowered
    ):
        return "es"
    if re.search(r"\b(ouvre|ouvrir|lance|langue)\b|[àâçèéêëîïôûùüÿœ]", lowered):
        return "fr"
    return "en"


def _message(key: str, language: str, **values: str) -> str:
    template = _ACTION_MESSAGES.get(language, {}).get(key) or _ACTION_MESSAGES["en"].get(key, key)
    return template.format(**values)
