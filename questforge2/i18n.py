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
