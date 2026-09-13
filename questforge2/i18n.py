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
