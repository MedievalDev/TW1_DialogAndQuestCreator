"""Guide window: Help > Guide (point 8 of the usability update).

Chapter tree on the left, text on the right, search field on top, German and
English. Every table that maps numbers to names is generated from the same
tables the pickers use (``model.NUMBER_LISTS``, ``model.FC_SPECS``,
``model.ACTION_SPECS``, ``data._FC_MARKERS``, ``data._ACTION_MARKERS``), with
the source and whether it is proven, so nothing is maintained twice.

A separate module and not part of guide.py: guide.py holds the tour and the
tutorial coach, this is the reference that the "?" marks open.
"""

import re
import tkinter as tk
from tkinter import ttk

from . import data, model, theme
from .i18n import get_lang, t


def _l(de, en):
    return de if get_lang() == 'de' else en


def _table(head, rows):
    out = ['| ' + ' | '.join(head) + ' |',
           '|' + '---|' * len(head)]
    for r in rows:
        out.append('| ' + ' | '.join(str(c) for c in r) + ' |')
    return '\n'.join(out)


def _status(s):
    return _l('belegt', 'proven') if s == 'proven' else _l('ungeprueft',
                                                          'unverified')


# ---------------------------------------------------------------------------
# chapters

def ch_start():
    keys = [('Strg+N', 'Ctrl+N', _l('Neues Projekt', 'New project')),
            ('Strg+O', 'Ctrl+O', _l('Projekt oeffnen', 'Open project')),
            ('Strg+S', 'Ctrl+S', _l('Speichern', 'Save')),
            ('Strg+Shift+S', 'Ctrl+Shift+S', _l('Speichern unter', 'Save as')),
            ('Strg+E', 'Ctrl+E', _l('Als Mod exportieren', 'Export as mod')),
            ('F7', 'F7', _l('Quest pruefen', 'Validate quest')),
            ('Strg+Z / Strg+Y', 'Ctrl+Z / Ctrl+Y',
             _l('Rueckgaengig / Wiederholen', 'Undo / Redo')),
            ('Strg+C / X / V', 'Ctrl+C / X / V',
             _l('Kopieren, Ausschneiden, Einfuegen', 'Copy, cut, paste')),
            ('Strg+D', 'Ctrl+D', _l('Duplizieren', 'Duplicate')),
            ('Entf', 'Del', _l('Loeschen', 'Delete')),
            ('Strg+A', 'Ctrl+A', _l('Alles auswaehlen', 'Select all')),
            ('Strg+L', 'Ctrl+L', _l('Auto-Layout', 'Auto layout')),
            ('F', 'F', _l('Auf Inhalt einpassen', 'Fit to content')),
            (_l('Mausrad', 'Mouse wheel'), '', _l('Zoomen', 'Zoom')),
            (_l('Strg+Mausrad', 'Ctrl+wheel'), '',
             _l('Senkrecht scrollen', 'Scroll vertically')),
            (_l('Shift+Mausrad', 'Shift+wheel'), '',
             _l('Waagerecht scrollen', 'Scroll horizontally')),
            (_l('Mittlere Maustaste', 'Middle mouse button'), '',
             _l('Ansicht verschieben', 'Pan'))]
    rows = [(k if get_lang() == 'de' else (e or k), what)
            for k, e, what in keys]
    return _l("""# Einstieg

Der Quest Creator baut Quests fuer Two Worlds 1 als Mod. Das Fenster hat fuenf
Bereiche:

- **Zeitleiste** oben: alle Quests deines Spiels als Karten, je Questreihe eine
  Farbe, darueber Reiter fuer jede Reihe.
- **Sprecher** links oben: wer in der Quest spricht.
- **Aufgaben, Aktionen, Bedingungen** links unten: zum Ziehen in den Graphen.
- **Graph** in der Mitte: das Gespraech als Nodes und Verbindungen.
- **Eigenschaften** rechts: das Formular zu dem, was gewaehlt ist.

Das kleine `?` neben Titeln und Feldern erklaert beim Ueberfahren und springt
beim Klick in das passende Kapitel hier. Den Rundgang durch das Fenster
startest du unter Hilfe > Rundgang starten.

## Tastenkuerzel
""", """# Getting started

The Quest Creator builds quests for Two Worlds 1 as a mod. The window has five
areas:

- **Timeline** at the top: every quest of your game as a card, one colour per
  quest line, tabs for every line above.
- **Speakers** top left: who talks in the quest.
- **Tasks, actions, conditions** bottom left: drag them into the graph.
- **Graph** in the middle: the conversation as nodes and connections.
- **Properties** on the right: the form for whatever is selected.

The small `?` next to titles and fields explains on hover and jumps to the
matching chapter here on click. The tour through the window is under
Help > Start tour.

## Keyboard shortcuts
""") + _table([_l('Taste', 'Key'), _l('Wirkung', 'Effect')], rows) + \
        '\n\n' + _l('Quelle: Tastenbelegung des Tools (app.py, graph.py).',
                     'Source: key bindings of the tool (app.py, graph.py).')


def ch_first_quest():
    return _l("""# Erste Quest in 10 Minuten

Beispiel: Tago bittet um 100 Gold und zahlt 500 zurueck.

1. **Neue Quest.** Quest > Neue Quest, "Aus einer mitgelieferten Vorlage",
   "Bring-Quest (Gold)". Die Quest bekommt eine freie Nummer.
2. **Titel und Tagebuch.** Rechts Titel und die drei Tagebuchtexte eintragen.
   Keine Umlaute, kein Semikolon.
3. **Dialog.** Im Graphen jede Zeile mit TODO anklicken und rechts den Text
   schreiben. Die Zeile "annehmen" traegt den Haken "Nimmt die Quest an".
4. **Aufgabe.** Den Block "Aufgabe" links neben dem Einstieg Erfuellt
   anklicken, Gold auf 100 setzen. Unten steht die Zeile `FC BRING_GOLD 100`.
5. **Belohnung.** Die angedockten Belohnungen am Node der Ebene Erfuellt
   anklicken und die Menge pruefen.
6. **Pruefen.** F7. Fehler muessen weg, Warnungen nicht.
7. **Exportieren.** Spiel schliessen, Strg+E. Das Tool packt die Mod, prueft
   jede Datei und schaltet sie ein.
8. **Testen.** Neues Spiel starten, Tagos erste Quest annehmen, ihn erneut
   ansprechen. Er bietet die neue Quest an.
""", """# First quest in 10 minutes

Example: Tago asks for 100 gold and pays 500 back.

1. **New quest.** Quest > New quest, "From a shipped template",
   "Bring quest (gold)". The quest gets a free number.
2. **Title and journal.** On the right fill in the title and the three journal
   texts. No accents, no semicolon.
3. **Dialog.** Click every line marked TODO in the graph and write the text on
   the right. The "accept" line carries the check "Takes the quest".
4. **Task.** Click the "Task" block left of the entry Solved, set the gold to
   100. Below you see the line `FC BRING_GOLD 100`.
5. **Reward.** Click the rewards docked on the node of the level Solved and
   check the amount.
6. **Validate.** F7. Errors must go, warnings may stay.
7. **Export.** Close the game, Ctrl+E. The tool packs the mod, checks every
   file and switches it on.
8. **Test.** Start a new game, take Tago's first quest, talk to him again. He
   offers the new quest.
""")


