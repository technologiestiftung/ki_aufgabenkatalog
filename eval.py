"""Misst die Trefferquote des Zuständigkeitsfinders gegen testfragen.json.

Diese Zahl ist die Messlatte: Jede Änderung am Prompt, am Filter oder am Modell
wird daran gemessen. Aufruf:  ./.venv/bin/python eval.py
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import llm

BEWERTUNGEN = {
    "top1": "richtig",
    "in_auswahl": "in Auswahl",
    "verfehlt": "verfehlt",
    "modus_richtig": "richtig",
    "modus_falsch": "verfehlt",
    "fehler": "Fehler",
}


def bewerte(frage, antwort, details):
    if antwort is None:
        return "fehler"

    modus = antwort.get("modus")
    if frage["erwartete_stelle"] is None:
        return "modus_richtig" if modus == frage["erwarteter_modus"] else "modus_falsch"

    erwartet = frage["erwartete_stelle"].lower()
    passt = [
        erwartet in details.get(t.get("nummer"), {}).get("Zuständigkeiten", "").lower()
        for t in (antwort.get("treffer") or [])
    ]
    if not any(passt):
        return "verfehlt"
    return "top1" if passt[0] else "in_auswahl"


def pruefe(frage, details):
    try:
        antwort = llm.frage(frage["frage"])
    except Exception as fehler:
        return {**frage, "bewertung": "fehler", "fehlermeldung": str(fehler), "antwort": None}
    return {**frage, "bewertung": bewerte(frage, antwort, details), "antwort": antwort}


def main():
    fragen = json.loads(Path("testfragen.json").read_text(encoding="utf-8"))["fragen"]
    details = json.loads(Path("katalog.index.json").read_text(encoding="utf-8"))

    print(f"Katalog: {llm.UMFANG} / {llm.PROFIL} — {len(fragen)} Fragen\n")
    with ThreadPoolExecutor(max_workers=4) as pool:
        ergebnisse = list(pool.map(lambda f: pruefe(f, details), fragen))

    for e in ergebnisse:
        genannt = ", ".join(t.get("stelle", "?") for t in (e["antwort"] or {}).get("treffer") or [])
        print(f"  {BEWERTUNGEN[e['bewertung']]:11} {e['frage'][:62]:62}")
        print(f"  {'':11} erwartet: {e['erwartete_stelle'] or e['erwarteter_modus']}")
        print(f"  {'':11} genannt:  {genannt or (e['antwort'] or {}).get('modus') or e.get('fehlermeldung', '')}")

    # Regel 2 verbietet "Wohnbezirk": bei ortsgebundenen Anliegen zählt der Ort
    # der Sache, nicht die Wohnung. Verstöße hier sichtbar machen.
    wohnbezirk = [e for e in ergebnisse
                  if "wohnbezirk" in json.dumps(e["antwort"] or {}, ensure_ascii=False).lower()]
    if wohnbezirk:
        print(f"\n  ACHTUNG: {len(wohnbezirk)} Antwort(en) sagen \"Wohnbezirk\" (Regel 2 verletzt):")
        for e in wohnbezirk:
            print(f"    - {e['frage'][:70]}")

    gezaehlt = {b: sum(1 for e in ergebnisse if e["bewertung"] == b) for b in BEWERTUNGEN}
    richtig = gezaehlt["top1"] + gezaehlt["modus_richtig"]
    brauchbar = richtig + gezaehlt["in_auswahl"]
    n = len(ergebnisse)

    print(f"\n  richtig an erster Stelle : {richtig:3}/{n}  ({richtig / n:.0%})")
    print(f"  richtig oder in Auswahl  : {brauchbar:3}/{n}  ({brauchbar / n:.0%})")
    print(f"  verfehlt                 : {gezaehlt['verfehlt'] + gezaehlt['modus_falsch']:3}/{n}")
    if gezaehlt["fehler"]:
        print(f"  technische Fehler        : {gezaehlt['fehler']:3}/{n}")

    Path("eval_ergebnis.json").write_text(
        json.dumps(ergebnisse, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n  Vollständige Antworten in eval_ergebnis.json")


if __name__ == "__main__":
    main()
