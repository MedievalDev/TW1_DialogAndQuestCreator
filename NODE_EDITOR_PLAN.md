# Plan: Node-basierter Dialog- und Quest-Editor (QuestForge 2)

Stand: 2026-09-13, **Plan freigegeben (Marco)**. Umsetzung laeuft auf Branch
`questforge2` im Clone `C:\Users\marco\Desktop\TW1QuestCreator`.
**Alle Meilensteine M1 bis M10 umgesetzt** (2026-09-13). Offen sind nur
die Spieltests und die [PRUEFEN]-Punkte, die sie klaeren (Abschnitt 11 und
12, "Offen").

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
| UI-Sprache | **Umschaltbar Deutsch / Englisch** (entschieden 2026-09-13) | Alle sichtbaren Texte laufen ueber `i18n.t('key')`, zwei Woerterbuecher in `questforge2/i18n.py`. Standard nach Windows-Sprache (`locale.getlocale`), Umschalten ueber `DE · EN` oben rechts in der Menueleiste oder im Menue Ansicht; wirkt sofort, das Hauptfenster wird neu aufgebaut und uebernimmt Projekt und Ansicht (12.52). Guides und Validierungstexte sind ebenfalls zweisprachig |
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
| `questforge2/guide.py` | Rundgang-Guide und Tutorial-Quest, Doku-Fenster |
| `questforge2/retail.py` | (ergaenzt in M6) Spielquest-Bloecke ins Modell und byte-gleich zurueck |
| `questforge2/questlimit.py` | (2.5.0) Questgrenze 400/600: `PQuests.eco` patchen, `QuestLimit600.wd`, wirksame Grenze lesen |
| `questforge2/enemylevel.py` | (2.6.0) Stufen aller 90 Gegnerarten: Tabelle im Gegner-Skript finden, patchen, `EnemyLevels.wd` |
| `questforge2/assets/` | (ergaenzt in M9) Programm-Icon |
| `questforge2/tests/` | Round-Trip-Tests (M4), Modell-Tests, Validierungs-Tests; laufen ohne Spieldaten mit kleinen Fixtures, Retail-Tests zusaetzlich mit `base/` |
| `build_exe.spec`, `build_exe.bat` | Exe-Build (Repo-Root) |
| `TW1QuestCreator.pyw` | (ergaenzt in M9) Starter ohne Konsole, Einstieg der Exe |
| `tools/make_icon.py` | (ergaenzt in M9) zeichnet das Icon, braucht Pillow |

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
klickbare Links (GitHub-Repo, Alchemy Fox `https://alchemy-fox.de/`,
Guide-Seite, Community), Trennlinie, Ueber (12.50).

**Ueber-Dialog:** Name, Versionsnummer (eine Konstante `VERSION` in
`questforge2/__init__.py`, Stand 3.8.0 (2.0.0 bis M10, 2.1.0 mit 12.52, 2.1.1 mit 12.54, 2.5.0 mit 12.57, 2.5.1 mit 12.58, 2.6.0 mit 12.59, 2.6.1 mit 12.60, 2.7.0 mit 12.61, 2.8.0 mit 12.62, 2.9.0 mit 12.63, 3.0.0 mit 12.64, 3.1.0 mit 12.65, 3.2.0 mit 12.66, 3.3.0 mit 12.67, 3.3.1 mit 12.68, 3.3.2, 3.4.0 mit 12.69, 3.4.1, 3.5.0, 3.5.1 mit 12.70, 3.5.2 mit 12.71, 3.6.0 mit 12.72, 3.6.1, 3.6.2, 3.6.3, 3.6.4, 3.7.0, 3.7.1, 3.7.2, 3.8.0 mit 12.74); wird im Ueber-Dialog und in der
Projektdatei als `tool_version` geschrieben), Links:
Guide-Seite (`https://alchemy-fox.de/game/TW1_DialogAndQuestCreator/`),
GitHub-Repo (`https://github.com/MedievalDev/TW1_DialogAndQuestCreator`),
Community (`https://twmp.alchemy-fox.de/`), Alchemy Fox
(`https://alchemy-fox.de/`), Credits (buglord fuer `wdio.py`,
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

**Ebenen-Wechsel innerhalb eines Baums (entschieden 2026-09-13, SDK):**
`next`-Indizes zeigen in denselben Baum, das Spiel filtert die Nachfolger
nach dem Zustand (Abschnitt 6.3, Ergebnis). Retail verzweigt so staendig:
eine Taken-Zeile hat als Nachfolger eine Solved- und eine NotSolved-Zeile,
neutrale `0x0`-Fragemenues haengen an Zeilen jeder Ebene. Kanten ueber
Ebenen-Grenzen sind deshalb **erlaubt**. Entscheidung (Marco, 2026-09-13):
**ein Graph pro Quest**, jeder Node traegt seine Ebene (Zustandsbits) als
farbiges Band, die Tabs sind Filter, die zum Einstieg der Ebene springen
und fremde Nodes abblenden (Abschnitt 12, Punkt 18).

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

**Ergebnis aus dem SDK (2026-09-13): Hypothese A trifft zu.** Das Bit
`0x20000` (`eQuestTakeNow`) ist ein Ereignis, das nur feuert, wenn das
Gespraech ueber eine Zeile mit diesem Bit lief; `0.FT.AS` ist FirstTime +
TakeNow, `1.TAKE` ist NotSolved + TakeNow. Endet das Angebot auf einem Pfad
ohne TakeNow, bleibt die Quest freigeschaltet, der Dialogzustand steht auf
NotTaken, und beim naechsten Gespraech spielen die `0x2`-Zeilen (Ebene
"Bekannt"). Gibt es dort keine, spielen die NotSolved-Zeilen der Ebene
"Laeuft" (die sind im freigeschalteten Zustand ebenfalls spielbar).
Der Haken "Nimmt die Quest an" bleibt; das Tool setzt das Bit auf den
ganzen Pfad ab der angehakten Zeile. **Spieltest 4a bestanden
(Marco 2026-09-14, 12.53):** Ablehnen nimmt die Quest nicht an, beim
naechsten Gespraech spielt die Ebene "Bekannt", die Annahme dort traegt die
Quest ein, Abgabe und Belohnung laufen.

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
- Pan: mittlere Maustaste oder Leertaste+Ziehen. Zoom: Mausrad (12.52),
  Strg+Rad scrollt senkrecht, Umschalt+Rad waagerecht. Mehrfachauswahl:
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

**Zeitpunkt der Aktion wird nicht abgefragt, sondern abgeleitet (bestaetigt
durch die Pruefung in 6.3):** Das Spiel haengt Aktionen an Quest-Ereignisse
(`TAKE, SOLVE, CLOSE, ENABLE, HEAR, FAIL, FIGHT`), nicht an Dialogzeilen.
Einen Zeilen-Hook gibt es nicht; die Zeilen loesen ueber ihre Ereignisbits
(TakeNow, CloseNow, FightNow) genau diese Ereignisse aus. Ableitung aus der
Ebene, in der der Node haengt:

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

**Ergebnis der Pruefung (2026-09-13, Schritte 1 bis 3 erledigt, Schritt 4
offen):**

*Schritt 1, Flag-Bits.* Alle 6942 Zeilen der 378 Quest-Baeume
(`translateDQ_*`) zerfallen restlos in elf Bits, kein unbekanntes Bit. Die
Bits mit anderen Werten (0x10, 0x40, 0x400 ... 0x80000000) kommen nur in den
Gruss-Baeumen `translateCitizen_*`, `translateGuard_*`, `translateBandit_*`
vor; dort ist jedes Bit ein Gruss-Slot (`PGreetings.ech`,
`eGreetingsFriendly0..7`, `Unfriendly`, `Help`, `Work`), das hat mit Quests
nichts zu tun.

*Schritt 2, SDK-Quellen* (`Scripts\Campaigns\Missions\PInc\PQuestsCommon.ech`,
`PDialogUnits.ec`, `PQuestActions.ech`, `PQuestLoader.ech`). Der Skript ruft
`PlayDialog(..., nDialogFlags, nDisabledEventsMask, "translateDQ_<n>", ...)`.
Die Maske entsteht in `GetDialogInputFlags`: Start mit allen acht
Zustandsbits, dann werden die Bits des aktuellen Zustands **abgezogen**.
Eine Zeile ist also spielbar, wenn alle ihre Zustandsbits im aktuellen
Zustand gesetzt sind (`flags & maske == 0`); eine Zeile mit `0x0` ist immer
spielbar. Die drei hohen Bits stehen nie in der Maske, sie sind
**Ereignisse**, die das Spiel am Gespraechsende in `EndTalkDialog` an den
Skript meldet (`UpdateQuestStateAfterDialog`):

| Bit | SDK-Name | Bedeutung | Retail-Zeilen in DQ-Baeumen |
|---|---|---|---|
| `0x1` | `eFirstTime` | erstes Ansprechen (Quest freigeschaltet, noch nie angeboten) | 1012 pur, 1610 mit TakeNow |
| `0x2` | `eQuestNotTaken` | Angebot gehoert, nicht angenommen | 105 |
| `0x4` | `eQuestTaken` | angenommen (unabhaengig von erfuellt) | 137 |
| `0x8` | `eQuestClosed` | abgeschlossen | 370 |
| `0x10` | `eQuestFailed` | fehlgeschlagen | 18 |
| `0x20` | `eQuestLowReputation` | Ruf unter `minRep` der Kopfzeile (dann feuert kein HEAR) | 105 |
| `0x100` | `eQuestNotSolved` | Aufgabe noch nicht erledigt (in Zustand freigeschaltet **oder** angenommen) | 531 pur, 355 mit TakeNow, 10 mit FightNow |
| `0x200` | `eQuestSolved` | Aufgabe erledigt (wird beim Gespraechsstart geprueft: Gegenstand/Gold im Inventar, Ort gefunden) | 90 pur, 1054 mit CloseNow |
| `0x10000` | `eQuestFightNow` | Ereignis: Questgeber wird feindlich, Held zieht die Waffe, `FIGHT`-Aktionen | 59 pur |
| `0x20000` | `eQuestTakeNow` | Ereignis: `TakeQuest` (Quest angenommen, `TAKE`-Aktionen und -Belohnungen) | 20 pur |
| `0x40000` | `eQuestCloseNow` | Ereignis: `CloseQuest` (Gegenstaende/Gold werden abgenommen, `CLOSE`-Aktionen und -Belohnungen) | nur mit Solved |

Damit sind die bisherigen Namen aufgeloest: `0.FT.AS` = FirstTime + TakeNow,
`0.QNS.AE` = NotSolved, `0.QS.AE` = Solved + CloseNow, `0.QC` = Closed,
`1.TAKE` = NotSolved + TakeNow, `0.FT` = FirstTime ohne Annahme, `0.QNT` =
NotTaken.

Weitere Fakten aus dem Code:
- **Kein freier Zeilen-Hook.** Es gibt keine Bedingung pro Zeile ausser den
  Zustandsbits und keine Aktion pro Zeile ausser den drei Ereignisbits.
  Inventar/Gold werden nur indirekt geprueft: `nFinished` wird beim
  Gespraechsstart fuer `BRING_OBJECT`, `BRING_GOLD`, `FIND_PLACE`,
  `FIND_LOCATION` berechnet und ergibt Solved/NotSolved. Fuer `KILL` ist die
  Pruefung im SDK auskommentiert, dort zaehlt der Questzustand.
- `HEAR` feuert beim allerersten Gespraechsstart (vor der ersten Zeile),
  sofern der Ruf reicht, und setzt den Dialogzustand auf NotTaken.
- `TALK`-Aufgaben werden beim Gespraechsstart mit dem Ziel-NPC geloest
  (`CheckQuestTalk`), die `SOLVE`-Aktionen laufen nach dem Gespraech. Das
  ist der im SKILL beschriebene Effekt "Angebot wird uebersprungen".
- Der Loader kennt eine im Retail nicht benutzte Aktion
  `ACTION NPC_DIALOG <zeit> NPC_<n> <baumname>` (`AddActionNPCDialog`), die
  zu einem Quest-Ereignis einen beliebigen Baum mit dem NPC abspielt.
  **[PRUEFEN]** am Spiel, dann Kandidat fuer "Aktion: Gespraech starten".
- Antwortmenues: alle 1109 Eintraege mit mehreren `next` zeigen
  ausschliesslich auf Held-Zeilen. NPC-Zeilen haben genau einen Nachfolger
  pro Zustand; Verzweigung nach Zustand laeuft ueber Held-Zeilen mit
  verschiedenen Zustandsbits (z. B. `next [24, 37]` mit 24 = Solved,
  37 = NotSolved, das Spiel zeigt nur die spielbare). **Kanten ueber
  Zustands-Grenzen sind also Retail-Alltag**, der Punkt in 5.1 ist damit
  entschieden: sie muessen erlaubt sein.
- Ereignisbit-Verteilung: In 1647 von 2026 Faellen traegt auch der
  Nachfolger einer TakeNow-Zeile TakeNow; die 379 Ausnahmen fuehren in
  neutrale `0x0`-Fragemenues (z. B. `DQ_4` Zeile 15 nach 19/25/32). Da Q_4
  nachweislich annimmt, obwohl das Gespraech in neutralen Zeilen endet,
  reicht es, dass **eine** gespielte Zeile das Bit traegt. Das Tool setzt
  das Bit trotzdem wie Retail auf den ganzen Annahme-Pfad (sicher unter
  beiden Lesarten).
- Negative `next`: alle 264 Faelle in DQ-Baeumen zeigen auf eine Zeile mit
  kleinerem Index, also auf eine schon gespielte Zeile (Rueckschleife).
  Deckt sich mit dem SKILL-Befund "wird nicht angezeigt". Das Tool erzeugt
  keine, reicht sie beim Retail-Round-Trip aber durch.
- **Startzeile [PRUEFEN]:** Beim Durchzaehlen ist die erste spielbare
  Zeile in Dateireihenfolge in 90 bis 95 % der Baeume eine NPC-Zeile, die
  Ausnahmen sind neutrale Fragemenues und Kampf-Zeilen. Ob das Spiel die
  erste spielbare Zeile nimmt oder anders waehlt, steht nicht im Skript
  (das macht die Engine). Die getestete Reihenfolge FirstTime, NotSolved,
  Solved, Closed (`build_quest_tago.py`) funktioniert; der Export haelt sie
  ein.

*Schritt 3, unbekannte Felder.* `next_pad`, `cam_pad` und der Baum-`pad`
sind in allen 9799 Zeilen 1. `anim1 == anim2` in allen Zeilen (13 Werte,
0 bis 17); `cams` ist immer leer oder ein einzelner Wert 1, 2, 6, 7. Nichts
davon traegt versteckte Bedingungen.

*Schritt 4, Spieltest (Marco):* a) Angebot mit zwei Held-Zeilen, nur
eine mit TakeNow, Ablehnen waehlen, danach muss eine NotTaken-Zeile (`0x2`)
spielen und das Tagebuch leer bleiben. **Bestanden 2026-09-14 (12.53).**
b) TakeNow nur auf der letzten Zeile statt auf dem ganzen Pfad.
**Bestanden 2026-09-14 (12.55).** c) `ACTION NPC_DIALOG`: offen, im Tool
nicht angeboten.