def ch_quests():
    return _l("""# Quests

Eine Quest ist ein Block in der Questdatei `TwoWorldsQuests.qtx`:

```
QUEST Q_<nummer> <enable_level> <gruppe> <gilde> <mindest-ruf> True
  GIVER ACTIVE NPC_<n> BACK_TO_GIVER_MAP_SIGN NONE
  FC <ziel> <werte>
  AOQ <typ> <ausloeser> Q_<andere>
  ACTION <was> <wann> <werte>
  REWARD <was> <wann> <menge>
END
```

## Nummern
Das Original belegt 1 bis 380 lueckenlos. Frei sind 381 bis 399. Mit der
Questgrenze 600 (Quest > Questgrenze) kommen 400 bis 599 dazu. Eine Nummer ueber
der wirksamen Grenze wird im Spiel zu Quest 0: namenloser Tagebucheintrag.

## Ein Ziel pro Quest
Eine Quest hat genau ein `FC`. Im Original gibt es keine einzige mit zwei.
"Bring drei verschiedene Dinge" geht nur als drei Quests.

## enable_level
Kein Heldenlevel, sondern ein Zaehler. Jedes `AOQ PROMOTE` auf die Quest zaehlt
eins hoch, bei Erreichen wird sie freigeschaltet. Stufe 2 heisst: zwei
Vorquests muessen sie freischalten.

## Multiplayer-Quests uebernehmen
Q_700 bis Q_819 stehen zwar in derselben Questdatei, gehoeren aber dem
Multiplayer-Skript (`PQuestsMulti.ec`, zaehlt ab 699). Das Einzelspieler-Skript
verwirft Questnummern ab 400 **und NPC-Nummern ab 698** beim Laden; Q_700 mit
NPC_700 kann im Einzelspieler nie erscheinen. Dazu fehlen den MP-Zeilen die
Kacheln (`(null)`), ihre Marker erzeugt das MP-Skript zur Laufzeit.

Quest > **Multiplayer-Quest uebernehmen** fuehrt durch: MP-Quest waehlen, freie
Questnummer und freie NPC-Nummer (ab 507, unter 698), Kachel fuer den Geber und
jede Zeile, Markernummern (bleiben, wenn die Kachel sie noch nicht hat). Am
Ende steht die **Marker-Checkliste**: welche Marker mit welchem Namen, welcher
Nummer und auf welcher Kachel du im Two Worlds Editor setzen musst, zum
Beispiel `MARKER_QUEST_START 507 auf E1` fuer den Geber. Das Tool setzt keine
Marker. Die Liste steht danach im Quest-Panel mit Haken; offene Punkte meldet
die Pruefung als Warnung. Der Geber bekommt Partei 25 (Menschen), die
MP-Bloecke haben keine.

**Karten aus dem Editor zurueck ins Tool:** Der Editor speichert die Kachel
unter `Saved Games\\Two Worlds Saves\\Levels` als `Map_<Kachel>s.lnd`, die
Physik als `physic\\Map_<Kachel>s.phx`. Beide unter der Checkliste auf das
Feld **Karten aus dem Editor** ziehen (oder klicken und waehlen; zur `.lnd`
findet das Tool die `.phx` selbst). Sie landen unter dem Namen, den das Spiel
erwartet, im Ordner `<Projekt>_levels` neben der Projektdatei
(`Levels\\Map_E01.lnd`, `Levels\\physic\\Map_E01.phx`), der als Mod ins
Projekt kommt. Das Tool liest die Marker sofort und hakt ab, was jetzt auf
der Karte liegt. Der Export packt `.lnd` und `.phx` der Kacheln mit, die die
Quests brauchen.

**Marker direkt im Tool setzen (ab 3.9.0):** Der Editor ist dafuer nicht
mehr noetig. Knopf **Marker auf der Karte setzen** in Schritt 3 des
Assistenten oder im Quest-Panel ueber der Checkliste. Die Karte oeffnet sich
ohne die vorhandenen Marker (die wuerden nur verwirren), links stehen die zu
setzenden. Eintrag anklicken, der Marker haengt an der Maus, Klick auf die
Karte setzt ihn, der Eintrag wird gruen mit Haken. Gruenen Eintrag nochmal
anklicken hebt den Marker wieder auf, Esc oder Rechtsklick legt ihn zurueck.
Die Kachel kommt vom Klick, die Nummer ist auf der Kachel frei (Geber = seine
NPC-Nummer), die Hoehe aus der Hoehenkarte der Kachel (gemessen an 8895
Spielmarkern: 97 % liegen innerhalb von 16 Einheiten; Bruecken und
Hausboeden stehen hoeher, dort im Spiel pruefen). Unbegehbarer Boden (Baum,
Fels, Mauer) wird ab Nahzoom rot getoent und fragt vor dem Setzen nach.
Innenraeume (`_1`) gehen so nicht, dort bleibt der Editor. **Bestaetigen**
schreibt die Kacheln nach `<Projekt>_levels` (Kopie der Spielkarte, der
fremden Mod-Karte, die das Projekt fuer die Kachel nutzt, oder deiner
Editor-Kachel, die vorher nach `<Projekt>_levels_base` gesichert wird; die
Spielmarker, die der Kopie fehlen, kommen mit hinein) und liest die Mods neu.
Danach wie unten: exportieren, dann LevelHeadersCacheGen.

**Vor dem naechsten Spielstart** erst exportieren, dann
`LevelHeadersCacheGen.bat` aus dem SDK (`Tools`) ausfuehren, Knopf im
Quest-Panel. Der Level-Header-Cache traegt die Marker jeder Karte; ohne
frischen kennt das Spiel die neuen Marker nicht. Er backt alles ein, was
gerade installiert ist, auch fremde Mods: nur mit den Mods bauen, mit denen
gespielt wird.

## Zustaende
Freigeschaltet (ENABLE), Angebot gehoert (HEAR), angenommen (TAKE), erfuellt
(SOLVE), abgeschlossen (CLOSE), gescheitert (FAIL). Das Tagebuch zeigt den Text
zur Annahme, zum Erfuellen und zum Abschluss.
""", """# Quests

A quest is a block in the quest file `TwoWorldsQuests.qtx`:

```
QUEST Q_<number> <enable_level> <group> <guild> <min reputation> True
  GIVER ACTIVE NPC_<n> BACK_TO_GIVER_MAP_SIGN NONE
  FC <goal> <values>
  AOQ <type> <trigger> Q_<other>
  ACTION <what> <when> <values>
  REWARD <what> <when> <amount>
END
```

## Numbers
The original uses 1 to 380 without a gap. 381 to 399 are free. The quest limit
600 (Quest > Quest limit) adds 400 to 599. A number above the effective limit
becomes quest 0 in the game: a nameless journal entry.

## One goal per quest
A quest has exactly one `FC`. The original has not a single one with two.
"Bring three different things" only works as three quests.

## enable_level
Not a hero level but a counter. Every `AOQ PROMOTE` on the quest counts it up
by one; once reached, the quest is enabled. Level 2 means two quests have to
enable it.

## Taking over multiplayer quests
Q_700 to Q_819 sit in the same quest file but belong to the multiplayer
script (`PQuestsMulti.ec`, counting from 699). The single player script drops
quest ids from 400 **and NPC ids from 698** while loading; Q_700 with NPC_700
can never appear in single player. The MP lines also lack tiles (`(null)`),
their markers are made by the MP script at run time.

Quest > **Take over multiplayer quest** walks you through: pick the MP quest,
a free quest id and a free NPC id (from 507, below 698), a tile for the giver
and for every line, marker numbers (kept when the tile does not have them
yet). At the end stands the **marker checklist**: which markers, with which
name, number and tile, you have to place in the Two Worlds editor, for
example `MARKER_QUEST_START 507 on E1` for the giver. The tool places no
markers. The list then lives in the quest panel with check boxes; open items
are reported as warnings. The giver gets party 25 (humans), the MP blocks
have none.

**Maps from the editor back into the tool:** the editor saves the tile under
`Saved Games\\Two Worlds Saves\\Levels` as `Map_<tile>s.lnd`, the physics as
`physic\\Map_<tile>s.phx`. Drag both onto the field **Maps from the editor**
below the checklist (or click and choose; for a `.lnd` the tool finds the
`.phx` itself). They go under the name the game expects into the folder
`<project>_levels` next to the project file (`Levels\\Map_E01.lnd`,
`Levels\\physic\\Map_E01.phx`), which joins the project as a mod. The tool
reads the markers at once and ticks what is on the map now. The export packs
`.lnd` and `.phx` of the tiles the quests need.

**Placing markers right in the tool (from 3.9.0):** the editor is no longer
needed for this. Button **Place markers on the map** in step 3 of the wizard
or in the quest panel above the checklist. The map opens without the existing
markers (they would only confuse), the ones to place stand on the left. Click
an entry, the marker hangs at the mouse, a click on the map sets it and the
entry turns green with a tick. Click a green entry again to pick the marker
up, Esc or right click puts it back. The tile comes from the click, the
number is free on that tile (giver = its NPC number), the height from the
tile's heightmap (measured on 8895 game markers: 97 % lie within 16 units;
bridges and house floors stand higher, check those in the game). Blocked
ground (tree, rock, wall) is tinted red when zoomed in and asks before
placing. Interiors (`_1`) do not work this way, the editor stays for them.
**Confirm** writes the tiles to `<project>_levels` (a copy of the game map,
of the foreign mod map the project uses for that tile, or of your editor
tile, which is kept in `<project>_levels_base` first; game markers the copy
lacks go in as well) and reads the mods again. Then as below: export, then
LevelHeadersCacheGen.

**Before the next game start** export first, then run
`LevelHeadersCacheGen.bat` from the SDK (`Tools`), button in the quest panel.
The level header cache holds the markers of every map; without a fresh one
the game does not know the new markers. It bakes in everything installed at
that moment, foreign mods too: build it only with the mods you play with.

## States
Enabled (ENABLE), offer heard (HEAR), taken (TAKE), solved (SOLVE), closed
(CLOSE), failed (FAIL). The journal shows the texts for taking, solving and
closing.
""")


