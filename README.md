# TW1 Dialog & Quest Creator (QuestForge)

Eigene Quests und Dialoge für **Two Worlds 1** (2007, Reality Pump) — als Mod,
ohne den Spielcode anzufassen. Alles hier wurde am lebenden Spiel verifiziert:
Die Referenz-Quest **Q_385 „Der Schutzgelderpresser"** ist vollständig
spielbar — Angebotsdialog beim Questgeber, Tagebucheinträge, Kill-Ziel,
Rückkehr, Belohnung.

Diese Doku beschreibt **jeden Schritt und jede Falle**. Die Fallen sind keine
Theorie — jede einzelne hat beim Bau der ersten Quest Stunden gekostet.

---

## Inhalt

1. [Voraussetzungen](#1-voraussetzungen)
2. [Schnellstart](#2-schnellstart)
3. [Wie das Spiel Mod-Inhalte lädt](#3-wie-das-spiel-mod-inhalte-lädt)
4. [Das Quest-Format `.qtx`](#4-das-quest-format-qtx)
5. [Das Text-Format `.lan`](#5-das-text-format-lan)
6. [Dialogbäume](#6-dialogbäume)
7. [Quest-Design: was funktioniert und was nicht](#7-quest-design-was-funktioniert-und-was-nicht)
8. [Packen und Ausliefern](#8-packen-und-ausliefern)
9. [Verifizieren und Testen](#9-verifizieren-und-testen)
10. [Troubleshooting: Symptom → Ursache](#10-troubleshooting-symptom--ursache)
11. [Fallstudie: der Weg zur ersten Quest](#11-fallstudie-der-weg-zur-ersten-quest)
12. [Modul-Referenz](#12-modul-referenz)
13. [QuestForge 2: der Quest-Editor](#13-questforge-2-der-quest-editor)
14. [Credits und Lizenz](#14-credits-und-lizenz)

---

## 1. Voraussetzungen

- **Two Worlds 1 Epic Edition** (Steam/GOG), Patchstand 1.6 —
  d. h. `WDFiles\Update16.wd` existiert
- **Python 3.10+** (keine weiteren Pakete nötig, alles Standard-Library)
- Basiskenntnisse: Dateien kopieren, eine Kommandozeile benutzen

Das Repository enthält **keine Spieldaten** (Copyright). Die Basisdateien
zieht sich jeder selbst aus der eigenen Installation:

```
python extract_base.py "F:\SteamLibrary\steamapps\common\Two Worlds - Epic Edition"
```

Das legt `base/TwoWorldsQuests.qtx` (aus Update16.wd — **nur** diese Fassung
benutzen, die kursierenden 1.0-Kopien sind veraltet) und
`base/TwoWorldsQuests.lan` (aus Language.wd) an.

## 2. Schnellstart

```
python extract_base.py "<Spielverzeichnis>"
python build_quest_tago.py --into "<Spielverzeichnis>\Mods\<DeinMod>.wd"
```

Dann die erzeugte `.wd.new` bei **geschlossenem Spiel** über das Original
schieben (Backup behalten!), neues Spiel starten, Tagos erste Quest annehmen,
ihn **erneut** ansprechen → er bietet die neue Quest an.

`build_quest_tago.py` ist die Referenz-Implementierung: jede Zeile darin
entspricht dem Stand, der im Spiel nachweislich läuft. Für eigene Quests
kopieren und anpassen — oder `questforge.py` mit einer JSON-Spec benutzen
(siehe `example_quest.json`; das Tool automatisiert noch nicht alle
Erkenntnisse dieser Doku, insbesondere die AOQ-Verkettung — Stand siehe
Abschnitt 12).

## 3. Wie das Spiel Mod-Inhalte lädt

Das ist das wichtigste Kapitel. Wer es überspringt, debuggt später blind.

### 3.1 Archive

Alle Spieldaten stecken in `.wd`-Archiven (zlib-komprimierte Container,
Version 0x200). Drei Orte werden geladen:

| Ort | Verhalten |
|---|---|
| `WDFiles\*.wd` | Basisspiel + Patches |
| `Mods\*.wd` | Mods — **nur wenn in der Registry aktiviert** |
| **Spiel-ROOT** (`*.wd` neben der EXE) | lädt **immer**, ignoriert die Registry! |

Registry-Schalter: `HKCU\SOFTWARE\Reality Pump\TwoWorlds\Mods`,
DWORD `"<Name>.wd" = 1` (an) bzw. `0` (aus).

**Fallen:**
- Eine `.wd` im Spiel-ROOT wird man per Registry **nicht** los — die Datei
  muss physisch raus. (Ein Community-Mod im Root hat so hartnäckig zwei
  Level-Tiles überschrieben, obwohl der Mod-Selector ihn „aus" zeigte.)
- **`= 0` ist ein bewusster Aus-Schalter, kein toter Eintrag.** Nie die
  Registry „aufräumen": Ein auf 0 gestelltes Archiv in `WDFiles\` hielt eine
  ältere `TwoWorlds.par` zurück; das Löschen des Eintrags hat sie reaktiviert
  und stillschweigend Spielwerte zurückgedreht. Vorher immer `reg export`.
- **Zwei aktive Mods mit derselben inneren Datei kämpfen stumm**, der spätere
  gewinnt. Alte Testarchive entfernen, nicht nur deaktivieren.
- **Ein strukturell perfektes Archiv kann trotzdem komplett ignoriert
  werden.** Ein frisch gebautes Mod-Archiv (korrekte Flags, Zeiten, Registry
  = 1) wurde vom Spiel nie geladen — derselbe Inhalt in ein anderes,
  nachweislich ladendes Archiv gelegt, funktionierte sofort. Ursache
  ungeklärt. Konsequenz: **Ladefähigkeit immer erst mit einem Textmarker
  beweisen** (Abschnitt 9), bevor man Inhalte debuggt.

### 3.2 Datei-Ebene vs. Schlüssel-Ebene

Zwei völlig verschiedene Override-Mechanismen:

**Datei-Ebene** (`.par`, `.qtx`, Levels, Modelle, Texturen …): Pro innerem
Pfad gewinnt genau eine Datei. Ein Mod muss die Datei **vollständig ersetzen**
und am **Originalpfad** liegen (`Scripts\Quests\TwoWorldsQuests.qtx`).

**Schlüssel-Ebene** (`.lan`-Texte): Das Spiel sammelt **alle** `Language\*.lan`
aus allen geladenen Archiven ein und mergt sie **schlüsselweise — der spätere
gewinnt**. Bewiesene Reihenfolge:

```
Basis (Language.wd) → Mod-Ersatz (TwoWorldsQuests.lan) → ZZ_*-Overlays
```

Genau so funktionieren auch die offiziellen Dateien: `TwoWorldsPatch1.6.lan`
(33 Schlüssel) und GOGs `ZZ_special.lan` (3 Schlüssel) sind winzige Overlays.
**Auch Dialogbäume laden aus Mod-`.lan`-Dateien.** Für reine Text-/Dialog-Mods
reicht also eine kleine `Language\ZZ_MeinMod.lan` mit nur den eigenen
Schlüsseln und Bäumen — die 3-MB-Masterdatei muss nicht mit.

### 3.3 Der Level-Header-Cache

`Levels\Map_LevelHeaders.lhc` ist ein **Cache**. Wird er neu erzeugt, während
ein fremder Mod installiert ist, backt er dessen Level ein — und die Einträge
überleben die Deinstallation. Symptom: kaputte/bunte Bodentexturen auf den
betroffenen Tiles. Diagnose: Level-Anzahl im Header (`"LC\0\0"` + u32) mit der
Basiskopie in `Levels.wd` vergleichen (160). Fix: Basiskopie zurückspielen —
ein Mod, der nur Vanilla-Tiles ändert, braucht keine Cache-Änderung.

## 4. Das Quest-Format `.qtx`

`Scripts\Quests\TwoWorldsQuests.qtx` — ASCII, **ausschließlich LF**
(`\n`). Ein einziges `\r` zerlegt den Parser, der Zeilen an Leerzeichen
splittet. Die Datei enthält alle 500 Quests; Mods hängen neue Blöcke an.

```
QUEST Q_<id> <enableLevel> <group> <guild|(null)> <minRep> <True|False>
  GIVER  <ACTIVE|PASSIVE> NPC_<n> <BACK_TO_GIVER_MAP_SIGN|AUTO_CLOSE_ON_SOLVE|BACK_TO_GIVER> <NONE|CLOSE|SOLVE|TAKE>
  AOQ    <PROMOTE|TAKE|CLOSE|SOLVE|DISABLE|FAIL_CLOSE> <TAKE|SOLVE|CLOSE|ENABLE|HEAR|FAIL|FIGHT> Q_<n>
  FC     KILL|TALK NPC_<n>
       | BRING_OBJECT <obj> <n> | BRING_GOLD <n>
       | GO <marker> <sektor> <reichweite>
       | CLEAR_AREA <marker> <sektor> <reichweite> <party>
  ACTION <verb> <zeitpunkt> <args...>
  REWARD <GLD|EXP|SKL> <TAKE|SOLVE|CLOSE|HEAR> <SMALL|MEDIUM|HIGH|zahl>
       | ITM <anzahl> <obj> | REP <anzahl> <gilde>
END
```

**Regeln (alle im Spiel verifiziert):**

| Regel | Grund |
|---|---|
| Quest-ID **381–399** | Im Einzelspieler gibt es eine harte Grenze bei 400, im Spiel getestet: ab 400 löst die Engine jede AOQ-Referenz auf Quest 0 auf, die Quest erscheint nie und das Tagebuch zeigt einen Phantom-Eintrag `translateQ_0`. Dieselbe Quest lief als `Q_389` sofort. Es bleiben 19 freie IDs; danach IDs erledigter Original-Quests wiederverwenden. QuestForge 2 lässt 381–399 zu, mit der Questgrenze 600 (13.2) 381–599. |
| `enableLevel 1` | wie die Retail-Startquests; `0` funktionierte in Tests nicht zuverlässig |
| Kopfzeile letzte Spalte `True` | sonst kein Tagebucheintrag |
| Symbolische Belohnungen sind mager | `MEDIUM` Gold ≈ 160, `SMALL` EXP ≈ 20 — konkrete Zahlen benutzen (Retail tut das auch: `REWARD GLD SOLVE 5000`) |
| Bestehenden Giver-NPC (< 698) nehmen | hat seinen `MARKER_QUEST_START` schon — erspart die komplette Editor-/Marker-Arbeit |
| `(null)` heißt „nicht gesetzt" | nie leer lassen |

`tw1_qtx.py` kennt die vollständigen Aritäts- und Enum-Tabellen und validiert
jede Zeile. **Nie Opcodes erfinden** — jedes Verb erst gegen eine echte Quest
in der Basisdatei prüfen.

## 5. Das Text-Format `.lan`

Binär, little-endian: `"LAN\0"` + u32 Version 3, dann Übersetzungen
(ASCII-Schlüssel → UTF-16LE-Text), Aliasse, Dialogbäume. Alle Schlüssel tragen
das Präfix `translate`.

**Pflicht-Schlüssel pro Quest — alle vier, sonst steht der rohe
Schlüsselname im Tagebuch** (genau so gefunden: `translateQ_385_QSD` stand
wörtlich im Journal):

| Schlüssel | Wann sichtbar |
|---|---|
| `translateQ_<id>` | Questtitel |
| `translateQ_<id>_QTD` | Tagebuch bei Annahme |
| `translateQ_<id>_QSD` | Tagebuch nach Erfüllung (vor Abgabe) |
| `translateQ_<id>_QCD` | Tagebuch nach Abschluss |

Gruppen-Titel (`translateGROUP_<n>`) sind eigene Schlüssel. Farbige Texte:
`<0xAARRGGBB>` im Text. Umlaute funktionieren (UTF-16), zur Sicherheit beim
ersten Test ASCII benutzen.

## 6. Dialogbäume

Die Bäume liegen im Baum-Abschnitt der `.lan` (`tw1_lan.parse_trees` /
`build_trees`). Baum-ID: `translateDQ_<questid>`. Jeder Eintrag:

```
lector    i32   wer spricht: 1 = Held, sonst NPC-Lector-ID (aus dessen Retail-Zeilen ablesen)
tid       str   Schlüssel des Textes in der Übersetzungstabelle
cue       str   Audio-Cue ("" = stumm — völlig legal, 2157 Retail-Zeilen sind stumm)
next      i32[] Folgeeinträge (Indizes im selben Baum); mehrere = Auswahlmenü,
                negativer Index = Option nach Benutzung ausblenden
flags     u32   Zustand (Tabelle unten)
cams      i32[] Kamera: 1/2 = auf NPC, 6/7 = auf Held
anim1/2   u32   Animationen (0 = Standard)
```

**Zustands-Flags** — steuern, in welchem Quest-Zustand eine Zeile spielt:

| Flag | Hex | Bedeutung |
|---|---|---|
| `0.FT.AS` | `0x20001` | **Das Questangebot.** Eröffnet das Gespräch, an dessen Ende die Quest angenommen ist |
| `0.FT` | `0x1` | Passiver Gruß — **kein** Angebot! |
| `0.QNT` | `0x2` | Quest bekannt, nicht angenommen |
| `0.QT` | `0x4` | Quest angenommen |
| `0.QC` | `0x8` | Quest abgeschlossen |
| `1.TAKE` | `0x20100` | Annahme-Option |
| `0.QNS.AE` | `0x100` | Quest aktiv, noch nicht erfüllt |
| `0.QS.AE` | `0x40200` | Quest erfüllt → Belohnungsgespräch |
| `0x0` | `0x0` | Neutrale Menü-/Smalltalk-Zeile |

**Die teuerste Falle des ganzen Projekts:** Das Angebot **muss** `0.FT.AS`
sein. Mit `0.FT` hat der NPC „nichts anzubieten" und bleibt komplett stumm —
ohne jede Fehlermeldung. 132 von 158 vergleichbaren Retail-Quests nutzen
`0.FT.AS`. Als Vorlage einen echten Baum nehmen (z. B. `translateDQ_205`) und
nur Texte/IDs tauschen.

Aufbau des bewährten Angebots: abwechselnd NPC/Held als `0.FT.AS`-Kette
(`next` jeweils auf den Folgeeintrag, letzte Zeile `next=[]`), dazu je eine
Zeile `0.QNS.AE` (noch nicht erledigt), `0.QS.AE` (Belohnung) und `0.QC`
(danach). Komplett in `build_quest_tago.py` zu sehen.

### 6.1 Was die Flags laut SDK bedeuten

Quelle: Kampagnen-Skript des Two Worlds SDK
(`Scripts\Campaigns\Missions\PInc\PQuestsCommon.ech`, `GetDialogInputFlags`,
`UpdateQuestStateAfterDialog`). Das ist Code-Lesart, kein Spieltest; die
Ergebnisse passen aber zu allen bisherigen Spielbefunden.

Die Flags sind **kein Aufzählungswert**, sondern zwei Gruppen von Bits.
Beim Ansprechen baut der Skript eine Maske aus acht **Zustandsbits** und
zieht die Bits des aktuellen Questzustands ab. Eine Zeile ist spielbar, wenn
alle ihre Zustandsbits zum Zustand passen; `0x0` ist immer spielbar. Drei
hohe Bits sind **Ereignisse**: Lief das Gespräch über eine Zeile mit so einem
Bit, meldet das Spiel es am Gesprächsende an den Skript.

| Bit | SDK-Name | Bedeutung |
|---|---|---|
| `0x1` | `eFirstTime` | erstes Ansprechen, Quest freigeschaltet und noch nie angeboten |
| `0x2` | `eQuestNotTaken` | Angebot gehört, nicht angenommen |
| `0x4` | `eQuestTaken` | angenommen |
| `0x8` | `eQuestClosed` | abgeschlossen |
| `0x10` | `eQuestFailed` | fehlgeschlagen |
| `0x20` | `eQuestLowReputation` | Ruf unter dem Mindestruf der Kopfzeile |
| `0x100` | `eQuestNotSolved` | Aufgabe nicht erledigt (freigeschaltet **oder** angenommen) |
| `0x200` | `eQuestSolved` | Aufgabe erledigt (beim Gesprächsstart geprüft: Gegenstand/Gold dabei, Ort gefunden) |
| `0x10000` | `eQuestFightNow` | Ereignis: Questgeber wird feindlich, `FIGHT`-Aktionen |
| `0x20000` | `eQuestTakeNow` | Ereignis: Quest wird angenommen, `TAKE`-Aktionen und -Belohnungen |
| `0x40000` | `eQuestCloseNow` | Ereignis: Quest wird abgeschlossen, Gegenstände/Gold werden abgenommen, `CLOSE`-Belohnungen |

Damit lösen sich die Namen der Tabelle oben auf: `0.FT.AS` = FirstTime +
TakeNow, `1.TAKE` = NotSolved + TakeNow, `0.QS.AE` = Solved + CloseNow.
Folgerungen:

- Es gibt **keine** freien Bedingungen oder Aktionen pro Dialogzeile.
  Aktionen hängen an Quest-Ereignissen (`TAKE`, `SOLVE`, `CLOSE`, `ENABLE`,
  `HEAR`, `FAIL`, `FIGHT`).
- Ablehnen ist möglich: Endet das Angebot auf einem Pfad ohne TakeNow, bleibt
  die Quest freigeschaltet, beim nächsten Gespräch spielen `0x2`-Zeilen.
  (Spieltest steht aus, siehe `NODE_EDITOR_PLAN.md` 6.3.)
- Antwortmenüs zeigen nur auf Held-Zeilen; Verzweigungen nach Zustand laufen
  über Held-Zeilen mit verschiedenen Zustandsbits. Nachfolger über
  Zustandsgrenzen hinweg sind normal.
- Alle 6942 Zeilen der 378 Retail-Questbäume bestehen nur aus diesen elf
  Bits. Andere Bits kommen nur in den Gruß-Bäumen der Bürger und Wachen vor
  (dort ist jedes Bit ein Gruß-Slot).

## 7. Quest-Design: was funktioniert und was nicht

**Das bewährte Muster** (Retail macht es genauso, 103-mal):

```
# an der VORGÄNGER-Quest:
AOQ PROMOTE TAKE Q_<neu>
```

Beim Annehmen der Vorgängerquest wird die neue Quest **freigeschaltet**. Beim
**nächsten** Gespräch bietet der Giver sie über die `0.FT.AS`-Kette an.

**Was nicht funktioniert** (alles ausprobiert):

| Versuch | Ergebnis |
|---|---|
| Neue Quest nur mit `GIVER` + `enableLevel`, ohne AOQ | wird **nie** angeboten |
| `AOQ TAKE TAKE` statt `PROMOTE TAKE` | Quest wird stumm auto-angenommen — das Angebotsgespräch entfällt |
| Angebot als zusätzliche Menü-Option im laufenden Gespräch | unmöglich — `next`-Indizes zeigen nur in den eigenen Baum, Sprünge zwischen Bäumen existieren im Format nicht; Angebote starten nur am Gesprächsbeginn |
| `GIVER PASSIVE` | funktioniert, aber `ACTIVE` (wie die Retail-Kette) drängt das Angebot aktiver auf |

**Weitere Design-Punkte:**
- **Kill-Ziele mit Bedacht wählen:** Quest-NPCs haben massive Widerstände —
  ein `FC KILL` auf einen Quest-NPC ist zäh. Normale NPCs/Gegner bevorzugen.
- `BACK_TO_GIVER_MAP_SIGN` setzt nach Erfüllung den Kartenmarker zurück zum
  Giver — der Spieler weiß, wo es die Belohnung gibt.
- Vertonung: Cue leer lassen. Neue Sprachausgabe wäre ein XACT-Rebuild der
  935-MB-`UnitTalk.xwb` — ungelöst, und Retail akzeptiert stumme Zeilen.

## 8. Packen und Ausliefern

**Nur mit den Referenz-Werkzeugen packen:** `wdio.py` (buglord, liegt bei)
oder `Tw1WDRepacker.exe`. Ein selbstgeschriebener Packer hat Archive erzeugt,
die jeder Reader klaglos las — **das Spiel hat sie stumm ignoriert.**
Stundenlange Phantom-Fehlersuche. `tw1_wd.py` dient deshalb nur noch zum
**Lesen**; sein `write()` ist absichtlich deprecated.

```python
import wdio
wdio.unpack_single('Mods/MeinMod.wd', 'staging/')   # entpacken
wdio.pack_single('staging/', 'MeinMod.wd', 1, None) # packen (Version 1!)
```

Ablauf:
1. **Spiel schließen** — es hält alle `Mods\*.wd` offen; Schreiben schlägt fehl
2. **Backup des Zielarchivs** anlegen
3. Archiv entpacken, Dateien einfügen/ersetzen, als **v1** neu packen
4. Nach `Mods\` kopieren, Registry-DWORD auf 1
5. Verifizieren: Archiv wieder einlesen und die eigenen Dateien byte-vergleichen

Empfohlene Paketstruktur einer Quest-Mod:

```
Scripts\Quests\TwoWorldsQuests.qtx   Basis + eigene Blöcke + AOQ-Patch (Datei-Ebene: komplett)
Language\TwoWorldsQuests.lan         Master + eigene Schlüssel/Bäume
Language\ZZ_<Name>.lan               nur die eigenen Schlüssel/Bäume (Overlay, gewinnt zuletzt)
```

## 9. Verifizieren und Testen

**Die Marker-Methode** — immer zuerst beweisen, dass überhaupt geladen wird:

1. Eine bekannte, früh erreichbare Dialogzeile im Mod mit `[MOD] ` prefixen
2. Neues Spiel, Zeile ansehen
3. Marker da → Mod lädt, jetzt Inhalte debuggen.
   Marker fehlt → **Ladeproblem**, alles andere ist Zeitverschwendung
   (Archiv im falschen Ort? Registry? ignoriertes Archiv → Abschnitt 3.1?)

Mit zwei Markern (`[MOD]` in der Voll-Datei, `[MOD2]` im ZZ_-Overlay) sieht
man sogar, **welcher** Ladeweg greift.

**Testregeln:**
- **Immer neues Spiel.** Quest-*Zustand* backt in Spielstände ein; ein alter
  Save zeigt neue Quests nicht zuverlässig. (Texte hingegen laden live.)
- Spiel vor jedem Neupacken schließen (offene Dateien).
- Belohnungs-Probe: eine sichtbare Zahl (`REWARD GLD TAKE 1234`) beweist in
  Sekunden, ob die `.qtx` aus dem Mod kommt.

## 10. Troubleshooting: Symptom → Ursache

| Symptom | Ursache | Fix |
|---|---|---|
| Mod hat gar keine Wirkung, auch kein Marker | Archiv wird ignoriert (3.1) oder Registry aus | Marker-Test in ein nachweislich ladendes Archiv legen |
| Questtext neu, Dialoge original | eigener Schlüssel kollidiert mit späterem `.lan` in der Ladeordnung | Overlay `ZZ_*.lan` benutzen (gewinnt zuletzt) |
| NPC bietet Quest nicht an, sonst alles da | `0.FT` statt `0.FT.AS`, **oder** keine `AOQ PROMOTE`-Verkettung | Abschnitte 6 + 7 |
| Quest erscheint ohne Gespräch im Tagebuch | `AOQ TAKE TAKE` statt `PROMOTE TAKE` | PROMOTE |
| Roher Schlüsselname im Tagebuch | fehlender QTD/QSD/QCD-Schlüssel | alle vier Schlüssel liefern |
| Ganze `.qtx` tot, Parser-Chaos | CRLF-Zeilenenden | LF erzwingen (`assert b'\r' not in data`) |
| Bunte/kaputte Bodentexturen | vergifteter `Map_LevelHeaders.lhc` | Basiskopie zurück (3.3) |
| Werte im Spiel plötzlich „zurückgesetzt" | Registry-„Aufräumen" hat ein 0-Archiv reaktiviert | Registry-Backup einspielen |
| Änderung trifft mehr als gewollt | `str.replace()` ohne Anker über die Gesamtdatei | Block isolieren, Assert auf Eindeutigkeit |
| Archiv lässt sich nicht schreiben | Spiel läuft und hält die Datei | Spiel schließen |

## 11. Fallstudie: der Weg zur ersten Quest

Chronologie der echten Fehlversuche — als Landkarte, damit niemand sie
wiederholen muss:

1. **Eigener WD-Packer** → Archive perfekt lesbar, Spiel ignoriert sie.
   *Lektion: nur Referenz-Packer.*
2. **Neue `.lan` als Fantasiename** neben dem Master → nie geladen, weil der
   Test-Packer schuld war; später stellte sich heraus: `ZZ_`-Overlays
   funktionieren sehr wohl. *Lektion: erst Ladefähigkeit beweisen, dann
   Schlüsse ziehen.*
3. **Angebot mit `0.FT`** → NPC stumm. *Lektion: `0.FT.AS`.*
4. **Registry „aufgeräumt"** → altes Archiv reaktiviert, Spielwerte
   zurückgedreht. *Lektion: `= 0` ist ein Schalter.*
5. **Frisches Mod-Archiv komplett ignoriert** → gleicher Inhalt in ein
   ladendes Archiv gelegt: funktioniert. *Lektion: Marker-Methode.*
6. **Quest ohne AOQ** → nie angeboten. **`AOQ TAKE TAKE`** → stumm
   auto-angenommen. **`AOQ PROMOTE TAKE`** → Angebot im nächsten Gespräch.
7. **QSD vergessen** → roher Schlüssel im Tagebuch.
8. **`replace()` über die Gesamtdatei** → vier fremde Quests mit-gebufft.
   *Lektion: Änderungen ankern und zählen.*

Endzustand: Quest komplett spielbar, Referenz in `build_quest_tago.py`.

## 12. Modul-Referenz

| Datei | Zweck |
|---|---|
| `wdio.py` | **Der Packer.** buglords Referenz-Implementierung (CC0). `unpack_single(wd, dir)`, `pack_single(dir, wd, 1, None)` |
| `tw1_wd.py` | WD-**Leser** (`read(path)` → Entries mit `.path`/`.data`). `write()` deprecated — nie zum Packen benutzen |
| `tw1_lan.py` | `.lan` lesen/schreiben: `read()`, `build()`, `parse_trees()`, `build_trees()`, `DialogEntry`, `DialogTree`. Byte-exakter Round-Trip gegen die 3,3-MB-Master verifiziert |
| `tw1_qtx.py` | `.qtx` parsen/erzeugen mit Validierung: `make_quest()`, `sub_giver/sub_fc/sub_aoq/sub_action/sub_reward`, `append_quest()`, `free_quest_id()`, `index_ids()`. 500/500 Retail-Quests byte-exakt |
| `questforge.py` | JSON-Spec → fertige Mod-`.wd` (`--deploy`, `--register`). Automatisiert noch nicht: AOQ-Verkettung, ZZ_-Overlay — bei neuen Quests aktuell `build_quest_tago.py` als Vorlage nehmen |
| `build_quest_tago.py` | **Referenz-Quest**, reproduziert den spielgetesteten Stand byte-exakt. `--into <wd>` mergt in ein bestehendes Archiv |
| `extract_base.py` | zieht die Basisdateien aus der eigenen Installation |
| `tw1-quest-modding/SKILL.md` | Kurzfassung dieser Doku als Claude-Skill |
| `QuestForge_Guide.html` | illustrierte Einführung |
| `questforge2/` | **QuestForge 2**, der Node-Editor (Abschnitt 13). Importiert nur `tw1_qtx`, `tw1_lan`, `tw1_wd`, `wdio` |
| `TW1QuestCreator.pyw` | Starter ohne Konsole, zugleich Einstieg des Exe-Builds |
| `build_exe.spec`, `build_exe.bat` | Exe-Build mit PyInstaller → `dist\TW1QuestCreator.exe` |
| `tools/make_icon.py` | zeichnet das Programm-Icon (Pillow, nur für den Build nötig) |
| `NODE_EDITOR_PLAN.md` | Plan, Entscheidungen und Prüfergebnisse von QuestForge 2 |
| `testprojekte/` | Projekte für die offenen Spieltests (Ablehnen, Annahme auf der letzten Zeile) |

## 13. QuestForge 2: der Quest-Editor

Ein grafisches Werkzeug, das von "Neue Quest" bis zur gepackten, im Spiel
aktivierten Mod führt. Dialoge werden als Node-Graph gezeichnet, alle Quests
des Spiels liegen in einer Zeitleiste, ein Coach erklärt das Tool und baut auf
Wunsch mit einem Tutorial eine Test-Quest.

### 13.1 Starten

Die fertige Exe liegt bei jedem Release auf GitHub:
<https://github.com/MedievalDev/TW1_DialogAndQuestCreator/releases>

```
TW1QuestCreator.exe                 fertige Exe, kein Python nötig
py -3.12 -m questforge2             aus dem Quelltext (Repo-Ordner)
TW1QuestCreator.pyw                 Doppelklick, ohne Konsole
```

Beim ersten Start sucht das Tool den Spielordner (Konfig, Registry,
Steam-Bibliotheken), zieht die Basisdateien aus `Update16.wd` und
`Language.wd` und baut einen Index aller Quests, NPCs, Orte, Marker und
Voice-Cues (etwa 1,5 s). Danach startet es aus dem Cache (Exe unter 2 s).
Daten liegen neben dem Quelltext bzw. bei der Exe in
`%LOCALAPPDATA%\TW1QuestCreator` (`questforge_config.json`, `base\`,
`cache\index.json`, `templates\`).

### 13.2 Bedienung in Kürze

- **Zeitleiste** (oben): alle Quests als Karten in Kettenreihenfolge, nach
  Tagebuchgruppen getrennt. Jede Questreihe hat ihre eigene Farbe, über den
  Karten liegt eine Reiterleiste mit allen Questreihen und ihrer Anzahl, und
  die Gruppenüberschrift nennt die Zahl der Quests darin. Klick öffnet eine Quest. Spielquests sind erst
  eine Ansicht und werden bei der ersten Änderung nach Rückfrage Teil des
  Projekts. Rechtsklick: duplizieren als eigene Quest, nur diese Quest
  exportieren, als Text anzeigen. "Quellen" blendet Spiel, eigene Quests,
  Mods und jede Mod einzeln ein und aus.
- **Sprecher** (links oben): "+ Neuer Sprecher" wählt einen NPC des Spiels
  oder legt einen neuen an (ID aus dem Two Worlds Editor, Stimme, Kachel,
  Q_Giver-Marker, Vorlage für das Aussehen). Sprecher in den Graph ziehen oder
  doppelklicken.
- **Graph** (Mitte): Spieler-Nodes (Antwort oder Frage mit mehreren Zeilen)
  und NPC-Nodes, verbunden von Ausgang zu Eingang. Die Reiter Angebot,
  Läuft, Erfüllt, Abgeschlossen (plus Bekannt, Fehlgeschlagen, Ruf, Immer)
  sind die Zustandsebenen aus 6.1. Pro Zeile die Haken "Nimmt die Quest an",
  "Schließt die Quest ab", "Kampf beginnt". Nodes zeigen den ganzen Text
  und wachsen nach unten mit. Mausrad zoomt, Strg+Rad scrollt senkrecht,
  Umschalt+Rad waagerecht, mittlere Maustaste verschiebt.
- **Aufgabe, Aktionen, Bedingungen** (links unten): die Aufgabe (`FC`) steht
  links neben dem Einstieg Erfüllt, Aktionen docken oben an Dialogzeilen (der
  Zeitpunkt folgt aus der Ebene), Bedingungen hängen unter dem Einstieg
  Angebot (Vorgängerquest, Level, Gilde). Aktionen ohne Dialog stehen im
  Quest-Panel.
- **Ziehen und Ablegen:** "+ Neue Aktion" hängt beim Ziehen an der Maus, der
  Ziel-Node bekommt einen goldenen Rahmen, und die Statusleiste sagt, ob dort
  abgelegt werden kann. Die drei Einträge im Kasten haben Hilfetexte beim
  Überfahren.
- **Kopfleiste:** Neben "+ Neue Quest" liegen die Knöpfe "Questgrenze" mit der
  wirksamen Grenze und "Gegnerstufen".
- **Guide (F1, Hilfe > Guide):** eigenes Fenster mit 14 Kapiteln von "Erste
  Quest in 10 Minuten" bis "Fehlersuche", Suchfeld, Deutsch und Englisch. Die
  Tabellen (Aufgaben, Aktionen, Marker-Sorten, Parteien, Gilden, AOQ,
  Animationen) werden aus denselben Code-Tabellen erzeugt wie die
  Auswahllisten, mit Quelle und Status "belegt" oder "ungeprüft".
- **Updates:** Beim Start fragt das Tool (abschaltbar unter Hilfe) die GitHub-API
  nach dem neuesten Release. Ist es neuer, zeigt ein Fenster die Release Notes:
  Jetzt aktualisieren, Später, Diese Version überspringen. "Jetzt
  aktualisieren" lädt die Exe neben die laufende (`.new`), prüft die
  SHA-256-Prüfsumme, die GitHub zum Asset speichert (ohne Prüfsumme oder bei
  Abweichung wird nichts installiert), schließt das Tool nach Rückfrage bei
  ungespeicherten Änderungen, und ein kleiner Batch tauscht die Exe, sobald
  der Prozess beendet ist, und startet die neue Version. Die alte Exe bleibt
  bis zum nächsten Start als `.old`. Aus dem Quelltext gestartet öffnet der
  Knopf nur die Release-Seite. Immer neueste Version:
  https://github.com/MedievalDev/TW1_DialogAndQuestCreator/releases/latest
- **Neue Quest:** Knopf im leeren Graph, in der Kopfleiste und im Quest-Menü;
  leer, aus einer mitgelieferten Vorlage (Bring-Quest,
  Töte-X, Sprich-mit-NPC, Questkette mit Tor) oder als Kopie einer
  bestehenden Quest. Die Kopie bekommt eine freie Nummer, Verweise auf sich
  selbst werden umgeschrieben, Verweise auf andere Quests aufgelistet. Nach
  einer Vorlage ist der erste TODO-Node ausgewählt; die Prüfung meldet jeden
  Node mit TODO einzeln, Doppelklick springt hin.
- **Vorlagen:** liegen als JSON in `questforge2/templates/`. Format:
  `{"template": {"kind": "quest"|"enemy", "title": {"de", "en"}, "note":
  {"de", "en"}}, ...}`; Quest-Vorlagen tragen dazu eine vollständige Quest
  (`Quest.to_dict`), Gegner-Vorlagen `args` für `ACTION ENEMY_CREATE`. Neue
  Datei ablegen genügt. Gegnergruppen stehen im Aktionsformular "Gegner
  erzeugen" als Auswahl. Stellen mit `TODO` meldet die Prüfung als Warnung.
- **Mods als Quelle (Menü Mods):** `.wd`-Archive oder entpackte Ordner werden
  pro Projekt eingebunden (Liste und Reihenfolge stehen in der Projektdatei).
  Das Tool liest Questdatei, NPCs, Orte, Truhen, Sprachdateien und Karten
  (`Levels\Map_E01.lnd` = Tile `E1`), zwischengespeichert je Mod unter
  `cache/mods/`. Alles aus Mods ist hellblau: eigener Bereich in der
  Zeitleiste ("MOD neu", "MOD geändert"), Punkt vor dem Namen in Listen,
  Tooltip mit Mod, Datei und Tile.
  - **Mod-Quests** werden in der Mod bearbeitet: Speichern schreibt Questblock
    und Texte zurück, beim Archiv mit `wdio` und Prüfung aller übrigen
    Einträge samt Verzeichnisdaten, danach Vergleich mit den Archiven des
    Spiels. Vor dem ersten Schreiben des Tages entsteht
    `<Mod>.bak-<Datum>`, "Sicherung wiederherstellen" spielt sie zurück.
    Hinweis einmal pro Sitzung: Änderungen wirken erst in einem neuen Spiel
    (Questdatei wird in `state Initialize` gelesen, SDK `PQuests.ec`).
  - **Marker:** Der Marker-Picker liest die Karten selbst (Spiel:
    `Levels.wd`, `Update11-15.wd`, `Update16.wd`, Cache
    `cache/lnd_markers.json`) und die Karten der Mods. Die Markernamen je
    Befehl stammen aus SDK `PEnums.ech`; gemessen am 16.09.2026 liegen alle
    287 Markerverweise der Original-Quests und alle 216 NPC-Startmarker unter
    diesen Namen auf ihrem Tile.
  - **Rote Tiles:** Fehlen in einer Mod-Karte Marker des Spiels, ist das Tile
    rot und seine Marker sind für Quests außerhalb der Mod gesperrt.
  - **Abhängigkeiten:** Benutzt eine eigene Quest einen Marker, den nur eine
    Mod hat, kommt deren `.lnd` beim Export mit Flags, Klassen-Id und GUID der
    Mod ins Archiv (Rückfrage beim Zuweisen, Liste unter Mods >
    Abhängigkeiten). Zwei Mods mit demselben Tile blockieren den Export, bis
    eine gewählt ist. Welche Mod das Spiel später lädt, ist ungeprüft; das
    Tool nimmt die Reihenfolge der Mod-Liste.
  - Freie Questnummern zählen die Quests der Mods mit; gleiche Nummern
    meldet die Prüfung.
- **Karte (Kopfleiste "Karte", Ansicht > Karte):** Weltkarte aus den Minimaps
  des Spiels (`Levels\MipMaps\Map_E01@0..3.dds`, DXT1, im Tool ohne
  Zusatzbibliothek entpackt und als PNG neben der Projektdatei in
  `<Projekt>_map/` zwischengespeichert). Nicht-modal, Mausrad zoomt (64 bis
  1024 Pixel je Tile), Ziehen verschiebt, Tile-Namen einblendbar, Ebene
  Oberfläche oder Innenräume `_1`. Punkte: alle Marker der Karten des Spiels
  und der Mods, Orte (`LOCATION`), Truhen der Mods (`CONTAINER`). Filter nach
  Herkunft, Marker-Typ (Gruppen aus SDK `PEnums.ech`,
  `TwoWorldsEnemies16.ec`, `TwoWorldsTeleports.ec`), benutzt/unbenutzt und
  Suche. Farben: Spiel hell, eigene gold, Mods hellblau. Hover zeigt Name,
  Typ, Nummer, Tile, Koordinaten, Herkunft.
  - **Anbindung:** Knopf "Karte" neben jedem Marker-Feld und im Marker-Picker
    (gefiltert auf die gelesene Sorte, Rechtsklick > In Quest verwenden
    trägt Nummer und Tile ein, falsche Sorte fragt nach, Mod-Marker laufen
    durch dieselbe Prüfung wie im Picker). "Auf der Karte zeigen" im Picker
    und in den Abhängigkeiten; Rechtsklick auf eine Quest zeigt ihre Marker
    hervorgehoben.
  - **Umrechnung:** 128 × 128 Zellen je Karte (Kartenkopf), 256 Einheiten je
    Zelle (SDK `nX/=256`), also 64 Einheiten je Minimap-Pixel; y zeigt auf
    der Minimap nach oben, Zeilen laufen nach unten. Per Sichtprüfung
    bestätigt (Tore D8, Truhen F8, Teleporter E1, Gänge B8_1, nahtlose
    Kachelgrenzen), im Spiel nicht nachgemessen; die Karte sagt das so.
- **Hilfe im Formular:** Neben Panel-Titeln und erklärungsbedürftigen Feldern
  steht ein `?`. Überfahren zeigt eine kurze Erklärung, Klick öffnet die
  Dokumentation. Eingabefelder zeigen ein Beispiel, ungültige Eingaben werden
  sofort rot erklärt (keine Zahl, falsche Kachel, Semikolon, Umlaut).
- **Vorschau:** Unter Aufgabe und Aktion steht die Zeile, die so in die
  Questdatei geschrieben wird. "Rohtext bearbeiten" macht sie tippbar:
  gültige Zeilen übernehmen die Felder sofort, ungültige werden erklärt
  (falscher Befehl, falsche Anzahl Werte, unbekannter Zeitpunkt) und ändern
  nichts.
- **Multiplayer-Quest übernehmen (Quest-Menü, "+ Neue Quest", Rechtsklick
  auf eine MP-Karte):** Q_700–Q_819 gehören dem Multiplayer-Skript
  (`PQuestsMulti.ec`, zählt ab 699); das Einzelspieler-Skript verwirft
  Questnummern ab 400 und NPC-Nummern ab 698 beim Laden (`PQuests.ec`
  `eQuestsNum 400`, `eQuestUnitsNum 698`), und die MP-Zeilen haben keine
  Kacheln. Der Assistent in drei Schritten: MP-Quest wählen; freie
  Questnummer, freie NPC-Nummer (ab 507), Name, Kachel, Tagebuchgruppe,
  je Markerzeile Kachel und Nummer (Nummern bleiben, wenn die Kachel sie
  nicht hat, sonst nächste freie); Marker-Checkliste. Das Tool setzt keine
  Marker: die Liste (Name, Nummer, Kachel) steht danach im Quest-Panel mit
  Haken, offene Punkte meldet die Prüfung. Der Geber wird ein neuer NPC mit
  Partei 25; Dialogzeilen ohne Sprecher (MP-Bäume haben keinen Lector)
  gehören ihm. Zeitleiste: MP-Quests tragen "MP".
  Unter der Checkliste nimmt das Feld **Karten aus dem Editor** die im Two
  Worlds Editor gespeicherten Kacheln an (`Map_<Kachel>s.lnd` und
  `physic\Map_<Kachel>s.phx` aus `Saved Games\Two Worlds Saves\Levels`,
  ziehen oder wählen). Sie kommen unter dem Spielnamen in den Ordner
  `<Projekt>_levels` (als Mod im Projekt), die Marker werden sofort gelesen
  und abgehakt, der Export packt `.lnd` und `.phx` mit. Danach vor dem
  nächsten Spielstart `LevelHeadersCacheGen.bat` aus dem SDK ausführen
  (Knopf im Panel, siehe 3.3).
- **Marker direkt auf der Karte setzen (3.9.0):** Knopf **Marker auf der
  Karte setzen** in Schritt 3 des MP-Assistenten und im Quest-Panel über der
  Checkliste. Die Karte öffnet sich ohne vorhandene Marker, links die zu
  setzenden: Eintrag anklicken, Marker hängt an der Maus, Klick auf die Karte
  setzt ihn (Eintrag grün mit Haken; nochmal anklicken hebt ihn wieder auf,
  Esc/Rechtsklick legt ihn zurück). Höhe aus der Höhenkarte der Kachel,
  unbegehbarer Boden rot ab Nahzoom. Bestätigen schreibt die Kacheln nach
  `<Projekt>_levels` (Basis: Spielkarte, Mod-Karte oder gesicherte
  Editor-Kachel, fehlende Spielmarker ergänzt). Innenräume weiter im Editor.
- **Level-Header-Cache automatisch (3.9.1):** Hat das Projekt Kartenkacheln,
  baut der Export den Cache danach selbst neu (`MeshParamsGen.exe` aus dem
  SDK, mit dem Spielpfad des Tools; Ergebnis im Export-Fenster, abschaltbar
  unter Datei > Einstellungen). Ohne SDK bleibt der Hinweis auf
  `LevelHeadersCacheGen.bat`.
- **Rote Kacheln reparieren:** Meldet der Export eine Mod-Karte ohne
  Originalmarker, bietet das Fehlerfenster **Reparieren** an: Kopie der
  Mod-Kachel mit den fehlenden Spielmarkern im Projektordner, dann erneut
  exportieren.
- **Zeilen aufnehmen:** Punkt-Knopf in der Voice-Cue-Zeile jeder Dialogzeile
  (Aufnehmen/Stopp, darunter Zeit und Pegel, danach Abspielen/Löschen).
  Mikrofon mit Probeaufnahme unter Datei > Einstellungen (gemerkt). WAV 16 Bit mono 44,1 kHz
  im Ordner `<Projekt>_voice`, verknüpft als `voice` an der Zeile. Aufnahme
  über winmm ohne Zusatzbibliothek. Ins Spiel kommt sie erst über den Bau
  der Sprachbank (Sounds.xsb/UnitTalk.xwb), den das Tool nicht macht.
- **Voiceline-Finder** (Suchen... beim Voice-Cue): tippen, was gesagt werden
  soll; gleiche und ähnliche Originalzeilen mit Trefferwert, Standard der
  Held, filterbar nach jedem Originalsprecher. Anhören direkt aus
  `UnitTalk.xwb` (MS-ADPCM als WAV verpackt, keine Zusatzbibliothek),
  Übernehmen setzt Cue und Wortlaut.
- **Aufnahme-Bibliothek und Kürzen:** Ansicht > Aufnahme-Bibliothek listet
  alle Aufnahmen mit Quest und Zeile (abspielen, hinspringen, kürzen,
  unbenutzte löschen). Der Kürzen-Editor zeigt die Wellenform mit zwei
  Griffen, erkennt Stille und hebt das Original in `_voice\_original` auf.
- **Dialog-Vorlage:** Quest > Dialog aus Vorlage einfügen > "Standard-
  Questgeber" setzt Angebot mit Annehmen/Ablehnen, Antwort während die Quest
  läuft, Dank beim Erfüllen und einen Satz danach in die offene Quest. Es
  spricht der Questgeber; freie Einstiege werden verbunden, belegte bleiben.
- **Quest-Verknüpfungen (AOQ):** Im Quest-Panel lassen sich Zeilen
  `AOQ <Typ> <Auslöser> Q_<Ziel>` anlegen. Typen laut SDK: PROMOTE, TAKE,
  DISABLE, SOLVE, CLOSE, FAIL_CLOSE. Auslöser: ENABLE, TAKE, HEAR, SOLVE,
  CLOSE, FAIL, FIGHT, NONE. `AOQ ENABLE` gibt es nicht.
- **Eigenschaften** (rechts): Formular des gewählten Elements, ohne Auswahl
  die Quest selbst. ID-Felder haben einen Kachel-Picker, Dialogzeilen eine
  Cue-Suche. Das Feld Partei listet die Fraktionsnummern des SDK mit Namen
  (18 Tiere, 19 Grünhäute, 20 Banditen, 21 Untote, 22 verseuchte Untote,
  23 böse Krieger, 24 Geister, 25 Menschen, 26 bis 42 Stadtparteien,
  43 neutrale Banditen); eigene Zahlen bleiben tippbar.
- **Validieren** (F7, Statusleiste): Fehler blockieren den Export, Warnungen
  nicht; Doppelklick springt zur Stelle.
- **Exportieren** (Strg+E): siehe 13.3. "Nur Dateien exportieren" schreibt
  die drei Dateien in einen Ordner.
- **Hilfe:** Rundgang, Tutorial, diese Dokumentation, klickbare Links (GitHub-Repo, Alchemy Fox, Guide-Seite, Community), Über.
- **Sprache:** `DE · EN` oben rechts in der Menüleiste schaltet sofort um.
  Projekt und Ansicht bleiben erhalten.
- **Gegnerstufen** (Quest > Gegnerstufen der Welt): Das Spiel erschafft
  herumlaufende Tiere und Gegner auf der mittleren Heldenstufe und begrenzt
  sie dann je Kreaturenart auf ein Minimum und ein Maximum (im SDK
  `InitializeEnemyLevels`, etwa Grauwolf 6 bis 10, Drache 40 bis 100).
  Deshalb bleiben Tiere im späten Spiel harmlos. Das Fenster zeigt alle 90
  Arten nach Gruppen sortiert, mit Filter, Schieberegler und Eingabefeld je
  Wert, dazu Schnellwahl für die angezeigten Arten: an Heldenstufe koppeln,
  Zuschlag, Faktor, Originalwerte. "Übernehmen" schreibt beide
  Gegner-Skripte (`TwoWorldsEnemies.eco` und `TwoWorldsEnemies16.eco`) mit
  frischer GUID als `Mods\EnemyLevels.wd`. Gilt für neu erschaffene Gegner,
  also neues Spiel oder noch nicht betretene Gebiete.
- **Questgrenze** (Quest > Questgrenze, oder Klick auf "Grenze" in der
  Statusleiste): Das Spiel kennt ab Werk 400 Questnummern. "Auf 600 anheben"
  liest das Original-Questskript `PQuests.eco` aus `Update16.wd`, setzt die
  41 Stellen mit 400 auf 600 und legt es als `Mods\QuestLimit600.wd` mit
  frischer GUID ab (die Engine führt Skripte über die GUID, mit der
  Original-GUID liefe weiter die 400). Die Mod-Schalter werden vorher nach
  `backup\` exportiert. Danach sind eigene IDs bis 599 frei; die Validierung
  sperrt IDs über der wirksamen Grenze und warnt ab 400, dass Spieler die
  Grenz-Mod ebenfalls brauchen. Gilt nur für neue Spiele. "Zurück auf 400"
  entfernt die Datei und schaltet sie aus. Übernommen aus dem TW1 Quest Limit
  Patcher 1.0, gleicher Dateiname, beide Werkzeuge erkennen sich gegenseitig.

### 13.3 Was der Export macht

1. Prüft alle Quests des Projekts, bricht bei Fehlern ab.
2. Bricht ab, wenn ein Two-Worlds-Prozess läuft (`TwoWorlds*.exe`).
3. Warnt, wenn eine andere aktive Mod ebenfalls die komplette `.qtx` oder
   Master-`.lan` liefert (3.1). In dem Fall am besten in dieses Archiv
   exportieren (Quest-Panel, Zielarchiv).
4. Nimmt `.qtx` und `.lan` aus dem Zielarchiv, sonst aus der Basis. Setzt den
   Questblock ein bzw. ersetzt ihn, trägt die `AOQ PROMOTE`- (oder `TAKE`-)
   Zeilen in die Vorgängerquests ein, legt NPC-Blöcke für neue NPCs an und
   schreibt Titel, Tagebuch, Dialogbaum und NPC-Namen in die Master-`.lan`
   und in `Language\ZZ_QF_<Projekt>.lan`. Liegen im Archiv
   `ZZ_QF_`-Dateien anderer Projekte mit denselben Quest-IDs, werden deren
   Texte dieser IDs entfernt, leere Dateien fliegen raus.
5. Packt mit `wdio.py`, liest das Archiv wieder ein und vergleicht alle
   Dateien byte-genau sowie Flags, Namen, Klassen-IDs und GUIDs aller
   unberührten Einträge. Erst dann wird das Archiv ersetzt. Vor dem ersten
   Export entsteht einmalig `<Archiv>.qf2backup`.
6. Setzt `HKCU\SOFTWARE\Reality Pump\TwoWorlds\Mods\<Archiv> = 1`.

Unveränderte Spielquests kommen byte-gleich wieder heraus (getestet für alle
500 Questblöcke und alle 378 Questbäume der Basisdateien).

### 13.4 Projektdatei

`*.tw1proj` ist JSON (UTF-8, LF): Projektname, Zielarchiv und die Quests mit
Graph, Sprechern, Tagebuch und Aktionen. Unbekannte Felder bleiben beim
Speichern erhalten. Quest-Vorlagen (`*.tw1quest`) liegen im Ordner
`templates`.

### 13.5 Exe bauen

```
build_exe.bat
```

Braucht Python mit PyInstaller (auf Marcos Rechner Python 3.13). Ergebnis:
`dist\TW1QuestCreator.exe`, eine Datei, rund 11,5 MB, ohne Spieldaten.
Selbsttest ohne Fenster: Umgebungsvariable `QF2_SELFTEST=<Datei>` schreibt
Version und Startzeit in die Datei und beendet das Programm.

### 13.6 Offene Punkte

Im Spiel bestätigt (Stand 2.1.1): Ablehnen und Annahme im Angebot,
Annahme nur auf der letzten Zeile, eine komplett mit dem Tool gebaute Quest
und eine geänderte Original-Quest. Die Testprojekte liegen in
`testprojekte\`.

Noch offen, Details in `NODE_EDITOR_PLAN.md` Abschnitt 12: die
Startzeilen-Regel der Engine, die übernommenen Spalten im NPC-Block neuer
NPCs und `ACTION NPC_DIALOG` (im Tool nicht angeboten).

## 14. Credits und Lizenz

- `wdio.py`: **buglord** — CC0, aus dessen Misc-Projects übernommen. Ohne
  diesen Packer wäre das Projekt an Phantom-Fehlern gescheitert.
- Alle übrigen Werkzeuge und diese Doku: MedievalDev-Projekt.
- Es werden **keine Spieldaten** verteilt. Two Worlds ist ein Titel von
  Reality Pump / TopWare Interactive; für den Bau eigener Mods braucht jeder
  eine eigene Spielkopie.

Alchemy Fox: <https://alchemy-fox.de/>  
Community: <https://twmp.alchemy-fox.de/>
