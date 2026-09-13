# Plan: Node-basierter Dialog- und Quest-Editor (QuestForge 2)

Stand: 2026-09-13, **Plan freigegeben (Marco)**. Noch kein Code. Umsetzung
startet mit Meilenstein 1 auf Branch `questforge2`.

Dieses Dokument ist die Arbeitsanweisung fuer die Umsetzung. Es beschreibt
**wie das Tool bedient wird** und **wie die Node-Konzepte auf das echte
Spielformat abgebildet werden**. Alles, was das Spiel kann und nicht kann,
stammt aus `README.md` und `tw1-quest-modding/SKILL.md` (beides am lebenden
Spiel verifiziert). Der Implementierer kennt das Questsystem und entscheidet
selbst, welche Felder eine Eingabemaske im Detail braucht. Hier wird nur
festgelegt, wie es am einfachsten zu bedienen ist.

Punkte, die noch nicht bewiesen sind, sind mit **[PRUEFEN]** markiert.
Annahmen des Planers mit **Annahme:**.

---

## 1. Ziel in einem Satz

Ein Werkzeug, das jemanden ohne Modding-Wissen Schritt fuer Schritt von
"Neue Quest" bis zur fertig gepackten, im Spiel aktivierten Mod fuehrt, mit
einem Node-Graphen fuer Dialoge, einer Zeitleiste aller Quests im Spiel, und
zwei eingebauten Guides.

Nicht-Ziele: kein Level-/Marker-Editor (das bleibt der Two Worlds Editor),
keine neue Sprachausgabe (nur Wiederverwendung vorhandener Cues), kein
Multiplayer-Questsystem.

---

## 2. Technik

### 2.1 Stack

| Entscheidung | Wahl | Grund |
|---|---|---|
| Sprache | Python 3.12, nur Standard-Library + bestehende Module | Bestehende Pipeline (`tw1_qtx`, `tw1_lan`, `wdio`, `questforge`, `DataHub`-Logik aus `quest_creator_gui.py`) wird 1:1 wiederverwendet |
| GUI | **Tkinter, Node-Graph als eigener `Canvas`** (entschieden 2026-09-13) | Keine Abhaengigkeit, eine einzige exe von ca. 12 MB, Start unter 1 s, das Dark-Theme aus `quest_creator_gui.py` existiert schon. Alternative PySide6 (QGraphicsView) waere fuer den Graphen komfortabler, kostet aber 50 bis 100 MB exe und 2 bis 4 s Start. Umstieg auf Qt nur, wenn der Canvas in Meilenstein 2 nachweislich zu langsam ist |
| Exe | **`TW1QuestCreator.exe`**, PyInstaller `--onefile --noconsole --icon`, Build-Spec im Repo (`build_exe.spec`), Build-Skript `build_exe.bat` | Nutzer brauchen kein Python. Eine Datei, wie gewuenscht. Hinweis: onefile entpackt beim Start nach `%TEMP%`, bei Tkinter etwa 0,5 s, akzeptabel |
| UI-Sprache | **Umschaltbar Deutsch / Englisch** (entschieden 2026-09-13) | Alle sichtbaren Texte laufen ueber `i18n.t('key')`, zwei Woerterbuecher in `questforge2/i18n.py`. Standard nach Windows-Sprache (`locale.getlocale`), Umschalten im Menue Ansicht, wirkt nach Neustart (Widgets werden nicht live umbeschriftet, das haelt den Code einfach). Guides und Validierungstexte sind ebenfalls zweisprachig |
| Projektdatei | `*.tw1proj` (JSON, lesbar, Git-freundlich) | Ein Projekt = eine Mod (`.wd`) mit beliebig vielen Quests |
| Konfig | `questforge_config.json` wie bisher (Spielpfad, zuletzt geoeffnete Projekte, Guide-schon-gesehen) | Bleibt kompatibel zum bestehenden Tool |

### 2.2 Performance-Regeln (verbindlich)

- Basisdaten (500 Quests, ca. 700 NPCs, 7578 Voice-Cues, Dialogbaeume der
  3-MB-`.lan`) werden **einmal** geparst und als Index-Cache
  (`cache/index.json` neben der Konfig, mit mtime der Quell-`.wd`) abgelegt.
  Zweiter Start liest nur den Cache.
- Retail-Dialogbaeume werden **erst beim Oeffnen einer Quest** in Nodes
  umgewandelt, nicht beim Start.
- Der Canvas zeichnet nur, was sich geaendert hat (Tag-basierte Updates, kein
  `delete('all')` pro Frame). Beim Ziehen eines Nodes werden nur der Node und
  seine Kanten bewegt.
- Zoom in festen Stufen (50/75/100/125/150 %), Schriftgroessen pro Stufe
  vorberechnet (Tkinter skaliert Text nicht mit `canvas.scale`).
- Listen mit Autocomplete (NPC-Namen, Objekte, Cues) filtern im Speicher per
  Praefix, keine Neu-Erzeugung der Widgets pro Tastendruck.
- Build/Export laeuft in einem Thread, Log-Ausgabe im UI wie bisher.

### 2.3 Neubau auf eigenem Branch

Entscheidung (Marco, 2026-09-13): **Das Tool wird neu gebaut, nicht aus
`quest_creator_gui.py` weiterentwickelt.** Die Umsetzung laeuft auf einem
eigenen Branch (`questforge2`), `main` bleibt bis zum ersten Spieltest
unberuehrt. Der alte `quest_creator_gui.py` wird nicht angefasst und dient
nur als Nachschlagewerk (Dark-Theme, `DataHub`-Parsing, `_convert_tree`,
`_do_build`, `_pack_into_archive`), aus dem man Logik **abschreibt**, nicht
importiert.

**Annahme:** Neubau meint die GUI. Die Format-Module `tw1_qtx.py`,
`tw1_lan.py`, `tw1_wd.py`, `wdio.py` sind byte-exakt gegen Retail
verifiziert und werden unveraendert importiert. Sie neu zu schreiben waere
nur Risiko ohne Nutzen.

Layout auf dem Branch: ein Unterordner `questforge2/` als Paket, damit das
neue Tool nicht mit den Root-Skripten vermischt wird.

| Datei | Inhalt |
|---|---|
| `questforge2/__main__.py` | Einstieg (`python -m questforge2`), Start des Hauptfensters |
| `questforge2/app.py` | Hauptfenster, Menueleiste, Kontextmenues, Statusleiste, Fensterlayout, `VERSION` |
| `questforge2/theme.py` | Dark-Theme, Farben, Schriften, Node-Farbpalette |
| `questforge2/i18n.py` | `t(key)` und die beiden Woerterbuecher DE/EN, Spracherkennung, Umschalten |
| `questforge2/model.py` | Datenmodell: Projekt, Quest, Sprecher, Node-Typen, Kanten; JSON laden/speichern; Undo-Stack |
| `questforge2/graph.py` | Der Canvas-Node-Editor: Nodes zeichnen, Ports, Kanten, Drag, Auswahl, Pan/Zoom, Auto-Layout |
| `questforge2/inspector.py` | Rechte Seitenleiste: Eigenschaften-Formulare pro Node-Typ |
| `questforge2/palette.py` | Linke Box: Sprecher-Bereich oben, Aufgaben/Aktionen/Bedingungen unten |
| `questforge2/timeline.py` | Zeitleiste aller Quests |
| `questforge2/mappicker.py` | Kartenkachel-Fenster als Filter fuer IDs |
| `questforge2/data.py` | Spielpfad-Suche, Basisdaten extrahieren, Index-Cache, NPC/Quest/Location/Marker/Cue-Indizes |
| `questforge2/export.py` | Graph zu `.qtx`-Block und `.lan`-Baum; Packen; Registry. Nutzt `tw1_qtx`, `tw1_lan`, `wdio` |
| `questforge2/validate.py` | Regelpruefung vor dem Export (Abschnitt 8) |
| `questforge2/guide.py` | Rundgang-Guide und Tutorial-Quest |
| `questforge2/tests/` | Round-Trip-Tests (M4), Modell-Tests, Validierungs-Tests; laufen ohne Spieldaten mit kleinen Fixtures |
| `build_exe.spec`, `build_exe.bat` | Exe-Build (Repo-Root) |