def _spec_rows(specs, prefix):
    rows = []
    for key, spec in specs.items():
        if isinstance(key, tuple):
            name = t(f'op.{key[0]}.{key[1]}')
            code = f'{key[0]} {key[1]}'
        else:
            name = t(f'op.FC.{key}')
            code = f'FC {key}'
        fields = ', '.join(t('field.' + f[0]) for f in spec)
        rows.append((name, f'`{code}`', fields or '-'))
    return rows


def ch_tasks():
    head = _l("""# Aufgaben

Die Aufgabe (`FC`) ist das eine Ziel der Quest. Du waehlst sie im Block
"Aufgabe" links neben dem Einstieg Erfuellt. Darunter zeigt das Tool die Zeile,
die in die Questdatei geht.

Fallen:
- Toeten eines Questgeber-NPCs dauert, sie haben hohe Widerstaende.
- Bei "Sprechen mit" ueberspringt der Ziel-NPC sein eigenes Angebot, solange die
  Quest laeuft.
- Gebiete saeubern braucht Gegner derselben Partei (Aktion "Gegner erzeugen").

""", """# Tasks

The task (`FC`) is the one goal of the quest. Pick it in the "Task" block left
of the entry Solved. Below, the tool shows the line that goes into the quest
file.

Traps:
- Killing a quest giver NPC takes ages, they have huge resistances.
- With "Talk to", the target NPC skips its own offer while the quest runs.
- Clearing an area needs enemies of the same party (action "Create enemies").

""")
    return head + _table([_l('Aufgabe', 'Task'), 'qtx',
                          _l('Felder', 'Fields')],
                         _spec_rows(model.FC_SPECS, 'FC')) + '\n\n' + _l(
        'Quelle: SDK PQuestLoader.ech (ParseFC); die Tabelle kommt aus '
        'model.FC_SPECS, denselben Daten wie das Formular.',
        'Source: SDK PQuestLoader.ech (ParseFC); the table comes from '
        'model.FC_SPECS, the same data as the form.')


def ch_actions():
    head = _l("""# Aktionen

Aktionen passieren zu einem Zeitpunkt der Quest. Angedockt an einen Dialog-Node
ergibt sich der Zeitpunkt aus der Ebene (Angebot = bei Annahme, Erfuellt = beim
Abschliessen). Aktionen ohne Dialog legst du im Quest-Panel an und waehlst den
Zeitpunkt selbst.

Ziehe "+ Neue Aktion" auf einen Dialog-Node. Der Node bekommt beim Ueberfahren
einen goldenen Rahmen. Rechtsklick auf eine Aktion: bearbeiten, nach oben,
nach unten.

""", """# Actions

Actions happen at a point in the quest. Docked on a dialog node, the time comes
from the level (offer = on taking, solved = on closing). Actions without a
dialog are created in the quest panel and you pick the time yourself.

Drag "+ New action" onto a dialog node. The node gets a gold frame while you
hover. Right click on an action: edit, move up, move down.

""")
    rows = _spec_rows(model.ACTION_SPECS, 'ACTION')
    tail = '\n\n' + _l('Zeitpunkte laut SDK: ', 'Times from the SDK: ') + \
        ', '.join(f'`{w}`' for w in model.ACTION_WHEN) + '\n\n' + _l(
            'Quelle: SDK PQuestLoader.ech (ParseACT, ParseRWD); die Tabelle '
            'kommt aus model.ACTION_SPECS.',
            'Source: SDK PQuestLoader.ech (ParseACT, ParseRWD); the table '
            'comes from model.ACTION_SPECS.')
    return head + _table([_l('Aktion', 'Action'), 'qtx',
                          _l('Felder', 'Fields')], rows) + tail


def ch_conditions():
    return _l("""# Bedingungen

Bedingungen haengen unter dem Einstieg Angebot und bestimmen, wann die Quest
angeboten wird.

| Bedingung | Wirkung | Wird geschrieben als |
|---|---|---|
| Nach Quest | Angebot erst, wenn eine andere Quest einen Zustand erreicht | `AOQ PROMOTE <zustand> Q_<diese>` in der anderen Quest |
| Mindest-Level | Zaehler `enable_level` in der Kopfzeile | Kopfzeile Spalte 2 |
| Gilde | Gilde und Mindest-Ruf | Kopfzeile Spalten 4 und 5 |

Ohne "Nach Quest" wird die Quest nie angeboten. "Start" im Quest-Panel
ausgeschaltet schreibt `AOQ TAKE` statt `PROMOTE`: die Quest steht dann ohne
Gespraech im Tagebuch.

Quelle: SDK PQuestLoader.ech (ParseQUEST fuer die Kopfzeile, ParseAOQ),
PQuests.ec (PromoteQuest zaehlt enable_level hoch).
""", """# Conditions

Conditions hang below the entry Offer and decide when the quest is offered.

| Condition | Effect | Written as |
|---|---|---|
| After quest | Offer only once another quest reaches a state | `AOQ PROMOTE <state> Q_<this>` in the other quest |
| Minimum level | Counter `enable_level` in the header | header column 2 |
| Guild | Guild and minimum reputation | header columns 4 and 5 |

Without "After quest" the quest is never offered. "Start" switched off in the
quest panel writes `AOQ TAKE` instead of `PROMOTE`: the quest then lands in the
journal without a conversation.

Source: SDK PQuestLoader.ech (ParseQUEST for the header, ParseAOQ),
PQuests.ec (PromoteQuest counts enable_level up).
""")


def ch_links():
    rows = [(f'`{x}`', t('links.type.' + x)) for x in model.AOQ_TYPES]
    rows2 = [(f'`{x}`', t('ev.' + x) if t('ev.' + x) != 'ev.' + x else x)
             for x in model.AOQ_TRIGGERS]
    return _l("""# Quest-Verknuepfungen (AOQ)

`AOQ <typ> <ausloeser> Q_<ziel>` steht in einer Quest und heisst: Wenn diese
Quest den Ausloeser erreicht, tue den Typ mit der Zielquest. Du legst sie im
Quest-Panel unter "Quest-Verknuepfungen" an.

""", """# Quest links (AOQ)

`AOQ <type> <trigger> Q_<target>` sits in a quest and means: when this quest
reaches the trigger, do the type with the target quest. Create them in the
quest panel under "Quest links".

""") + _table([_l('Typ', 'Type'), _l('Wirkung', 'Effect')], rows) + '\n\n' + \
        _table([_l('Ausloeser', 'Trigger'), _l('Bedeutung', 'Meaning')],
               rows2) + '\n\n' + _l("""## Muster

- **Kette:** Q_A hat `AOQ PROMOTE CLOSE Q_B`. B wird angeboten, sobald A
  abgeschlossen ist.
- **Tor:** Q_C hat `enable_level 2`, Q_A und Q_B haben je `AOQ PROMOTE CLOSE
  Q_C`. C erscheint erst nach beiden.
- **Entweder-oder:** Drei Quests beim selben Geber, jede traegt `AOQ DISABLE
  TAKE` auf die beiden anderen. Wer eine annimmt, verliert die anderen.

**`AOQ ENABLE` gibt es nicht.** Eine abgeschaltete Quest bleibt aus.

Quelle: SDK `PQuestLoader.ech` (ParseAOQ).
""", """## Patterns

- **Chain:** Q_A has `AOQ PROMOTE CLOSE Q_B`. B is offered once A is closed.
- **Gate:** Q_C has `enable_level 2`, Q_A and Q_B each have `AOQ PROMOTE CLOSE
  Q_C`. C only appears after both.
- **Either-or:** Three quests at the same giver, each carrying `AOQ DISABLE
  TAKE` on the two others. Taking one loses the others.

**`AOQ ENABLE` does not exist.** A disabled quest stays off.

Source: SDK `PQuestLoader.ech` (ParseAOQ).
""")