**Folge fuer den Bau (Bauweise "nur Zustands-Flags" aus der Tabelle unten,
mit Praezisierung):** NPC-Nodes bekommen keinen Bedingungs-Port. Die
Bedingung einer Zeile ist ihr Zustand, und der wird ueber die Ebene gesetzt.
Zusaetzlich gibt es pro Zeile drei Haken fuer die Ereignisbits:
"Nimmt die Quest an" (TakeNow), "Schliesst die Quest ab" (CloseNow,
Standard in der Ebene Erfuellt), "Kampf beginnt" (FightNow, unter
Erweitert). Aktionen haengen weiter an Quest-Ereignissen (6.2), die
Ableitung aus der Ebene ist jetzt begruendet: `TAKE` feuert, wenn ein
Gespraech ueber eine TakeNow-Zeile lief, `CLOSE` ueber eine CloseNow-Zeile.


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
| M1 | Fenster, Menues, Statusleiste, Projekt neu/oeffnen/speichern, `data.py` mit Cache | Start unter 1 s beim zweiten Mal, Projektdatei round-trippt. **Fertig 2026-09-13:** Start 0,3 s (Cache 0,01 s), Vollaufbau des Index 0,8 bis 1,4 s, 14 Tests gruen, Projektdatei byte-gleich nach Speichern/Oeffnen/Speichern |
| M2 | Canvas-Editor: Nodes, Ports, Kanten, Drag, Auswahl, Pan/Zoom, Undo, Kommentar-Node | 300 Nodes fluessig ziehbar; Entscheidung Tkinter vs Qt wird hier final. **Fertig 2026-09-13:** `graph.py`; bei 300 Nodes (4449 Canvas-Items) ein Node ziehen 1,7 ms/Frame, alle 300 zusammen 13 ms/Frame, Zoomstufe wechseln 92 ms, Undo 107 ms. **Tkinter bleibt (final).** 21 Tests gruen |
| M3 | **Zuerst** Pruefung 6.3 (Flag-Bits, SDK). Dann Sprecher-Box, Spieler-/NPC-Nodes, Tabs, Eigenschaften-Panel, Cue-Suche | Pruefergebnis im Plan; ein Dialog laesst sich komplett bauen. **Fertig 2026-09-13:** Pruefung in 6.3 eingetragen; `palette.py` (Sprecher-Box mit Dialog Vorhandener/Neuer NPC, Ziehen und Doppelklick), `inspector.py` (Formulare je Node-Typ, Quest-Panel, Cue-Suche), Modell auf einen Graphen pro Quest umgestellt; Beispiel-Dialog mit Angebot/Frage/Annahme, Laeuft, Erfuellt gebaut, gespeichert, wieder geoeffnet, byte-gleich; 27 Tests gruen |
| M4 | Export Dialog zu `.lan`-Baum, Retail-Baum laden | `translateDQ_205` laden und ohne Aenderung exportieren = byte-gleich. **Fertig 2026-09-13:** `export.py` (`tree_to_graph`, `graph_to_tree`, `preview_text`), "Quest > Dialog aus dem Spiel laden", "Vorschau als Text", "Quest wechseln". Round-Trip byte-gleich fuer **alle 378 Retail-Quest-Baeume** der Basis-`.lan` sowie alle 457 Baeume aus Yamalin.wd und Content02_Lan.wd, auch nach Speichern und Laden des Projekts; Import des groessten Baums (DQ_359, 74 Zeilen) 1 ms. 31 Tests gruen |
| M5 | Aufgabe-Block, Aktions- und Bedingungs-Nodes, Kachel-Picker, Export `.qtx`, Packen, Registry | Quest aus dem Tool laeuft im Spiel (Marco testet). **Code fertig 2026-09-13, Spieltest bestanden 2026-09-14 (12.53, 12.55):** Aufgabe-Node, angedockte Aktionen und Bedingungen, Aktionen ohne Dialog, `mappicker.py`, `.qtx`-Block und AOQ-Einfuegen, volle `.lan` plus `ZZ_`-Overlay, Packen mit Verifikation, Registry. Einmischen in eine Kopie von Yamalin.wd: 2,9 s, alle 47 unberuehrten Eintraege samt `.lnd`/`.par`-Metadaten identisch. Testprojekte fuer 6.3 Schritt 4a/4b in `testprojekte/`. 38 Tests gruen |
| M6 | Zeitleiste mit Retail-Quests, Retail-Quest bearbeiten | Retail-Quest aendern und im Spiel sehen. **Code fertig 2026-09-13, Spieltest bestanden 2026-09-14 (12.56):** `timeline.py`, `retail.py`; Ansicht mit Rueckfrage bei der ersten Aenderung, Duplizieren, Loeschen, Einzelexport, Vorlagen; alle 500 Bloecke und 378 Baeume unveraendert byte-gleich; Aenderung an Q_4 in eine Yamalin-Kopie exportiert, restliche `.qtx` identisch (12.40 bis 12.43) |
| M7 | Validierung komplett | Alle Regeln aus Abschnitt 8 mit Sprung zum Node. **Fertig 2026-09-13:** `validate.py`, F7-Fenster, Statusleiste, Sprung zu Node, Aktion ohne Dialog oder Quest-Panel (12.44) |
| M8 | Rundgang und Tutorial | Tutorial fuehrt ohne Vorwissen zur laufenden Test-Quest. **Code fertig 2026-09-13:** `guide.py`; Tutorial ohne Fenster komplett durchgespielt bis zum Export; ob die Test-Quest im Spiel laeuft, klaert Marcos Spieltest (12.45) |
| M9 | Exe-Build, Performance-Pass, Ueber-Dialog, Icons | Eine `.exe`, Start unter 2 s auf einem normalen PC. **Fertig 2026-09-13:** `dist\TW1QuestCreator.exe` 11,5 MB, zweiter Start 0,38 s bis bereit, 1,86 s gesamt; Ueber-Dialog mit Icon und Version 2.0.0 (12.48) |
| M10 | Doku: README-Abschnitt, Guide-HTML aktualisieren, `[PRUEFEN]`-Punkte mit Ergebnis eintragen | Alle [PRUEFEN] aufgeloest. **Doku fertig 2026-09-13** (12.49). Nicht erreicht: die [PRUEFEN]-Punkte, die nur ein Spieltest klaeren kann, sind offen und in Abschnitt 12 "Offen" gesammelt |

Reihenfolge der Tests im Spiel: nach M4 die beiden `[PRUEFEN]` zu `1.TAKE`
und Ablehnen; nach M5 die erste Tool-Quest; nach M6 eine Retail-Aenderung.
Stand 2026-09-13: Die Tests zu 1.TAKE und Ablehnen (6.3, Schritt 4a/4b)
brauchen einen Export ins Archiv; der kommt mit M5. Sie werden deshalb
zusammen mit der ersten Tool-Quest nach M5 gefahren.

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

Entschieden am 2026-09-13 (Umsetzung M1):

6. Arbeitsort ist ein frischer Clone `C:\Users\marco\Desktop\TW1QuestCreator`,
   TwStuff bleibt unangetastet. Start: `py -3.12 -m questforge2` vom Repo-Root
   (der `python`-Alias fehlt auf Marcos Rechner). Tests:
   `py -3.12 -m unittest discover -s questforge2/tests -t .`
