# Zuständigkeitsfinder Berlin

Bürgerinnen und Bürger beschreiben ihr Anliegen in Alltagssprache — der Dienst
nennt die zuständige Stelle der Berliner Verwaltung. Grundlage ist der
Aufgabenkatalog des Landes Berlin (2.429 Aufgaben, 135 Stellen).

Das Kernproblem ist die Sprachlücke: Wer nach *Ampel* sucht, findet im Katalog
nichts — dort heißt es *Lichtsignalanlage*. Eine Volltextsuche nach „Ampel"
liefert null Treffer. Gelöst wird das nicht durch Suchtechnik, sondern dadurch,
dass ein Sprachmodell den gesamten bürgerrelevanten Katalog gleichzeitig sieht
und die Übersetzung selbst leistet.

## Einrichten

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env          # Modell, Endpunkt und Schlüssel eintragen
./.venv/bin/python build_katalog.py
./.venv/bin/python -m uvicorn app:app --reload
```

Danach http://localhost:8000 im Browser öffnen.

## Trefferquote messen

```bash
./.venv/bin/python eval.py
```

Läuft 33 Bürgerfragen durch und gibt die Trefferquote aus. **Diese Zahl ist die
Messlatte** — jede Änderung an Prompt, Filter oder Modell wird daran gemessen.

**Stand 2026-09-02, `gemini-3.7-flash`, Katalog `vollstaendig`/`voll`: 33/33.**

Diese Zahl ist mit Vorsicht zu lesen. Der erste Durchlauf ergab 29/33; bei drei
der vier Abweichungen lag nicht das Modell falsch, sondern meine Erwartung — am
deutlichsten beim Müll auf dem Bürgersteig, wo 1.21.1.4.13 (Ordnungsamt,
öffentliche Straßen) und nicht 1.21.1.4.14 (Straßen- und Grünflächenamt, Grün-
und Erholungsanlagen) einschlägig ist. Die Erwartungen wurden nach Prüfung am
Katalogtext korrigiert und die gespeicherten Antworten neu bewertet.

Damit misst die Zahl: *Das Modell liest den Katalog so, wie ihn jemand liest, der
sich Zeit nimmt.* Sie misst nicht, ob der Finder echte Bürgerfragen richtig
beantwortet — die 33 Fragen stammen von derselben Person, die auch die Erwartungen
gesetzt hat, und die Erwartungen sind fachlich weiterhin ungeprüft.

Antwortzeit rund 16 Sekunden je Anfrage; ein voller Durchlauf schickt ohne Caching
13,7 Mio. Eingabe-Token.

## Aufbau

| Datei | Zweck |
|---|---|
| `build_katalog.py` | CSV → Katalogdateien und Detailindex |
| `prompt.md` | Regelwerk für das Modell — ohne Code änderbar |
| `llm.py` | Anbindung an ein beliebiges OpenAI-kompatibles Modell |
| `app.py` | Webdienst, ein Endpunkt `/api/suche` |
| `index.html` | Oberfläche, kein Build-Schritt |
| `schutz.py` | Antwortcache |
| `static/` | Designsystem Bürgerservices Berlin (CSS, JS, Symbole, Logos) |
| `vercel.json` | Deployment: Build-Befehl und Laufzeitgrenze |
| `eval.py`, `testfragen.json` | Messlatte |

Pro Anfrage genau ein Modellaufruf: Regelwerk + vollständiger Katalog + Frage.
Kein Retrieval, keine Vektordatenbank, kein Index — der Katalog passt komplett
in den Kontext. Das Modell wählt selbst zwischen vier Antwortarten: eindeutiger
`treffer`, `auswahl` mit zwei bis drei Stellen, `rueckfrage` bei Mehrdeutigkeit
und `kein_treffer`.

Das Modell sieht nur, was es zum Finden braucht. Die Oberfläche zeigt mehr: Sie
schlägt über die Laufende Nummer den vollständigen Datensatz nach und blendet
ihn unter „Worauf beruht diese Antwort?" ein — mit Rechtsgrundlage. So kostet
der Beleg keinen einzigen Kontext-Token und jede Antwort bleibt prüfbar.

## Katalogprofile

Der Katalog wird in drei Detailtiefen erzeugt, damit das Modell austauschbar
bleibt. `KATALOG_PROFIL` in der `.env` muss zum Kontextfenster passen:

`KATALOG_UMFANG` bestimmt, wie viele Aufgaben aufgenommen werden,
`KATALOG_PROFIL` die Detailtiefe je Aufgabe. Beides zusammen muss ins
Kontextfenster passen:

| Profil | `vollstaendig` (2.429) | `buerger` (1.618) | Inhalt |
|---|---|---|---|
| `voll` | 415.000 | 276.000 | alle Teilaufgaben |
| `mittel` | 247.000 | 165.000 | Teilaufgaben gekürzt |
| `kompakt` | 158.000 | 107.000 | nur Titel und Stelle |

Gemini 2M und Claude 1M vertragen jede Kombination. Für 200k-Modelle passt
`vollstaendig` + `kompakt`, für 128k-Modelle nur `buerger` + `kompakt`.

## Entscheidungen, die nicht offensichtlich sind

**Es wird nicht gefiltert, sondern markiert.** Alle 2.429 Aufgaben stehen im
Katalog. Ein früherer Filter auf „Zielgruppen enthält Bürger" entfernte 811
Zeilen — darunter das Beratungsnetzwerk gegen Rechtsextremismus, Beiräte,
Beauftragte und 219 Zeilen mit der Zielgruppe „Unternehmen". Der Denkfehler:
`Zielgruppen` beschreibt, mit wem die Verwaltung zu tun hat, nicht, wer fragen
darf. Wer ein Gewerbe anmeldet, ist eine Bürgerin mit einem Unternehmensanliegen.

Stattdessen tragen die 408 Aufgaben ohne jeden Außenbezug die Markierung
`nur verwaltungsintern` — maßgeblich ist `Wirkungsbereich`, nicht `Zielgruppen`.
Das Regelwerk nennt sie nur bei ausdrücklicher Frage nach der inneren
Organisation, nie als Antwort auf ein Alltagsanliegen. Auffindbar bleiben sie.

Wer ein Modell mit kleinem Kontextfenster einsetzen muss, kann mit
`KATALOG_UMFANG=buerger` auf 1.618 Zeilen sparen — und verliert damit genau die
Auffindbarkeit, um die es hier geht.

**`Aufgabenart` ist kein verlässlicher Hinweis darauf, wer etwas tut.** Der
Eintrag zur Ampel-Instandhaltung (1.15.5.1.6) ist als *Leitungsaufgabe*
klassifiziert, obwohl seine Teilaufgaben „Betrieb und Instandhaltung …
Schadensbeseitigung" lauten. Die Markierung steht im Katalog, aber das Regelwerk
behandelt sie ausdrücklich als Hinweis, nicht als Beweis.

**14 Bezirksaufgaben erledigt ein Bezirk für ganz Berlin.** Fundbüro, Heilpraktiker-
Erlaubnis, Schrottfahrzeuge und andere sind regionalisiert. Ein Verweis auf „den
zuständigen Bezirk" wäre dort eine falsche Auskunft, deshalb sind sie im Katalog
eigens markiert.

**„Ihres Wohnbezirks" ist als Formulierung untauglich.** Bei ortsgebundenen
Anliegen zählt der Ort der Sache, nicht die Wohnung: Für Sperrmüll ist der Bezirk
zuständig, in dem der Müll liegt, für eine Gewerbeanmeldung der Bezirk der
Betriebsstätte. Und Berliner Bürgerämter bedienen ohnehin alle Einwohnerinnen und
Einwohner unabhängig vom Bezirk. Das Regelwerk unterscheidet deshalb zwischen
ortsgebundenen und personengebundenen Aufgaben und benennt im ersten Fall den Ort.

**Die Oberfläche nutzt das Designsystem für Bürgerservices des Landes Berlin.**
Unter `static/` liegen CSS und JS des Bundles, die beiden Berlin-Logos und das
CLB-Logo. Die übrigen Symbolgrafiken des Bundles (`.bicon-*`-Masken) wurden
entfernt, weil die Oberfläche sie nicht nutzt; die CSS verweist noch auf sie.
Wer ein weiteres Symbol braucht, holt es aus dem Bundle nach. Nichts wird zur
Laufzeit von berlin.de nachgeladen, es
gibt keine externen Anfragen und keine Webfonts (das Designsystem setzt auf
Arial). Projekteigenes CSS steht als kurzer Block in `index.html` und beschränkt
sich auf das, was das Bundle nicht mitbringt.

Zwei bewusste Abweichungen vom Muster:

- **Der Beleg ist ein natives `<details>`, kein `.js-accordion`.** Das Akkordeon
  des Bundles initialisiert sich einmalig beim Laden über
  `.js-accordion:not(.initialized)` und erfasst nachträglich eingefügte
  Ergebnisse nicht. `<details>` braucht kein JavaScript.
- **Die Antwort steht in der `h2`, das Etikett „Zuständig ist" als Dachzeile
  darüber.** Die `h1` stellt die Frage, die `h2` gibt die Antwort — so trägt der
  Name der Stelle den roten Akzentbalken des Designsystems. Für die Dachzeile
  kennt das Bundle keinen eigenen Baustein; `.antwort__label` übernimmt Größe und
  Farbe seiner `.caption`-Konvention (14px, `#454545`).

