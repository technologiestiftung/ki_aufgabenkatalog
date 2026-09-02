"""Anbindung an ein Sprachmodell über die OpenAI-kompatible Chat-API.

Bewusst modellagnostisch: Basis-URL, Modellname und Schlüssel kommen aus der
Umgebung. Damit lässt sich Gemini, OpenAI, Claude oder ein selbst gehostetes
Modell einsetzen, ohne den Code zu ändern.
"""

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

PROFIL = os.getenv("KATALOG_PROFIL", "voll")
UMFANG = os.getenv("KATALOG_UMFANG", "vollstaendig")


class Konfigurationsfehler(RuntimeError):
    pass


def _pflichtwert(name):
    wert = os.getenv(name)
    if not wert:
        raise Konfigurationsfehler(
            f"Die Umgebungsvariable {name} ist nicht gesetzt. Lokal in der Datei .env "
            f"eintragen (Vorlage: .env.example), im Betrieb in der Umgebung des Dienstes."
        )
    return wert


@lru_cache(maxsize=1)
def systemprompt():
    """Regelwerk plus Aufgabenkatalog. Wird einmal gelesen und gehalten."""
    katalog = Path(f"katalog.{PROFIL}.txt")
    if not katalog.exists():
        raise Konfigurationsfehler(
            f"{katalog} fehlt. Bitte zuerst 'python build_katalog.py' ausführen."
        )
    return Path("prompt.md").read_text(encoding="utf-8") + "\n\n" + katalog.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _client():
    return OpenAI(api_key=_pflichtwert("LLM_API_KEY"), base_url=_pflichtwert("LLM_BASE_URL"))


def _json_lesen(text):
    """Antwort in JSON umwandeln, auch wenn das Modell einen Codeblock drumherum setzt."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Letzter Versuch: das äußerste Objekt aus einer längeren Ausgabe schneiden.
        anfang, ende = text.find("{"), text.rfind("}")
        if anfang == -1 or ende <= anfang:
            raise
        return json.loads(text[anfang:ende + 1])


@lru_cache(maxsize=1)
def kennung():
    """Kurzer Fingerabdruck von Regelwerk und Katalog.

    Dient als Namensraum für den Antwortcache: Ändert sich der Prompt oder der
    Katalog, verfallen gespeicherte Antworten automatisch.
    """
    return hashlib.sha256(systemprompt().encode()).hexdigest()[:16]


def frage_mit_nutzung(text):
    """Wie frage(), liefert zusätzlich die Verbrauchsdaten des Aufrufs.

    Die Verbrauchsdaten sind wichtig: Gemini cacht den unveränderten Systemprompt
    implizit und rechnet die zwischengespeicherten Token günstiger ab. Bleibt
    `cached` dauerhaft bei null, hat eine Änderung den gemeinsamen Präfix zerstört
    - das würde sonst nur an der Rechnung auffallen.
    """
    nachrichten = [
        {"role": "system", "content": systemprompt()},
        {"role": "user", "content": text},
    ]
    aufruf = dict(model=_pflichtwert("LLM_MODELL"), messages=nachrichten, temperature=0)

    try:
        antwort = _client().chat.completions.create(**aufruf, response_format={"type": "json_object"})
    except Exception:
        # Nicht jede OpenAI-kompatible API kennt response_format. Dann ohne.
        antwort = _client().chat.completions.create(**aufruf)

    verbrauch = getattr(antwort, "usage", None)
    einzelheiten = getattr(verbrauch, "prompt_tokens_details", None) if verbrauch else None
    nutzung = {
        "eingabe": getattr(verbrauch, "prompt_tokens", 0) or 0,
        "ausgabe": getattr(verbrauch, "completion_tokens", 0) or 0,
        "gecacht": (getattr(einzelheiten, "cached_tokens", 0) or 0) if einzelheiten else 0,
    }
    return _json_lesen(antwort.choices[0].message.content), nutzung


def frage(text):
    """Eine Bürgerfrage an das Modell stellen und die strukturierte Antwort zurückgeben."""
    return frage_mit_nutzung(text)[0]