---

## 3. Fensteraufbau

```
+----------------------------------------------------------------------------+
| Datei  Bearbeiten  Ansicht  Quest  Hilfe                                   |
+----------------------------------------------------------------------------+
| ZEITLEISTE (einklappbar)  [Suche...] [Gruppe v] [nur eigene]  (o) Zoom     |
| [Q_1 Kapitel..][Q_2 ..][Q_4 ..]  ...  [Q_385 eigene *]  [+ Neue Quest]     |
+------------------+-------------------------------------+-------------------+
| SPRECHER         |                                     | EIGENSCHAFTEN     |
|  [+ Neuer        |          NODE-GRAPH                 |                   |
|     Sprecher]    |     (Canvas, Pan/Zoom)              |  Felder des       |
|  o Spieler       |                                     |  gewaehlten Nodes |
|  o Ferid         |   Tabs oben im Graph:               |                   |
|  o Tago          |   [Angebot] [Laeuft] [Erfuellt]     |                   |
|------------------|   [Abgeschlossen]  (Abschnitt 5.1)  |                   |
| AUFGABEN /       |                                     |-------------------|
| AKTIONEN /       |                                     | COACH (Guide)     |
| BEDINGUNGEN      |                                     | Schritt 3 von 9   |
|  [+ Neue Aktion] |                                     | "Zieh jetzt..."   |
|  [+ Neue Beding.]|                                     |                   |
+------------------+-------------------------------------+-------------------+
| Statusleiste: Projekt | Spielpfad | Quest Q_385 | 12 Nodes | Validierung ok |
+----------------------------------------------------------------------------+
```

- Alle drei Seitenbereiche (Zeitleiste, linke Box, rechte Leiste) sind per
  Griff in der Breite verstellbar und ueber `Ansicht` ein-/ausblendbar.
- Dark-Theme wie im bestehenden Tool (Farben `GOLD`, `MUT` etc. uebernehmen).

### 3.1 Menueleiste

**Datei:** Neues Projekt, Projekt oeffnen, Zuletzt geoeffnet (Untermenue),
Speichern (Strg+S), Speichern unter, Trennlinie, Spielpfad waehlen,
Trennlinie, Exportieren als Mod (Strg+E), Nur Dateien exportieren (Ordner
mit `.qtx`/`.lan`, fuer Leute, die selbst packen), Trennlinie, Beenden.

**Bearbeiten:** Rueckgaengig (Strg+Z), Wiederholen (Strg+Y), Ausschneiden,
Kopieren, Einfuegen, Duplizieren (Strg+D), Loeschen (Entf), Alles auswaehlen,
Trennlinie, Auto-Layout (Strg+L).

**Ansicht:** Zoom + / - / 100 % / Auf Inhalt einpassen (F), Zeitleiste,
Sprecher-Box, Eigenschaften, Coach (jeweils Haken), Raster anzeigen,
Kanten-Stil (Kurve/Gerade).

**Quest:** Neue Quest, Quest duplizieren, Quest loeschen, Validieren (F7),
Vorschau als Text (zeigt den erzeugten `.qtx`-Block und die Dialogzeilen als
Lesetext, damit man sieht, was rauskommt), Als Vorlage speichern.

**Hilfe:** Rundgang starten, Tutorial: Test-Quest anlegen, Dokumentation
(oeffnet `README.md`-Inhalt im Fenster wie bisher `show_docs`), Trennlinie,
Ueber.

**Ueber-Dialog:** Name, Versionsnummer (eine Konstante `VERSION` in
`qf2_app.py`, wird auch in Exe-Name und Projektdatei geschrieben), Links:
Guide-Seite (`https://alchemy-fox.de/game/TW1_DialogAndQuestCreator/`),
GitHub-Repo (`https://github.com/MedievalDev/TW1_DialogAndQuestCreator`),
Community (`https://twmp.alchemy-fox.de/`), Credits (buglord fuer `wdio.py`,
CC0), Hinweis "keine Spieldaten enthalten".

### 3.2 Kontextmenues (Rechtsklick)

| Wo | Eintraege |
|---|---|
| Leerer Graph | Node hinzufuegen (Untermenue mit allen Typen), Einfuegen, Auto-Layout, Auf Inhalt einpassen |
| Node | Duplizieren, Loeschen, Kommentar anheften, Kante(n) trennen, Als Start dieser Ebene setzen (nur Dialog-Nodes) |
| Kante | Trennen |
| Zeitleisten-Karte | Oeffnen, Duplizieren als eigene Quest, Loeschen (nur eigene), Nur diese Quest exportieren, Im Text anzeigen |
| Sprecher in der Box | Umbenennen, Entfernen (nur wenn kein Node ihn nutzt), Alle Zeilen dieses Sprechers markieren |

---

## 4. Ablauf beim ersten Start

1. Spielpfad: wie bisher aus Konfig, Registry, Steam-Pfaden; sonst Dialog.
2. Basisdaten extrahieren (`base/`) und Index-Cache bauen, mit
   Fortschrittsbalken. Passiert nur beim allerersten Start.
3. **Rundgang-Guide** startet automatisch (Abschnitt 9.1). Am Ende die Frage:
   "Moechtest du jetzt mit dem Tutorial eine kleine Test-Quest anlegen?"
   Ja startet das Tutorial (9.2), Nein landet im leeren Projekt.
4. Haken "Beim Start nicht mehr zeigen", jederzeit ueber Hilfe erneut startbar.

---

## 5. Der Node-Graph fuer Dialoge

### 5.1 Warum vier Tabs (Gespraechs-Ebenen) statt einer Start-Node

Das Spiel kennt keinen "Dialog-Start" als freie Node. Jede Dialogzeile traegt
ein Zustands-Flag, und das Spiel springt beim Ansprechen des NPC in die erste
Zeile, deren Flag zum Quest-Zustand passt (README Abschnitt 6):

| Ebene im Tool | Flag | Wann spielt sie |
|---|---|---|
| **Angebot** | `0.FT.AS` | Erstes Gespraech, am Ende ist die Quest angenommen |
| **Laeuft** | `0.QNS.AE` | Spieler kommt zurueck, Aufgabe noch nicht erledigt |
| **Erfuellt** | `0.QS.AE` | Aufgabe erledigt, Belohnungsgespraech |
| **Abgeschlossen** | `0.QC` | Jedes Gespraech danach |

Daraus folgt die Entscheidung: **Die Start-Node gibt es, aber fest je Ebene.**
Jeder Tab hat genau eine nicht loeschbare, nicht verschiebbare Node
"Einstieg" (abgerundet, gruen). Deren Ausgang ist der Gespraechsanfang. Damit
ist die Frage "wo faengt der Dialog an" fuer den Nutzer beantwortet, ohne
dass er Flags kennen muss.

