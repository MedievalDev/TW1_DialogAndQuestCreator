"""UI language: ``t(key)`` with German and English dictionaries.

The language is picked once at start-up (config, else Windows locale) and
does not change live; switching in the View menu takes effect after a
restart (plan section 2.1). Unknown keys return the key itself so a missing
translation is visible instead of crashing.
"""

import locale

LANGS = ('de', 'en')
_lang = 'en'

_DE = {
    # generic
    'app.title': 'TW1 Quest Creator',
    'ok': 'OK', 'cancel': 'Abbrechen', 'yes': 'Ja', 'no': 'Nein',
    'close': 'Schliessen', 'error': 'Fehler',
    'ctrl': 'Strg',
    # menus
    'menu.file': 'Datei', 'menu.edit': 'Bearbeiten', 'menu.view': 'Ansicht',
    'menu.quest': 'Quest', 'menu.help': 'Hilfe',
    'file.new': 'Neues Projekt', 'file.open': 'Projekt oeffnen...',
    'file.recent': 'Zuletzt geoeffnet', 'file.recent.none': '(leer)',
    'file.save': 'Speichern', 'file.saveas': 'Speichern unter...',
    'file.gamepath': 'Spielpfad waehlen...',
    'file.export': 'Exportieren als Mod...',
    'file.exportfiles': 'Nur Dateien exportieren...',
    'file.quit': 'Beenden',
    'edit.undo': 'Rueckgaengig', 'edit.redo': 'Wiederholen',
    'edit.cut': 'Ausschneiden', 'edit.copy': 'Kopieren',
    'edit.paste': 'Einfuegen', 'edit.duplicate': 'Duplizieren',
    'edit.delete': 'Loeschen', 'edit.selectall': 'Alles auswaehlen',
    'edit.autolayout': 'Auto-Layout',
    'view.zoomin': 'Zoom +', 'view.zoomout': 'Zoom -',
    'view.zoom100': 'Zoom 100 %', 'view.fit': 'Auf Inhalt einpassen',
    'view.timeline': 'Zeitleiste', 'view.palette': 'Sprecher-Box',
    'view.inspector': 'Eigenschaften', 'view.coach': 'Coach',
    'view.grid': 'Raster anzeigen', 'view.edges': 'Kanten-Stil',
    'view.edges.curve': 'Kurve', 'view.edges.line': 'Gerade',
    'view.lang': 'Sprache', 'view.lang.de': 'Deutsch',
    'view.lang.en': 'English',
    'view.lang.restart': 'Die Sprache wird nach dem naechsten Start '
                         'verwendet.',
    'quest.new': 'Neue Quest', 'quest.duplicate': 'Quest duplizieren',
    'quest.delete': 'Quest loeschen', 'quest.validate': 'Validieren',
    'quest.preview': 'Vorschau als Text', 'quest.template':
    'Als Vorlage speichern',
    'help.tour': 'Rundgang starten',
    'help.tutorial': 'Tutorial: Test-Quest anlegen',
    'help.docs': 'Dokumentation', 'help.about': 'Ueber',
    # panels
    'panel.timeline': 'ZEITLEISTE', 'panel.speakers': 'SPRECHER',
    'panel.actions': 'AUFGABEN / AKTIONEN / BEDINGUNGEN',
    'panel.inspector': 'EIGENSCHAFTEN', 'panel.coach': 'COACH',
    'panel.placeholder': 'Kommt in Meilenstein {m}',
    'graph.empty': 'Keine Quest geoeffnet.\n'
                   'Quest > Neue Quest legt eine an (Meilenstein 3).',
    # status bar
    'status.noproject': 'Kein Projekt', 'status.nogame': 'Kein Spielpfad',
    'status.noquest': 'Keine Quest', 'status.nodes': '{n} Nodes',
    'status.validation.none': 'Validierung: -',
    'status.index.loading': 'Index wird geladen...',
    'status.index.cache': 'Index aus Cache ({s:.2f} s)',
    'status.index.built': 'Index neu gebaut ({s:.1f} s)',
    'status.start': 'Start {s:.2f} s',
    # project
    'project.untitled': 'Unbenannt',
    'project.filter': 'QuestForge-Projekt',
    'project.unsaved.title': 'Ungespeicherte Aenderungen',
    'project.unsaved.q': 'Das Projekt "{name}" hat ungespeicherte '
                         'Aenderungen. Speichern?',
    'project.open.error': 'Projekt konnte nicht geoeffnet werden:\n{err}',
    'project.save.error': 'Projekt konnte nicht gespeichert werden:\n{err}',
    'project.missing': 'Die Datei existiert nicht mehr:\n{path}',
    # game path / index
    'game.ask.title': 'Spielverzeichnis waehlen',
    'game.ask.msg': 'Bitte den Ordner von Two Worlds waehlen '
                    '(der Ordner, der WDFiles enthaelt).',
    'game.invalid': 'In diesem Ordner fehlt WDFiles\\Update16.wd.\n'
                    'Nochmal versuchen?',
    'game.set': 'Spielpfad gesetzt:\n{path}',
    'index.title': 'Spieldaten werden eingelesen',
    'index.intro': 'Das passiert nur beim ersten Start oder wenn sich '
                   'Spieldateien geaendert haben.',
    'index.step.base': 'Basisdaten aus dem Spiel extrahieren...',
    'index.step.qtx': 'Quests und NPCs lesen...',
    'index.step.lan': 'Texte und Dialogbaeume lesen...',
    'index.step.mods': 'Mods lesen: {name}',
    'index.step.save': 'Index speichern...',
    'index.error': 'Spieldaten konnten nicht gelesen werden:\n{err}',
    # about
    'about.title': 'Ueber {app}',
    'about.version': 'Version {v}',
    'about.links': 'Links', 'about.guide': 'Guide-Seite',
    'about.github': 'GitHub-Repo', 'about.community': 'Community',
    'about.credits': 'wdio.py von buglord (CC0). Alle uebrigen Teile: '
                     'MedievalDev.',
    'about.nodata': 'Dieses Programm enthaelt keine Spieldaten. Two Worlds '
                    'ist ein Titel von Reality Pump / TopWare Interactive.',
    'stats': '{q} Quests, {n} NPCs, {c} Cues, {f} freie IDs',
    # graph
    'tab.0.FT.AS': 'Angebot', 'tab.0.QNS.AE': 'Laeuft',
    'tab.0.QS.AE': 'Erfuellt', 'tab.0.QC': 'Abgeschlossen',
    'tab.0.FT': 'Gruss', 'tab.0.QNT': 'Bekannt', 'tab.0x0': 'Neutral',
    'node.entry': 'Einstieg', 'node.end': 'Ende',
    'node.dialog': 'Dialog-Node', 'node.comment': 'Kommentar',
    'ctx.add': 'Node hinzufuegen', 'ctx.attach': 'An Node anheften',
    'ctx.detach': 'Kommentar loesen',
    'ctx.attach_comment': 'Kommentar anheften',
    'ctx.disconnect': 'Kante(n) trennen', 'ctx.cut_edge': 'Trennen',
    'ctx.color': 'Farbe',
    'status.frame': 'Ziehen {ms:.1f} ms',
    'quest.debug300': 'Debug: 300 Test-Nodes',
    'quest.noquest': 'Keine Quest geoeffnet.',
    'quest.noid': 'Keine freie Quest-ID mehr (381 bis 399 sind belegt).',
    # levels (states)
    'state.first': 'Angebot', 'state.known': 'Bekannt',
    'state.running': 'Laeuft', 'state.taken': 'Angenommen',
    'state.solved': 'Erfuellt', 'state.closed': 'Abgeschlossen',
    'state.failed': 'Fehlgeschlagen', 'state.lowrep': 'Ruf zu niedrig',
    'state.neutral': 'Immer',
    'state.short.first': 'Angebot', 'state.short.known': 'Bekannt',
    'state.short.running': 'Laeuft', 'state.short.taken': 'Angen.',
    'state.short.solved': 'Erfuellt', 'state.short.closed': 'Abgeschl.',
    'state.short.failed': 'Fehlgeschl.', 'state.short.lowrep': 'Ruf',
    'state.short.neutral': 'Immer',
    'state.help.first': 'Spielt beim ersten Ansprechen. Endet das Gespraech '
                        'ueber eine Zeile mit "Nimmt die Quest an", ist die '
                        'Quest angenommen.',
    'state.help.known': 'Spielt, wenn der Spieler das Angebot gehoert und '
                        'nicht angenommen hat.',
    'state.help.running': 'Spielt, solange die Aufgabe nicht erledigt ist '
                          '(auch schon vor der Annahme).',
    'state.help.taken': 'Spielt nach der Annahme, egal ob erledigt oder '
                        'nicht (Retail-Ebene, selten noetig).',
    'state.help.solved': 'Spielt, wenn die Aufgabe erledigt ist. '
                         '"Schliesst die Quest ab" gibt die Belohnung.',
    'state.help.closed': 'Spielt nach dem Abschluss der Quest.',
    'state.help.failed': 'Spielt, wenn die Quest fehlgeschlagen ist.',
    'state.help.lowrep': 'Spielt statt des Angebots, wenn der Ruf unter dem '
                         'Mindestruf der Quest liegt.',
    'state.help.neutral': 'Spielt in jedem Zustand (Fragemenues, Smalltalk).',
    'tab.more': '+', 'tab.all': 'Alle',
    # speakers
    'speaker.player': 'Spieler', 'speaker.new': '+ Neuer Sprecher',
    'speaker.dialog.title': 'Neuer Sprecher',
    'speaker.existing': 'Vorhandener NPC', 'speaker.newnpc': 'Neuer NPC',
    'speaker.search': 'Name oder NPC-ID tippen:',
    'speaker.own': 'Eigene', 'speaker.id': 'NPC-ID (Two Worlds Editor)',
    'speaker.name': 'Anzeigename', 'speaker.lector': 'Stimme (Lector)',
    'speaker.lector.none': 'stumm / eigener Lector',
    'speaker.lector.of': 'Stimme von {names} (Lector {n})',
    'speaker.tile': 'Heimat-Kachel (z. B. F05)',
    'speaker.hint': 'Der NPC braucht im Two Worlds Editor einen Q_Giver-'
                    'Marker mit derselben Nummer in dieser Kachel, sonst '
                    'friert das Spiel beim Laden der Kachel ein.',
    'speaker.id.invalid': 'Bitte eine Zahl eingeben (z. B. 700).',
    'speaker.id.taken': 'NPC_{id} ist im Spiel schon vergeben ({name}). '
                        'Fuer einen vorhandenen NPC die erste Karte benutzen.',
    'speaker.rename': 'Umbenennen', 'speaker.remove': 'Entfernen',
    'speaker.remove.used': 'Dieser Sprecher wird noch von Nodes benutzt.',
    'speaker.mark': 'Alle Zeilen dieses Sprechers markieren',
    'node.player': 'Spieler', 'node.npc': 'NPC',
    # inspector
    'insp.quest': 'QUEST', 'insp.id': 'Quest-ID',
    'insp.id.hint': 'Frei sind 381 bis 399 (das Spiel kennt nur 19 eigene '
                    'IDs).',
    'insp.title': 'Titel', 'insp.group': 'Tagebuchgruppe',
    'insp.journal.take': 'Tagebuch: Annahme',
    'insp.journal.solve': 'Tagebuch: Erfuellt',
    'insp.journal.close': 'Tagebuch: Abgeschlossen',
    'insp.giver': 'Questgeber', 'insp.giver_type': 'Giver-Typ',
    'insp.map_sign': 'Kartenmarker',
    'insp.map_sign.hint': 'BACK_TO_GIVER_MAP_SIGN setzt den Marker nach '
                          'Erfuellung zurueck zum Questgeber.',
    'insp.offered': 'Start', 'insp.offered.check':
    'Quest wird angeboten (Gespraech). Aus = startet automatisch.',
    'insp.archive': 'Zielarchiv (Mods\\*.wd)',
    'insp.speaker': 'Sprecher', 'insp.state': 'Ebene', 'insp.text': 'Text',
    'insp.take': 'Nimmt die Quest an', 'insp.close': 'Schliesst die Quest ab',
    'insp.fight': 'Kampf beginnt', 'insp.advanced': 'Erweitert',
    'insp.cue': 'Voice-Cue', 'insp.cue.search': 'Suchen...',
    'insp.cue.text': 'Aufnahme:',
    'insp.cue.mismatch': 'Untertitel weicht von der Aufnahme ab. Der Text '
                         'muss zur Aufnahme passen.',
    'insp.cam': 'Kamera', 'insp.anim': 'Animation (0 bis 17)',
    'insp.kind': 'Art', 'insp.kind.answer': 'Antwort',
    'insp.kind.question': 'Frage',
    'insp.line': 'Zeile {n}', 'insp.addline': 'Zeile',
    'insp.color': 'Farbe', 'insp.multi': '{n} Nodes gewaehlt',
    'insp.entry.first': 'Hier beginnt das Gespraech beim ersten Ansprechen.',
    'insp.entry.known': 'Hier beginnt das Gespraech, wenn das Angebot '
                        'abgelehnt wurde.',
    'insp.entry.running': 'Hier beginnt das Gespraech, solange die Aufgabe '
                          'nicht erledigt ist.',
    'insp.entry.taken': 'Hier beginnt das Gespraech nach der Annahme.',
    'insp.entry.solved': 'Hier beginnt das Belohnungsgespraech.',
    'insp.entry.closed': 'Hier beginnt jedes Gespraech nach dem Abschluss.',
    'insp.entry.failed': 'Hier beginnt das Gespraech nach dem Scheitern.',
    'insp.entry.lowrep': 'Hier beginnt das Gespraech bei zu niedrigem Ruf.',
    'insp.entry.neutral': 'Neutrale Zeilen haben keinen eigenen Einstieg.',
    'insp.entry.cond': 'Bedingungen (Vorgaengerquest, Mindest-Level, Gilde) '
                       'docken hier an (Meilenstein 5).',
    'cam.default': 'Standard', 'cam.npc': 'auf NPC (2)',
    'cam.npc2': 'auf NPC, Variante (1)', 'cam.hero': 'auf Held (7)',
    'cam.hero2': 'auf Held, Variante (6)',
    'cue.title': 'Voice-Cue suchen', 'cue.filter': 'Text:',
    'cue.lector.speaker': 'nur Stimme des Sprechers (Lector {n})',
    'cue.count': '{n} Treffer (max. 500)',
    'ctx.newnode': 'Neuer Node',
    'quest.loadretail': 'Dialog aus dem Spiel laden...',
    'quest.switch': 'Quest wechseln',
    'retail.title': 'Dialog aus dem Spiel laden',
    'retail.filter': 'Suche:', 'retail.lines': 'Zeilen',
    'retail.kind.sp': 'Einzelspieler', 'retail.kind.mp': 'Mehrspieler',
    'retail.kind.all': 'Alle',
    'retail.exists': 'Q_{id} ist schon im Projekt. Durch den Spiel-Dialog '
                     'ersetzen? (Nein oeffnet die vorhandene Quest)',
    'retail.loaded': '{tid} aus {src}: {n} Zeilen, {menus} Antwortmenues '
                     '({ms:.0f} ms)',
    'retail.notes': '{n} Hinweise beim Import (lose Startzeilen)',
    'preview.title': 'Vorschau Q_{id}',

    # milestone 5: task, actions, conditions, picker, export
    'op.FC.KILL': 'Toeten', 'op.FC.TALK': 'Sprechen mit',
    'op.FC.BRING_OBJECT': 'Gegenstand bringen', 'op.FC.BRING_GOLD': 'Gold bringen',
    'op.FC.GO': 'Ort erreichen', 'op.FC.CLEAR_AREA': 'Gebiet saeubern',
    'op.FC.FIND_LOCATION': 'Ort finden', 'op.FC.FIND_OBJECT': 'Gegenstand finden',
    'op.FC.DELIVER_OBJECT': 'Gegenstand abliefern',
    'op.FC.FIND_KILL': 'Suchen und toeten', 'op.FC.FIND_TALK': 'Suchen und sprechen',
    'op.FC.GO_AWAY': 'Gebiet verlassen', 'op.FC.FIND_PLACE': 'Platz finden',
    'op.REWARD.GLD': 'Belohnung Gold', 'op.REWARD.EXP': 'Belohnung Erfahrung',
    'op.REWARD.ITM': 'Belohnung Gegenstand', 'op.REWARD.REP': 'Belohnung Ruf',
    'op.REWARD.SKL': 'Belohnung Skillpunkte',
    'op.ACTION.NPC_CREATE': 'NPC erzeugen', 'op.ACTION.NPC_REMOVE': 'NPC entfernen',
    'op.ACTION.NPC_KILL': 'NPC toeten', 'op.ACTION.NPC_TELEPORT': 'NPC teleportieren',
    'op.ACTION.NPC_GO': 'NPC gehen lassen',
    'op.ACTION.HERO_TELEPORT_DELAYED': 'Held teleportieren',
    'op.ACTION.ENEMY_CREATE': 'Gegner erzeugen',
    'op.ACTION.OBJECT_CREATE': 'Objekt erzeugen', 'op.ACTION.OPEN': 'Tuer oeffnen',
    'op.ACTION.CLOSE': 'Tuer schliessen',
    'op.ACTION.SHOW_LOCATION': 'Ort auf Karte zeigen',
    'op.ACTION.CREATE_EFFECT': 'Effekt erzeugen',
    'op.ACTION.NPC_CHANGE_PARTY': 'NPC Partei aendern',
    'op.ACTION.CLEAR_AREA': 'Gebiet leeren', 'op.ACTION.KILL_AREA': 'Gebiet toeten',
    'op.ACTION.PLAY_CUTSCENE': 'Cutscene abspielen',
    'op.ACTION.SET_WORLD_STATE': 'Weltzustand setzen',
    'op.more': 'Weitere', 'op.none': '(keine Aufgabe)',
    'field.npc': 'NPC', 'field.object': 'Gegenstand', 'field.count': 'Anzahl',
    'field.gold': 'Gold', 'field.marker': 'Marker-Nummer', 'field.tile': 'Kachel',
    'field.range': 'Reichweite (m)', 'field.party': 'Partei (Gegner 18 bis 23)',
    'field.location': 'Ort', 'field.amount': 'Menge (Zahl oder SMALL/MEDIUM/HIGH)',
    'field.guild': 'Gilde / Partei', 'field.angle': 'Blickrichtung (0 bis 255)',
    'field.delay': 'Verzoegerung', 'field.enemy': 'Gegnertyp',
    'field.level': 'Stufe', 'field.effect': 'Effekt', 'field.x': 'X',
    'field.y': 'Y', 'field.number': 'Nummer',
    'field.pick': 'Kachel waehlen...',
    'field.reads': 'liest Marker: {kind}',
    'node.task': 'Aufgabe', 'node.action': 'Aktion', 'node.condition': 'Bedingung',
    'cond.after': 'Nach Quest', 'cond.level': 'Mindest-Level',
    'cond.guild': 'Gilde / Mindest-Ruf',
    'cond.after.sum': 'nach Q_{q} ({ev})', 'cond.level.sum': 'ab Level {n}',
    'cond.guild.sum': 'Gilde {g}, Ruf {r}',
    'ev.TAKE': 'angenommen', 'ev.SOLVE': 'erfuellt', 'ev.CLOSE': 'abgeschlossen',
    'ev.ENABLE': 'freigeschaltet', 'ev.HEAR': 'Angebot gehoert',
    'ev.FAIL': 'fehlgeschlagen', 'ev.FIGHT': 'Kampf',
    'when.TAKE': 'bei Annahme (TAKE)', 'when.SOLVE': 'bei Erfuellung (SOLVE)',
    'when.CLOSE': 'bei Abschluss (CLOSE)', 'when.ENABLE': 'bei Freischaltung (ENABLE)',
    'when.HEAR': 'wenn Angebot gehoert (HEAR)', 'when.FAIL': 'bei Scheitern (FAIL)',
    'when.FIGHT': 'bei Kampf (FIGHT)',
    'when.derived': 'Zeitpunkt: {when} (aus der Ebene abgeleitet)',
    'when.notallowed': 'In der Ebene "{state}" sind Aktionen nicht erlaubt. '
                       'Nur Angebot (TAKE) und Erfuellt (CLOSE/SOLVE).',
    'when.solve.check': 'schon bei Erfuellung statt bei Abschluss',
    'palette.task': 'Aufgabe (Ebene Erfuellt)',
    'palette.action': '+ Neue Aktion', 'palette.condition': '+ Neue Bedingung',
    'palette.hint': 'Aktion auf einen Dialog-Node ziehen oder doppelklicken '
                    '(haengt an den gewaehlten Node).',
    'ctx.addaction': 'Aktion hinzufuegen', 'ctx.addcond': 'Bedingung hinzufuegen',
    'ctx.settask': 'Aufgabe festlegen',
    'hint.kill': 'Quest-NPCs sind extrem widerstandsfaehig.',
    'hint.cleararea': 'Zaehlt nur Gegner, die diese Quest selbst erzeugt hat. '
                      'Braucht eine Aktion "Gegner erzeugen" derselben Partei '
                      '(18 bis 23).',
    'hint.cleararea.add': 'Aktion "Gegner erzeugen" anlegen',
    'hint.talk': 'Wird die Aufgabe beim eigenen Questgeber erledigt, '
                 'entfaellt das Angebot.',
    'hint.showloc': 'Wirkt nur bei Annahme (TAKE) und nur fuer echte Orte.',
    'hint.teleport': 'Nie in eine Innenraum-Kachel (Name mit _1) teleportieren.',
    'hint.npcgo': 'Nur innerhalb der eigenen Kachel, nie direkt nach NPC erzeugen.',
    'hint.cutscene': 'Cutscene 7 und 8 beenden das Spiel.',
    'hint.location.type10': 'Typ 10 mit Radius 0 kann nicht markiert werden.',
    'insp.qactions': 'Aktionen ohne Dialog',
    'insp.qaction.add': '+ Aktion ohne Dialog', 'insp.edit': 'Bearbeiten',
    'insp.when': 'Zeitpunkt', 'insp.conditions.hint':
    'Bedingungen haengen am Einstieg Angebot. Mehrere "Nach Quest" sind '
    'erlaubt (z. B. fuer alte Spielstaende).',
    'insp.speaker.template': 'Aussehen wie NPC (Vorlage)',
    'insp.speaker.marker': 'Q_Giver-Marker-Nummer',
    'picker.title': 'Kachel waehlen', 'picker.search': 'Suche:',
    'picker.all': 'Alle Kacheln', 'picker.interior': 'Innenraeume',
    'picker.own': 'Eigene Marker-Nummer (aus dem Two Worlds Editor):',
    'picker.lnd': 'Marker aus .lnd-Dateien kann das Tool nicht lesen. Die Liste '
                  'zeigt Nummern, die Retail-Quests in dieser Kachel benutzen.',
    'picker.counts': '{t}: {n} NPCs, {l} Orte, {m} Marker',
    'picker.used': 'benutzt von {q}',
    'picker.notile': 'Objekte gelten fuer alle Kacheln.',
    'val.id.range': 'Quest-ID Q_{id} liegt nicht im Bereich 381 bis 399.',
    'val.id.taken': 'Q_{id} ist schon vergeben ({src}).',
    'val.id.replace': 'Q_{id} existiert in {src} und wird ersetzt.',
    'val.id.twice': 'Q_{id} kommt im Projekt zweimal vor.',
    'val.title': 'Titel fehlt.',
    'val.journal.take': 'Tagebuchtext "Annahme" fehlt.',
    'val.journal.solve': 'Tagebuchtext "Erfuellt" fehlt.',
    'val.journal.close': 'Tagebuchtext "Abgeschlossen" fehlt.',
    'val.giver': 'Questgeber fehlt.', 'val.task': 'Keine Aufgabe gesetzt.',
    'val.task.field': 'Aufgabe: {err}',
    'val.after': 'Keine Bedingung "Nach Quest": die Quest wuerde nie '
                 'angeboten.',
    'val.after.quest': 'Bedingung: Quest Q_{id} gibt es nicht.',
    'val.offer.empty': 'Die Ebene Angebot hat keine Zeilen.',
    'val.offer.npc': 'Das Angebot muss mit einer NPC-Zeile beginnen.',
    'val.action.level': 'Aktion in einer Ebene, in der Aktionen nicht erlaubt '
                        'sind.',
    'val.action.when': 'Zeitpunkt {when} ist fuer diese Aktion nicht erlaubt.',
    'val.action.field': 'Aktion: {err}',
    'val.cr': 'Text enthaelt einen Zeilenumbruch (CR).',
    'val.text.empty': 'Leere Textzeile.',
    'val.speaker': 'NPC-Node ohne gueltigen Sprecher.',
    'warn.teleport.interior': 'NPC_TELEPORT in eine Innenraum-Kachel laesst das '
                              'Spiel abstuerzen.',
    'warn.showloc': 'Ort zeigen wirkt nur bei Annahme (TAKE).',
    'warn.cutscene': 'Cutscene 7 oder 8 beendet das Spiel.',
    'warn.cleararea': 'Gebiet saeubern ohne "Gegner erzeugen" derselben Partei: '
                      'die Quest erfuellt sich sofort.',
    'warn.cleararea.party': 'Partei ausserhalb 18 bis 23: Gegner sind nicht '
                            'feindlich.',
    'warn.talk.giver': 'Sprechen mit dem eigenen Questgeber ueberspringt das '
                       'Angebot.',
    'warn.group': 'Tagebuchgruppe {g} hat keinen Namen im Spiel: im Tagebuch '
                  'steht dann der rohe Schluessel.',
    'export.title': 'Export', 'export.nothing': 'Das Projekt hat keine Quests.',
    'export.nogame': 'Kein Spielpfad gesetzt.',
    'export.running': 'Two Worlds laeuft. Bitte das Spiel schliessen: es haelt '
                      'die Mod-Archive offen.',
    'export.errors': 'Export nicht moeglich, {n} Fehler:',
    'export.warnings': '{n} Warnungen. Trotzdem exportieren?',
    'export.conflict': 'Diese aktiven Mods liefern ebenfalls die komplette '
                       'Quest- oder Textdatei: {mods}. Das spaeter geladene '
                       'Archiv gewinnt still. Empfehlung: in eines davon '
                       'exportieren (Quest-Panel, Zielarchiv). Trotzdem nach '
                       '{target} exportieren?',
    'export.target': 'Zielarchiv: Mods\\{name}. Exportieren?',
    'export.log.base': 'Basis {kind}: {src}',
    'export.log.file': 'Datei {inner} ({n} B)',
    'export.log.unpack': '{name} entpacken ({n} Dateien)...',
    'export.log.pack': '{name} packen (wdio)...',
    'export.log.verified': 'Geprueft: {n} Dateien, Inhalt und Metadaten ok',
    'export.log.backup': 'Sicherung angelegt: {name}',
    'export.log.registry': 'Registry: {name} = 1 (vorher {old})',
    'export.done': 'Export fertig: {path}',
    'export.done.files': 'Dateien geschrieben nach {path}',
    'export.failed': 'Export fehlgeschlagen: {err}',
    'export.next': 'Naechste Schritte: Neues Spiel starten (Questzustand steckt '
                   'in Spielstaenden), die Vorgaengerquest annehmen und den '
                   'Questgeber danach erneut ansprechen. Erscheint nichts, zuerst '
                   'mit der [MOD]-Markermethode pruefen, ob das Archiv geladen '
                   'wird (README 9).',
    'export.gotonode': 'Doppelklick springt zum Node.',
}