def ch_npcs():
    return _l("""# NPCs und Sprecher

"+ Neuer Sprecher" nimmt einen NPC aus dem Spiel oder legt einen neuen an.

- **Vorhandener NPC:** steht schon in der Welt, spricht mit seiner Stimme.
- **Neuer NPC:** Nummer, Name, Kachel, Marker `Q_Giver`, Vorlage fuer das
  Aussehen, Stimme. Ein NPC-Block erschafft niemanden: fuer die Figur in der
  Welt braucht es zusaetzlich die Aktion "NPC erzeugen".
- **Ein NPC fuehrt genau ein Gespraech.** Hat er mehrere Quests, gewinnt die mit
  dem hoeheren Zustand, bei Gleichstand die aeltere.

Ungeklaert: die Spalten 9 und 10 im NPC-Block (`SMALL True`) sowie was der
Wert hinter der Einheit genau steuert. Das Tool uebernimmt sie von der Vorlage.

## Zeilen selbst aufnehmen

In der Voice-Cue-Zeile jeder Dialogzeile steht neben **Suchen...** der
Punkt-Knopf. Klick, Zeile sprechen, derselbe Knopf (jetzt ein Quadrat)
stoppt; waehrenddessen zeigen Zeit und Pegel darunter, dass etwas ankommt.
Liegt eine Aufnahme vor, stehen darunter Laenge, **Abspielen** (Dreieck) und
loeschen (x); der Punkt nimmt neu auf. Mikrofon und Probeaufnahme stehen
unter Datei > **Einstellungen**.

- Format: WAV, 16 Bit, mono, 44,1 kHz (Rate der Sprachbank des Spiels).
- Ablage: Ordner `<Projekt>_voice` neben der Projektdatei, Name
  `Q<Quest>_<Node>_<Zeile>.wav`. Das Projekt muss dafuer gespeichert sein.
- Wechselst du waehrend der Aufnahme zu einem anderen Node, wird sie beendet
  und fuer ihre Zeile gespeichert. Rueckgaengig (Strg+Z) nimmt die Zuordnung
  zurueck, die Datei bleibt.
- **Ins Spiel kommt die Aufnahme so noch nicht:** Dafuer muss sie in die
  Sprachbank (`Sounds.xsb`, `UnitTalk.xwb`) gebaut und als Cue an die Zeile
  gehaengt werden. Das macht der Quest Creator nicht.

## Aufnahmen verwalten und kuerzen

Neben einer Aufnahme stehen **Abspielen** (Dreieck), **Kuerzen** (Schere),
**Bibliothek** (drei Striche) und loeschen (x).

- **Kuerzen:** Das Fenster zeigt die Wellenform. Die blauen Griffe an Anfang
  und Ende ziehen, grau faellt weg. **Stille erkennen** setzt beide Griffe
  an die Sprache (10-ms-Abschnitte, leiser als 4 % des lautesten gilt als
  Stille, 0,08 s bleiben stehen). **Auswahl abspielen** hoert vorher rein.
  Beim ersten Kuerzen bleibt die ungekuerzte Aufnahme in `_voice/_original`;
  **Original wiederherstellen** holt sie zurueck. Eine neue Aufnahme fuer
  dieselbe Zeile verwirft diese Sicherung.
- **Aufnahme-Bibliothek** (Ansicht > Aufnahme-Bibliothek): alle Aufnahmen
  des Projekts mit Laenge, Quest und Zeilentext, gekuerzte mit Schere.
  Suche nach Datei, Quest oder Text. Knoepfe: abspielen (Leertaste), zur
  Zeile springen (Doppelklick), kuerzen, loeschen. Loeschen geht nur fuer
  Dateien, die keine Zeile benutzt (grau). Rot = die Zeile verweist auf eine
  Datei, die fehlt.

## Voiceline-Finder: vorhandene Sprachzeilen nutzen

Der Knopf **Suchen...** in der Voice-Cue-Zeile oeffnet den Finder. Oben steht
der Text der Zeile; tippe, was gesagt werden soll. Gleiche und aehnliche
Zeilen, die im Spiel schon gesprochen sind, stehen oben, mit Trefferwert.

- **Sprecher:** Standard ist der Held (1820 gesprochene Zeilen). In der
  Liste stehen alle Originalsprecher mit Zeilenzahl, oder alle zusammen.
- **Trefferwert:** Anteil deiner Woerter in der Zeile, Zeichenaehnlichkeit
  des ganzen Satzes und Abzug fuer Woerter, die die Aufnahme zusaetzlich
  sagt. Der Cue spielt immer die ganze Aufnahme, deshalb stehen kurze,
  passende Zeilen vor langen, die den Satz nur enthalten.
- **Anhoeren** (Leertaste) spielt die Originalaufnahme direkt aus der
  Tonbank des Spiels (`XACT/win/UnitTalk.xwb`).
- **Uebernehmen** (Doppelklick) setzt den Cue der Zeile, dann spricht der
  Originalsprecher. Der Wortlaut wird mit uebernommen (abschaltbar), weil
  der Untertitel zur Aufnahme passen muss. Strg+Z nimmt beides zurueck.
- Die Texte kommen aus deiner Installation, also in ihrer Sprache.

## Dialog-Vorlage

Quest > **Dialog aus Vorlage einfuegen** > "Standard-Questgeber" setzt ein
fertiges Gespraech in die offene Quest: Angebot mit Annehmen und Ablehnen,
Antwort solange die Quest laeuft, Dank beim Erfuellen (schliesst die Quest ab),
ein Satz danach. Es spricht der Questgeber, sonst der erste NPC-Sprecher. Freie
Einstiege werden verbunden, schon belegte bleiben unveraendert; die neuen Nodes
stehen dann rechts daneben und du verbindest sie selbst. Die Zeilen mit TODO
schreibst du um. Vorlagen liegen als JSON in `questforge2/templates/`.
""", """# NPCs and speakers

"+ New speaker" takes an NPC of the game or creates a new one.

- **Existing NPC:** already stands in the world and talks with its own voice.
- **New NPC:** number, name, map cell, marker `Q_Giver`, template for the look,
  voice. An NPC block creates nobody: for the figure in the world you also need
  the action "Create NPC".
- **An NPC holds exactly one conversation.** With several quests, the one in
  the higher state wins, on a tie the older one.

Unresolved: columns 9 and 10 of the NPC block (`SMALL True`) and what the value
after the unit controls exactly. The tool takes them from the template.

## Recording lines yourself

In the voice cue row of every dialog line there is a dot button next to
**Search...**. Click, speak the line, the same button (now a square) stops;
time and level below show that sound arrives. Once a take exists, its
length, **Play** (triangle) and delete (x) show below; the dot records again.
Microphone and test recording are under File > **Settings**.

- Format: WAV, 16 bit, mono, 44.1 kHz (the rate of the game's voice bank).
- Storage: folder `<project>_voice` next to the project file, name
  `Q<quest>_<node>_<line>.wav`. The project has to be saved for that.
- Selecting another node while recording ends the take and stores it for
  its line. Undo (Ctrl+Z) removes the link, the file stays.
- **This does not put the recording into the game yet:** it has to be built
  into the voice bank (`Sounds.xsb`, `UnitTalk.xwb`) and hung on the line as
  a cue. The Quest Creator does not do that.

## Managing and trimming recordings

Next to a take there are **Play** (triangle), **Trim** (scissors),
**Library** (three lines) and delete (x).

- **Trim:** the window shows the waveform. Drag the blue handles at start
  and end, grey is cut away. **Detect silence** puts both handles around the
  speech (10 ms slices, quieter than 4 % of the loudest counts as silence,
  0.08 s stay). **Play selection** lets you listen first. The first trim
  keeps the untrimmed take in `_voice/_original`; **Restore original** brings
  it back. A new take for the same line drops that backup.
- **Recording library** (View > Recording library): every take of the
  project with length, quest and line text, trimmed ones with scissors.
  Search by file, quest or text. Buttons: play (space), go to the line
  (double click), trim, delete. Delete only works for files no line uses
  (grey). Red = the line points to a file that is missing.

## Voice line finder: reuse existing voice lines

**Search...** in the voice cue row opens the finder. The line's text is
filled in; type what should be said. Identical and similar lines that are
already spoken in the game come first, with a match value.

- **Speaker:** the hero by default (1820 spoken lines). The list has every
  original speaker with the number of lines, or all of them together.
- **Match:** share of your words in the line, character similarity of the
  whole sentence and a deduction for words the recording says on top. A cue
  always plays the whole recording, so short fitting lines come before long
  ones that merely contain the sentence.
- **Listen** (space) plays the original recording straight from the game's
  sound bank (`XACT/win/UnitTalk.xwb`).
- **Take** (double click) sets the line's cue, then the original actor
  speaks it. The wording is taken along (can be switched off) because the
  subtitle has to match the recording. Ctrl+Z undoes both.
- The texts come from your installation, so in its language.

## Dialog template

Quest > **Insert dialog from template** > "Standard quest giver" puts a ready
conversation into the open quest: an offer with accept and decline, an answer
while the quest runs, thanks on solving (closes the quest), a line afterwards.
The quest giver speaks, otherwise the first NPC speaker. Free entries get
connected, occupied ones stay as they are; the new nodes then stand to the
right and you connect them yourself. Rewrite the lines marked TODO. Templates
are JSON files in `questforge2/templates/`.
""")