Erweitert (ausgeklappt, standardmaessig zu): Zusaetzliche Ebenen `0.FT`
(passiver Gruss, **kein** Angebot), `0.QNT` (bekannt, nicht angenommen),
`0x0` (neutrale Menuezeile). Werden nur gebraucht, wenn man Retail-Dialoge
bearbeitet, die sie benutzen. Beim Laden eines Retail-Baums werden alle
vorkommenden Flags automatisch als Tabs angelegt.

**[PRUEFEN] Ebenen-Wechsel innerhalb eines Baums:** `next`-Indizes zeigen
in denselben Baum, unabhaengig vom Flag. Ob eine Kante von einer
`0.FT.AS`-Zeile auf eine `0.QNS.AE`-Zeile im Spiel etwas Sinnvolles tut, ist
nicht dokumentiert. Bis das getestet ist: **Kanten nur innerhalb eines Tabs**
erlauben, Validierung meldet Ebenen-uebergreifende Kanten als Fehler.

### 5.2 Node-Typen im Dialog-Graph

Alle Dialog-Nodes haben **abgerundete Ecken**. Nur "Kommentar" hat scharfe.

**Einstieg** (fest, 1 pro Tab): ein Ausgangsport rechts. Unten ein
Bedingungs-Port (Abschnitt 6.3).

**Spieler-Node** (blau): erzeugt durch Ziehen von "Spieler" aus der
Sprecher-Box. Oben im Node ein Dropdown `Antwort | Frage`.
- *Antwort:* eine Textzeile, ein Eingang links, ein Ausgang rechts.
- *Frage:* eine Liste von Zeilen, zu Beginn eine, Button `+ Zeile`. **Jede
  Zeile hat einen eigenen Ausgangsport** rechts. Im Spiel wird das ein
  Auswahlmenue (mehrere `next`-Eintraege). Zeile loeschen ueber das kleine x
  rechts neben der Zeile.
- Abbildung: eine Frage-Node mit n Zeilen wird zu n Held-Eintraegen
  (`lector 1`); die Vorgaenger-NPC-Zeile bekommt alle n als `next`. Bei
  *Antwort* ist es ein einzelner Held-Eintrag.
- Kein "nach Benutzung ausblenden"-Haken. Negative Indizes verstecken die
  Option im Spiel komplett (SKILL: "keep every next entry positive").

**NPC-Node** (Farbe je Sprecher, automatisch aus einer Palette): erzeugt
durch Ziehen eines Sprechers aus der Box. Immer genau eine Textzeile, ein
Eingang, ein Ausgang. Oben ein Aktions-Port, unten ein Bedingungs-Port
(Abschnitt 6). Im Eigenschaften-Panel zusaetzlich: Voice-Cue (Suche ueber den
Cue-Index aus `voice_index.py`, Vorschau des Originaltexts der Aufnahme mit
Warnung "Untertitel muss zur Aufnahme passen"), Kamera (Standard auf NPC),
Animation 1/2 (Zahl, Standard 0). Beim Bearbeiten von Retail-Zeilen bleiben
Cue und Animationen erhalten (SKILL: "never drop cue/anim1/anim2").