_EN = {
    'app.title': 'TW1 Quest Creator',
    'ok': 'OK', 'cancel': 'Cancel', 'yes': 'Yes', 'no': 'No',
    'close': 'Close', 'error': 'Error',
    'ctrl': 'Ctrl',
    'menu.file': 'File', 'menu.edit': 'Edit', 'menu.view': 'View',
    'menu.quest': 'Quest', 'menu.help': 'Help',
    'file.new': 'New project', 'file.open': 'Open project...',
    'file.recent': 'Open recent', 'file.recent.none': '(empty)',
    'file.save': 'Save', 'file.saveas': 'Save as...',
    'file.gamepath': 'Choose game path...',
    'file.export': 'Export as mod...',
    'file.exportfiles': 'Export files only...',
    'file.quit': 'Quit',
    'edit.undo': 'Undo', 'edit.redo': 'Redo',
    'edit.cut': 'Cut', 'edit.copy': 'Copy',
    'edit.paste': 'Paste', 'edit.duplicate': 'Duplicate',
    'edit.delete': 'Delete', 'edit.selectall': 'Select all',
    'edit.autolayout': 'Auto layout',
    'view.zoomin': 'Zoom in', 'view.zoomout': 'Zoom out',
    'view.zoom100': 'Zoom 100 %', 'view.fit': 'Fit to content',
    'view.timeline': 'Timeline', 'view.palette': 'Speaker box',
    'view.inspector': 'Properties', 'view.coach': 'Coach',
    'view.grid': 'Show grid', 'view.edges': 'Edge style',
    'view.edges.curve': 'Curve', 'view.edges.line': 'Straight',
    'view.lang': 'Language', 'view.lang.de': 'Deutsch',
    'view.lang.en': 'English',
    'view.lang.restart': 'The language is used after the next start.',
    'quest.new': 'New quest', 'quest.duplicate': 'Duplicate quest',
    'quest.delete': 'Delete quest', 'quest.validate': 'Validate',
    'quest.preview': 'Preview as text', 'quest.template':
    'Save as template',
    'help.tour': 'Start tour',
    'help.tutorial': 'Tutorial: build a test quest',
    'help.docs': 'Documentation', 'help.about': 'About',
    'panel.timeline': 'TIMELINE', 'panel.speakers': 'SPEAKERS',
    'panel.actions': 'TASKS / ACTIONS / CONDITIONS',
    'panel.inspector': 'PROPERTIES', 'panel.coach': 'COACH',
    'panel.placeholder': 'Coming in milestone {m}',
    'graph.empty': 'No quest open.\n'
                   'Quest > New quest creates one (milestone 3).',
    'status.noproject': 'No project', 'status.nogame': 'No game path',
    'status.noquest': 'No quest', 'status.nodes': '{n} nodes',
    'status.validation.none': 'Validation: -',
    'status.index.loading': 'Loading index...',
    'status.index.cache': 'Index from cache ({s:.2f} s)',
    'status.index.built': 'Index rebuilt ({s:.1f} s)',
    'status.start': 'Start {s:.2f} s',
    'project.untitled': 'Untitled',
    'project.filter': 'QuestForge project',
    'project.unsaved.title': 'Unsaved changes',
    'project.unsaved.q': 'The project "{name}" has unsaved changes. Save?',
    'project.open.error': 'Could not open project:\n{err}',
    'project.save.error': 'Could not save project:\n{err}',
    'project.missing': 'The file no longer exists:\n{path}',
    'game.ask.title': 'Choose game folder',
    'game.ask.msg': 'Please choose your Two Worlds folder '
                    '(the one containing WDFiles).',
    'game.invalid': 'That folder has no WDFiles\\Update16.wd.\nTry again?',
    'game.set': 'Game path set:\n{path}',
    'index.title': 'Reading game data',
    'index.intro': 'This only happens on the first start or when game '
                   'files changed.',
    'index.step.base': 'Extracting base data from the game...',
    'index.step.qtx': 'Reading quests and NPCs...',
    'index.step.lan': 'Reading texts and dialog trees...',
    'index.step.mods': 'Reading mods: {name}',
    'index.step.save': 'Saving index...',
    'index.error': 'Could not read game data:\n{err}',
    'about.title': 'About {app}',
    'about.version': 'Version {v}',
    'about.links': 'Links', 'about.guide': 'Guide page',
    'about.github': 'GitHub repository', 'about.community': 'Community',
    'about.credits': 'wdio.py by buglord (CC0). Everything else: '
                     'MedievalDev.',
    'about.nodata': 'This program contains no game data. Two Worlds is a '
                    'title by Reality Pump / TopWare Interactive.',
    'stats': '{q} quests, {n} NPCs, {c} cues, {f} free ids',
    'tab.0.FT.AS': 'Offer', 'tab.0.QNS.AE': 'Running',
    'tab.0.QS.AE': 'Solved', 'tab.0.QC': 'Closed',
    'tab.0.FT': 'Greeting', 'tab.0.QNT': 'Known', 'tab.0x0': 'Neutral',
    'node.entry': 'Entry', 'node.end': 'End',
    'node.dialog': 'Dialog node', 'node.comment': 'Comment',
    'ctx.add': 'Add node', 'ctx.attach': 'Attach to node',
    'ctx.detach': 'Detach comment',
    'ctx.attach_comment': 'Attach comment',
    'ctx.disconnect': 'Disconnect edge(s)', 'ctx.cut_edge': 'Disconnect',
    'ctx.color': 'Colour',
    'status.frame': 'Drag {ms:.1f} ms',
    'quest.debug300': 'Debug: 300 test nodes',
    'quest.noquest': 'No quest open.',
    'quest.noid': 'No free quest id left (381 to 399 are taken).',
    'state.first': 'Offer', 'state.known': 'Known',
    'state.running': 'Running', 'state.taken': 'Taken',
    'state.solved': 'Solved', 'state.closed': 'Closed',
    'state.failed': 'Failed', 'state.lowrep': 'Low reputation',
    'state.neutral': 'Always',
    'state.short.first': 'Offer', 'state.short.known': 'Known',
    'state.short.running': 'Running', 'state.short.taken': 'Taken',
    'state.short.solved': 'Solved', 'state.short.closed': 'Closed',
    'state.short.failed': 'Failed', 'state.short.lowrep': 'Rep',
    'state.short.neutral': 'Always',
    'state.help.first': 'Plays on the first talk. If the conversation ends '
                        'through a line marked "Takes the quest", the quest '
                        'is taken.',
    'state.help.known': 'Plays when the player heard the offer and did not '
                        'take it.',
    'state.help.running': 'Plays while the task is not done (also before '
                          'the quest is taken).',
    'state.help.taken': 'Plays after taking, solved or not (retail level, '
                        'rarely needed).',
    'state.help.solved': 'Plays when the task is done. "Closes the quest" '
                         'hands out the reward.',
    'state.help.closed': 'Plays after the quest is closed.',
    'state.help.failed': 'Plays when the quest failed.',
    'state.help.lowrep': 'Plays instead of the offer when reputation is '
                         'below the quest minimum.',
    'state.help.neutral': 'Plays in every state (question menus, small talk).',
    'tab.more': '+', 'tab.all': 'All',
    'speaker.player': 'Player', 'speaker.new': '+ New speaker',
    'speaker.dialog.title': 'New speaker',
    'speaker.existing': 'Existing NPC', 'speaker.newnpc': 'New NPC',
    'speaker.search': 'Type a name or NPC id:',
    'speaker.own': 'Own', 'speaker.id': 'NPC id (Two Worlds Editor)',
    'speaker.name': 'Display name', 'speaker.lector': 'Voice (lector)',
    'speaker.lector.none': 'silent / own lector',
    'speaker.lector.of': 'Voice of {names} (lector {n})',
    'speaker.tile': 'Home tile (e.g. F05)',
    'speaker.hint': 'The NPC needs a Q_Giver marker with the same number in '
                    'this tile in the Two Worlds Editor, otherwise the game '
                    'freezes when the tile loads.',
    'speaker.id.invalid': 'Please enter a number (e.g. 700).',
    'speaker.id.taken': 'NPC_{id} already exists in the game ({name}). Use '
                        'the first card for an existing NPC.',
    'speaker.rename': 'Rename', 'speaker.remove': 'Remove',
    'speaker.remove.used': 'This speaker is still used by nodes.',
    'speaker.mark': 'Select all lines of this speaker',
    'node.player': 'Player', 'node.npc': 'NPC',
    'insp.quest': 'QUEST', 'insp.id': 'Quest id',
    'insp.id.hint': 'Free ids are 381 to 399 (the game allows only 19 '
                    'custom ids).',
    'insp.title': 'Title', 'insp.group': 'Journal group',
    'insp.journal.take': 'Journal: taken',
    'insp.journal.solve': 'Journal: solved',
    'insp.journal.close': 'Journal: closed',
    'insp.giver': 'Quest giver', 'insp.giver_type': 'Giver type',
    'insp.map_sign': 'Map marker',
    'insp.map_sign.hint': 'BACK_TO_GIVER_MAP_SIGN moves the marker back to '
                          'the giver once the task is done.',
    'insp.offered': 'Start', 'insp.offered.check':
    'Quest is offered in a conversation. Off = starts automatically.',
    'insp.archive': 'Target archive (Mods\\*.wd)',
    'insp.speaker': 'Speaker', 'insp.state': 'Level', 'insp.text': 'Text',
    'insp.take': 'Takes the quest', 'insp.close': 'Closes the quest',
    'insp.fight': 'Fight starts', 'insp.advanced': 'Advanced',
    'insp.cue': 'Voice cue', 'insp.cue.search': 'Search...',
    'insp.cue.text': 'Recording:',
    'insp.cue.mismatch': 'The subtitle differs from the recording. The text '
                         'must match the recording.',
    'insp.cam': 'Camera', 'insp.anim': 'Animation (0 to 17)',
    'insp.kind': 'Kind', 'insp.kind.answer': 'Answer',
    'insp.kind.question': 'Question',
    'insp.line': 'Line {n}', 'insp.addline': 'line',
    'insp.color': 'Colour', 'insp.multi': '{n} nodes selected',
    'insp.entry.first': 'The conversation starts here on the first talk.',
    'insp.entry.known': 'The conversation starts here after the offer was '
                        'declined.',
    'insp.entry.running': 'The conversation starts here while the task is '
                          'not done.',
    'insp.entry.taken': 'The conversation starts here after taking.',
    'insp.entry.solved': 'The reward conversation starts here.',
    'insp.entry.closed': 'Every conversation after closing starts here.',
    'insp.entry.failed': 'The conversation starts here after failing.',
    'insp.entry.lowrep': 'The conversation starts here with low reputation.',
    'insp.entry.neutral': 'Neutral lines have no entry of their own.',
    'insp.entry.cond': 'Conditions (previous quest, minimum level, guild) '
                       'dock here (milestone 5).',
    'cam.default': 'Default', 'cam.npc': 'on NPC (2)',
    'cam.npc2': 'on NPC, variant (1)', 'cam.hero': 'on hero (7)',
    'cam.hero2': 'on hero, variant (6)',
    'cue.title': 'Search voice cue', 'cue.filter': 'Text:',
    'cue.lector.speaker': 'only the speaker\'s voice (lector {n})',
    'cue.count': '{n} matches (max. 500)',
    'ctx.newnode': 'New node',
    'quest.loadretail': 'Load dialog from the game...',
    'quest.switch': 'Switch quest',
    'retail.title': 'Load dialog from the game',
    'retail.filter': 'Search:', 'retail.lines': 'lines',
    'retail.kind.sp': 'Single player', 'retail.kind.mp': 'Multiplayer',
    'retail.kind.all': 'All',
    'retail.exists': 'Q_{id} is already in the project. Replace it with the '
                     'game dialog? (No opens the existing quest)',
    'retail.loaded': '{tid} from {src}: {n} lines, {menus} reply menus '
                     '({ms:.0f} ms)',
    'retail.notes': '{n} import notes (loose start lines)',
    'preview.title': 'Preview Q_{id}',

    'op.FC.KILL': 'Kill', 'op.FC.TALK': 'Talk to',
    'op.FC.BRING_OBJECT': 'Bring item', 'op.FC.BRING_GOLD': 'Bring gold',
    'op.FC.GO': 'Reach place', 'op.FC.CLEAR_AREA': 'Clear area',
    'op.FC.FIND_LOCATION': 'Find location', 'op.FC.FIND_OBJECT': 'Find item',
    'op.FC.DELIVER_OBJECT': 'Deliver item',
    'op.FC.FIND_KILL': 'Find and kill', 'op.FC.FIND_TALK': 'Find and talk',
    'op.FC.GO_AWAY': 'Leave area', 'op.FC.FIND_PLACE': 'Find place',
    'op.REWARD.GLD': 'Reward gold', 'op.REWARD.EXP': 'Reward experience',
    'op.REWARD.ITM': 'Reward item', 'op.REWARD.REP': 'Reward reputation',
    'op.REWARD.SKL': 'Reward skill points',
    'op.ACTION.NPC_CREATE': 'Create NPC', 'op.ACTION.NPC_REMOVE': 'Remove NPC',
    'op.ACTION.NPC_KILL': 'Kill NPC', 'op.ACTION.NPC_TELEPORT': 'Teleport NPC',
    'op.ACTION.NPC_GO': 'Let NPC walk',
    'op.ACTION.HERO_TELEPORT_DELAYED': 'Teleport hero',
    'op.ACTION.ENEMY_CREATE': 'Create enemies',
    'op.ACTION.OBJECT_CREATE': 'Create object', 'op.ACTION.OPEN': 'Open door',
    'op.ACTION.CLOSE': 'Close door',
    'op.ACTION.SHOW_LOCATION': 'Show location on map',
    'op.ACTION.CREATE_EFFECT': 'Create effect',
    'op.ACTION.NPC_CHANGE_PARTY': 'Change NPC party',
    'op.ACTION.CLEAR_AREA': 'Clear area', 'op.ACTION.KILL_AREA': 'Kill area',
    'op.ACTION.PLAY_CUTSCENE': 'Play cutscene',
    'op.ACTION.SET_WORLD_STATE': 'Set world state',
    'op.more': 'More', 'op.none': '(no task)',
    'field.npc': 'NPC', 'field.object': 'Item', 'field.count': 'Count',
    'field.gold': 'Gold', 'field.marker': 'Marker number', 'field.tile': 'Tile',
    'field.range': 'Range (m)', 'field.party': 'Party (enemies 18 to 23)',
    'field.location': 'Location', 'field.amount': 'Amount (number or SMALL/MEDIUM/HIGH)',
    'field.guild': 'Guild / party', 'field.angle': 'Facing (0 to 255)',
    'field.delay': 'Delay', 'field.enemy': 'Enemy type',
    'field.level': 'Level', 'field.effect': 'Effect', 'field.x': 'X',
    'field.y': 'Y', 'field.number': 'Number',
    'field.pick': 'Choose tile...',
    'field.reads': 'reads marker: {kind}',
    'node.task': 'Task', 'node.action': 'Action', 'node.condition': 'Condition',
    'cond.after': 'After quest', 'cond.level': 'Minimum level',
    'cond.guild': 'Guild / minimum reputation',
    'cond.after.sum': 'after Q_{q} ({ev})', 'cond.level.sum': 'from level {n}',
    'cond.guild.sum': 'guild {g}, reputation {r}',
    'ev.TAKE': 'taken', 'ev.SOLVE': 'solved', 'ev.CLOSE': 'closed',
    'ev.ENABLE': 'enabled', 'ev.HEAR': 'offer heard', 'ev.FAIL': 'failed',
    'ev.FIGHT': 'fight',
    'when.TAKE': 'on take (TAKE)', 'when.SOLVE': 'on solve (SOLVE)',
    'when.CLOSE': 'on close (CLOSE)', 'when.ENABLE': 'on enable (ENABLE)',
    'when.HEAR': 'when the offer is heard (HEAR)', 'when.FAIL': 'on failure (FAIL)',
    'when.FIGHT': 'on fight (FIGHT)',
    'when.derived': 'Time: {when} (derived from the level)',
    'when.notallowed': 'Actions are not allowed in level "{state}". Only '
                       'Offer (TAKE) and Solved (CLOSE/SOLVE).',
    'when.solve.check': 'already on solve instead of on close',
    'palette.task': 'Task (level Solved)',
    'palette.action': '+ New action', 'palette.condition': '+ New condition',
    'palette.hint': 'Drag an action onto a dialog node or double click '
                    '(docks to the selected node).',
    'ctx.addaction': 'Add action', 'ctx.addcond': 'Add condition',
    'ctx.settask': 'Set task',
    'hint.kill': 'Quest NPCs are extremely resistant.',
    'hint.cleararea': 'Counts only enemies this quest created itself. Needs an '
                      'action "Create enemies" of the same party (18 to 23).',
    'hint.cleararea.add': 'Add action "Create enemies"',
    'hint.talk': 'Solving the task at the own quest giver skips the offer.',
    'hint.showloc': 'Only works on take (TAKE) and only for real locations.',
    'hint.teleport': 'Never teleport into an interior tile (name with _1).',
    'hint.npcgo': 'Only within the NPC\'s own tile, never right after creating it.',
    'hint.cutscene': 'Cutscenes 7 and 8 end the game.',
    'hint.location.type10': 'Type 10 with radius 0 cannot be marked.',
    'insp.qactions': 'Actions without dialog',
    'insp.qaction.add': '+ Action without dialog', 'insp.edit': 'Edit',
    'insp.when': 'Time', 'insp.conditions.hint':
    'Conditions dock at the offer entry. Several "After quest" are allowed '
    '(e.g. for old saves).',
    'insp.speaker.template': 'Looks like NPC (template)',
    'insp.speaker.marker': 'Q_Giver marker number',
    'picker.title': 'Choose tile', 'picker.search': 'Search:',
    'picker.all': 'All tiles', 'picker.interior': 'Interiors',
    'picker.own': 'Own marker number (from the Two Worlds Editor):',
    'picker.lnd': 'The tool cannot read markers from .lnd files. The list shows '
                  'numbers retail quests use in this tile.',
    'picker.counts': '{t}: {n} NPCs, {l} locations, {m} markers',
    'picker.used': 'used by {q}',
    'picker.notile': 'Items are the same for all tiles.',
    'val.id.range': 'Quest id Q_{id} is not within 381 to 399.',
    'val.id.taken': 'Q_{id} is already taken ({src}).',
    'val.id.replace': 'Q_{id} exists in {src} and will be replaced.',
    'val.id.twice': 'Q_{id} appears twice in the project.',
    'val.title': 'Title missing.',
    'val.journal.take': 'Journal text "taken" missing.',
    'val.journal.solve': 'Journal text "solved" missing.',
    'val.journal.close': 'Journal text "closed" missing.',
    'val.giver': 'Quest giver missing.', 'val.task': 'No task set.',
    'val.task.field': 'Task: {err}',
    'val.after': 'No "After quest" condition: the quest would never be offered.',
    'val.after.quest': 'Condition: quest Q_{id} does not exist.',
    'val.offer.empty': 'The Offer level has no lines.',
    'val.offer.npc': 'The offer must start with an NPC line.',
    'val.action.level': 'Action in a level where actions are not allowed.',
    'val.action.when': 'Time {when} is not allowed for this action.',
    'val.action.field': 'Action: {err}',
    'val.cr': 'Text contains a carriage return (CR).',
    'val.text.empty': 'Empty text line.',
    'val.speaker': 'NPC node without a valid speaker.',
    'warn.teleport.interior': 'NPC_TELEPORT into an interior tile crashes the game.',
    'warn.showloc': 'Show location only works on take (TAKE).',
    'warn.cutscene': 'Cutscene 7 or 8 ends the game.',
    'warn.cleararea': 'Clear area without "Create enemies" of the same party: '
                      'the quest solves itself at once.',
    'warn.cleararea.party': 'Party outside 18 to 23: enemies are not hostile.',
    'warn.talk.giver': 'Talking to the own quest giver skips the offer.',
    'warn.group': 'Journal group {g} has no name in the game: the journal '
                  'shows the raw key.',
    'export.title': 'Export', 'export.nothing': 'The project has no quests.',
    'export.nogame': 'No game path set.',
    'export.running': 'Two Worlds is running. Please close the game: it keeps '
                      'the mod archives open.',
    'export.errors': 'Export not possible, {n} errors:',
    'export.warnings': '{n} warnings. Export anyway?',
    'export.conflict': 'These enabled mods also ship the full quest or text '
                       'file: {mods}. The archive loaded later wins silently. '
                       'Recommendation: export into one of them (quest panel, '
                       'target archive). Export to {target} anyway?',
    'export.target': 'Target archive: Mods\\{name}. Export?',
    'export.log.base': 'Base {kind}: {src}',
    'export.log.file': 'File {inner} ({n} B)',
    'export.log.unpack': 'Unpacking {name} ({n} files)...',
    'export.log.pack': 'Packing {name} (wdio)...',
    'export.log.verified': 'Verified: {n} files, content and metadata ok',
    'export.log.backup': 'Backup created: {name}',
    'export.log.registry': 'Registry: {name} = 1 (before {old})',
    'export.done': 'Export finished: {path}',
    'export.done.files': 'Files written to {path}',
    'export.failed': 'Export failed: {err}',
    'export.next': 'Next steps: start a new game (quest state lives in saves), '
                   'take the previous quest and talk to the giver again. If '
                   'nothing appears, first check with the [MOD] marker method '
                   'whether the archive loads (README 9).',
    'export.gotonode': 'Double click jumps to the node.',
}

_DICTS = {'de': _DE, 'en': _EN}


def detect_lang():
    """'de' when Windows runs in German, else 'en'."""
    try:
        name = (locale.getlocale()[0] or '').lower()
    except Exception:
        name = ''
    return 'de' if name.startswith(('de', 'german')) else 'en'


def set_lang(code):
    global _lang
    _lang = code if code in _DICTS else 'en'


def get_lang():
    return _lang


def t(key, **fmt):
    text = _DICTS[_lang].get(key)
    if text is None:
        text = _EN.get(key, key)
    return text.format(**fmt) if fmt else text
