"""Webdienst für den Zuständigkeitsfinder.

Entrypoint für Vercel: Die Datei heißt app.py und stellt eine FastAPI-Instanz
namens `app` bereit - genau die Konvention, die Vercel ohne Konfiguration erkennt.
"""

import json
import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import llm
import schutz

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
protokoll = logging.getLogger("zustaendigkeitsfinder")

DETAILS = json.loads(Path("katalog.index.json").read_text(encoding="utf-8"))
FRAGE_MAXLAENGE = 500

# Der erste Aufruf trifft Geminis Cache naturgemäß nie, und nach längerer Pause
# läuft er ab. Erst mehrere magere Aufrufe hintereinander sind ein echtes Zeichen
# dafür, dass der gemeinsame Präfix zerstört wurde.
MAGERE_AUFRUFE_BIS_WARNUNG = 3
magere_aufrufe = 0

app = FastAPI(title="Zuständigkeitsfinder Berlin")

# Designsystem für Bürgerservices des Landes Berlin. Vercel hebt eingebundene
# Verzeichnisse beim Bauen aufs CDN, solange keine Top-Level-Middleware im Weg ist.
app.mount("/static", StaticFiles(directory="static"), name="static")

cache = schutz.Antwortcache(kennung=llm.kennung())


class Anfrage(BaseModel):
    frage: str


@app.get("/")
def startseite():
    return FileResponse("index.html")


@app.get("/api/status")
def status():
    """Kurzer Betriebsblick: Ausbeute des Antwortcaches."""
    gesamt = cache.treffer + cache.verfehlt
    return {
        "antwortcache": {
            "treffer": cache.treffer,
            "verfehlt": cache.verfehlt,
            "quote": round(cache.treffer / gesamt, 3) if gesamt else None,
            "eintraege": len(cache.eintraege),
        },
        "katalog": {"umfang": llm.UMFANG, "profil": llm.PROFIL},
    }


@app.post("/api/suche")
def suche(anfrage: Anfrage):
    text = anfrage.frage.strip()
    if not text:
        raise HTTPException(400, "Bitte geben Sie eine Frage ein.")
    if len(text) > FRAGE_MAXLAENGE:
        raise HTTPException(400, f"Bitte fassen Sie sich kürzer (höchstens {FRAGE_MAXLAENGE} Zeichen).")

    gespeichert = cache.hole(text)
    if gespeichert is not None:
        protokoll.info("cache-treffer  %r", text[:60])
        return gespeichert

    beginn = time.time()
    try:
        ergebnis, nutzung = llm.frage_mit_nutzung(text)
    except llm.Konfigurationsfehler as fehler:
        raise HTTPException(503, str(fehler))
    except Exception as fehler:
        raise HTTPException(502, f"Das Sprachmodell hat nicht geantwortet: {fehler}")

    anteil = nutzung["gecacht"] / nutzung["eingabe"] if nutzung["eingabe"] else 0
    protokoll.info("modellaufruf   %.1fs  eingabe=%d  davon gecacht=%d (%.0f%%)  ausgabe=%d",
                   time.time() - beginn, nutzung["eingabe"], nutzung["gecacht"],
                   anteil * 100, nutzung["ausgabe"])

    global magere_aufrufe
    magere_aufrufe = magere_aufrufe + 1 if (nutzung["eingabe"] > 50_000 and anteil < 0.5) else 0
    if magere_aufrufe >= MAGERE_AUFRUFE_BIS_WARNUNG:
        protokoll.warning("%d Aufrufe in Folge mit geringer Cache-Ausbeute. Wurde der Systemprompt "
                          "je Anfrage verändert? Das treibt die Kosten.", magere_aufrufe)

    # Vollständige Katalogdaten nachschlagen, damit die Oberfläche den Beleg zeigen kann.
    for treffer in ergebnis.get("treffer") or []:
        treffer["details"] = DETAILS.get(treffer.get("nummer"))

    cache.lege_ab(text, ergebnis)
    return ergebnis