7. Ablageort fuer Konfig, `base/` und `cache/index.json`: aus dem Quellcode
   gestartet der Repo-Root (kompatibel zum alten Tool), als Exe
   `%LOCALAPPDATA%\TW1QuestCreator\` (`data.app_dir()`).
8. Index-Cache: `cache/index.json` mit mtime/Groesse von `Update16.wd`,
   `Language.wd`, `Content01/02_Lan.wd` und allen `Mods\*.wd`; `INDEX_FORMAT`
   wird bei jeder Inhaltsaenderung hochgezaehlt. Inhalt: Quests (Titel, Gruppe,
   Giver, FC, AOQ-Liste, Zeilenzahl und Flag-Menge des Dialogbaums, Herkunft),
   NPCs (Name, Kachel, Lector), Gruppen, Locations, Kacheln, Objekte,
   Marker-Nummern je Art und Kachel, Cues (Lector, Text, Baum), Lectors.
   Dialogbaeume selbst werden nicht gecacht.
9. Mod-Semantik im Index: Ein Mod liefert die volle `.qtx`, daher ersetzen
   seine Bloecke die Retail-Bloecke. Unveraenderte Retail-Quests behalten
   `source='retail'`, veraenderte bekommen zusaetzlich `modified_by=<Mod>`
   (Grundlage fuer die gold-gestrichelte Karte in der Zeitleiste), neue IDs
   tragen den Mod als `source`. `.lan`-Titel und Baeume: spaeterer gewinnt
   (README 3.2). Beispiel Yamalin.wd: Q_1, Q_3, Q_4, Q_18, Q_21, Q_91,
   Q_100, Q_192, Q_291 sind `modified_by`.
10. Menueleiste als thematisierte `Menubar.TFrame` mit `tk.Menu`-Popups
    (Windows zeichnet die native Leiste hell), alle Eintraege aus 3.1 sind
    angelegt, M1-fremde ausgegraut. Sprache wirkt nach Neustart.
11. Projektdatei `*.tw1proj`: JSON, `format: 1`, `tool_version`, `name`,
    `target_archive`, `quests[]`; unbekannte Schluessel werden beim Laden
    bewahrt und beim Speichern zurueckgeschrieben (Vorwaertskompatibilitaet).

Entschieden am 2026-09-13 (Umsetzung M2):

12. Tkinter-Canvas ist final (Messwerte in der M2-Zeile). Drag laeuft ueber
    ein Sammel-Tag `sel` (ein `move`-Aufruf pro Frame), Kanten werden ueber
    eine Item-Tabelle statt `find_withtag` aktualisiert, Drag-Deltas werden
    auf ganze Welt-Einheiten gerundet (Modell bleibt int, kein Neuzeichnen
    beim Loslassen).
13. Node-Schema im Projekt: `type` (`entry` | `node` | `comment`), `x`, `y`,
    `lines[]` (eine Zeile = ein Ausgangsport), `title`, `color`, bei
    Kommentaren `w`, `h`, `text`, `attached_to`. Kanten `[von, port, nach]`,
    genau eine Kante je Ausgangsport (Neuverbinden ersetzt), beliebig viele
    Eingaenge (Wiedereinstieg). Der Einstieg heisst `entry`, ist je Tab fest,
    nicht loeschbar, nicht verschiebbar.
14. Undo als Snapshot von `quest.tabs` pro Aktion (`UndoStack`, 100 Stufen),
    Undo-Stack wird beim Quest-Wechsel geleert. Zwischenablage haelt Nodes
    plus interne Kanten, Einfuegen versetzt um 30/30 und vergibt neue IDs.
15. Kante ins Leere ziehen erzeugt in M2 direkt eine Dialog-Node und
    verbindet sie; M3 haengt dort das Popup "Spieler / Sprecher / Kommentar"
    an. Doppelklick auf einen Node ist fuer das Eigenschaften-Panel (M3)
    reserviert.
16. Tabs ueber dem Graph als Label-Leiste (`Angebot`, `Laeuft`, `Erfuellt`,
    `Abgeschlossen`; `Gruss`, `Bekannt`, `Neutral` nur wenn im Modell
    vorhanden). "Quest > Neue Quest" ist schon in M2 aktiv (naechste freie
    ID), der Quest-Panel-Rest bleibt M3.
17. Nur im Quellcode-Modus (nicht in der Exe): "Quest > Debug: 300
    Test-Nodes" und die Frame-Zeit des letzten Drags in der Statusleiste.

Entschieden am 2026-09-13 (nach der Pruefung 6.3, vor M3):

18. **Ein Graph pro Quest** statt ein Graph pro Tab (Marco, Widget). Jeder
    Dialog-Node traegt seine Ebene (`state`: `first`, `known`, `running`,
    `taken`, `solved`, `closed`, `failed`, `lowrep`, `neutral`) und die drei
    Ereignis-Haken (`take`, `close`, `fight`). Je Ebene gibt es einen festen
    Einstieg-Node (`entry:<state>`), die Tabs ueber dem Graph springen zum
    Einstieg und blenden Nodes anderer Ebenen ab (neutrale bleiben sichtbar).
    Neue Nodes bekommen die Ebene des aktiven Tabs. Retail-Baeume laden 1:1,
    Kanten ueber Ebenen sind normale Kanten. Das M2-Schema `quest.tabs`
    wird zu `quest.graph` mit einem Node-Feld `state`; Projektformat bleibt
    `format: 1`, weil noch keine Projekte existieren.
19. Ebenen-zu-Bits-Tabelle des Exports (6.3): `first` = 0x1, `known` = 0x2,
    `running` = 0x100, `solved` = 0x200, `closed` = 0x8, `failed` = 0x10,
    `lowrep` = 0x1|0x20, `neutral` = 0x0; `take` addiert 0x20000, `close`
    addiert 0x40000 (Standard an in `solved`), `fight` addiert 0x10000.
    `taken` (0x4, 137 Retail-Zeilen) wird beim Laden als eigene Ebene
    "Angenommen" gefuehrt, im Tool aber nicht angeboten (Laeuft deckt den
    Fall ab).

Entschieden am 2026-09-13 (Umsetzung M3):

20. Sprecher gelten pro Quest: `{'id', 'name', 'lector', 'tile', 'new'}`,
    der Spieler ist implizit (`speaker: 'player'`, Lector 1). "Neuer NPC"
    prueft die ID gegen den Index **inklusive Mod-NPCs** (Yamalin belegt
    z. B. NPC_700 bis 701). Lector-Dropdown listet jeden Retail-Lector mit
    den Namen seiner NPCs. Heimat-Kachel ist bis zum Kachel-Picker (M5)
    Freitext.
21. Node-Kopf: Sprecherfarbe aus der Palette (Spieler blau), rechts ein
    Zustandsband in der Ebenenfarbe. Je Zeile Ereignis-Glyphen (Haken =
    annehmen, Raute = abschliessen, Schwerter = Kampf). Frage-Nodes haben
    "+ Zeile" und ein x je Zeile direkt im Node, die Art (Antwort/Frage)
    haengt als Dropdown im Kopf. NPC-Nodes haben genau eine Zeile; die
    "Ebene" ist im Kontextmenue und im Panel umstellbar.
22. Panel-Aenderungen: ein Undo-Snapshot je Feld-Fokus, Live-Uebernahme in
    den Graph bei jedem Tastendruck; der Snapshot umfasst den ganzen Quest
    (Graph, Sprecher, Kopffelder).
23. Cue-Suche: Filter nach dem Lector des Sprechers (abschaltbar) und
    Textsuche ueber Cue-Name und Aufnahmetext, Vorschau, Warnung im Panel,
    wenn der Untertitel von der Aufnahme abweicht. Kamera-Standard ist
    "leer"; der Export setzt 2 fuer NPC und 7 fuer Held (wie das alte Tool).
24. Kante ins Leere ziehen oeffnet das Popup Spieler / Sprecher... /
    Kommentar und verbindet sofort (Plan 5.3 umgesetzt).

Entschieden am 2026-09-13 (Umsetzung M4):

25. Import-Abbildung: jede NPC-Zeile wird ein NPC-Node, ein Antwortmenue
    (die `next`-Liste einer Zeile, alle Ziele Held-Zeilen) wird ein
    Spieler-Frage-Node mit einer Zeile je Option, einzelne Held-Zeilen
    werden Antwort-Nodes. Jede Zeile merkt sich `order` (Index im Baum) und
    `tid` (Textschluessel); Export sortiert importierte Zeilen nach `order`
    und haengt neue Zeilen nach Ebene (Angebot ... Abgeschlossen) und
    Gespraechsfluss an.
26. Was sich nicht ueber Ebene und Haken ausdruecken laesst, bleibt roh an
    der Zeile: `raw_flags` (z. B. `0x20` LowRep allein, `0x10000` Fight
    ohne Zustand), `cams` bei leerer oder mehrfacher Kamera, `anim2` wenn
    abweichend, und `next_ref` = {Zielnode, Zeilenauswahl, negative
    Indizes} fuer Referenzen, die vom Standard abweichen (Teilmenge eines
    Menues, Rueckschleife mit negativem Index). `next_ref` gilt nur,
    solange die Kante auf denselben Node zeigt; wird sie umgehaengt, gilt
    wieder der Standard. Negative Indizes erzeugt das Tool selbst nie.
27. TakeNow-Pfad (6.3): beim Export bekommen neue Zeilen derselben Ebene
    hinter einer "Nimmt die Quest an"-Zeile ebenfalls das Bit;
    importierte Zeilen behalten ihre exakten Retail-Flags.
28. Sprecher beim Import: Lector wird ueber den Index einem NPC
    zugeordnet, bevorzugt dem Questgeber der Quest; ohne Treffer entsteht
    ein Platzhalter-Sprecher `L<lector>`. Beim Laden aus dem Spiel werden
    Titel, Tagebuchtexte, Gruppe, Giver, Giver-Typ und Level aus Index und
    `.lan` uebernommen, die Quest ist `retail=True`.
29. Baumquelle `data.load_trees`: Basis-`.lan`, `Content01/02_Lan.wd`, alle
    `Mods\*.wd`, spaeterer gewinnt (README 3.2), einmal pro Sitzung
    geparst (0,8 s). Die Retail-Zeitleiste (M6) ersetzt den Auswahldialog.
30. Neue Textschluessel: `translateDQ_<id>_<ebene>_<n>` mit den Suffixen
    `0.FT`, `0.FT.AS` (Angebot mit Annahme), `0.QNT`, `0.QNS.AE`, `0.QT`,
    `0.QS.AE`, `0.QC`, `0.QF`, `0.LR`, `0.X` (neutral). Nur Namenskonvention,
    das Spiel liest die Schluessel nicht aus.

Entschieden am 2026-09-13 (Umsetzung M5):

31. Spalten jedes Opcodes stammen aus dem SDK-Loader
    (`PQuestLoader.ech`, `ParseFC`, `ParseACT`, `ParseRWD`). Dabei
    korrigiert: ENEMY_CREATE hat die Marker-Nummer in Spalte 4
    (`<typ> <anzahl> <level> <marker> <kachel> <partei>`), OBJECT_CREATE in
    Spalte 2 (`<objekt> <marker> <kachel>`); `INDEX_FORMAT` 3. Angeboten
    werden nur Opcodes, die `tw1_qtx` validiert. Der Loader kennt zusaetzlich
    `NPC_DIALOG`, `OBJECT_ADD`, `OBJECT_REMOVE`, `CHANGE_RELATIONS`,
    `ACTIVATE_LEVEL`, `KILL_AREA_DELAYED`, `FC OPEN` und `REWARD RND`; sie
    fehlen in `tw1_qtx` und bleiben draussen. Entschieden (Marco
    2026-09-13, 12.51): `tw1_qtx` wird nicht erweitert.
32. Aufgabe = fester Node `task` links neben dem Einstieg Erfuellt (nicht
    loeschbar, nicht verschiebbar). Aktionen = Nodes, die an einen
    Dialog-Node andocken und darueber gestapelt werden (bewegen sich mit,
    werden mit geloescht und kopiert). Bedingungen = Nodes unter dem
    Einstieg Angebot (`after`, `level`, `guild`); Kopfzeile `enableLevel`,
    `guild`, `minRep` kommen aus ihnen. Aktionen ohne Dialog stehen in
    `quest.actions` mit eigenem Zeitpunkt (Quest-Panel). Neue Quests
    bekommen "nach Q_4 angenommen" und "ab Level 1"; der erste NPC-Sprecher
    wird Questgeber.
33. AOQ-Export: vor dem Einfuegen werden alle
    `AOQ PROMOTE|TAKE <ereignis> Q_<id>`-Zeilen im ganzen `.qtx` entfernt,
    dann je Bedingung "Nach Quest" eine Zeile in den Block der
    Vorgaengerquest gesetzt (hinter die letzte AOQ, sonst hinter FC oder
    GIVER). PROMOTE bei "wird angeboten", TAKE bei "startet automatisch".
    Wiederholter Export erzeugt keine Duplikate.
34. Neue NPCs (`new=True`): der Export setzt einen NPC-Block
    (`NPC ...`, `OBJECTS True`, `END`) vor den Questblock. Grundlage ist
    der Record einer Vorlage (Feld "Aussehen wie NPC", sonst der NPC der
    gewaehlten Stimme, sonst Tago); ersetzt werden ID, Q_Giver-Marker
    (Spalte 3, Yamalin nutzt dort abweichende Nummern wie `NPC_500 500 10`),
    Kachel, Blickrichtung und Lector. Der Anzeigename geht nach
    `translateNPC_<id>`. **[PRUEFEN]** Partei, Gilde, `SMALL`, `True/False`,
    Aussehen-String und letzte Zahl werden unveraendert von der Vorlage
    uebernommen.
35. Export-Ablauf: Basis sind `.qtx` und `.lan` aus dem Zielarchiv, sonst
    Update16 und Language.wd. Drei Dateien: volle `.qtx`, volle Master-`.lan`,
    `Language\ZZ_QF_<Projekt>.lan`. Packen mit wdio (entpacken ohne
    GUID-Datei, wie das alte Tool), danach Vergleich aller Dateien byte-genau
    und aller unberuehrten Eintraege inklusive Flags, Name, Klassen-ID und
    GUID-Vorhandensein; erst dann ersetzt `.new` das Archiv. Einmalige
    Sicherung `<Archiv>.qf2backup` vor dem ersten Export. Registry-DWORD = 1.
    `wd_metadaten.py` wird nicht gebraucht: `.qtx` und `.lan` tragen keine
    Verzeichnis-Metadaten, und unberuehrte Eintraege behalten ihren
    Kopfsatz-Strom.
36. Vor dem Export: Pflichtfehler blockieren (Liste mit Sprung zum Node),
    Warnungen fragen nach; laufendes Spiel (`TwoWorlds.exe`,
    `TwoWorlds_RADEON.exe`) blockiert; andere aktive Mods, die ebenfalls die
    volle `.qtx` oder Master-`.lan` liefern, werden mit Empfehlung gemeldet
    (README 3.1). Bei Marco liefert Yamalin.wd beides, deshalb ist fuer
    Tests Yamalin.wd das richtige Ziel.
37. Hintergrund-Threads (Index-Aufbau, Export) melden ueber `queue.Queue`,
    der Hauptthread holt ab. `root.after` aus einem Nebenthread ist nicht
    threadsicher und scheiterte ohne laufende Hauptschleife.
38. Spieltest-Paket (6.3 Schritt 4a/4b): `testprojekte/Test_4a_Ablehnen` und
    `Test_4b_TakeLetzteZeile`, beide Q_386 (in Marcos Yamalin die einzige
    freie ID), Questgeber Tago, Bedingung "nach Q_385 abgeschlossen" (daran
    haengt in Yamalin nichts; "nach Q_4 angenommen" wuerde gleichzeitig mit
    Q_385 freigeschaltet), Aufgabe 10 Gold bringen, Belohnung 1234 Gold als
    sichtbarer Beweis, Zielarchiv Yamalin.wd. Alle Dialogzeilen tragen
    `[TEST 4a]`/`[TEST 4b]` als Ladungsmarker.
    Nachtrag 2026-09-14 (Marco): Q_385 "Der Schutzgelderpresser" war eine
    Testquest des alten Tools und ist aus Yamalin.wd entfernt (Block, AOQ in
    Q_4, Texte, Dialogbaum, `ZZ_TagoQuest.lan`; Original in
    `Yamalin.wd.qf2backup`). Beide Testprojekte haengen jetzt an "nach Q_4
    angenommen".

Entschieden am 2026-09-13 (Umsetzung M6 bis M10):

39. Arbeitsweise: Marco hat nach M5 angewiesen, das Tool ohne Halt vor jedem
    Meilenstein fertigzustellen ("mach das tool jetzt fertig komplett"). M6
    bis M10 wurden deshalb ohne Einzelbesprechung umgesetzt; Commits bleiben
    auf Anweisung.
40. Spielquests im Projekt (`retail.py`): Der `QUEST`-Block wird ins Modell
    importiert (Kopfzeile als Bedingungen, GIVER, Aufgabe, Aktionen und
    Belohnungen als Aktionen ohne Dialog). Was nicht exakt abbildbar ist
    (AOQ-Zeilen, `CHANGE_RELATIONS`, `DISABLE_TOWN`, `ENABLE` usw.), bleibt
    roh. Der Originalblock und eine Signatur der importierten Felder stehen in
    `quest.extra['qtx']`; solange die Signatur gleich ist, wird der
    Originalblock exportiert. Ergebnis: alle 500 Retail-Bloecke und alle 522
    Bloecke der Installation mit Yamalin byte-gleich, 829 rohe Zeilen.
    Geaenderte Bloecke werden neu gebaut (Kopf, GIVER, FC, AOQ, ACTION,
    REWARD, rohe Zeilen) und behalten alle Zeilen. Die Gruppe `(null)` (Q_700)
    bleibt als Token erhalten.
41. Zeitleiste (`timeline.py`): Karten aus Index und Projekt, Reihenfolge per
    Kahn-Algorithmus ueber `AOQ PROMOTE/TAKE` (kleinste ID zuerst, Zyklen nach
    ID aufgebrochen, Quests ohne Kette dahinter), Gruppen als Abschnitte in
    der Reihenfolge ihrer ersten Quest. Zoom als Schalter "grosse Karten"
    statt Regler. Neuzeichnen 30 ms bei 522 Karten.
42. Spielquest oeffnen = Ansicht (`App.preview`), nicht im Projekt. Die
    erste Aenderung fragt (Plan 10); Nein setzt auf den Stand beim Oeffnen
    zurueck, Ja nimmt die Quest ins Projekt (`retail=True`). Texte eines
    Retail-Baums ohne eigenen Schluessel (`notext`) werden nur geschrieben,
    wenn Text eingetragen wird; Tagebuchschluessel, die eine Spielquest nie
    hatte, werden nicht angelegt. Alle 378 Retail-Baeume zusammen ergeben die
    Master-`.lan` byte-gleich.
43. Quest-Menue: Duplizieren (eigene Quest mit freier ID, Textschluessel
    neu), Loeschen (aus dem Projekt), Als Vorlage speichern /
    Neue Quest aus Vorlage (`templates/*.tw1quest`), Validieren F7, Vorschau
    mit `.qtx`-Block. Neue Quests uebernehmen die Tagebuchgruppe von Q_4.
44. Validierung (`validate.py`) nach Abschnitt 8 mit Sprungziel (Node-ID,
    `qaction:<i>` oder Quest-Feld). Regel "Kante ueber Tab-Grenzen" entfaellt
    (12.18). Zusaetzlich zu Abschnitt 8: Vorgaengerquest aus einer anderen Mod
    als dem Zielarchiv ist ein Fehler (dort fehlt der Block fuer die
    AOQ-Zeile), Tagebuchgruppe ohne Namen ist eine Warnung. Feldfehler
    kommen als `model.FieldError` mit Feldname. Statusleiste validiert
    600 ms nach jeder Aenderung.
45. Coach (`guide.py`): Rundgang mit 15 Schritten, Tutorial mit 11
    Schritten und Zustandspruefung (Weiter gesperrt bis erledigt, automatisch
    weiter nach 0,9 s), jeder Tutorial-Schritt mit "Fuer mich erledigen".
    Goldrahmen = vier `place`-Frames auf dem Root. Rundgang startet beim
    ersten Start nach dem Index, Haken "Beim Start nicht mehr zeigen" ist
    vorbelegt. Hilfe > Dokumentation rendert `README.md` (Ueberschriften,
    Listen, Code, Tabellen monospace).
46. Menues: eigene Klasse `theme.Menu` (Segoe UI 10). Windows zeichnet
    deaktivierte `tk.Menu`-Eintraege eingepraegt und schwer lesbar (Marcos
    Rueckmeldung); deaktivierte Eintraege sind daher technisch aktiv, in
    `DIM`, ohne Hover und ohne Befehl. Menueleiste in `INK` statt `MUT`.
    Design aller Tools festgehalten in `Desktop\PY_TOOL_DESIGN.md`.
47. Spielerkennung vor dem Export: jeder Prozess `TwoWorlds*.exe` (bei Marco
    laeuft `TwoWorldsExtended.exe`, das die alte Liste nicht kannte).
48. Exe (M9): `TW1QuestCreator.pyw` als Einstieg, `build_exe.spec` (onefile,
    ohne Konsole, Icon, README und Icons als Daten, Tests und Altwerkzeuge
    ausgeschlossen), `build_exe.bat` mit PyInstaller 6.18 unter Python 3.13
    (unter 3.12 ist PyInstaller nicht installiert). Groesse 11,5 MB. Icon
    eigene Grafik aus `tools/make_icon.py`. Selbsttest ohne Fenster:
    `QF2_SELFTEST=<datei>` (Startzeit), zusaetzlich
    `QF2_SELFTEST_EXPORT=<projekt>|<spielordner>` (Export ohne Registry).
    Gemessen: erster Start der Exe mit Index-Aufbau 1,84 s, zweiter Start
    0,38 s bis bereit (1,86 s inklusive Entpacken und Beenden), Export mit
    Pruefung in der Exe erfolgreich.
49. Doku (M10): README Abschnitt 6.1 (Flags laut SDK) und 13 (QuestForge 2),
    Modul-Referenz, Guide-HTML Abschnitt 12 mit Fensterskizze, Skill-Datei
    mit Flag-Tabelle und Loader-Spalten.
50. Hilfe-Menue (Marco 2026-09-13): die vier Links (GitHub-Repo,
    `https://alchemy-fox.de/`, Guide-Seite, `https://twmp.alchemy-fox.de/`)
    stehen klickbar direkt im Hilfe-Menue und im Ueber-Dialog. Sichtpruefung
    der Menues nach 12.46 per Screenshot erledigt: Segoe UI 10 normal,
    deaktivierte Eintraege flach grau ohne Schatten. Die Design-Vorlage fuer
    weitere Tools liegt ausserhalb des Repos (`Desktop\PY_TOOL_DESIGN.md`)
    und gibt nur Farben, Menueleiste, Guide beim Start und Hilfe-Links vor.
51. `tw1_qtx` bleibt unveraendert (Marco 2026-09-13). Die Loader-Opcodes
    ausserhalb von `tw1_qtx` (12.31) bietet das Tool nicht an. Commit von
    M6 bis M10 auf `questforge2` freigegeben.
52. Bedienung nach erstem Ausprobieren (Marco 2026-09-13):
    - Sprachumschalter `DE · EN` oben rechts in der Menueleiste, links vom
      Programmnamen, aktive Sprache gold (Design-Vorlage 5.3). Ein Klick
      baut das Hauptfenster sofort neu auf; Projekt, offene Quest, Undo,
      Index, Zoom, Scrollposition und Panelgroessen gehen mit, kein Dialog.
    - Mausrad zoomt um den Mauszeiger, Strg+Rad scrollt senkrecht,
      Umschalt+Rad waagerecht. Zoomstufen 30 bis 200 % in 12 Stufen.
    - Dialog-Nodes zeigen den vollen Text: jede Zeile bricht um, der Node
      waechst nach unten (`model.line_tops`, Umbruch mit der Zeilenschrift
      bei 100 %). Ports sitzen auf der ersten Textzeile ihrer Zeile.
    - Der Scrollbereich des Graphen umfasst immer alle Nodes plus Rand;
      vorher lagen Nodes ausserhalb des festen Bereichs und waren
      abgeschnitten.
    - Scrollbalken-Schieber hellgrau (`SCROLL_THUMB` #7a7061), gold bei
      Hover und Ziehen; vorher PANEL auf BG, kaum sichtbar.
53. Spieltest 4a bestanden (Marco 2026-09-14). Testprojekt 4a mit dem Tool
    exportiert in Yamalin.wd (Q_386 bei Tago, nach Q_4 angenommen, 10 Gold
    bringen, 1234 Gold Belohnung), neues Spiel: laeuft sauber durch.
    Bestaetigt damit: Ablehnen im Angebot ohne Annahme-Haken nimmt nicht an,
    die Ebene "Bekannt" spielt danach, der Annahme-Haken traegt die Quest
    ein (5.2, Hypothese A); `AOQ PROMOTE TAKE` in Q_4 schaltet frei (6.4);
    Export mit AOQ-Einfuegen, Overlay-`.lan`, `FC BRING_GOLD` und
    `REWARD GLD CLOSE` wirken im Spiel. Damit ist auch die erste
    Tool-Quest (M5) im Spiel geprueft. Vorher entfernt: Q_385 (siehe 12.38).
54. Export-Fehler beim Wechsel 4a auf 4b gefunden und behoben (2026-09-14,
    Version 2.1.1): Exportierte ein zweites Projekt dieselbe Quest-ID ins
    selbe Archiv, blieb die `ZZ_QF_<anderes Projekt>.lan` mit Titel,
    Tagebuch und Dialogbaum derselben ID liegen und konkurrierte mit dem
    neuen Overlay (das Spiel nimmt das zuletzt geladene). Der Export
    entfernt jetzt aus fremden `ZZ_QF_*.lan` des Zielarchivs alle Schluessel,
    Aliase und Baeume der exportierten Quest-IDs; bleibt nichts uebrig, wird
    die Datei aus dem Archiv geloescht (`export.clean_other_overlays`,
    `pack_archive(remove=...)`, geprueft wie alle anderen Eintraege, Test
    `test_other_project_overlay_cleaned`). Nur `ZZ_QF_`-Dateien des Tools
    werden angefasst, fremde Overlays nie.
55. Spieltest 4b bestanden (Marco 2026-09-14). Testprojekt 4b mit Version
    2.1.1 in Yamalin.wd exportiert (dabei `ZZ_QF_Test_4a_Ablehnen.lan`
    automatisch entfernt, 12.54), neues Spiel: laeuft sauber durch.
    Bestaetigt: TakeNow (`0x20000`) nur auf der letzten NPC-Zeile des
    Angebots reicht; die Held-Zeile "Warum?" davor ohne TakeNow nimmt nicht
    an. Der Annahme-Haken muss also nicht auf dem ganzen Pfad sitzen.
56. Spieltest M6 bestanden (Marco 2026-09-14). Retail-Quest Q_4 "Ein
    Lichtstreif..." im Tool aus dem Spiel geladen (`build_game_quest`,
    Import mit Signatur), Belohnung `REWARD GLD TAKE SMALL` auf 777, Titel
    und alle 33 Dialogzeilen mit `[TEST M6]` markiert, als
    `testprojekte/Test_M6_Q4Belohnung` in Yamalin.wd exportiert. Im Archiv
    geaendert nur der Q_4-Block der `.qtx` (Rest byte-gleich, fremde
    Rohzeile `AOQ PROMOTE TAKE Q_386` erhalten), 34 Q_4-Schluessel der
    Master-`.lan` (alle 601 Baumstrukturen identisch) und das neue Overlay.
    Neues Spiel: Texte, Titel und 777 Gold erscheinen, laeuft sauber durch.
    Damit sind alle Meilensteine im Spiel bestaetigt.
57. Questgrenze integriert (Marco 2026-09-15, Version 2.5.0, Branch `v2.5`).
    Der TW1 Quest Limit Patcher 1.0 (`Desktop\TW1QuestLimitPatcher`, eigenes
    Repo, unveraendert) ist als `questforge2/questlimit.py` uebernommen: 41
    Immediates in `PQuests.eco` (Update16, SHA-256 geprueft) von 400 auf
    600, Ablage als `Mods\QuestLimit600.wd` mit frischer GUID, Flags 0x3b,
    Ressource `PQuests`, Klasse 4, Rueckleseprobe, Registry-Export vor jeder
    Aenderung. Das Tool liest beim Start die wirksame Grenze (eigene Mod,
    sonst eine andere aktive Mod mit eigenem Questskript wie
    `QuestMigrate.wd`, sonst 400; 6 ms): freie IDs 381 bis Grenze-1,
    Statusleiste "Grenze", Quest-Menue "Questgrenze", Fenster mit Anheben und
    Zuruecknehmen, bei vollen IDs Angebot zum Anheben. Validierung: Fehler bei
    ID ueber der Grenze (`val.id.limit`), Warnung ab 400
    (`warn.id.limit600`: Spieler brauchen die Grenz-Mod, nur neue Spiele).
    Beleg fuer die Grenze im Spiel: Q_400 bis 402 und Q_599 liefen am
    11.09.2026 mit Grenze 600 und frischer GUID (Kira-Kampagne, HANDOFF).
    Ein Spieltest einer mit dem Tool exportierten Quest ueber 399 steht aus;
    Marco hat entschieden, ohne ihn zu releasen. Tests
    `test_questlimit.py` (Patch, Archiv-Rundlauf, apply/remove mit
    Ersatz-Registry, andere Mod mit 600, Validierung).
58. Partei-Feld mit Namen (Version 2.5.1, nach einer Frage von Orion im
    Discord: "which number is which faction?"). Die Nummern stehen im SDK in
    `Scripts\Common\Enums.ech`: 18 Tiere (allgemeine Gegner), 19
    Gruenhaeute, 20 Banditen, 21 Untote, 22 verseuchte Untote, 23 boese
    Krieger, 24 Geister, 25 Menschen (neutrale NPCs), 26 bis 42 die
    Stadtparteien (Cathalon, Qudinaar, Ashos, Komorin, Karga, Skelden,
    Windmuehle, Covenant, Vier Steine, Clovelly, Aussenposten, Kehar,
    Siedlung, Nekro-Dorf, Gorelin, Rovan, Tharbakin), 43 neutrale Banditen;
    0 bis 17 sind Spieler und deren Gegner und kommen in Quests nicht vor.
    Die Original-Quests nutzen 19 (77x), 21 (59x), 18 (19x), 20 (6x), 25
    (2x), 22 und 23 (je 1x). Das Feld ist jetzt eine Auswahlliste
    "Nummer + Name" (`model.PARTIES`, `party_label`, `parse_party`), bleibt
    aber frei tippbar; darunter ein Hinweis, dass ab 24 neutrale und
    Stadtparteien stehen, die von sich aus nicht angreifen (aus dem SDK
    abgeleitet, nicht im Spiel gemessen).
59. Gegnerstufen der Welt (Version 2.6.0, nach Orions Frage im Discord, wie
    man Tiere und Gegner auf Heldenniveau bringt). Gemessen: `CreateEnemy`
    im SDK (`Scripts\Common\Enemies.ech`) nimmt die mittlere Heldenstufe,
    addiert den Gruppenzuschlag und klemmt dann je Art auf das Paar aus
    `InitializeEnemyLevels`; Karten ab Reihe 10 geben plus 5; ein
    ausdruecklicher Wert in `ENEMY_CREATE` (`nForceLevel`) schlaegt die
    Klemme. In der `.par` steht davon nichts (Feldnamen des PAR-Editors
    geprueft). Die 90 Paare liegen im kompilierten Skript als 32-Bit-Werte
    in Quelltextreihenfolge, je Aufruf `max, min, [marker], typ`; gefunden
    wird die Reihe ueber die Typnummern, nicht ueber die Stufen, damit auch
    ein bereits geaendertes Skript gelesen werden kann. Das Fenster
    (Quest > Gegnerstufen der Welt) zeigt alle Arten nach Gruppen, mit
    Filter, Regler plus Eingabefeld und Schnellwahl; `apply` schreibt beide
    Skriptfassungen mit je frischer GUID als `Mods\EnemyLevels.wd`, nach
    Registry-Sicherung und mit Rueckleseprobe. Tests `test_enemylevel.py`.
    Offen: Spieltest im Spiel (Stufen neuer Gegner).
60. Bedienung nach Marcos Rueckmeldung (Version 2.6.1):
    - "+ Neue Aktion" zieht jetzt sichtbar: ein Etikett haengt am Mauszeiger,
      der Ziel-Node bekommt einen goldenen gestrichelten Rahmen
      (`graph.highlight_drop`), die Statusleiste sagt "Hier ablegen" oder
      "Auf eine Dialog-Node ziehen". Aufgabe, Aktion und Bedingung haben
      Hilfetexte beim Ueberfahren.
    - Zahlenfelder mit fester Bedeutung bekommen Namen: nach der Partei
      (12.58) jetzt auch die Gilde (200 keine, 201 Magier, 202 Krieger,
      203 Haendler, 204 Diebe, 205 Nekromanten, 207 Karga, 208 Skelden;
      206 ist im SDK unbenutzt). Uebrige Zahlenfelder (Anzahl, Stufe,
      Radius, Marker, Animation 0 bis 17) haben keine bekannten Namen und
      bleiben Zahlen.
    - Questgrenze und Gegnerstufen sind zusaetzlich Knoepfe in der Kopfleiste
      der Zeitleiste; die Beschriftung der Questgrenze zeigt den wirksamen
      Wert.
    - Statusleiste wird vor den Panels gepackt, sonst schnitt sie ein
      kleines Fenster ab (bei Marco war sie nur im Vollbild zu sehen).
61. Zeitleiste lesbarer (Version 2.7.0, Marco 2026-09-16):
    - Jede Tagebuchgruppe hat eine eigene Farbe (`theme.group_color`, zwoelf
      Farben reihum, `theme.mix` blendet sie fuer Fuellung und Reiter).
      Karte: farbiger Balken links, farbiger Rahmen, leicht getoente
      Fuellung; eigene und geaenderte Quests behalten den goldenen Rahmen.
    - Die Gruppenueberschrift zeigt jetzt die Zahl der Quests statt der
      Gruppennummer (die Klammer wurde als Anzahl gelesen).
    - Neue Reiterleiste ueber den Karten: ein Reiter je Questreihe mit
      Anzahl plus "Alle", in Kettenreihenfolge, unabhaengig vom gewaehlten
      Filter, waagerecht scrollbar; Klick setzt den Gruppenfilter.
    - Kleine Karten schneiden den Titel einzeilig ab statt umzubrechen.
62. Usability-Update, Teil 1 (Version 2.8.0, nach
    `Desktop\PROMPT_QuestCreator_Usability_Update.md`, Punkte 2, 3, 4, 6;
    5b Mod-Quellen, 5c Karte, 7 Vorlagen und 8 Guide-Fenster kommen danach,
    Reihenfolge von Marco: Guide zuerst):
    - Zentrale Tabelle `model.NUMBER_LISTS` (Wert, Quelle, belegt oder
      ungeprueft) fuer Partei, Gilde, AOQ-Typen, AOQ-Ausloeser,
      Aktionszeitpunkte und Animationen. Die Picker lesen daraus; die
      Referenztabellen des Guide-Fensters sollen spaeter dieselbe Quelle
      nutzen.
    - Animation ist eine Liste "Geste 0" bis "Geste 17" mit Hinweis: die
      Bedeutung steht nirgends (`anTalk0..17` in der par), im Original sind
      0, 10, 11, 17 am haeufigsten. `SET_WORLD_STATE` und `PLAY_CUTSCENE`
      bekommen den Hinweis "ungeprueft" (`model.UNVERIFIED_FIELDS`).
    - Quest-Verknuepfungen: `Quest.links` speichert echte AOQ-Zeilen dieser
      Quest, der Export schreibt sie (`tw1_qtx.sub_aoq`), die Validierung
      prueft Typ, Ausloeser und Ziel. Damit sind Ketten, Tore und
      Mehrfachentscheidungen im Tool baubar, nicht nur ueber Bedingungen.
    - Hilfe-Fragezeichen an Panel-Titeln und Feldern (Tooltip plus Klick
      oeffnet die Doku; das eigene Guide-Fenster folgt in 2.9.0).
    - Beispiele als Platzhalter in leeren Feldern, Sofortpruefung mit roter
      Begruendung (keine Zahl, falsche Kachel, Semikolon, Nicht-ASCII).
    - Live-Vorschau der qtx-Zeile unter Aufgabe und Aktion.
    - Kontextmenue auf angedockten Aktionen und Bedingungen: Bearbeiten,
      nach oben, nach unten (Reihenfolge ueber `slot`).
63. Usability-Update, Teil 2 (Version 2.9.0, Punkte 5, 7, 8):
    - Guide-Fenster `questforge2/guidebook.py` (Hilfe > Guide, F1): 14
      Kapitel DE/EN, Suche mit Trefferliste und Markierung, die `?`-Marken
      springen ins passende Kapitel (`HELP_CHAPTER`). Tabellen werden aus
      `model.NUMBER_LISTS`, `FC_SPECS`, `ACTION_SPECS`, `data._FC_MARKERS`,
      `_ACTION_MARKERS` erzeugt, mit Quelle und Status. Kapitel "Mods einbinden"
      beschreibt den heutigen Stand; eigene Mod-Quellen und die Karte folgen.
    - Vorlagen `questforge2/templates/*.json`: vier Quest-Vorlagen (Bring,
      Toete, Sprich, Kette mit Tor ueber enable_level 2), vier
      Gegnergruppen. Mit dem Modell erzeugt, Test baut jede Quest-Vorlage und
      packt alle in ein Archiv. Im Spiel noch nicht einzeln gespielt.
    - Dialog "Neue Quest": leer, Vorlage, Kopie (Projekt- und Spielquests);
      `model.copy_references` schreibt Selbstverweise um und listet fremde.
    - Warnung `warn.todo` fuer uebrig gebliebene TODO-Stellen.
64. Mods als dritte Quelle (Version 3.0.0, Punkt 5b):
    - `questforge2/mods.py`: liest `.wd` (Verzeichnis mit Flags, Name,
      Klassen-Id, GUID; Daten nur fuer qtx, lan, lnd) und Ordner (wdio-Kopf
      wird ausgepackt). Herkunft je Inhalt: Mod, Pfad, Datei, Tile. Cache je
      Mod in `cache/mods/<hash>.json` (mtime/Groesse bzw. Hash der relevanten
      Ordnerdateien plus Stempel der Basis-qtx). `tw1_lnd.py` als Kopie aus
      QuestForge uebernommen (unveraendert).
    - Karten des Spiels: `retail_markers` liest nur den Markerabschnitt jeder
      `Levels\Map_*.lnd` (teilweises Entpacken, 160 Tiles in 0,25 s),
      `Levels.wd` < `Update11-15.wd` < `Update16.wd`. Tile-Namen
      `Map_E01` = `E1`, `Map_B08_1` = `B8_1`.
    - Markernamen je Befehl aus SDK `PEnums.ech` (`MARKER_NAMES`); gemessen
      16.09.2026: 287 von 287 Markerverweisen der Original-Quests und 216 von
      216 NPC-Startmarkern liegen unter diesen Namen auf ihrem Tile.
    - Projektdatei: `mods` [{path, enabled}] und `mod_tiles` {tile: mod},
      nur geschrieben, wenn belegt. Leere `links` (seit 2.8.0 immer
      geschrieben) werden wieder weggelassen: alte Projekte speichern
      byte-gleich bis auf `tool_version` (Test).
    - Mod-Quests: Oeffnen aus der Mod (Questblock + Baum aus den lan der Mod,
      sonst Spiel), Bearbeiten ohne Projektkopie, Speichern ueber
      `mods.write_quest`: `export.patch_qtx`, `build_lan` in die lan der Mod,
      die den Baum oder Titel traegt (sonst `TwoWorldsQuests.lan`, sonst
      Overlay `ZZ_QF_Mod_<Name>.lan`), Sicherung `<Mod>.bak-<Datum>` einmal
      pro Tag, `pack_archive(backup=False)` prueft alle uebrigen Eintraege
      inklusive exakter GUID, danach `metadata_problems` gegen die Archive des
      Spiels (Port von `wd_metadaten.pruefen`, qtx/lan ausgenommen, neue
      Abweichungen brechen ab). Wiederherstellen sichert den aktuellen Stand
      vorher als `...-before-restore`.
    - Abhaengigkeiten: `mods.dependencies` leitet aus den Markerverweisen der
      Projektquests ab, welche Mod-Karten mit muessen (Status ok, missing =
      rotes Tile, conflict = mehrere Mods). `pack_archive` nimmt dafuer
      `tw1_wd.Entry` mit Metadaten an und stagt sie in wdio-Kopfform.
      Echttest mit Kopien von Yamalin.wd und Dream Worlds CE 3.0: D8-Marker
      aus Yamalin -> Karte im Export, Metadaten und Daten gleich, keine
      Abweichung gegen die Spielarchive; F8_1 rot -> gesperrt und Fehler.
      Befund: Dream Worlds CE 3.0 fehlen auf 9 Tiles Marker des Spiels (E2: 25).
    - UI: Menue Mods, `modswin.py` (Mods verwalten, Abhaengigkeiten,
      Speicherhinweis), Zeitleiste mit "Quellen" und Mod-Bereich, Picker mit
      Kartenmarkern, blauen Punkten, roten Tiles, Sperre und Rueckfrage,
      Mod-Quests im Kopierdialog und in den Questlisten. Hellblau `theme.MOD`
      nur fuer Mods; die Gruppenfarbe `#8fa8d8` wurde dafuer ersetzt, Blau fuer
      die Enklave (Marcos Wunsch 12.61) bleibt.
    - Ungeprueft: Ladereihenfolge zweier Mods im Spiel.
65. Interaktive Karte (Version 3.1.0, Punkt 5c):
    - `questforge2/mapdata.py`: Minimap-Tiles `Levels\MipMaps\Map_<Tile>@0..3.dds`
      (DXT1, 512/256/128/64 px; 108 Oberflaechen-Tiles A1..I12 vollstaendig,
      52 Innenraeume). Eigener DXT1-Decoder (gegen Pillow verglichen: 0 von
      196.608 Bytes weichen um mehr als 1 ab) und PNG-Schreiber, damit keine
      Bildbibliothek ins Paket muss. Cache `<Projekt>_map/` (ungespeichertes
      Projekt: `cache/maptiles`), Stempel aus Archivposition der DDS.
    - Umrechnung: Kartenkopf 128 x 128 Zellen (20 Byte nach dem Namen, alle
      Map_*.lnd), SDK `TwoWorldsHeroControl16.ec` `nX/=256`, also Tile =
      32768 Einheiten, 64 Einheiten je Pixel bei 512 px. y waechst auf der
      Minimap nach oben (Zeilen nach unten). Sichtpruefung 16.09.2026 mit
      Overlays: D8 Tore in beiden Stadttoren und Wachrouten auf Strassen (ohne
      Spiegelung alles ausserhalb der Mauern), F8 Truhen im Ringbau, E1
      Teleporter am Wegende, B8_1/D8_1 Marker in den Gaengen, Wege laufen ueber
      Kachelgrenzen weiter. Im Spiel nicht nachgemessen; `POSITIONS_CHECKED`
      und der Hinweis im Fenster sagen "per Sichtpruefung".
    - LOCATION x/y sind Zellen (`PLocations.ech` `AddLocation(.., A2G(nX)`).
    - Marker-Gruppen aus den Abschnitten von `PEnums.ech`,
      `TwoWorldsEnemies16.ec` (`MARKER_ENEMY_*`, `MARKER_TRAP*`),
      `TwoWorldsTeleports.ec`; im Spiel vorkommende Namen ohne SDK-Eintrag
      (`MARKER_CAMP_*`, `MARKER_DANCE`, `MARKER_DUMMY`) unter "Sonstige".
      10.342 Punkte aus den Karten des Spiels plus 116 Orte.
    - `questforge2/mapwin.py`: nicht-modales Fenster, Zoomstufen 64..1024,
      Ziehen, Gitter und Tile-Namen, Ebene Oberflaeche/Innenraeume, Filter
      (Herkunft je Mod, Typ, benutzt/unbenutzt, Suche mit Sprung), Liste
      synchron zur Karte, Hover-Tooltip, Blinken, "In Quest verwenden" mit
      Sortenpruefung und `confirm_mod_marker` (rote Tiles, Build-Hinweis).
      Anbindung: Kopfleiste, Ansicht-Menue, Karte-Knopf an Marker-Feldern und
      im Picker, "Auf der Karte zeigen" im Picker und in den Abhaengigkeiten,
      "Marker dieser Quest" im Zeitleisten-Kontextmenue.
    - Tests `tests/test_map.py`: DXT1-Block, PNG, Umrechnung hin und zurueck,
      Gruppen, Punkte aus Spiel und Mod.
66. Abnahme des Usability-Updates (Version 3.2.0, Abschnitt 9 des Prompts):
    - Luecken aus dem Abgleich geschlossen: "Rohtext bearbeiten" unter der
      Vorschau von Aufgabe und Aktion (Punkt 6; Parser ueber
      `retail.args_from_tokens` und `model.op_tokens`, ungueltige Eingaben
      aendern nichts), Dialog-Vorlage "Standard-Questgeber"
      (`templates/dialog_standard_giver.json`, `model.insert_dialog`, Punkt 7),
      Quellenangabe unter jeder Guide-Tabelle (Tastenkuerzel, Aufgaben,
      Aktionen, Bedingungen, Fehlersuche).
    - Projekte: alle vier Testprojekte laden und speichern byte-gleich bis auf
      `tool_version` (Test), Export (qtx, lan, Overlay) mit 2.7.0 und 3.2.0
      SHA-1-gleich fuer alle vier Projekte.
    - Vorlagen: jede Quest-Vorlage validiert, baut ihren Block und packt in ein
      Archiv (Test); die Dialog-Vorlage baut einen Baum. Im Spiel noch nicht
      gespielt, siehe Offen.
67. Multiplayer-Quests uebernehmen (Version 3.3.0, Community-Frage von Orion
    am 16.09.2026, Marcos Vorgabe: Marker setzt der Nutzer im Editor, das Tool
    liefert nur die Liste):
    - Gemessen im SDK: `PQuests.ec` `eFirstQuest 0`, `eQuestsNum 400`,
      `eFirstQuestUnit 0`, `eQuestUnitsNum 698`; `PQuestsMulti.ec`
      `eFirstQuest 699`, `eQuestsNum 300`, `eFirstQuestUnit 699`.
      `ParseQuestNumber`/`ParseGiverNumber` verwerfen alles ausserhalb: Q_700
      und NPC_700 werden im Einzelspieler nie geladen. 120 MP-Quests
      (Q_700..Q_819, 131 MP-NPCs ab 700) stehen in derselben qtx, Bloecke mit
      `(null)`-Kacheln, `ParseMissionNumber("(null)")` = eNoMission im
      Einzelspieler-Build. Retail-NPCs des Einzelspielers enden bei NPC_506;
      MP-Baeume (60) haben Lector -1.
    - `questforge2/mpmerge.py`: `marker_refs` (Zeilen mit Marker+Kachel aus
      den Specs), `plan` (Checkliste: Geber `MARKER_QUEST_START <npc>` zuerst;
      Nummern bleiben, wenn die Retail-Kachel sie nicht hat, sonst naechste
      freie, geteilte Nummern bleiben geteilt), `apply` (make_own, Geber als
      neuer Sprecher mit Kachel, Marker = NPC-Nummer, Partei 25, Platzhalter-
      Sprecher "Lector -1" wird der Geber, Level 0 -> 1, `extra['mp_source']`
      und `extra['markers_todo']`). `MpMergeWindow` in drei Schritten.
    - Quest-Panel: Checkliste mit Haken (im Projekt gespeichert), Knopf
      "Kachel auf der Karte zeigen". Pruefung: Warnung je offenem Marker,
      Fehler bei NPC-Nummern ueber 697 (`val.npc.limit`). `export.npc_block`
      nimmt `party`/`guild` vom Sprecher. Zeitleiste: Badge "MP", Hinweis,
      Kontextmenue. Dialog "Neue Quest": vierte Option.
    - Echttest mit Q_700: Q_385, NPC_508, Kachel E1, zwei Marker in der Liste,
      Block und NPC-Zeile korrekt; im Spiel nicht getestet (Offen).
68. Bedienbarkeits-Runde und zwei Debug-Runden (Version 3.3.1):
    - Leerer Graph: Knopf "+ Neue Quest" direkt im Canvas. Dialog "Neue
      Quest": bei "Leer" verschwinden Suche und Liste, sonst ist der erste
      Eintrag vorgewaehlt, Enter = OK, Suchfeld mit Beispieltext.
    - Quest aus Vorlage: Tagebuchgruppe wie bei leeren Quests (Q_4), danach
      ist der erste TODO-Node ausgewaehlt und im Panel offen.
    - TODO-Warnungen je Node mit Sprecher, Ebene und Sprungziel statt einer
      Sammelmeldung; Titel/Tagebuch als eigene Meldung.
    - Debug-Runde 1 (Tests, alle GUI-Pruefskripte): ein Fehler im neuen
      Dialog (`pack before` auf ein nicht gepacktes Widget), behoben.
      Debug-Runde 2 (Vorlage, Undo, Spielquest uebernehmen, Projekt
      speichern/laden byte-gleich, Export nur Dateien, Karte/Guide/Mods/
      Questgrenze/Gegnerstufen oeffnen und schliessen): keine Fehler.
69. Update-Pruefung und Selbst-Update (Version 3.4.0; 3.3.2 davor: Hoehe
    der Zeitleiste aus dem Bedarf der Karten statt fest 110 px):
    - `questforge2/updater.py`: GitHub-API `releases/latest` im Thread beim
      Start (1,5 s nach dem Fenster, nicht im Selbsttest, abschaltbar),
      Versionsvergleich als Tupel, Asset `TW1QuestCreator.exe` mit `digest`
      (sha256). `UpdateWindow` in app.py: Notes, Jetzt/Spaeter/Ueberspringen
      (`update_skip` in der Konfig), Hilfe-Menue "Nach Updates suchen".
    - Download nach `<exe>.new` (`.part` waehrend des Ladens), SHA-256 gegen
      den Digest; ohne Digest oder bei Abweichung keine Installation.
    - Tausch per Batch im Temp-Ordner. Gemessen 16.09.2026: Windows erlaubt
      das Umbenennen der laufenden Exe; ein Batch, der nur auf die Datei
      wartet, tauschte sofort und startete eine zweite Instanz. Jetzt wartet
      er auf die Prozess-ID des Tools (bei PyInstaller-onefile der
      Kindprozess, `os.getpid()` im Tool), mit vollen Pfaden zu
      `tasklist.exe`/`find.exe` (im Git-PATH war `find` das Unix-find) und nur
      `CREATE_NO_WINDOW` (mit `DETACHED_PROCESS` liefen tasklist/find nicht).
      Echter Test mit der gebauten Exe: waehrend sie lief unveraendert, nach
      dem Ende getauscht (Hash = Release-Digest), neue Version gestartet,
      `.old` erhalten, Batch geloescht.
    - Build: `http` und `email` standen in den Excludes der Spec, `urllib`
      braucht sie; der erste Test-Build startete nicht. Excludes korrigiert,
      `urllib` wird erst beim Pruefen importiert, der Selbsttest meldet
      `https=ok`.
70. Zeilen aufnehmen (Version 3.5.0, Marco 2026-09-16: "einfach record
    tool beim cue ... direkt fuer die line aufnehmen"; 3.4.1 davor: dunkler
    Hover am Quellen-Knopf, Gruppentitel ueber AOQ-Linien):
    - `questforge2/recorder.py`: winmm `waveIn*` per ctypes ohne Callback,
      8 Puffer zu 0,1 s, Thread fragt `WHDR_DONE` in Reihenfolge ab und
      stellt sie neu ein; PCM 16 Bit mono 44100 Hz (BANK_RATE der
      Vertonungs-Pipeline), hoechstens 120 s; `write_wav`, `duration`,
      `play` (winsound), `device_names` (waveInGetDevCapsW).
    - Inspector (Marco: "record button ... gleich hier rein in die
      seitenleiste und in den einstellungen den rest"): Punkt-Knopf in der
      Voice-Cue-Zeile neben Suchen (Aufnehmen, waehrend der Aufnahme
      Stopp), darunter Zeit und Pegelbalken bzw. Laenge, Abspielen,
      Loeschen. Neues Fenster Datei > Einstellungen: Mikrofon
      (`voice_device` in der Konfig), Probeaufnahme 3 s mit Pegel und
      Wiedergabe, Update-Pruefung, Spielordner. Datei in
      `<Projekt>_voice/Q<id>_<node>_<zeile>.wav`, `line['voice']` = Name
      (nur gesetzt, wenn aufgenommen: alte Projekte bleiben byte-gleich).
      Verlassen der Zeile oder Beenden des Tools stoppt und behaelt die
      Aufnahme; Undo nimmt die Zuordnung zurueck.
    - Gemessen: 1,2 s vom Standardgeraet (Razer-Headset) = 53.330 Samples,
      Rauschen vorhanden; 5 Eingabegeraete auf Marcos Rechner. GUI-Test:
      Aufnehmen/Stopp, Datei 1,96 s, Undo/Redo, Auto-Stopp beim
      Node-Wechsel, Projekt speichert `voice`.
    - Nicht enthalten: Bau in die Sprachbank und Cue-Vergabe (Pipeline in
      QuestForge: voice_lines, build_soundbank).
    - 3.5.1, zwei Debugrunden (29 Faelle GUI-Skript): Dateiname ueberschreibt
      nie die Aufnahme einer anderen Zeile (`take_name`: eigene Datei
      wiederverwenden, sonst `_2`, `_3`; kopierte Nodes teilen die Datei,
      Loeschen behaelt sie fuer die andere Zeile); Zeile geloescht waehrend
      der Aufnahme -> verworfen; Undo/Redo waehrend der Aufnahme -> Stopp
      ohne eigenen Undo-Schritt, Zuordnung ueber Platz und Text; Quest- oder
      Projektwechsel und Sprachwechsel stoppen und behalten; Speichern unter
      kopiert die Aufnahmen in den neuen `_voice`-Ordner; Probeaufnahme und
      Zeilenaufnahme schliessen sich aus; fehlende Datei: x entfernt die
      Verknuepfung; Selbsttest prueft winsound/wave in der Exe.
71. Marker-Karte lesbar (Version 3.5.2, Marco 2026-09-17: "punkte etwas
    groesser machen und farbig jeder marker typ eine unterschiedliche farbe
    ... links in der checkbox liste selbe farben", "map tile beschriftung ist
    auch schlecht lesbar"):
    - `mapdata.MARKER_GROUPS`: "Quest: Punkt, Teleport, Weg, Gebiet" in fuenf
      Ebenen geteilt (Q_Solve, Q_Action_Walk, Q_Action_Teleport,
      Q_Action_Clear_Area, Q_Action_Kill_Area); Quest-Ebenen tragen den
      Namen aus dem Two Worlds Editor (Objektbaum Special Objects > Quests).
    - `mapdata.GROUP_COLORS`: 17 Farben, paarweise mindestens Delta E 29
      (CIE76), Helligkeit L >= 50 auf dunklem Grund; `test_map` prueft beides.
      Farbpunkt vor jedem Haken in der Liste (Klick schaltet mit).
    - Punkte Radius 4/5/6 statt 2/3/4; Herkunft als Ring (eigene gold, Mods
      hellblau) statt als Fuellfarbe; Auswahlring 12 statt 9.
    - Tile-Namen weiss auf dunklem Schild mit Goldrand, Schrift je Zoom
      7/9/11 pt.
    - GIF-Anleitung (EN/DE) "Marker-Karte oeffnen": Aktion an Node ziehen,
      Aktion markieren, Karte beim Marker-Feld, Marker waehlen, uebernehmen.
72. Voiceline-Finder, Aufnahme-Bibliothek, Kuerzen (Version 3.6.0, Marco
    2026-09-17: "vorhandene suchen standart suche vom helden ... man gibt ein
    was man sagen moechte und alle gleichen oder aehnlichen werden
    vorgeschlagen", "record bibliothek ... in welcher quest ... was ihre
    line ist", "jede record audio kuerzen vorne und hinten"):
    - `questforge2/voicebank.py`: `search` ueber den Cue-Index (7764 Cues,
      Held Lector 1 mit 1820). Wert = 0,4 Wortabdeckung (Praefix ab 4
      Zeichen, Apostroph trennt) + 0,35 SequenceMatcher + 0,25 (1 - Anteil
      zusaetzlicher Woerter) + Phrasenbonus; gemessen 70 ms Held, 0,6 s alle.
      Probe: "Ich werde es versuchen" -> "Ich werd's versuchen." zuerst.
      `speakers` (Namen aus NPC-Bloecken, sonst Nummer).
    - Anhoeren: Sounds.xsb -> Wave-Index -> UnitTalk.xwb-Eintrag (ADPCM) in
      RIFF mit MS-ADPCM-Formatblock, Windows spielt es ohne Codec; gemessen
      3 ms je Zeile. Parser aus QuestForge/tw1_xact.py uebernommen (Kopie,
      TwStuff unveraendert).
    - `voicewin.py`: VoiceFinder (ersetzt CueDialog), LibraryPanel (drittes
      Pane rechts, Ansicht > Aufnahme-Bibliothek, `panels.voices`),
      TrimWindow (Wellenform, Griffe, Stille erkennen, `_original`-Sicherung,
      wiederherstellen).
    - `recorder.py`: read_wav, peaks, detect_trim, cut, trim_file,
      restore_original, drop_original, library; Speichern unter kopiert die
      Sicherungen mit; neue Aufnahme und Loeschen verwerfen die Sicherung.
    - Pruefung: 115 Tests, GUI-Skripte gui_360 (18 Faelle DE/EN) und
      dbg_360b (16 Randfaelle: alte Konfig, ohne Tonbank, Stereo, zu kurz,
      fehlende Datei, Aufnahme waehrend Kuerzen), Regression dbg_rec/dbg_rec2.
    - Selbsttest der Exe: `voicebank=<Treffer>hits/<Bytes>b`.
    - 3.6.1, Kartenzoom (Marco: "map zoom fluessiger und in kleineren
      schritten"): 22 Stufen 48..2048 statt 5 (Faktor 1,14 bis 1,25 statt 2).
      Tk skaliert nur ganzzahlig, deshalb `scale_of(px)`: Stufe erst zoomen,
      dann subsamplen (haelt die Schaerfe), nur Stufen <= px, Zwischenbild
      hoechstens min(max(1024, px*4), 3072) Pixel. Mausrad zeichnet gebuendelt
      (30 ms), Bildspeicher ab 512 px auf 8 Kacheln begrenzt. Gemessen:
      schlimmster Neuaufbau 218 ms (Fernsicht, 108 Kacheln), acht Rasten
      25 ms, 640 px kommt jetzt aus der 512er-Stufe statt der 128er.
    - 3.6.2 (Marco: "karte immer mittig zentriert"): `_set_region` legt den
      Scrollbereich mit gleichem Rand links/rechts und oben/unten um die
      Welt, solange sie kleiner als die Leinwand ist; `_scroll_to` und
      `_clamp_view` (nach Ziehen, vor jedem Neuzeichnen) halten die Ansicht
      darin. Beim Oeffnen ohne Ziel steht die ganze Welt in der Mitte.
    - 3.6.3 (Marco: "das scrollt schrecklich es wird andauernd kleiner und
      groesser ... die groesste aufloesung behalten"): 12 Stufen statt 22
      (48..2048, Faktor 1,33/1,5), ab 384 px kommt jede Stufe aus der
      512er-Kachel, darunter aus den kleinen (schnell). Damit bleibt die
      Schaerfe ueber die Stufen gleich; gemessen: schlimmster Schritt 246 ms
      (Fernsicht 108 Kacheln), 384 px 231 ms, alle anderen unter 150 ms,
      acht Rasten 28 ms. Neu: Umschalt + Rad scrollt seitwaerts, Knoepfe
      minus/plus/Ganze Karte mit Stufenanzeige und Hinweistext,
      Strg+Plus/Minus.
    - 3.6.4 (Marco: "zwischen jeder zoom stufe verschiebt sich alles kurz und
      wird schwarz"): Ursache 1 war die Reihenfolge - `_draw_tiles` loeschte
      erst und zeichnete dann; jetzt entstehen die neuen Kacheln unter einem
      eigenen Tag und erst danach fallen die alten weg. Ursache 2 war der
      Takt: gezoomt wurde sofort, gezeichnet 30 ms spaeter, dazwischen stand
      die Leinwand leer; jetzt zeichnet `after_idle` noch vor dem naechsten
      Bildaufbau und fasst eine ganze Radumdrehung zusammen. Zoomt die Maus
      eine Karte, die ganz ins Fenster passt, ist der Mittelpunkt der Anker
      statt des Zeigers, damit nichts seitlich springt. Gemessen: schwarzer
      Anteil direkt nach der Raste 0,5 % (vorher 98 %), sechs schnelle
      Rasten = eine Neuzeichnung in 193 ms.
    - 3.7.0 (Marco: "warum kann das nicht so rein zoomen wie in paint"):
      Tk skaliert Bilder nur ganzzahlig, deshalb waren Stufen noetig. Jetzt
      skaliert Pillow die Kacheln (`mapwin.SMOOTH`, im Spec nicht mehr
      ausgeschlossen, Exe 12,7 -> 18,3 MB): stufenlos 40..2048 px, je Raste
      ein Achtel, Quelle ist die kleinste Minimap-Stufe, die noch mindestens
      so gross ist (`source_level`), Verkleinern mit LANCZOS, Vergroessern
      bilinear; ohne Pillow bleibt die alte Stufenleiter. Gemessen:
      schlimmster Neuaufbau 162 ms (vorher 246), Fernsicht 59..118 ms,
      je Raste rund 50 ms, schwarzer Anteil 0,3 %.
    - 3.7.1 (Marco: "verschiebt die map sich fuer wenige millisekunden bevor
      die dann rein zoomt"): Ursache war die Reihenfolge in der Leerlauf-
      Warteschlange - `zoom_to` scrollte sofort, die Leinwand malte daraufhin
      die alten Kacheln an der neuen Stelle, erst danach kam unser Neuzeichnen.
      Jetzt merkt sich `zoom_to` nur Ziel und Anker (`_zoom_target`,
      `_zoom_anchor`), `_apply_zoom` scrollt und zeichnet in einem Schritt;
      `zoom_step` baut auf dem wartenden Ziel auf, damit Rasten sich
      addieren. Ziehen zeichnet ebenfalls im selben Leerlauf-Schritt.
      Gemessen: direkt nach der Raste unveraendert, Weltpunkt unter der
      Maus 5,210 -> 5,211, fuenf Rasten = eine Neuzeichnung (400 -> 810 px).
73. MP-Assistent, Anzeigename (Version 3.7.2, Discord 2026-09-18: Nutzer
    uebernahm "Ravenous Hunger" (Q_700) als Q_381, die Nodes zeigten
    "NPC 700", er setzte Q_Giver mit der Questnummer 381): Der Assistent
    vergab richtig eine freie NPC-Nummer (leeres Projekt: 508), als Name
    stand aber "NPC <alte MP-Nummer>". Jetzt folgt der Vorgabename der neuen
    Nummer ("NPC 508"), bis man einen eigenen tippt; MP-Platzhalter
    ("Lector ...", "NPC_700") gelten nicht als Name.
74. Grosse Bugfix-Runde "Fehler, die das Spiel still schluckt" (Version
    3.8.0, Marco 2026-09-18 nach Orions Q_Giver-381-Fall). Vier Pruefer
    lasen je einen Bereich gegen das SDK; jeder Fund im Code nachgeprueft.
    - Pruefung (validate.py `_engine_checks`, auch mit modset): Q_Giver mit
      der NPC-Nummer auf der Kachel des neuen NPC (Orions Fall), jeder
      Aufgaben-/Aktionsmarker auf seiner Kachel (Warnung; Retail- und
      Mod-Kartendaten), Q_Action_Walk auf der Kachel des NPC, Kachel leer
      oder unbekannt = Fehler, NPC-Nummern 1..697 in Geber/Aufgabe/Aktionen,
      unbekannte NPC-Nummer (Warnung), neuer NPC als Ziel gebraucht aber nie
      erzeugt, derselbe neue NPC in zwei Quests verschieden, Freischaltung
      (Zaehler -1, Spielstart +1, je AOQ PROMOTE +1; SDK PQuests.ec 229/429,
      PQuestsCommon.ech eQuestInitialLevel): Stufe > Vorgaenger = Fehler
      "nie frei", Stufe 0 mit Bedingung = Warnung; Verknuepfung auf
      unbekannte Quest jetzt Fehler (Quest 0), Ziel ueber der Questgrenze
      Fehler, Platzhalter-Geber Fehler, unbekannter Ort Fehler. Vier
      Meldungen hatten gar keinen Text (val.link.*), ergaenzt.
    - Sprecher: Entfernen zaehlt Geber und NPC-Ziele mit; Listen zeigen
      "Name (NPC_n)" (gleiche Namen waehlten den falschen); Geber nur echte
      NPC; Tooltip mit Kachel und noetigem Q_Giver; Umbenennen eines
      Spiel-NPC sagt, dass nur der Tool-Name wechselt; Neuer-NPC-Dialog
      prueft 1..697, Kachel, Marker > 0. Karte "In Quest verwenden" nach
      Rueckgaengig schreibt nicht mehr ins Leere. Erneuter Export ersetzt
      den NPC-Eintrag statt den alten zu behalten. Zeitleiste zeigt den
      Geber der jeweiligen Quest.
    - MP-Assistent: `recover_null_lines` holt Zeilen mit "(null)" in
      Zahlenfeldern zurueck - vorher hatten 90 der 120 MP-Quests nach der
      Uebernahme keine Aufgabe, 204 Zeilen fielen weg; jetzt 0. Zeilen ohne
      Nummer bekommen je einen eigenen Marker, getippte Nummern bleiben je
      Zeile; Hauptkachel ueberschreibt nur Zeilen, die ihr noch folgen;
      leerer Name faellt auf die neue Nummer; Checkliste mit Editor-Namen
      (Q_Giver ...) und `current_todo` (veraltete Eintraege fallen weg);
      MP-Quests nicht mehr in der Kopierliste.
    - Export/Mods: Quests frueherer Exporte, die das Projekt nicht mehr hat
      (umnummeriert, geloescht), werden samt AOQ-Zeilen und Texten entfernt
      (Vergleich mit dem Original-qtx); Teil-Export behaelt die Texte der
      anderen Quests; Mod ohne Quest-lan: zweite gespeicherte Quest loescht
      die Texte der ersten nicht mehr; Backup wiederherstellen oeffnet die
      offene Mod-Quest neu; Aufnahmen an Mod-Quests gesperrt (Mod haelt sie
      nicht); Kopie einer Spielquest behaelt AOQ-Verknuepfungen,
      Geber-Entfernung und Tagebuch-Flag; Umnummerieren zieht Bedingungen
      und Verknuepfungen anderer Projekt-Quests mit.
    - Vorlagen: "Kette mit Tor" war kein Tor (Bedingung Stufe 1, eine
      Vorbedingung) - jetzt Stufe 2 mit Q_4 angenommen + erfuellt;
      "Mit NPC reden" zielte auf NPC_5 wie Q_4 selbst - jetzt NPC_190
      (Nalax Gonga, E2, im Spiel ungeprueft).
    - Bewusst nicht geaendert: ein vorhandener Marker mit derselben Nummer
      gilt im Assistenten als "vorhanden" (Wiederverwenden ist erlaubt und
      spart den Editor); Vorlage-NPC aus eigenen/Mod-Sprechern (selten).
    - Pruefung: 121 Tests (neu test_bugfix380), gui_380 (11 Faelle),
      Regression dbg_rec/dbg_rec2/gui_360/dbg_360b/map_check/map_check2.

Offen:

- Spieltest einer Tool-Quest mit ID ueber 399 bei Questgrenze 600 (12.57).
- Spieltest der geaenderten Gegnerstufen (12.59).
- Usability-Update abgeschlossen: Guide und Vorlagen (2.9.0), Mod-Quellen
  (3.0.0), interaktive Karte (3.1.0).
- Spieltest einer uebernommenen Multiplayer-Quest (12.67): Marker im Editor
  setzen, Karte als Mod einbinden, Quest annehmen und loesen.
- Spieltest der mitgelieferten Vorlagen (vier Quests, vier Gegnergruppen,
  Dialog-Vorlage): je eine Quest exportieren, im neuen Spiel annehmen und
  abschliessen (Abnahme Punkt 9 "laeuft im Spiel").
- Kartenpositionen im Spiel nachmessen (Held an einen Marker teleportieren
  und Position vergleichen), bisher nur Sichtpruefung (12.65).
- Ladereihenfolge zweier Mods im Spiel messen (12.64).
- Spieltest: Quest einer Mod im Tool geaendert und gespeichert (12.64).
- `quest_creator_gui.py` bleibt vorerst in `main` neben QuestForge 2
  (Marco 2026-09-14, nach den bestandenen Spieltests entschieden).
- `[PRUEFEN]`-Punkte, Stand 2026-09-13 (alle brauchen Marcos Spieltest,
  sonst geklaert):
  - Bedingungen/Aktionen pro Zeile (6.3): **per SDK geklaert, im Spiel
    bestaetigt** (4a, 4b; 12.53, 12.55).
  - Annahme/Ablehnen (5.2): **Hypothese A, im Spiel bestaetigt** (4a,
    12.53).
  - Kanten ueber Ebenen (5.1): **geklaert, erlaubt**.
  - `AOQ TAKE TAKE` gegen `PROMOTE TAKE` (6.4): **geklaert, nicht noetig**
    (Marco 2026-09-15). `PROMOTE TAKE` mit Angebot ist der Normalfall und im
    Spiel bestaetigt (4a, 12.53). `TAKE TAKE` (ohne Angebot sofort
    angenommen) bleibt als Schalter im Quest-Panel, ein eigener Spieltest
    ist erst noetig, wenn es jemand nutzt.
  - Startzeilen-Regel der Engine (6.3): offen; der Export haelt die
    getestete Reihenfolge ein.
  - `ACTION NPC_DIALOG` (6.3): offen, im Tool nicht angeboten.
  - NPC-Block neuer NPCs (12.34): offen, Spalten 7 bis 12 von der Vorlage.
- Spieltests (Marco): alle geplanten bestanden, 4a, 4b und die geaenderte
  Retail-Quest (12.53, 12.55, 12.56).

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