def ch_enemies():
    parties = [(p, t(f'party.{p}'),
                _l('feindlich', 'hostile') if p in model.PARTY_FIGHT
                else _l('neutral oder Stadt', 'neutral or town'))
               for p in model.PARTIES]
    tpls = [(tp['title'].get(get_lang()) or tp['name'],
             tp['data']['args'].get('enemy'), tp['data']['args'].get('count'),
             tp['data']['args'].get('level'), tp['data']['args'].get('party'))
            for tp in data.builtin_templates('enemy')]
    return _l("""# Gegner anlegen und spawnen

Aktion "Gegner erzeugen": Typ, Anzahl, Stufe, Marker (Sorte
`Q_Action_Create_Enemy`), Kachel, Partei. Die Vorlagen oben im Formular fuellen
Typ, Anzahl, Stufe und Partei aus.

Die Stufe herumlaufender Gegner stellst du fuer die ganze Welt unter
Quest > Gegnerstufen ein.

## Parteien
""", """# Creating and spawning enemies

Action "Create enemies": type, count, level, marker (kind
`Q_Action_Create_Enemy`), map cell, party. The templates on top of the form
fill in type, count, level and party.

The level of wandering enemies for the whole world is set under
Quest > Enemy levels.

## Parties
""") + _table(['Nr.', _l('Name', 'Name'), _l('Verhalten', 'Behaviour')],
              parties) + '\n\n' + _l('Quelle: SDK Enums.ech. ',
                                     'Source: SDK Enums.ech. ') + \
        '\n\n## ' + _l('Vorlagen', 'Templates') + '\n' + \
        _table([_l('Vorlage', 'Template'), _l('Typ', 'Type'),
                _l('Anzahl', 'Count'), _l('Stufe', 'Level'),
                _l('Partei', 'Party')], tpls)


def ch_markers():
    from .mods import MARKER_NAMES
    rows = []
    for fc, (kind, _m, _t) in sorted(data._FC_MARKERS.items()):
        rows.append((f'`FC {fc}`', f'`{kind}`', MARKER_NAMES[kind]))
    for verb, (kind, _m, _t) in sorted(data._ACTION_MARKERS.items()):
        rows.append((f'`ACTION {verb}`', f'`{kind}`', MARKER_NAMES[kind]))
    return _l("""# Marker, Orte, Truhen

Viele Aufgaben und Aktionen lesen einen Marker der Karte. Jede liest eine
bestimmte Sorte. **Falsche Sorte heisst: nichts passiert**, ohne Fehler.

Der Knopf `...` neben dem Marker-Feld oeffnet den Karten-Picker mit Kacheln und
allen Markern dieser Sorte, gelesen aus den Karten des Spiels (`Levels.wd`,
`Update16.wd`) und der eingebundenen Mods.

""", """# Markers, locations, chests

Many tasks and actions read a marker of the map. Each one reads a specific
kind. **Wrong kind means: nothing happens**, without an error.

The `...` button next to the marker field opens the map picker with the map
cells and every marker of that kind, read from the maps of the game
(`Levels.wd`, `Update16.wd`) and of the added mods.

""") + _table([_l('Befehl', 'Command'), _l('Marker-Sorte', 'Marker kind'),
               _l('Name in der Karte', 'Name in the map')],
              rows) + '\n\n' + _l(
        'Quelle: SDK PQuestLoader.ech (Argumente), PEnums.ech (Namen), '
        'gegen die Karten gemessen (Kapitel Mods).',
        'Source: SDK PQuestLoader.ech (arguments), PEnums.ech (names), '
        'measured against the maps (chapter Mods).') + _l("""

## Die Karte

**Karte** oben in der Zeitleiste (oder Ansicht > Karte) oeffnet die Weltkarte,
zusammengesetzt aus den Minimaps des Spiels. Das Fenster bleibt offen, waehrend
du weiterarbeitest.

- **Bedienung:** Mausrad zoomt stufenlos um den Mauszeiger, je Raste ein
  Achtel (40 bis 2048 Pixel je Tile), wie in einem Bildbetrachter. Umschalt
  und Rad scrollt seitwaerts. Unter der Karte stehen die Knoepfe minus, plus
  und **Ganze Karte** samt aktueller Groesse. Die Kacheln werden geglaettet
  skaliert, beim Verkleinern mit einem feineren Filter. Die Karte sitzt immer mittig: passt sie ganz ins
  Fenster, bleibt sie in der Mitte, sonst laesst sie sich bis an ihren Rand
  schieben. Ziehen verschiebt,
  Klick auf einen Punkt waehlt ihn in der Liste rechts, Klick in der Liste
  springt auf der Karte hin. Unten steht, auf welchem Tile und welchen
  Koordinaten der Mauszeiger ist.
- **Filter:** Herkunft (Spiel, eigene, Mods, jede Mod einzeln), Ebene
  (Oberflaeche oder Innenraeume `_1`), Marker-Typ, nur benutzte oder nur
  unbenutzte Marker, Suche nach Name, Nummer oder Tile (Enter springt zum
  ersten Treffer).
- **Farben:** Jeder Marker-Typ hat eine eigene Farbe, dieselbe steht als
  Punkt vor dem Haken in der Liste links. Die Quest-Marker tragen dort auch
  ihren Namen im Two Worlds Editor (`Q_Giver`, `Q_Solve`, `Q_Action_...`).
  Die Herkunft zeigt der Ring: eigene Quests gold, Mods hellblau. Orte sind
  gruene Quadrate. Tile-Namen stehen weiss auf dunklem Schild.
- **Aus einem Feld waehlen:** Der Knopf **Karte** neben einem Marker-Feld (und
  im Marker-Picker) oeffnet die Karte gefiltert auf die Sorte, die das Feld
  liest. Rechtsklick auf einen Marker > **In Quest verwenden** traegt Nummer
  und Tile ein. Eine andere Sorte fragt nach, Marker aus Mods laufen durch
  dieselbe Pruefung wie im Picker (rote Tiles gesperrt, Karte kommt in den
  Build).
- **Auf der Karte zeigen:** Rechtsklick auf einen Eintrag im Marker-Picker oder
  in den Abhaengigkeiten; Rechtsklick auf eine Quest in der Zeitleiste zeigt
  alle ihre Marker hervorgehoben.

Die Marker-Typen kommen aus den Abschnitten von `PEnums.ech` (Quest-, Einheiten-,
Stadt-, Wachen-, Arbeits- und sonstige Marker), `TwoWorldsEnemies16.ec`
(`MARKER_ENEMY_*`, Fallen) und `TwoWorldsTeleports.ec`; Namen, die dort nicht
stehen, landen unter "Sonstige".

**Wie die Positionen entstehen:** Jede Karte hat laut Kopf 128 mal 128 Zellen,
das SDK rechnet 256 Einheiten je Zelle (`TwoWorldsHeroControl16.ec`), ein Tile
ist also 32768 Einheiten breit, die Minimap 512 Pixel. Die y-Achse zeigt auf der
Minimap nach oben. Per Sichtpruefung bestaetigt: Tore von D8 in beiden
Stadttoren, Truhen von F8 im Ringbau, Teleporter von E1 am Wegende, Marker in
den Gaengen von B8_1, Wege laufen ueber die Kachelgrenzen. Im Spiel selbst ist
das nicht nachgemessen. Orte (`LOCATION`) stehen in Zellen
(`AddLocation(.., A2G(nX), ..)`).
""", """

## The map

**Map** at the top of the timeline (or View > Map) opens the world map, put
together from the minimaps of the game. The window stays open while you keep
working.

- **Controls:** the mouse wheel zooms around the mouse without steps, an
  eighth per notch (40 to 2048 pixels per tile), like an image viewer. Shift
  and the wheel scroll sideways. Below the map there are minus, plus and
  **Whole map** with the current size. Tiles are scaled smoothly, with a
  finer filter while shrinking. The map
  always sits in the middle: while it fits into the window it stays centred,
  otherwise it pans up to its edge. Dragging
  pans, a click on a point selects it in the list on the right, a click in the
  list jumps there on the map. The bottom line shows the tile and coordinates
  under the mouse.
- **Filters:** origin (game, own, mods, every mod), layer (surface or
  interiors `_1`), marker type, only used or only unused markers, search by
  name, number or tile (Enter jumps to the first hit).
- **Colours:** every marker type has its own colour, shown as a dot in front
  of its check box on the left. The quest markers also carry their name in the
  Two Worlds Editor there (`Q_Giver`, `Q_Solve`, `Q_Action_...`). The ring
  shows the origin: own quests gold, mods light blue. Locations are green
  squares. Tile names are white on a dark plate.
- **Picking for a field:** the **Map** button next to a marker field (and in
  the marker picker) opens the map filtered on the kind the field reads.
  Right click a marker > **Use in quest** fills in number and tile. Another
  kind asks first; markers from mods go through the same check as in the
  picker (red tiles blocked, the map goes into the build).
- **Show in map:** right click an entry in the marker picker or in the
  dependencies; right click a quest in the timeline to see all its markers
  highlighted.

The marker types come from the sections of `PEnums.ech` (quest, unit, town,
guard, worker and other markers), `TwoWorldsEnemies16.ec` (`MARKER_ENEMY_*`,
traps) and `TwoWorldsTeleports.ec`; names not listed there go to "Other".

**How positions are placed:** every map header says 128 by 128 cells, the SDK
counts 256 units per cell (`TwoWorldsHeroControl16.ec`), so a tile is 32768
units wide and its minimap 512 pixels. The y axis points up on the minimap.
Confirmed by eye: gates of D8 in both city gates, chests of F8 in the ring
structure, the teleporter of E1 at the end of its path, markers in the
corridors of B8_1, roads running on across tile borders. It is not measured in
the game itself. Locations (`LOCATION`) are given in cells
(`AddLocation(.., A2G(nX), ..)`).
""")


