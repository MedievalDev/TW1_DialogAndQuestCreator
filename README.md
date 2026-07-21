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
13. [Credits und Lizenz](#13-credits-und-lizenz)

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
| Quest-ID **381–699** | 1–380 ist Einzelspieler, 700–959 ist Multiplayer, dazwischen ist alles frei. Der Parser selbst kennt keine Obergrenze — die mitgelieferten Mehrspieler-Kartendateien nutzen IDs wie 2001 und 4001. Eine engine-seitige Array-Grenze irgendwo in diesem Bereich lässt sich aus den Daten allein nicht ausschließen; sie würde sich als Quest zeigen, die einfach nie erscheint. |
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

## 13. Credits und Lizenz

- `wdio.py`: **buglord** — CC0, aus dessen Misc-Projects übernommen. Ohne
  diesen Packer wäre das Projekt an Phantom-Fehlern gescheitert.
- Alle übrigen Werkzeuge und diese Doku: MedievalDev-Projekt.
- Es werden **keine Spieldaten** verteilt. Two Worlds ist ein Titel von
  Reality Pump / TopWare Interactive; für den Bau eigener Mods braucht jeder
  eine eigene Spielkopie.

Community: <https://twmp.alchemy-fox.de/>