**Annahme und Ablehnen im Tab Angebot.** Wie das Spiel eine Annahme
erkennt, ist nicht eindeutig dokumentiert; README Abschnitt 6 nennt zwei
Dinge nebeneinander: die `0.FT.AS`-Kette, "an deren Ende die Quest angenommen
ist" (so laeuft `build_quest_tago.py`), und das Flag `1.TAKE` (`0x20100`) als
"Annahme-Option". Ausserdem gibt es den Zustand `0.QNT` (`0x2`, "Quest
bekannt, nicht angenommen") und das Ereignis `HEAR` (Angebot gehoert) fuer
`AOQ` und `REWARD`. Daraus folgt: **Ablehnen verwirft die Quest nicht.** Sie
geht in den Zustand "bekannt, nicht angenommen", und der NPC kann sie beim
naechsten Gespraech wieder anbieten. Offen ist nur der Mechanismus:

| Hypothese | Bedeutung fuer den Nutzer |
|---|---|
| A: `1.TAKE` markiert die Annahme-Zeile, jede andere Endzeile im Angebot lehnt ab | Im Tab Angebot bekommt jede Zeile einer Spieler-Frage einen Haken **"Nimmt die Quest an"** (gold markiert). Zeilen ohne Haken, deren Zweig endet, sind Ablehnungen. Ein fuenfter Tab **"Bekannt"** (`0.QNT`) spielt nach einer Ablehnung; dort kann man erneut anbieten (wieder mit Annahme-Haken) |
| B: Das Ende jeder `0.FT.AS`-Kette nimmt an, egal welche Zeile | Ablehnen ist im Angebot nicht moeglich. Der Haken entfaellt, der Coach sagt das klar ("Sobald das Angebotsgespraech endet, ist die Quest angenommen"). Der Tab "Bekannt" bleibt fuer Retail-Dialoge, die `0.QNT` nutzen |

**[PRUEFEN] vor Meilenstein 4, am Spiel:** Angebot mit zwei Spieler-Zeilen
bauen, eine mit `1.TAKE`, eine ohne, beide Zweige enden. Ablehnen waehlen,
Tagebuch pruefen, NPC erneut ansprechen. Ergebnis entscheidet zwischen A und
B; die Palette wird danach festgelegt. Bis dahin implementiert M3 den Haken
(Hypothese A), weil er bei B einfach entfernt werden kann.

**Kommentar-Node** (scharfe Ecken, grau, halbtransparent, groessenverstellbar,
Farbe waehlbar): kein Port, keine Wirkung im Export. Kann per "Kommentar
anheften" an einen Node gebunden werden und zieht dann mit.

**Ende-Node: bewusst nicht vorgesehen.** Im Format endet ein Gespraech, wenn
eine Zeile keinen Nachfolger hat (`next=[]`). Eine Ende-Node waere nur
Dekoration und eine weitere Sache, die der Nutzer verbinden muss. Stattdessen
zeichnet der Graph an jedem offenen Ausgangsport ein kleines graues
"Ende"-Kaeppchen, sodass sichtbar ist, wo das Gespraech auslaeuft.
Ablehnen: siehe Annahme und Ablehnen oben.

### 5.3 Bedienung im Graph

- Ziehen aus der Box in den Graph erzeugt den Node an der Mausposition.
  Doppelklick auf einen Eintrag der Box erzeugt ihn rechts neben dem
  gewaehlten Node und verbindet ihn automatisch (schnellster Weg fuer lineare
  Dialoge).
- Kante ziehen: von Ausgangsport auf Eingangsport. Loslassen im Leeren
  oeffnet ein Popup "Neuer Node: Spieler / <Sprecher> / Kommentar" und
  verbindet gleich.
- Ports nehmen nur zulaessige Verbindungen an (Dialog zu Dialog, Aktion zu
  Aktions-Port, Bedingung zu Bedingungs-Port). Unzulaessige Ports sind waehrend
  des Ziehens ausgegraut.
- Textbearbeitung: Doppelklick auf den Node oeffnet den Text im
  Eigenschaften-Panel mit Fokus. Kein Inline-Editing im Canvas (Tkinter kann
  das nicht sauber, und das Panel ist eh da).
- Pan: mittlere Maustaste oder Leertaste+Ziehen. Zoom: Strg+Rad. Mehrfachauswahl:
  Rahmen ziehen oder Strg+Klick.
- Auto-Layout: links nach rechts nach Gespraechsfluss (Breitensuche vom
  Einstieg), Zeilen einer Frage faechern nach unten auf.
- Undo/Redo fuer alles im Graph und im Panel (Snapshot des Quest-Modells pro
  Aktion, das ist bei der Datenmenge unkritisch).

---

## 6. Sprecher, Aufgaben, Aktionen, Bedingungen (die linke Box)

### 6.1 Sprecher (oberer Bereich)

"Spieler" ist immer da. Button **+ Neuer Sprecher** oeffnet einen kleinen
Dialog mit zwei Karten:

- **Vorhandener NPC:** Suchfeld mit Autocomplete ueber alle Retail-NPCs
  (Name aus `translateNPC_<id>`, dazu ID und Kachel). Darunter die volle
  Liste, gefiltert beim Tippen. Auswahl uebernimmt Name, `NPC_<id>`, Lector
  (aus der NPC-Zeile der `.qtx`, Spalte 6) und Heimat-Kachel.
- **Neuer NPC:** Felder: NPC-ID (die ID aus dem Two Worlds Editor, Pflicht,
  Pruefung: nicht in Retail vergeben, Bereich nach `tw1_qtx.index_ids`),
  Anzeigename, Lector (Dropdown "Stimme von ..." mit den vorhandenen Lectors,
  Standard: stumm/eigener Lector), Heimat-Kachel (ueber Kachel-Picker,
  Abschnitt 7). Hinweis im Dialog: "Der NPC braucht im Two Worlds Editor einen
  `Q_Giver`-Marker mit derselben Nummer in dieser Kachel, sonst friert das
  Spiel beim Laden der Kachel ein" (SKILL, Marker-Abschnitt).

Sprecher gelten **pro Quest**. Ein einmal angelegter neuer NPC kann in anderen
Quests desselben Projekts ueber "Vorhandener NPC" gewaehlt werden (er
erscheint dort unter "Eigene").

Der **Questgeber** ist der Sprecher, der als erster im Tab Angebot spricht.
Das Panel der Quest (Abschnitt 6.5) zeigt ihn an und erlaubt Umstellen.

### 6.2 Aufgaben und Aktionen (unterer Bereich, links)

Das Spiel trennt drei Dinge, und das Tool zeigt sie als drei Untergruppen in
einem abgetrennten Bereich:

**Aufgabe** (= `FC`, was der Spieler tun muss, damit die Quest "erfuellt"
ist). Genau eine Aufgabe pro Quest, deshalb keine Node im Graph, sondern
ein **fester Block im Tab "Erfuellt" links neben dem Einstieg** mit
Dropdown und Feldern. Dropdown: `Toeten | Sprechen mit | Gegenstand bringen |
Gold bringen | Ort erreichen | Gebiet saeubern | Ort finden | Gegenstand
finden | Gegenstand abliefern` (= `KILL, TALK, BRING_OBJECT, BRING_GOLD, GO,
CLEAR_AREA, FIND_LOCATION, FIND_OBJECT, DELIVER_OBJECT`; `FIND_KILL`,
`FIND_TALK`, `GO_AWAY`, `FIND_PLACE` unter "Weitere"). Felder je Typ legt der
Implementierer nach `tw1_qtx._FC` fest; jedes ID-Feld hat den Button
**Kachel waehlen** (Abschnitt 7). Warnhinweise direkt im Block:
- Toeten: "Quest-NPCs sind extrem widerstandsfaehig".
- Gebiet saeubern: "Zaehlt nur Gegner, die diese Quest selbst erzeugt hat.
  Braucht eine Aktion `Gegner erzeugen` derselben Gruppe (18 bis 23)" und
  automatisches Anlegen dieser Aktion anbieten.

**Aktion** (= `ACTION` und `REWARD`). Button **+ Neue Aktion** legt eine
Aktions-Node in die Box, die man auf den **oberen Port eines Dialog-Nodes**
zieht. Mehrere pro Node erlaubt, sie werden gestapelt gezeichnet. Dropdown in
der Node: `Belohnung Gold | Belohnung Erfahrung | Belohnung Gegenstand |
Belohnung Ruf | NPC erzeugen | NPC entfernen | NPC toeten | NPC teleportieren
| NPC gehen lassen | Held teleportieren | Gegner erzeugen | Objekt erzeugen |
Tuer oeffnen | Tuer schliessen | Ort auf Karte zeigen | Effekt erzeugen |
Weitere...`. Die Eingabemaske wechselt mit der Auswahl (Beispiel Teleport:
NPC-Auswahl, Kachel, Marker-Nummer, Sektor; alle vier Felder mit Picker).
Welche Felder genau: `tw1_qtx._ACTION` und die Marker-Tabelle im SKILL.
Jede Maske zeigt in einer Zeile, **welche Marker-Art** die Aktion liest
(z. B. "liest Marker: Q_Action_Teleport"), weil das die haeufigste Fehlerquelle
ist.

**Zeitpunkt der Aktion wird nicht abgefragt, sondern abgeleitet (vorlaeufig,
siehe Pruefung in 6.3):** Nach heutigem Wissen haengt das Spiel Aktionen an
Quest-Ereignisse (`TAKE, SOLVE, CLOSE, ENABLE, HEAR, FAIL, FIGHT`), nicht an
Dialogzeilen. Falls die Pruefung einen Zeilen-Hook findet, entfaellt die
Ableitung und die Aktion haengt echt an der Zeile. Bis dahin: Ableitung aus
dem Tab, in dem der Node haengt:

| Node haengt im Tab | Zeitpunkt |
|---|---|
| Angebot | `TAKE` |
| Laeuft | nicht erlaubt (Validierungsfehler mit Erklaerung) |
| Erfuellt | `CLOSE` (Standard) oder `SOLVE` (Umschalter im Panel) |
| Abgeschlossen | nicht erlaubt |

Zusaetzlich gibt es im Quest-Panel einen Bereich "Aktionen ohne Dialog"
(`ENABLE`, `FAIL`, `FIGHT`, `HEAR`), fuer Faelle wie "beim Freischalten NPC
erzeugen". Die Position im Graph ist damit reine Lesbarkeit: der Nutzer sieht
"nach diesem Satz bekommt er Gold", das Spiel bekommt `REWARD GLD CLOSE 500`.
Aktions-Nodes haben abgerundete Ecken und ein Blitz-Symbol.

**Annahme:** Dass ein Nutzer eine Aktion lieber an den Satz haengt als an ein
abstraktes Ereignis. Falls das in der Praxis verwirrt, ist der Fallback ein
reines Aktions-Listen-Panel pro Ereignis; das Modell bleibt gleich.

### 6.3 Bedingungen

**Vorlaeufige Annahme, nicht bewiesen:** Das Spiel hat keine freien
Bedingungen an einzelnen Dialogzeilen. Diese Annahme stammt aus README
Abschnitt 6 und 7 (Zeilen tragen nur das Zustands-Flag, Spruenge zwischen
Baeumen existieren nicht) und aus dem, was das alte Tool kann. Das alte Tool
deckt aber nur einen Teil dessen ab, was seither ueber das Questsystem
herausgefunden wurde, und der Planer konnte nichts am Spiel testen.

**[PRUEFEN] Pflichtaufgabe vor M3, entscheidet den Aufbau der NPC-Node:**
Kann eine Bedingung oder eine Aktion an einer **beliebigen** Dialogzeile
haengen, oder nur am Gespraechsanfang bzw. am Quest-Ereignis? Der
Implementierer prueft das in dieser Reihenfolge, bevor er Ports zeichnet:

1. **Flag-Bits der Retail-Baeume auszaehlen.** Alle `DialogEntry.flags` der
   3-MB-`.lan` sammeln (`tw1_lan.parse_trees`), jedes gesetzte Bit gegen die
   bekannte Tabelle (`0x1, 0x2, 0x4, 0x8, 0x100, 0x200, 0x20000, 0x40000`)
   halten. Jedes unbekannte Bit ist ein Kandidat fuer eine Zeilen-Bedingung
   oder Zeilen-Aktion. Dazu die Zeilen listen, die es tragen, und deren
   Quest-Kontext in der `.qtx` ansehen.
2. **SDK-Quellen lesen.** Im Two Worlds SDK (`D:\Games\TwoWorldsSDK`,
   EarthC-Kampagnencode, u. a. `PQuestActions.ech`) nach dem Code suchen, der
   Dialogeintraege auswertet: Welche Felder liest er pro Zeile (flags, cams,
   anim1/anim2), gibt es einen Hook, der beim Abspielen einer Zeile eine
   Aktion feuert oder eine Bedingung prueft (Inventar, Gold, Ruf, Quest)?
3. **Unbekannte Felder der `.lan`-Eintraege.** `next_pad`, `cam_pad` und
   `anim1/anim2` in `tw1_lan.DialogEntry` sind beim Round-Trip nur
   durchgereicht. Pruefen, ob eines davon in Retail-Zeilen Werte traegt, die
   sich nicht als Animation erklaeren lassen.
4. **Spieltest** (Marco): eine Zeile mit einem unbekannten Bit oder einem
   im SDK gefundenen Hook in eine Testquest legen und im Spiel ansehen.

Ergebnis in dieses Dokument eintragen. Danach gilt eine von zwei Bauweisen:

| Ergebnis | NPC-Node | Bedingungs-Nodes |
|---|---|---|
| Zeilen-Bedingungen existieren | bekommt einen Bedingungs-Port unten, wie urspruenglich gewuenscht; die Palette listet genau die gefundenen Bedingungsarten | docken an jeder Zeile **und** am Einstieg |
| Es gibt nur Zustands-Flags | kein Bedingungs-Port; nur der Aktions-Port oben | docken nur am Einstieg (Tabelle unten) |

Gleiches gilt fuer Aktionen (6.2): Wenn das SDK einen Hook "Aktion beim
Abspielen dieser Zeile" zeigt, wird der Zeitpunkt nicht mehr aus dem Tab
abgeleitet, sondern die Aktion haengt echt an der Zeile. Bis zum Ergebnis
wird nach der Tabelle unten gebaut, weil sie in jedem Fall gebraucht wird.

Was nach heutigem Stand sicher existiert und wie es im Tool erscheint:

| Bedingung im Tool | Engine | Wo andockbar |
|---|---|---|
| "Quest X wurde angenommen / erfuellt / abgeschlossen" | `AOQ PROMOTE <TAKE\|SOLVE\|CLOSE> Q_neu` in der Vorgaengerquest | Bedingungs-Port des **Einstiegs im Tab Angebot** |
| "Mindest-Level" | Kopfzeile `enableLevel` | Einstieg Angebot |
| "Gilde / Mindest-Ruf" | Kopfzeile `guild`, `minRep` | Einstieg Angebot |
| "Aufgabe erledigt" | die `FC`-Zeile | ist implizit der Einstieg im Tab Erfuellt, keine Node noetig |

Diese Bedingungs-Nodes (abgerundet, Schloss-Symbol) haengen **unten an der
Einstiegs-Node**. Ob NPC-Nodes zusaetzlich einen Bedingungs-Port bekommen,
entscheidet die Pruefung oben. Der Coach erklaert den jeweiligen Stand in
einem Satz.

Standard bei neuer Quest: Bedingung "Quest angenommen: Q_4" ist vorbelegt
(bewaehrter Haken, wie im bestehenden Tool), Level 1. "Auch nach" fuer alte
Spielstaende bleibt als zweite AOQ-Bedingung moeglich (mehrere AOQ-Zeilen
sind erlaubt).

### 6.4 Nicht-Dialog-Pfad

**[PRUEFEN]** SKILL nennt als bewaehrte Route `AOQ TAKE TAKE` (Quest wird
stumm automatisch angenommen) und README `AOQ PROMOTE TAKE` (Angebot im
naechsten Gespraech). Beides ist getestet, sie widersprechen sich in der
Bewertung. Das Tool bietet im Quest-Panel den Schalter "Quest wird angeboten
(Gespraech)" vs. "Quest startet automatisch (ohne Angebot)". Standard:
angeboten, weil das bestehende Tool das so ausliefert und es laeuft.

### 6.5 Quest-Panel

Wird angezeigt, wenn nichts im Graph gewaehlt ist oder man auf die
Zeitleisten-Karte klickt. Felder: Quest-ID (Dropdown freie IDs 381 bis 399,
mit Hinweis auf das 400er-Limit), Titel, Tagebuchgruppe, Tagebuchtexte
(Annahme / Erfuellt / Abgeschlossen, alle drei Pflicht, sonst steht der rohe
Schluessel im Tagebuch), Questgeber, Giver-Typ (`ACTIVE`, `PASSIVE`),
Kartenmarker-Verhalten (`BACK_TO_GIVER_MAP_SIGN` als Standard mit Erklaerung),
Zielarchiv (bestehende `Mods\*.wd` oder neuer Name), Schalter aus 6.4,
Aktionen ohne Dialog (6.2).

---

## 7. Kachel-Picker (Kartenfenster als Filter)

Kleines modales Fenster, von jedem ID-Feld aus per **Kachel waehlen**
erreichbar.

- Oben ein Raster der Kartenkacheln (Spalten A bis ?, Zeilen 1 bis ?, aus den
  Kachel-Namen in `NPC`- und `LOCATION`-Zeilen der `.qtx` abgeleitet, z. B.
  `F05`, `B8_1` fuer Innenraeume). Kacheln mit Inhalt sind heller. Hover zeigt
  die Anzahl NPCs/Orte/Marker. **Annahme:** Es gibt kein Kartenbild im Tool
  (Spieldaten, Copyright). Falls das Spiel eine Minimap-Textur in einem `.wd`
  liefert, kann sie als Option zur Laufzeit aus der eigenen Installation
  geladen werden; ist Kuer, nicht Pflicht.
- Klick auf eine Kachel filtert die Liste darunter. Die Liste ist nach dem
  Feld gefiltert, aus dem der Picker aufgerufen wurde:
  - NPC-Feld: NPCs mit Heimat-Kachel = gewaehlte Kachel (Name, ID).
  - Orts-Feld (`SHOW_LOCATION`, `FIND_LOCATION`): `LOCATION`-Zeilen der Kachel
    mit Typ und Radius, Hinweis bei Typ 10 / Radius 0 ("kann nicht markiert
    werden").
  - Marker-Feld (Teleport, Walk, Create_Enemy, Create_Object, Solve, Giver):
    alle Marker-Nummern **dieser Art**, die Retail-Quests in dieser Kachel
    benutzen (aus den `ACTION`/`FC`-Zeilen der `.qtx` indiziert), plus ein
    Freitext "Eigene Marker-Nummer (aus dem Two Worlds Editor)". Das Tool kann
    Marker aus `.lnd`-Dateien nicht lesen; das steht so im Fenster.
  - Objekt-Feld: alle Objekt-IDs aus `BRING_OBJECT`/`REWARD ITM`/`OBJECT_CREATE`
    (kachelunabhaengig; Kachelfilter dann ausgegraut).
- Suchfeld ueber der Liste, Doppelklick uebernimmt.

---

## 8. Validierung (F7 und automatisch vor Export)

Jede Regel aus README/SKILL wird eine Pruefung mit Klartext und Sprung zum
betroffenen Node. Fehler blockieren den Export, Warnungen nicht.

Fehler: leere Textzeile, Quest-ID ausserhalb 381 bis 399 oder belegt, keine
Aufgabe, Tab Angebot ohne Zeilen, Tab Angebot beginnt nicht mit NPC-Zeile,
Kante ueber Tab-Grenzen (5.1), Aktion im Tab Laeuft/Abgeschlossen, fehlender
Tagebuchtext, `\r` im Text, Sprecher-NPC-ID kollidiert mit Retail, unbekannter
Opcode (kann durch Bearbeiten nicht passieren, aber nach Projekt-Import),
Objekt-/NPC-ID leer.

Warnungen (aus dem SKILL-Abschnitt "Engine pitfalls"): `NPC_TELEPORT` in
eine Innenraum-Kachel (Name mit `_1`), `NPC_GO` auf einen NPC, der in derselben
Quest per `NPC_CREATE` erzeugt wird, `CLEAR_AREA` ohne `ENEMY_CREATE`
derselben Gruppe oder mit Gruppe ausserhalb 18 bis 23, `SHOW_LOCATION` nicht
auf `TAKE`, Aufgabe "Sprechen mit" auf den eigenen Questgeber (Angebot wird
uebersprungen), zwei aufeinanderfolgende Quests mit demselben Sprech-Ziel,
Kill-Ziel ist Quest-NPC, Voice-Cue gesetzt aber Text weicht vom
Aufnahme-Text ab, Zeile ohne Nachfolger mitten in einer Frage-Node
(wahrscheinlich vergessen), Ebene Laeuft/Abgeschlossen leer (NPC bleibt dann
stumm).

---

## 9. Die zwei Guides

Beide laufen im **Coach-Panel** rechts unten, nicht als Modal-Dialog, damit
man das Tool waehrend des Guides benutzen kann. Ein Schritt = Ueberschrift,
zwei bis vier Saetze, Bild oder Pfeil auf das gemeinte Element (das Element
bekommt einen goldenen Rahmen), Buttons Zurueck / Weiter / Beenden.

### 9.1 Rundgang (Tour)

Nur Erklaerung, aendert nichts. Etwa 12 Schritte: Zeitleiste, Neue Quest,
Sprecher-Box, Spieler-Node und Frage-Zeilen, NPC-Node, Kanten ziehen,
die vier Tabs und was sie im Spiel bedeuten, Aufgabe, Aktionen und der
abgeleitete Zeitpunkt, Bedingungen am Einstieg, Kachel-Picker, Validieren,
Exportieren und was danach im Spiel zu tun ist (neues Spiel starten,
Marker-Methode). Letzter Schritt: Frage nach dem Tutorial.

### 9.2 Tutorial: Test-Quest

Fuehrt durch eine echte, kleine Quest und **prueft nach jedem Schritt den
Zustand** (auto-weiter, wenn erledigt; "Weiter" ist ausgegraut, bis die
Bedingung stimmt):

1. Neue Quest in der Zeitleiste anlegen (prueft: Quest existiert).
2. Titel und drei Tagebuchtexte eintragen (Vorschlaege per Klick uebernehmbar).
3. Sprecher "Vorhandener NPC" waehlen, Vorschlag: Tago (`NPC_3`), Bedingung
   "nach Q_4" ist vorbelegt.
4. Tab Angebot: NPC-Zeile ziehen, Text eintragen, mit Einstieg verbinden.
5. Spieler-Frage mit zwei Zeilen ("Ich helfe." / "Nicht jetzt."), verbinden.
6. NPC-Antwort auf die erste Zeile, Ende offen lassen.
7. Tab Erfuellt: Aufgabe "Gold bringen 100" setzen, NPC-Zeile "Danke",
   Aktion "Belohnung Gold 500" oben andocken.
8. Tabs Laeuft und Abgeschlossen je eine NPC-Zeile.
9. Validieren (muss gruen sein).
10. Exportieren: Zielarchiv waehlen, Build laeuft, Registry gesetzt.
11. Abschluss: Anleitung zum Test im Spiel (neues Spiel, Tagos erste Quest
    annehmen, erneut ansprechen), Hinweis auf die `[MOD]`-Marker-Methode, wenn
    nichts erscheint.

---

## 10. Zeitleiste

Horizontaler, scrollbarer Streifen oben, gedacht wie eine Foto-Zeitleiste:
Karten statt Text, Groesse per Zoom-Regler (klein: nur ID und Titel; gross:
dazu Questgeber, Gruppe, Aufgabe in einem Satz, Anzahl Dialogzeilen).

- **Reihenfolge:** Kette aus `AOQ`-Beziehungen (topologische Sortierung
  ueber `PROMOTE`/`TAKE`-Kanten), Quests ohne Kette dahinter nach ID.
  Gruppen (`translateGROUP_<n>`) als beschriftete Abschnitte mit Trennlinie.
- Eigene Quests sind gold umrandet, Retail-Quests grau; geaenderte
  Retail-Quests gold-gestrichelt.
- Suchfeld (Titel, ID, Questgeber-Name), Filter Gruppe, Haken "nur eigene",
  Haken "AOQ-Verbindungen zeichnen" (duenne Linien zwischen Karten).
- Klick oeffnet die Quest im Graph. Retail-Dialogbaeume werden dabei in Nodes
  umgewandelt (`_convert_tree`-Logik aus dem bestehenden Tool, alle Flags
  als Tabs, Cue/Anim/Cams pro Node behalten) und mit Auto-Layout gesetzt.
  Erste Bearbeitung einer Retail-Quest fragt einmal: "Diese Quest gehoert zum
  Spiel. Aenderungen werden als Teil deiner Mod exportiert. Fortfahren?"
- Export einer geaenderten Retail-Quest: geaenderter `QUEST`-Block ersetzt den
  Original-Block in der vollen `.qtx`, geaenderter Baum landet in Master-`.lan`
  und `ZZ_`-Overlay. Round-Trip-Test (Abschnitt 11, M4) sichert, dass eine
  **unveraenderte** Retail-Quest byte-gleich wieder rauskommt.
- **+ Neue Quest** ganz rechts (und im Menue Quest).

---

## 11. Meilensteine (jeder einzeln lauffaehig und testbar)

| M | Inhalt | Fertig wenn |
|---|---|---|
| M1 | Fenster, Menues, Statusleiste, Projekt neu/oeffnen/speichern, `qf2_data` mit Cache | Start unter 1 s beim zweiten Mal, Projektdatei round-trippt |
| M2 | Canvas-Editor: Nodes, Ports, Kanten, Drag, Auswahl, Pan/Zoom, Undo, Kommentar-Node | 300 Nodes fluessig ziehbar; Entscheidung Tkinter vs Qt wird hier final |
| M3 | **Zuerst** Pruefung 6.3 (Flag-Bits, SDK). Dann Sprecher-Box, Spieler-/NPC-Nodes, Tabs, Eigenschaften-Panel, Cue-Suche | Pruefergebnis im Plan; ein Dialog laesst sich komplett bauen |
| M4 | Export Dialog zu `.lan`-Baum, Retail-Baum laden | `translateDQ_205` laden und ohne Aenderung exportieren = byte-gleich |
| M5 | Aufgabe-Block, Aktions- und Bedingungs-Nodes, Kachel-Picker, Export `.qtx`, Packen, Registry | Quest aus dem Tool laeuft im Spiel (Marco testet) |
| M6 | Zeitleiste mit Retail-Quests, Retail-Quest bearbeiten | Retail-Quest aendern und im Spiel sehen |
| M7 | Validierung komplett | Alle Regeln aus Abschnitt 8 mit Sprung zum Node |
| M8 | Rundgang und Tutorial | Tutorial fuehrt ohne Vorwissen zur laufenden Test-Quest |
| M9 | Exe-Build, Performance-Pass, Ueber-Dialog, Icons | Eine `.exe`, Start unter 2 s auf einem normalen PC |
| M10 | Doku: README-Abschnitt, Guide-HTML aktualisieren, `[PRUEFEN]`-Punkte mit Ergebnis eintragen | Alle [PRUEFEN] aufgeloest |

Reihenfolge der Tests im Spiel: nach M4 die beiden `[PRUEFEN]` zu `1.TAKE`
und Ablehnen; nach M5 die erste Tool-Quest; nach M6 eine Retail-Aenderung.

---

## 12. Entscheidungen und offene Punkte

Entschieden am 2026-09-13:

1. Tkinter-Canvas fuer den Graphen (Abschnitt 2.1).
2. UI-Sprache umschaltbar Deutsch/Englisch (Abschnitt 2.1).
3. Bedingungen docken vorerst am Einstieg (Abschnitt 6.3). Ob sie auch an
   jeder NPC-Node moeglich sind, ist Pflichtpruefung vor M3; das alte Tool
   ist dafuer kein Beweis, es deckt nur einen Teil des Systems ab.
4. Neubau als Paket `questforge2/` auf eigenem Branch, altes Tool bleibt
   unangetastet (Abschnitt 2.3).
5. Exe heisst `TW1QuestCreator.exe`.

Offen:

- Ob `quest_creator_gui.py` nach dem ersten erfolgreichen Spieltest aus
  `main` entfernt wird.
- Alle `[PRUEFEN]`-Punkte: Bedingungen/Aktionen pro Zeile (6.3, vor M3,
  Flag-Bits + SDK + Spieltest), Annahme/Ablehnen (5.2), Kanten ueber
  Tab-Grenzen (5.1), `AOQ TAKE TAKE` vs `PROMOTE TAKE` (6.4). Ergebnis
  kommt in dieses Dokument.

---

## Anhang A: Gespraechsverlauf der Planungssession (2026-09-13)

Vollstaendiger Verlauf zwischen Marco und Claude, aus dem dieser Plan
entstanden ist. Marcos Nachrichten sind woertlich uebernommen (inklusive
Tippfehler), Claudes Antworten ebenfalls. Die Widget-Fragen sind mit den
gewaehlten Antworten aufgefuehrt.

### A.1 Marco (Auftrag)

> Können wir ein Plan für ein wirklich einfaches Tool erstellen mit dem man
> die Dialoge und Quest erstellen kann? Ich hab mir das diesmal node basiert
> vorgestellt zuerst klickt man auf new Questda drin ist es so das man links
> so ne Box hat mit nodes die man rechts in den node graph rein zieht das
> Tool soll ein richtig an der Hand nehmen und step für step durch führen
> was ma für ein Dialog braucht erst würde ich vorschlagen das man links
> spezifisch für diesen Dialog neue character anlegt oder bestehende wählt
> dazu geht man auf new speaker dann kommt new oder exist npc bei new muss
> man die ID angeben die er im two Worlds Editor hat bei. Exist werden alle
> original im spiel angezeigt mit ihren namen beim eintippen der namen
> autocompliet namensliste wird auch angezeigt dann bekommt man links also
> eine neue node sagen wir ferid dann haben wir links den Player und ferid
> zieht man die node vom Player rein und danach ferid kann man diese
> verbinden auf der node gibt's ein dropdown beim Player Dialog und question
> bei Dialog ganz normale Antwort oder Dialog bei question kann man in dieser
> node mehrere lines hinzufügen erstmal ist nur eine da aber mit Add line
> kommt eine weiter so viele man will jede bekommt dann ein andock punkt für
> npc nodes... npc nodes sind glaub immer Dialog die fragen ja keine liste
> jedoch haben die unten und oben einen speziellen andock punkt wo man
> actions oben und conditions unten verbinden kann. Es sind mehrere möglich
> die conditions und actions sind auch links in der Box jedoch unten in einem
> abgetrennten Bereich dort ist auch ein new condition und ein new Action
> Button actions gibt Aufgaben da kann man wenn man den rein zieht wählen was
> der Spieler tun muss in einem dropdown zb kill bring Item usw und darunter
> die ID vom Objekt da kann man aber auch zuerst auswählen über einen Button
> Map tile wählen da kommt ein kleines Fenster mit der Map das fungiert als
> Filter und zeigt dann eine Liste aller ids mit Namen von Objekten auf die
> man die Action anwenden kann es gibt auch andere Szenarien in dem man zb
> sagt über eine Action teleport npc3 zu Quest teleport marker 3 auf tile f05
> dann muss beim teleport die Eingabemaske angepasst sein das man all dies
> eingeben kann also immer abhängig von der Aktion ( der Claude Code den ich
> das Tool später umsetzen lasse hat schon Quest gemacht und kennt das System
> er soll dann entscheiden welche Felder man in der Maske braucht wir
> entscheiden nur wie es am einfachsten zu bedienen ist) bei conditions ist
> es das selbe nur das es keine Aktionen sind sondern dinge geprüft werden
> wie zb ob der Player das Item im Inventar hat zb ach und beim vorher Dialog
> anlegen hab ich noch ne idee wir machen so ne zeitleiste mit allen quests
> im spiel die kann man alle ändern und bearbeiten die sind schon mit den
> nodes alle aufgebaut sodass man einfach reingehen und eine Kleinigkeit
> ändern könnte die zeitleiste kannst du wie bei so ner Foto Claude machen...
> Zu den nodes nochmal in Dialogen mach alle mit abgerundeten Ecken und mach
> eine node die comment heißt die hat Scharfe Ecken hab ich noch was
> vergessen dann sagst einfach zum Tool selbst es muss übersichtlich sein am
> besten in pyton aber am ende als exe gebaut das die Benutzer kein pyton
> oder thinker brauchen wichtig ist das du auf gute Performance achtest am
> besten ist es am ende eine einzige exe file wenn man die auf macht Kommt
> erstmal ein ausführlicher guid der ein durch Tool begleitet und am ende
> fragt ob man noch mit einem weiteren guid zusammen ein kleinen test quest
> anlegen möchte der führt dann Schritt für Schritt durch die Erstellung von
> Quest vom erstellen in der timeline bis hin zur fertigen exportierten Quest
> ach und in den quests mit den nodes denkst du es sollte fertige nodes geben
> wie eine Start node? Und fürs beenden noch eine exit Dialog links in der
> Box die kann man dann verbinden wo der Dialog enden soll zb wenn man eine
> Quest ablehnt? Schreib rein das geprüft werden muss ob das Sinn macht oder
> man eher nach der letzten node wo keine neue mehr danach kommt es auslaufen
> lässt und das dann beendet jetzt denk mal darüber nacht das Tool soll
> übrigens ein sauberes Tool sein dit datei leiste oben Kontext Menüs oben in
> datei leiste help mit über punkt und den 2 guids die am anfang kommen bei
> über dann versiknsstand links zu meinen seiten und github repo link usw

### A.2 Claude

Hat README, SKILL, das bestehende `quest_creator_gui.py` und die
Format-Module gelesen, den Plan als `NODE_EDITOR_PLAN.md` geschrieben,
auf den Branch `claude/dialog-quest-editor-tool-mwopwi` gepusht und
Draft-PR #1 angelegt. Erste Fassung enthielt: Tkinter-Empfehlung,
Fensteraufbau, Menues, vier Gespraechs-Tabs statt freier Start-Node, keine
Ende-Node, Aktionen mit abgeleitetem Zeitpunkt, Bedingungen am Einstieg,
Kachel-Picker, Validierung, zwei Guides, Zeitleiste, Meilensteine M1 bis
M10, offene Punkte.

### A.3 Marco

> Ich empfehle einen Neubau des Tools statt einer Änderung am bestehenden
> der Neubau dann auf einem eigenen Branch

### A.4 Claude

> Eingetragen und gepusht: Neubau als Paket `questforge2/` auf eigenem
> Branch, altes Tool bleibt unangetastet, nur die verifizierten
> Format-Module (`tw1_qtx`, `tw1_lan`, `tw1_wd`, `wdio`) werden importiert.
> Draft-PR #1 enthaelt den Plan.
>
> Die restlichen Entscheidungen aus Abschnitt 12 haengen nicht voneinander
> ab, deshalb alle auf einmal:

Widget-Fragen und Antworten:

| Frage | Optionen | Marcos Antwort |
|---|---|---|
| Womit soll der Node-Graph gebaut werden? | Tkinter Canvas (empfohlen) / PySide6 Qt | Tkinter Canvas |
| In welcher Sprache soll die Oberflaeche sein? | Deutsch / Englisch / Umschaltbar DE/EN | Umschaltbar DE/EN |
| Bedingungen: Das Spiel kennt keine Bedingungen an einzelnen Dialogzeilen, nur am Gespraechsanfang. Wo sollen Bedingungs-Nodes andocken? | Nur am Einstieg (empfohlen) / An jeder NPC-Node | "Nur am Einstieg? Und wen man ableht wird es verworfen oder wie?" |
| Wie soll die fertige exe heissen? | QuestForge.exe / TW1QuestCreator.exe | TW1QuestCreator.exe |

### A.5 Claude

> Kurz zur Ablehnen-Frage, bevor ich es in den Plan schreibe: Verworfen
> wird die Quest nicht. Das Spiel kennt laut README den Zustand `0.QNT`
> (Quest bekannt, nicht angenommen) und das Ereignis `HEAR` (Angebot
> gehoert). Das spricht dafuer, dass Ablehnen ein eigener Zustand ist, in
> dem der NPC beim naechsten Ansprechen eine "Bekannt"-Ebene spielt und dort
> erneut anbieten kann. Unklar ist nur der Mechanismus: entweder markiert
> das Flag `1.TAKE` die eine Annahme-Zeile und alle anderen Zeilen lehnen
> ab, oder das Ende jeder Angebots-Kette nimmt die Quest automatisch an und
> Ablehnen ist im Angebot gar nicht moeglich. Das ist genau der
> [PRUEFEN]-Punkt vor Meilenstein 4. Der Plan deckt beide Faelle ab.

Danach Plan aktualisiert (Abschnitt 2.1, 5.2, 6.3, 12) und gepusht.

> Plan ist aktualisiert und gepusht (Draft-PR #1). Eingetragen:
> Tkinter-Canvas, UI umschaltbar DE/EN ueber ein `i18n`-Modul,
> `TW1QuestCreator.exe`, Bedingungen nur am Einstieg, Neubau als Paket
> `questforge2/` auf eigenem Branch.
>
> Zum Ablehnen steht jetzt in Abschnitt 5.2: Die Quest wird nicht
> verworfen, sondern landet im Zustand "bekannt, nicht angenommen" und kann
> erneut angeboten werden. Zwei Hypothesen, wie das Spiel die Annahme
> erkennt (Flag `1.TAKE` an der Annahme-Zeile, oder Ende der Angebots-Kette
> nimmt immer an), mit einem konkreten Spieltest vor Meilenstein 4, der das
> entscheidet. Bis dahin bekommt jede Spieler-Zeile im Angebot einen Haken
> "Nimmt die Quest an" und es gibt einen fuenften Tab "Bekannt".
>
> Damit bleibt vor dem Start der Umsetzung nur noch die Frage, ob der Plan
> so freigegeben ist. Die Umsetzung wuerde dann in einer neuen Session auf
> Branch `questforge2` mit Meilenstein 1 beginnen.

Widget-Frage: "Ist der Plan so freigegeben?" (Ja, Plan steht / Noch was
aendern).

### A.6 Marco

> Mach rein das geprüft wird ob man bei jeder npc node conditions und
> Action funktioniert oder ob es nur am anfang geht weil du kannst das spiel
> ja nicht prüfen nur das alte Tool das enthält ja nur ein Teil von dem was
> man wirklich machen kann wir haben viel seither herausgefunden

### A.7 Claude

> Drin und gepusht. Abschnitt 6.3 ist jetzt eine Pflichtpruefung vor
> Meilenstein 3, mit der Begruendung, dass das alte Tool nur einen Teil des
> Systems abdeckt und der Planer nichts am Spiel testen konnte. Die Pruefung
> hat vier konkrete Schritte:
>
> 1. Alle Flag-Bits der Retail-Dialogbaeume auszaehlen und jedes unbekannte
>    Bit als Kandidaten fuer Zeilen-Bedingung oder Zeilen-Aktion untersuchen.
> 2. SDK-Quellen (EarthC, `PQuestActions.ech`) nach dem Code lesen, der
>    Dialogzeilen auswertet, und nach Hooks fuer Aktionen oder Bedingungen
>    pro Zeile suchen.
> 3. Die bisher nur durchgereichten Felder der `.lan`-Eintraege auf
>    unerklaerte Werte pruefen.
> 4. Spieltest durch dich mit einer Testzeile.
>
> Je nach Ergebnis bekommt die NPC-Node einen Bedingungs-Port unten und
> Aktionen haengen echt an der Zeile, oder es bleibt beim Einstieg mit
> abgeleitetem Zeitpunkt. Beide Bauweisen stehen in einer Tabelle, die
> Zeitpunkt-Ableitung in 6.2 ist als vorlaeufig markiert, und Meilenstein 3
> beginnt mit dieser Pruefung.
>
> Stand: Plan in `NODE_EDITOR_PLAN.md`, Draft-PR #1, vier Commits auf dem
> Branch. Offene [PRUEFEN]-Punkte sind in Abschnitt 12 gesammelt. Naechster
> Schritt waere die Umsetzung von M1 auf Branch `questforge2` in einer neuen
> Session.

Zwischenstand PR #1 geprueft: mergebar, keine CI-Checks, keine Kommentare.

### A.8 Marco

> Füge den kompletten Verlauf von hier auch mit in die md

### A.9 Claude

Diesen Anhang angelegt, committet und gepusht.

### A.10 Marco

> Plan steht, Freigabe erteilt

### A.11 Claude

Freigabe im Kopf des Dokuments vermerkt. Damit ist die Planungssession
abgeschlossen.

## Anhang B: Uebergabe an die Umsetzungssession

Startanweisung fuer die naechste Session:

1. `git fetch origin main && git checkout -b questforge2 origin/main`,
   dann diesen Plan von Branch `claude/dialog-quest-editor-tool-mwopwi`
   (PR #1) uebernehmen oder PR #1 vorher nach `main` mergen.
2. Diesen Plan komplett lesen, danach `README.md` und
   `tw1-quest-modding/SKILL.md`.
3. Meilenstein 1 (Abschnitt 11) beginnen. Vor M3 die Pflichtpruefung aus
   6.3 durchfuehren und das Ergebnis hier eintragen.
4. Jede Aenderung an Entscheidungen in Abschnitt 12 nachfuehren, jeder
   aufgeloeste [PRUEFEN]-Punkt bekommt sein Ergebnis direkt an der Stelle
   im Text.
5. Build/Compile/Test streng nacheinander, ein Befehl, Ergebnis lesen, dann
   weiter (Marcos Arbeitsregel).