def ch_mods():
    from . import mods
    text = _l("""# Mods einbinden

Neben dem Spiel und deinem Projekt sind Mods eine dritte Quelle. Alles, was
aus einer Mod kommt, ist hellblau: Rahmen in der Zeitleiste, Punkt vor dem
Namen in Listen, Tooltip mit Herkunft (Mod, Datei, Tile).

## Mod hinzufuegen

1. Menue **Mods > Mod-Archiv hinzufuegen** (eine `.wd`) oder **Entpackten
   Mod-Ordner hinzufuegen**. **Mods aus dem Spielordner hinzufuegen** nimmt
   alle Archive aus `Mods` ausser deinem eigenen Zielarchiv.
2. Das Tool liest Questdatei, NPCs, Orte, Truhen, Sprachdateien und Karten
   (`Levels\\Map_E01.lnd` ist das Tile `E1`). Das Ergebnis wird je Mod
   zwischengespeichert; ein zweites Oeffnen dauert Millisekunden.
3. Die Liste steht im Projekt, nicht global. **Mods > Mods verwalten** zeigt
   sie mit Reihenfolge, an/aus und Details.

## Zeitleiste und Filter

Mod-Quests stehen hinter den Questreihen in einem eigenen Bereich, ein Block
je Mod. **Quellen** oben in der Zeitleiste blendet Spiel, eigene, Mods und
jede Mod einzeln ein und aus. "MOD neu" ist eine Quest, die es im Spiel nicht
gibt, "MOD geaendert" ueberschreibt eine Quest des Spiels.

## Mod-Quests bearbeiten

Ein Klick auf eine Mod-Karte oeffnet die Quest aus der Mod. Du bearbeitest sie
dort, sie wird nicht ins Projekt kopiert. **Speichern (Strg+S)** schreibt
Questblock und Texte zurueck in die Mod:

- Archiv: mit buglords `wdio`; alle anderen Eintraege bleiben Byte fuer Byte
  und mit ihren Verzeichnisdaten (Flags, Klassen-Id, GUID) erhalten. Danach
  vergleicht das Tool die Verzeichnisdaten mit den Archiven des Spiels.
- Ordner: die Dateien werden direkt geschrieben.
- Vor dem ersten Schreiben des Tages entsteht `<Mod>.bak-<Datum>` neben der
  Mod. **Mods > Sicherung wiederherstellen** spielt sie zurueck.
- Aenderungen kommen nur in einem neuen Spiel an: Das Questskript liest die
  Questdatei im Zustand `Initialize` (SDK `PQuests.ec`).

Rechtsklick auf eine Mod-Karte: **Als eigene Quest kopieren** holt sie mit
neuer Nummer ins Projekt.

## Marker aus Mods

Die Markerauswahl zeigt alle Marker aus den Karten des Spiels und der Mods.
Nimmst du fuer eine eigene Quest einen Marker, den nur eine Mod hat, kommt
deren Karte mit in dein Archiv, samt allen anderen Aenderungen der Mod an
dieser Karte. Das Tool fragt vorher; **Mods > Abhaengigkeiten** listet alle
solchen Karten mit Grund und Pruefergebnis.

- **Rot** ist ein Mod-Tile, in dem Marker des Spiels fehlen. Es wuerde
  Original-Quests brechen: Seine Marker sind fuer Quests ausserhalb der Mod
  gesperrt, die Pruefung meldet einen Fehler.
- Bringen zwei Mods dasselbe Tile und wird ein Marker daraus benutzt, blockiert
  der Export, bis du unter Abhaengigkeiten eine Mod waehlst.
- Welche von zwei Mods das Spiel spaeter laedt, ist **ungeprueft**. Das Tool
  nimmt die Reihenfolge der Mod-Liste, unten gewinnt.

## Welche Aktion welchen Marker liest

Aus dem SDK (`Campaigns/Missions/PInc/PEnums.ech`), am 16.09.2026 gegen die
Karten gemessen: alle 287 Markerverweise der Original-Quests und alle 216
NPC-Startmarker liegen unter diesen Namen auf ihrem Tile.

""", """# Using mods

Next to the game and your project, mods are a third source. Everything that
comes from a mod is light blue: frames in the timeline, a dot in front of the
name in lists, a tooltip with the origin (mod, file, tile).

## Adding a mod

1. Menu **Mods > Add mod archive** (a `.wd`) or **Add unpacked mod folder**.
   **Add mods from the game folder** takes every archive in `Mods` except
   your own target archive.
2. The tool reads the quest file, NPCs, locations, chests, language files and
   maps (`Levels\\Map_E01.lnd` is the tile `E1`). The result is cached per
   mod; opening it again takes milliseconds.
3. The list is stored in the project, not globally. **Mods > Manage mods**
   shows it with order, on/off and details.

## Timeline and filters

Mod quests stand after the quest lines in their own area, one block per mod.
**Sources** at the top of the timeline shows or hides the game, own quests,
mods and every single mod. "MOD new" is a quest the game does not have, "MOD
changed" overrides a quest of the game.

## Editing mod quests

A click on a mod card opens the quest from the mod. You edit it there, it is
not copied into the project. **Save (Ctrl+S)** writes the quest block and the
texts back into the mod:

- Archive: with buglord's `wdio`; every other entry stays byte for byte with
  its directory data (flags, class id, GUID). Afterwards the tool compares the
  directory data with the archives of the game.
- Folder: the files are written directly.
- Before the first write of the day `<Mod>.bak-<date>` is made next to the
  mod. **Mods > Restore backup** puts it back.
- Changes only reach a new game: the quest script reads the quest file in the
  state `Initialize` (SDK `PQuests.ec`).

Right click on a mod card: **Copy as own quest** brings it into the project
with a new number.

## Markers from mods

The marker picker lists every marker from the maps of the game and of the
mods. If an own quest uses a marker only a mod has, that mod's map goes into
your archive, with every other change the mod made to that map. The tool asks
first; **Mods > Dependencies** lists all such maps with reason and check
result.

- **Red** is a mod tile that lacks markers of the game. It would break
  original quests: its markers are blocked for quests outside the mod and the
  check reports an error.
- When two mods bring the same tile and a marker from it is used, the export
  is blocked until you pick one mod under Dependencies.
- Which of two mods the game loads later is **unverified**. The tool uses the
  order of the mod list, the lower one wins.

## Which action reads which marker

From the SDK (`Campaigns/Missions/PInc/PEnums.ech`), measured against the maps
on 2026-09-16: all 287 marker references of the original quests and all 216
NPC start markers lie on their tile under these names.

""")
    rows = list(mods.MARKER_NAMES.items())
    rows.append(('NPC', mods.NPC_MARKER))
    rows.append(('CONTAINER', mods.CHEST_MARKER))
    return text + _table([_l('Art im Tool', 'Kind in the tool'),
                          _l('Marker in der Karte', 'Marker in the map')],
                         rows)


