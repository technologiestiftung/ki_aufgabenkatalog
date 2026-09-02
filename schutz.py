"""Antwortcache für den Suchendpunkt.

Gleiche Frage, gespeicherte Antwort, kein Modellaufruf. In einem Bürgerportal
fragen sehr viele Menschen dasselbe; das spart mehr als jede Token-Optimierung,
weil die Anfrage gar nicht erst hinausgeht.

Der Cache liegt im Arbeitsspeicher der Instanz. Auf Vercel hält Fluid Compute
Instanzen zwischen Aufrufen warm, er greift dort also - aber nur innerhalb einer
warmen Instanz und nicht über einen Kaltstart hinweg. Er ist eine Ersparnis,
keine Garantie. Kostenobergrenzen gehören in die Google-Konsole.
"""

import hashlib
import os
import re
import time
from collections import OrderedDict


def _zahl(name, standard):
    try:
        return int(os.getenv(name, standard))
    except ValueError:
        return int(standard)


class Antwortcache:
    def __init__(self, kennung, ttl_stunden=None, groesse=None):
        # Ändert sich Regelwerk oder Katalog, ändert sich die Kennung und alle
        # alten Antworten verfallen automatisch.
        self.kennung = kennung
        self.ttl = (ttl_stunden if ttl_stunden is not None else _zahl("CACHE_TTL_STUNDEN", 168)) * 3600
        self.groesse = groesse if groesse is not None else _zahl("CACHE_MAX", 2000)
        self.eintraege = OrderedDict()
        self.treffer = 0
        self.verfehlt = 0

    def schluessel(self, frage):
        """Schreibweise, Satzzeichen und Leerraum sollen keine Rolle spielen."""
        norm = re.sub(r"[^\w\s]", " ", frage.lower())
        norm = re.sub(r"\s+", " ", norm).strip()
        return hashlib.sha256(f"{self.kennung}|{norm}".encode()).hexdigest()

    def hole(self, frage):
        k = self.schluessel(frage)
        eintrag = self.eintraege.get(k)
        if eintrag and time.time() - eintrag[0] < self.ttl:
            self.eintraege.move_to_end(k)
            self.treffer += 1
            return eintrag[1]
        if eintrag:
            del self.eintraege[k]
        self.verfehlt += 1
        return None

    def lege_ab(self, frage, antwort):
        k = self.schluessel(frage)
        self.eintraege[k] = (time.time(), antwort)
        self.eintraege.move_to_end(k)
        while len(self.eintraege) > self.groesse:
            self.eintraege.popitem(last=False)