Das Bundle wurde am 2026-09-02 von `https://www.berlin.de/i9f/r1/bundle/` geholt.
Ein Verweis im CSS (`~images/bicons/clock.svg`) ist auch auf berlin.de ein 404 —
ein Fehler im Bundle, kein fehlender Download.

## Kosten

Ein Modellaufruf verbraucht rund **428.000 Eingabe-Token**. Zwei Mechanismen
dämpfen das, ein dritter begrenzt es hart.

**Geminis implizites Caching** ist bei 2.5 und neuer automatisch aktiv und
braucht keine Konfiguration — gemessen am 2026-09-02 mit `gemini-3.7-flash`:

| | Eingabe-Token | davon aus dem Cache | Dauer |
|---|---|---|---|
| erster Aufruf | 428.135 | 0 | 20,0 s |
| Folgeaufruf | 428.133 | **425.881 (99 %)** | 7,6 s |

Voraussetzung ist, dass der Systemprompt byteweise identisch bleibt. Wer ihn je
Anfrage verändert — etwa durch ein eingesetztes Datum — zerstört den gemeinsamen
Präfix, und die Kosten vervielfachen sich lautlos. Deshalb protokolliert der
Dienst die Cache-Ausbeute jedes Aufrufs und warnt nach drei mageren in Folge.