def ch_reference():
    parts = [_l("""# Referenztabellen

Alle Listen, in denen eine Zahl oder ein Wort eine feste Bedeutung hat, an
einem Ort. Die Auswahllisten im Tool lesen dieselben Tabellen.

""", """# Reference tables

Every list in which a number or word has a fixed meaning, in one place. The
pickers in the tool read the same tables.

""")]
    overview = [(name, len(values), source, _status(status))
                for name, (values, source, status)
                in model.NUMBER_LISTS.items()]
    parts.append(_table([_l('Liste', 'List'), _l('Eintraege', 'Entries'),
                         _l('Quelle', 'Source'), 'Status'], overview))
    parts.append('\n\n## ' + _l('Gilden', 'Guilds') + '\n')
    parts.append(_table(['Nr.', _l('Name', 'Name')],
                        [(g, t(f'guild.{g}')) for g in model.GUILDS]))
    parts.append('\n\n## ' + _l('Animationen', 'Animations') + '\n')
    parts.append(_table(['Nr.', _l('Name', 'Name'), _l('Im Original oft',
                                                       'Common in retail')],
                        [(a, t('anim.name', n=a),
                          _l('ja', 'yes') if a in model.ANIM_COMMON else '')
                         for a in model.ANIMATIONS]))
    parts.append('\n\n' + _l(
        'Animationen: Bedeutung ungeprueft, nur anTalk0 bis anTalk17 in der par '
        'belegt. SET_WORLD_STATE und PLAY_CUTSCENE: Zahlen ungeprueft.',
        'Animations: meaning unverified, only anTalk0 to anTalk17 in the par '
        'are proven. SET_WORLD_STATE and PLAY_CUTSCENE: numbers unverified.'))
    return ''.join(parts)


def ch_trouble():
    rows = _l([
        ('Quest erscheint nicht, Tagebuch leer', 'Mod aus oder nicht geladen; '
         'Markermethode nutzen', 'Registry-Schalter, Spiel neu starten'),
        ('Tagebuch zeigt translateQ_0', 'Questnummer ueber der Grenze',
         'Nummer unter 400 oder Questgrenze 600'),
        ('NPC bietet nichts an', 'Keine Bedingung "Nach Quest" oder die '
         'Vorquest ist nicht erreicht', 'Bedingung pruefen, neues Spiel'),
        ('NPC nicht da', '"NPC erzeugen" fehlt', 'Aktion ergaenzen'),
        ('NPC sichtbar, nicht ansprechbar', 'Marker unter dem Boden des Raums',
         'Marker-Hoehe im Editor pruefen'),
        ('Marker tut nichts', 'Falsche Marker-Sorte', 'Kapitel Marker'),
        ('Dialog stumm', 'Zeile ohne Cue', 'Cue-Suche an der Zeile'),
        ('Komische Zeichen im Tagebuch', 'Umlaut oder Sonderzeichen in der '
         'Questdatei', 'Nur ASCII verwenden'),
        ('Aenderung kommt nicht an', 'Alter Spielstand', 'Neues Spiel'),
    ], [
        ('Quest does not appear, journal empty', 'Mod off or not loaded; use '
         'the marker method', 'Registry switch, restart the game'),
        ('Journal shows translateQ_0', 'Quest number above the limit',
         'Number below 400 or quest limit 600'),
        ('NPC offers nothing', 'No "After quest" condition or the previous '
         'quest is not reached', 'Check the condition, new game'),
        ('NPC missing', '"Create NPC" missing', 'Add the action'),
        ('NPC visible but cannot be talked to', 'Marker below the floor of the '
         'room', 'Check the marker height in the editor'),
        ('Marker does nothing', 'Wrong marker kind', 'Chapter markers'),
        ('Dialog silent', 'Line without a cue', 'Cue search on the line'),
        ('Odd characters in the journal', 'Accent or special character in the '
         'quest file', 'Use ASCII only'),
        ('Change does not arrive', 'Old save game', 'New game'),
    ])
    return _l('# Fehlersuche\n\nDie Engine meldet keine Fehler. Diese Faelle '
              'kosten sonst Stunden.\n\n',
              '# Troubleshooting\n\nThe engine reports no errors. These cases '
              'cost hours otherwise.\n\n') + \
        _table([_l('Symptom', 'Symptom'), _l('Ursache', 'Cause'),
                _l('Loesung', 'Fix')], rows) + '\n\n' + _l(
            'Quelle: README Abschnitte 3 und 9 (gemessene Fallen) und die '
            'Spieltests des Projekts (NODE_EDITOR_PLAN.md, Abschnitt 12).',
            'Source: README sections 3 and 9 (measured pitfalls) and the game '
            'tests of the project (NODE_EDITOR_PLAN.md, section 12).')


def ch_build():
    return _l("""# Bauen und Testen

1. **Pruefen:** F7. Fehler blockieren den Export.
2. **Spiel schliessen.** Das Spiel haelt die Archive offen.
3. **Exportieren:** Strg+E. Das Tool nimmt Questdatei und Texte aus dem
   Zielarchiv (sonst aus dem Spiel), setzt deine Quests ein, packt mit dem
   Referenz-Packer, liest das Archiv wieder ein und vergleicht jede Datei samt
   Metadaten. Vor dem ersten Export entsteht eine Sicherung.
4. **Einschalten:** Das Tool setzt den Mod-Schalter in der Registry.
5. **Testen:** Immer ein neues Spiel. Die Questdatei wird nur beim Start eines
   neuen Spiels gelesen und liegt danach im Spielstand.
6. **Markermethode:** Erscheint nichts, zuerst eine bekannte fruehe Textzeile mit
   `[MOD]` markieren. Sieht man den Marker nicht, laedt die Mod gar nicht.
""", """# Building and testing

1. **Validate:** F7. Errors block the export.
2. **Close the game.** The game keeps the archives open.
3. **Export:** Ctrl+E. The tool takes quest file and texts from the target
   archive (else from the game), puts your quests in, packs with the reference
   packer, reads the archive back and compares every file and its metadata. A
   backup is made before the first export.
4. **Switch on:** the tool sets the mod switch in the registry.
5. **Test:** always a new game. The quest file is only read when a new game
   starts and lives in the save afterwards.
6. **Marker method:** if nothing appears, mark a known early text line with
   `[MOD]` first. No marker visible means the mod does not load at all.
""")


