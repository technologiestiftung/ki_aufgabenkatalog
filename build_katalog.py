"""Erzeugt aus der Aufgaben-CSV die Katalogdateien für den Zuständigkeitsfinder.

Ausgabe:
  katalog.voll.txt     alle Teilaufgaben, mit Thema   -> Modelle ab ~300k Kontext
  katalog.mittel.txt   gekürzte Teilaufgaben          -> Modelle ab ~200k Kontext
  katalog.kompakt.txt  nur Titel und Stelle           -> Modelle ab ~128k Kontext
  katalog.index.json   vollständige Datensätze je Laufender Nummer (für die Oberfläche)
"""

import csv
import json
import os
import sys
from pathlib import Path

try:
    import tiktoken
except ImportError:  # nur für die Tokenzählung
    tiktoken = None

CSV_DATEI = "260706_DB BE_Beschäftigtenportal.csv"
LEERWERTE = {"keine angabe", "keine", "keine teilaufgabe", "-", ""}

# Je Profil: wie viele Zeichen der Teilaufgaben (None = alle, 0 = keine)
# und ob die Themenzeile mitgeschrieben wird.
PROFILE = {
    "voll": (None, True),
    "mittel": (150, True),
    "kompakt": (0, False),
}

# Kurzformen; wichtig ist, ob eine Stelle eine Aufgabe ausführt oder nur regelt.
AUFGABENART = {
    "Leitungsaufgabe": "Grundsatz/Leitung",
    "Steuerungsaufgabe": "Steuerung",
    "Durchführungsaufgabe": "Durchführung",
}

DETAILSPALTEN = ("Aufgabenbeschreibung", "Teilaufgaben", "Handlungsfeld",
                 "Zuständigkeiten", "Verwaltungsebene", "Rechtsgrundlage")


def leer(wert):
    return (wert or "").strip().lower() in LEERWERTE


def buergerrelevant(zeile):
    """Erkennbarer Außenbezug? Nur für KATALOG_UMFANG=buerger (kleines Kontextfenster)."""
    zielgruppen, wirkungsbereich = zeile["Zielgruppen"], zeile["Wirkungsbereich"]

    if not leer(zielgruppen) and "Bürger" not in zielgruppen:
        return False
    if not leer(wirkungsbereich) and "extern" not in wirkungsbereich:
        return False
    return True


def verwaltungsintern(zeile):
    """Aufgabe ohne Außenbezug.

    Maßgeblich ist Wirkungsbereich, nicht Zielgruppen ("Unternehmen" ist nicht intern).
    Solche Aufgaben werden markiert statt entfernt, damit sie auffindbar bleiben.
    """
    wirkungsbereich = zeile["Wirkungsbereich"].strip().lower()
    return wirkungsbereich.startswith("verwaltungsinter") and "extern" not in wirkungsbereich


def teilaufgaben(zeile):
    if leer(zeile["Teilaufgaben"]):
        return []
    return [z.strip() for z in zeile["Teilaufgaben"].splitlines() if z.strip()]


def merkmale(zeile):
    """Ebene, Aufgabenart und - falls zutreffend - berlinweite Regionalisierung."""
    teile = [zeile["Verwaltungsebene"].strip(),
             AUFGABENART.get(zeile["Aufgabenart"].strip(), zeile["Aufgabenart"].strip())]
    if zeile["Regionalisierte Bezirksaufgaben"].strip().lower() == "ja":
        # Ein Bezirk erledigt diese Aufgabe für ganz Berlin - nicht der Bezirk vor Ort.
        teile.append("berlinweit von diesem einen Bezirk")
    if verwaltungsintern(zeile):
        teile.append("nur verwaltungsintern")
    return " · ".join(t for t in teile if t)


def block(zeile, limit, mit_thema):
    """Ein Katalogeintrag als Text für das Sprachmodell."""
    zeilen = [f"### {zeile['Laufende Nummer']} {zeile['Aufgabenbeschreibung'].strip()}"]

    if mit_thema and not leer(zeile["Handlungsfeld"]):
        zeilen.append(f"Thema: {zeile['Handlungsfeld'].strip()}")

    if limit != 0 and (teile := teilaufgaben(zeile)):
        text = " / ".join(teile)
        if limit and len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0] + " …"
        zeilen.append(f"Umfasst: {text}")

    zeilen.append(f"Stelle: {zeile['Zuständigkeiten'].strip()} [{merkmale(zeile)}]")
    return "\n".join(zeilen)


def main():
    pfad = Path(CSV_DATEI)
    if not pfad.exists():
        sys.exit(f"CSV nicht gefunden: {pfad}")

    with pfad.open(encoding="utf-8-sig", newline="") as f:
        alle = list(csv.DictReader(f, delimiter=";"))

    # Tokenzahl ist nur Information; tiktoken lädt beim ersten Aufruf aus dem Netz und soll den Build nicht kippen.
    try:
        kodierer = tiktoken.get_encoding("o200k_base") if tiktoken else None
    except Exception as fehler:
        print(f"  (Tokenzählung übersprungen: {fehler})")
        kodierer = None

    # Standard: vollständiger Katalog; der Sparumfang ist für kleine Kontextfenster.
    umfang = os.getenv("KATALOG_UMFANG", "vollstaendig")
    eintraege = alle if umfang == "vollstaendig" else [z for z in alle if buergerrelevant(z)]
    intern = sum(1 for z in eintraege if verwaltungsintern(z))
    print(f"{len(alle)} Aufgaben gelesen, Umfang '{umfang}': {len(eintraege)} im Katalog "
          f"({intern} davon als nur verwaltungsintern markiert)")

    for profil, (limit, mit_thema) in PROFILE.items():
        text = "\n\n".join(block(z, limit, mit_thema) for z in eintraege)
        ziel = Path(f"katalog.{profil}.txt")
        ziel.write_text(text, encoding="utf-8")
        menge = f"{len(kodierer.encode(text)):>7} Tokens" if kodierer else "  (nicht gezählt)"
        print(f"  {ziel.name:22} {len(text):>9} Zeichen  {menge}")

    index = {
        z["Laufende Nummer"]: {s: z[s] for s in DETAILSPALTEN if not leer(z[s])}
        for z in eintraege
    }
    Path("katalog.index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  katalog.index.json     {len(index)} Datensätze für die Detailanzeige")


if __name__ == "__main__":
    main()