**Der Antwortcache** spart den Aufruf ganz: gleiche Frage, gespeicherte Antwort,
in Millisekunden. Schreibweise, Satzzeichen und Leerraum sind egal. Ändert sich
Regelwerk oder Katalog, verfallen alle Einträge automatisch, weil ihr Namensraum
ein Fingerabdruck des Systemprompts ist. Er liegt im Arbeitsspeicher der Instanz
und hilft deshalb innerhalb einer warmen Instanz, nicht über einen Kaltstart
hinweg — eine Ersparnis, keine Garantie.

**Die harte Grenze gehört in die Google-Konsole**, nicht in den Code: Zähler in
einer Serverless-Umgebung beginnen bei jedem Kaltstart wieder bei null und sind
damit wirkungslos. Vor dem Livegang dort ein Tageskontingent für die
Generative-Language-API und eine Budgetwarnung setzen. Zu bedenken: Ein
Kontingent gilt global — ein einzelner Dauerfeuer-Aufrufer verbraucht es für
alle. Das begrenzt die Kosten zuverlässig und macht aus dem Kostenproblem ein
Verfügbarkeitsproblem.

`GET /api/status` zeigt die Ausbeute des Antwortcaches.

## Deployment auf Vercel

Vercel erkennt die Anwendung ohne Zutun: `app.py` im Wurzelverzeichnis mit einer
FastAPI-Instanz namens `app` ist eine unterstützte Entrypoint-Konvention. Die
gesamte Anwendung wird zu einer einzigen Vercel Function.