CHAPTERS = (
    ('start', ('Einstieg', 'Getting started'), ch_start),
    ('first', ('Erste Quest in 10 Minuten', 'First quest in 10 minutes'),
     ch_first_quest),
    ('quests', ('Quests', 'Quests'), ch_quests),
    ('tasks', ('Aufgaben', 'Tasks'), ch_tasks),
    ('actions', ('Aktionen', 'Actions'), ch_actions),
    ('conditions', ('Bedingungen', 'Conditions'), ch_conditions),
    ('links', ('Quest-Verknuepfungen (AOQ)', 'Quest links (AOQ)'), ch_links),
    ('npcs', ('NPCs und Sprecher', 'NPCs and speakers'), ch_npcs),
    ('enemies', ('Gegner', 'Enemies'), ch_enemies),
    ('markers', ('Marker, Orte, Truhen', 'Markers, locations, chests'),
     ch_markers),
    ('mods', ('Mods einbinden', 'Using mods'), ch_mods),
    ('reference', ('Referenztabellen', 'Reference tables'), ch_reference),
    ('trouble', ('Fehlersuche', 'Troubleshooting'), ch_trouble),
    ('build', ('Bauen und Testen', 'Building and testing'), ch_build),
)

# "?" help keys -> chapter
HELP_CHAPTER = {
    'help.inspector': 'start', 'help.title': 'quests', 'help.id': 'quests',
    'help.task': 'tasks', 'help.action': 'actions', 'help.links': 'links',
    'help.preview': 'build', 'help.anim': 'reference',
    'help.enemytpl': 'enemies', 'help.map': 'markers',
    'help.mpmerge': 'quests',
}


_SEPARATOR = re.compile(r'^\|[\s|:-]+\|?$')
_LIST_ITEM = re.compile(r'^(- |\d+\. )')


def _prepare(text):
    """Join wrapped prose lines into paragraphs and turn markdown tables into
    aligned columns, so the text widget shows them readably."""
    out, para, table, in_code = [], [], [], False

    def flush_para():
        if para:
            out.append(' '.join(x.strip() for x in para))
            para.clear()

    def flush_table():
        if not table:
            return
        rows = [[c.strip().replace('`', '')
                 for c in r.strip().strip('|').split('|')]
                for r in table if not _SEPARATOR.match(r.strip())]
        ncol = max(len(r) for r in rows)
        widths = [max(len(r[i]) if i < len(r) else 0 for r in rows)
                  for i in range(ncol)]
        out.append('```')
        for n, r in enumerate(rows):
            cells = [(r[i] if i < len(r) else '').ljust(widths[i])
                     for i in range(ncol)]
            out.append('  '.join(cells).rstrip())
            if n == 0:
                out.append('  '.join('-' * w for w in widths))
        out.append('```')
        table.clear()

    for ln in text.split('\n'):
        if ln.startswith('```'):
            flush_para()
            flush_table()
            in_code = not in_code
            out.append(ln)
            continue
        if in_code:
            out.append(ln)
            continue
        if ln.startswith('|'):
            flush_para()
            table.append(ln)
            continue
        flush_table()
        stripped = ln.strip()
        if not stripped or ln.startswith('#'):
            flush_para()
            out.append(ln)
        elif _LIST_ITEM.match(stripped):
            flush_para()
            para.append(ln)
        else:
            para.append(ln)
    flush_para()
    flush_table()
    return '\n'.join(out)


def chapter_text(cid):
    for key, _title, fn in CHAPTERS:
        if key == cid:
            return fn()
    return ''


# ---------------------------------------------------------------------------
# window

class GuideWindow:
    _open = None

    @classmethod
    def show(cls, app, chapter='start'):
        win = cls._open
        if win is not None:
            try:
                win.win.lift()
                win.select(chapter)
                return win
            except tk.TclError:
                cls._open = None
        cls._open = cls(app, chapter)
        return cls._open

    def __init__(self, app, chapter='start'):
        from .guide import render_markdown
        self._render = render_markdown
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title(t('guidewin.title'))
        self.win.geometry('1120x760')
        self.win.minsize(820, 520)
        theme.dark_titlebar(self.win)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        top = ttk.Frame(self.win, padding=(10, 8))
        top.pack(fill='x')
        ttk.Label(top, text=t('guidewin.search')).pack(side='left')
        self.q = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.q, width=32)
        ent.pack(side='left', padx=6)
        ent.bind('<KeyRelease>', lambda e: self._search())
        self.hits = ttk.Label(top, style='Muted.TLabel')
        self.hits.pack(side='left', padx=8)
        body = ttk.PanedWindow(self.win, orient='horizontal')
        body.pack(fill='both', expand=True)
        left = ttk.Frame(body)
        self.tree = ttk.Treeview(left, show='tree', selectmode='browse')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._show_selected())
        right = ttk.Frame(body)
        sb = ttk.Scrollbar(right, orient='vertical')
        self.txt = tk.Text(right, wrap='word', bd=0, padx=26, pady=20,
                           cursor='arrow', spacing1=2, spacing3=4,
                           yscrollcommand=sb.set, font=('Segoe UI', 10))
        sb.configure(command=self.txt.yview)
        sb.pack(side='right', fill='y')
        self.txt.pack(fill='both', expand=True)
        for tag, kw in (('h1', dict(font=theme.FONT_H1, foreground=theme.GOLD,
                                    spacing1=18)),
                        ('h2', dict(font=theme.FONT_H2,
                                    foreground=theme.GOLD_HI, spacing1=14)),
                        ('h3', dict(font=('Segoe UI Semibold', 10),
                                    foreground=theme.GOLD_HI, spacing1=8)),
                        ('li', dict(lmargin1=20, lmargin2=34)),
                        ('code', dict(font=theme.FONT_MONO,
                                      background=theme.FIELD, lmargin1=16,
                                      lmargin2=16)),
                        ('inline', dict(font=theme.FONT_MONO,
                                        foreground=theme.GOLD_HI)),
                        ('bold', dict(font=('Segoe UI Semibold', 10))),
                        ('hit', dict(background=theme.SEL,
                                     foreground=theme.GOLD_HI))):
            self.txt.tag_configure(tag, **kw)
        body.add(left, weight=0)
        body.add(right, weight=1)
        self.win.update_idletasks()
        try:
            body.sashpos(0, 270)
        except tk.TclError:
            pass
        self._fill_tree()
        self.select(chapter)

    def close(self):
        GuideWindow._open = None
        self.win.destroy()

    def _fill_tree(self, only=None):
        self.tree.delete(*self.tree.get_children())
        lang = 0 if get_lang() == 'de' else 1
        for i, (cid, titles, _fn) in enumerate(CHAPTERS, start=1):
            if only is not None and cid not in only:
                continue
            self.tree.insert('', 'end', iid=cid, text=f'{i}. {titles[lang]}')

    def select(self, cid):
        if cid not in {c for c, _t, _f in CHAPTERS}:
            cid = 'start'
        if not self.tree.exists(cid):
            self._fill_tree()
        self.tree.selection_set(cid)
        self.tree.see(cid)
        self._show(cid)

    def _show_selected(self):
        sel = self.tree.selection()
        if sel:
            self._show(sel[0])

    def _show(self, cid):
        self.current = cid
        self.txt.configure(state='normal')
        self.txt.delete('1.0', 'end')
        self._render(self.txt, _prepare(chapter_text(cid)))
        self._mark_hits()
        self.txt.configure(state='disabled')

    def _search(self):
        needle = self.q.get().strip().lower()
        if not needle:
            self._fill_tree()
            self.hits.configure(text='')
            self.select(getattr(self, 'current', 'start'))
            return
        found = [cid for cid, _t, fn in CHAPTERS if needle in fn().lower()]
        self._fill_tree(set(found))
        self.hits.configure(text=t('guidewin.hits', n=len(found)))
        if found:
            self.select(found[0])

    def _mark_hits(self):
        needle = self.q.get().strip() if hasattr(self, 'q') else ''
        self.txt.tag_remove('hit', '1.0', 'end')
        if not needle:
            return
        first = None
        pos = '1.0'
        while True:
            pos = self.txt.search(needle, pos, nocase=True, stopindex='end')
            if not pos:
                break
            end = f'{pos}+{len(needle)}c'
            self.txt.tag_add('hit', pos, end)
            first = first or pos
            pos = end
        if first:
            self.txt.see(first)
