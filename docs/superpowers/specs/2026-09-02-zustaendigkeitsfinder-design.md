# Zuständigkeitsfinder Berlin — Entwurf

Stand: 2026-09-02

## Aufgabe

Bürgerinnen und Bürger sollen die für ihr Anliegen zuständige Stelle der Berliner
Verwaltung finden, ohne Verwaltungsbegriffe zu kennen. Datengrundlage ist der
Aufgabenkatalog des Landes Berlin: 2.429 Aufgaben, 135 Zuständigkeiten,
210 Handlungsfelder, als CSV mit 21 Spalten.

Das Kernproblem ist eine Sprachlücke. Eine Volltextsuche nach „Ampel" liefert im
Katalog null Treffer — dort steht „Lichtsignalanlage". Diese Lücke zieht sich
durch den gesamten Bestand.

## Verworfene Ansätze

**Klassisches RAG (Embeddings + Vektorsuche).** Verworfen. Embeddings sind
ausgerechnet beim Kernproblem schwach: „Ampel" und „Lichtsignalanlage" liegen im
Vektorraum nur dann nah beieinander, wenn das Modell diesen deutschen
Verwaltungs-Domänenbezug gelernt hat. Bei kurzen, nominalisierten Titeln ohne
Kontext ist das unzuverlässig. Zudem kann Ähnlichkeitssuche nicht schließen:
„Mein Nachbar baut ohne Genehmigung" → Bauaufsicht ist ein Denkschritt.

**Angereicherter Index.** Ein einmaliger Batch-Lauf erzeugt je Aufgabe
Alltagsbegriffe und typische Bürgerfragen; gesucht wird auf dem angereicherten
Text. Fachlich attraktiv, weil die Synonyme als Tabelle prüf- und korrigierbar
sind. Zurückgestellt: Bei 2 Mio. Kontext löst das Modell die Übersetzung selbst,
weil es beide Sprachseiten gleichzeitig sieht. Bleibt als Nachrüstoption, falls
die Messung Lücken zeigt.

**Retrieval-Vorstufe.** Nicht nötig, solange der Katalog vollständig in den
Kontext passt. Bleibt als Nachrüstoption gegen Latenz und Kosten — dann mit
großzügigem Netz (Top-150 statt Top-5), da bei großem Kontextfenster kein
Präzisionsdruck besteht, sondern nur Recall zählt.

## Gewählter Ansatz

Pro Anfrage genau ein Modellaufruf: Regelwerk + vollständiger bürgerrelevanter
Katalog + Frage. Kein Retrieval, kein Index, keine Datenbank.

Das Modell antwortet in strukturiertem JSON und wählt selbst zwischen vier
Modi: `treffer` (eindeutig), `auswahl` (zwei bis drei Stellen), `rueckfrage`
(mehrdeutig) und `kein_treffer`. Jeder Treffer trägt die Laufende Nummer, über
die die Oberfläche den vollständigen Datensatz nachschlägt und als Beleg
anzeigt. Dadurch kostet der Beleg keinen Kontext-Token und jede Antwort bleibt
auf eine Katalogzeile zurückführbar.

Die Anbindung spricht die OpenAI-kompatible Chat-API. Modell, Endpunkt und
Schlüssel kommen aus der Umgebung — Voraussetzung für die Compliance-Freigabe.

## Datenaufbereitung

Der Katalog wird **nicht gefiltert, sondern markiert**. Alle 2.429 Aufgaben gehen
in den Kontext.