`vercel.json`:

```json
{
  "buildCommand": "python build_katalog.py",
  "functions": { "app.py": { "maxDuration": 60 } }
}
```

Die Katalogdateien entstehen beim Bauen aus der CSV und liegen deshalb nicht im
Repository — so gibt es keine zwei Wahrheiten. `.python-version` pinnt 3.13.

**Umgebungsvariablen im Vercel-Dashboard setzen** (Settings → Environment
Variables). Anders als bei einer `render.yaml` gibt es keine deklarative
Ablage — `.env.example` ist die Referenz:

```
LLM_API_KEY        (geheim)
LLM_BASE_URL       https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODELL         gemini-3.7-flash
KATALOG_UMFANG     vollstaendig
KATALOG_PROFIL     voll
```

**Statische Dateien.** `app.mount("/static", StaticFiles(...))` wird beim Bauen
aufs CDN gehoben, das Designsystem geht also nicht durch die Function. Das gilt
nur, solange keine Top-Level-Middleware existiert — wer später eine hinzufügt,
holt alle statischen Dateien zurück in die Function.

**Laufzeit.** Hobby erlaubt 300 s; `maxDuration` ist auf 60 s gesetzt, damit eine
hängende Anfrage nicht fünf Minuten Rechenzeit verbrennt. Gemessene Werte: 13–20 s
bei kaltem Gemini-Cache, 3–8 s bei warmem, 9 ms aus dem Antwortcache.

**Kaltstart.** Fluid Compute hält Instanzen zwischen Aufrufen warm. Bei einem
Kaltstart kommen rund 0,8 s für das Laden von Katalog und Detailindex hinzu, und
der Antwortcache beginnt leer.

## Offene Punkte vor einem Livegang

- **Testfragen fachlich prüfen.** Die erwarteten Zuständigkeiten in
  `testfragen.json` sind aus dem Katalog abgeleitet, nicht von Fachleuten
  bestätigt. Ohne diese Prüfung misst die Messlatte nur Vermutungen.
- **Datenschutz klären.** Der Katalog ist unkritisch, die Suchanfragen sind es
  nicht: „Mein Nachbar baut ohne Genehmigung", „Ich brauche Hilfe wegen meiner
  Schwerbehinderung". Vor dem Livegang AV-Vertrag, Region und Logging des
  Modellanbieters klären — bei Unsicherheit compliance@ts.berlin.
- **Kontingent und Budgetwarnung in der Google-Konsole setzen.** Es gibt bewusst
  keine Ratenbegrenzung im Code — in einer Serverless-Umgebung wäre sie
  wirkungslos. Damit ist die Google-Konsole die einzige Kostengrenze, und sie
  ist vor dem Livegang zu setzen, nicht danach.
- **Barrierefreiheit prüfen.** Tastaturbedienung, Kontraste und `aria-live` sind
  angelegt, aber nicht gegen BITV 2.0 getestet. Das Designsystem bringt hier
  einiges mit, ersetzt die Prüfung aber nicht.
- **Landesredaktion einbeziehen.** Die Dokumentation des Designsystems weist
  ausdrücklich darauf hin, dass die Design-Variante (Vertical) nicht frei wählbar
  ist und vor Projektbeginn mit der Landesredaktion von Berlin.de abzustimmen ist.
- **Bundle aktuell halten.** `static/` ist eine eingefrorene Kopie. Wenn Berlin.de
  das Designsystem weiterentwickelt, wandert das nicht automatisch mit.