Zwei Filterentwürfe wurden verworfen. Der erste („Zielgruppen enthält Bürger UND
Wirkungsbereich enthält extern") scheiterte an der Datenpflege: Rund 320 Zeilen
haben dort „keine Angabe", darunter Fahrerlaubnis- und Fahrzeugzulassungsrecht.
Der zweite, nachgebesserte Filter behielt 1.618 Zeilen — entfernte aber immer
noch 811, darunter das Beratungsnetzwerk gegen Rechtsextremismus, Beiräte,
Beauftragte und 219 Zeilen mit der Zielgruppe „Unternehmen".

Der Denkfehler beider Entwürfe: `Zielgruppen` beschreibt, mit wem die Verwaltung
bei einer Aufgabe zu tun hat — nicht, wer danach fragen darf. Wer ein Gewerbe
anmeldet, ist eine Bürgerin mit einem Unternehmensanliegen; wer Rat gegen
Rechtsextremismus sucht, fragt nach einer Aufgabe mit Zielgruppe „Verwaltung".

Stattdessen tragen die 408 Aufgaben ohne jeden Außenbezug die Markierung
`nur verwaltungsintern`. Maßgeblich ist `Wirkungsbereich`, nicht `Zielgruppen`.
Regel 2 des Regelwerks nennt sie nur bei ausdrücklicher Frage nach der inneren
Organisation, nie als Antwort auf ein Alltagsanliegen — auffindbar bleiben sie.
Von den 811 zuvor entfernten Zeilen sind 403 gar nicht intern und damit jetzt
vollwertig auffindbar.

Nicht gefiltert wird nach `Aufgabenart`. Ein solcher Filter hätte 542 Zeilen
entfernt, darunter „Ansprechperson für die LSBTIQ+ Communitys" — Einträge, bei
denen ein Bürger richtig landet.

Der Preis ist Kontext: 415.000 statt 276.000 Token im Profil `voll`. Bei einem
Fenster von 2 Mio. ist das bezahlbar. Für Modelle mit kleinem Fenster gibt es
`KATALOG_UMFANG=buerger` als Sparumfang — mit dem ausdrücklichen Hinweis, dass er
genau die Auffindbarkeit kostet, um die es hier geht.

Drei Detailtiefen halten das Modell austauschbar:

| Profil | `vollstaendig` | `buerger` |
|---|---|---|
| `voll` | 415.000 | 276.000 |
| `mittel` | 247.000 | 165.000 |
| `kompakt` | 158.000 | 107.000 |

Gemessen mit `o200k_base`; deutsches Verwaltungsdeutsch tokenisiert mit rund
4,2 Zeichen je Token.

## Zwei Eigenheiten der Quelldaten

**Die Laufende Nummer kodiert Ebene und Aufgabenart.** Das vierte Segment ist
über alle 2.429 Zeilen ausnahmslos eindeutig: `.1.` Hauptverwaltung/Leitung,
`.2.` Hauptverwaltung/Durchführung, `.3.` Bezirk/Steuerung, `.4.`
Bezirk/Durchführung. Die Markierung steht im Katalog.

Sie ist aber **kein verlässlicher Hinweis darauf, wer etwas tatsächlich tut**:
Der Eintrag zur Ampel-Instandhaltung (1.15.5.1.6) ist als Leitungsaufgabe
klassifiziert, obwohl seine Teilaufgaben „Betrieb und Instandhaltung …
Schadensbeseitigung" lauten. Das Regelwerk behandelt die Markierung deshalb als
Hinweis, nicht als Beweis — entscheidend ist der Inhalt der Teilaufgaben.

**14 bürgerrelevante Bezirksaufgaben sind regionalisiert**: Ein Bezirk erledigt
sie für ganz Berlin (Fundbüro, Heilpraktiker-Erlaubnis, Schrottfahrzeuge,
Aufstiegs-BAföG und weitere). Die Regel „nenne nie einen konkreten Bezirk" wäre
dort falsch. Diese Einträge sind im Katalog eigens markiert und die Regel hat
eine ausdrückliche Ausnahme.

## Warum es „Ihres Wohnbezirks" nicht heißen darf

Der erste Entwurf ließ bezirkliche Zuständigkeiten mit dem Zusatz „Ihres
Wohnbezirks" benennen. Das ist für einen großen Teil der Fälle falsch.

Bezirkliche Aufgaben zerfallen in zwei Klassen. Bei **ortsgebundenen** Anliegen
richtet sich die Zuständigkeit nach dem Ort der Sache, nicht nach der Wohnung:
Sperrmüll gehört dem Bezirk, in dem er liegt; eine Gewerbeanmeldung dem Bezirk
der Betriebsstätte. Nur bei **personengebundenen** Leistungen wie Wohngeld oder
Elterngeld trifft der Wohnort zu — und selbst dort ist der Zusatz irreführend,
weil Berliner Bürgerämter alle Einwohnerinnen und Einwohner unabhängig vom
Bezirk bedienen.

Das Regelwerk unterscheidet deshalb nach Art des Anliegens: Bei ortsgebundenen
Fällen wird der Ort benannt („des Bezirks, in dem die Matratze liegt"), bei
personengebundenen genügt „des zuständigen Bezirksamts", im Zweifel steht
neutral „des zuständigen Bezirks". Die konkrete Benennung ist dabei nicht nur
korrekter, sondern für die suchende Person auch brauchbarer als eine
Allgemeinformel.

## Oberfläche

Die Oberfläche folgt dem Designsystem für Bürgerservices des Landes Berlin
(Vertical Citizenservice). Dessen Dokumentation beschreibt genau diesen Anwendungs-
fall: „Die Nutzenden sollen zielsicher zu der von ihnen gesuchten Dienstleistung
geleitet werden. Dabei steht eine möglichst ablenkungsfreie Präsentation zentraler
Informationen im Vordergrund."

Übernommen wurden das Seitengerüst (`#page-wrapper.screendefault.citizenservice`,
`#header`, `#layout-grid`, `#footer`), das Suchformular (`.searchform-slot`), die
Meldungsklassen (`.message--info`, `.message--error`) und die Buttons. Das Bundle
liegt vollständig unter `static/` — 152 Dateien inklusive der 148 Symbolgrafiken,
auf die das CSS relativ verweist. Keine Laufzeitabhängigkeit von berlin.de.

Zwei begründete Abweichungen:

1. **Beleg als natives `<details>` statt `.js-accordion`.** Das Akkordeon des
   Bundles initialisiert sich einmalig beim Laden (`:not(.initialized)`) und
   erfasst dynamisch eingefügte Ergebnisse nicht. Eine Re-Initialisierung ist von
   außen nicht ansprechbar, deshalb die JavaScript-freie Alternative.
2. **Die zuständige Stelle steht in der `h2`, „Zuständig ist" als Dachzeile
   darüber.** Die `h1` stellt die Frage („Wer ist zuständig?"), die `h2` gibt die
   Antwort — andernfalls trüge das Etikett den roten Akzentbalken und nicht die
   eigentliche Auskunft. Das Etikett ganz wegzulassen war die erste Fassung und
   nahm der Antwort die Einordnung; es steht jetzt als `.antwort__label` darüber,
   in Größe und Farbe der `.caption`-Konvention des Designsystems (14px, #454545).

Nebeneffekt: Die frühere Sorge um eingebettete Google Fonts erledigt sich, weil das
Designsystem Arial verwendet und keine Webfont lädt.

Zu klären: Die Dokumentation weist darauf hin, dass die Design-Variante nicht frei
wählbar ist und vor Projektbeginn mit der Landesredaktion von Berlin.de abzustimmen
ist.

## Messung

`testfragen.json` enthält 30 Bürgerfragen in Alltagssprache, jede an einen realen
Katalogeintrag gebunden: 26 eindeutige Treffer (davon 6 regionalisiert), eine
Mehrdeutigkeit, ein Fall ohne Landeszuständigkeit. Die erwarteten Zuständigkeiten
sind aus dem Katalog abgeleitet, **fachlich aber noch ungeprüft**. Bis diese
Prüfung erfolgt ist, misst die Messlatte Vermutungen.

`eval.py` unterscheidet „richtig an erster Stelle" von „richtig oder in Auswahl".

## Betrieb

Deployment als einzelne Vercel Function. `app.py` mit einer FastAPI-Instanz
namens `app` ist eine erkannte Entrypoint-Konvention, der Katalog entsteht über
den Build-Befehl aus der CSV, `static/` wird beim Bauen aufs CDN gehoben.

**Kein Ratenbegrenzer im Code.** Ein erster Entwurf hatte Ratenbegrenzung und
Tagesbudget im Prozess. In einer Serverless-Umgebung sind solche Zähler
wirkungslos, weil jede Instanz bei einem Kaltstart wieder bei null beginnt — sie
hätten Sicherheit vorgetäuscht. Die harte Grenze liegt stattdessen als
Tageskontingent in der Google-Konsole. Der bewusst in Kauf genommene Nachteil:
Ein Kontingent gilt global, ein einzelner Dauerfeuer-Aufrufer verbraucht es für
alle. Damit wird aus dem Kostenproblem ein Verfügbarkeitsproblem — für einen
Prototyp die bessere Seite des Tauschs.

**Zwei Caches, die nichts miteinander zu tun haben.** Geminis implizites Caching
senkt die Kosten des Aufrufs (99 % der Eingabe-Token, gemessen), der eigene
Antwortcache vermeidet den Aufruf ganz. Ersteres funktioniert nur bei
byteweise identischem Systemprompt, weshalb die Ausbeute je Aufruf protokolliert
und bei drei mageren in Folge gewarnt wird. Letzteres liegt im Arbeitsspeicher
der Instanz und überlebt keinen Kaltstart.

## Offene Punkte

- Testfragen von Fachleuten gegenlesen lassen
- Datenschutz für Bürgeranfragen an den Modellanbieter klären
- Context Caching einrichten — erst nach belastbarer Trefferquote
- Barrierefreiheit gegen BITV 2.0 prüfen
