"""Take a multiplayer quest over into the single player game.

Measured in the SDK (2026-09-16):

- ``PQuests.ec`` (single player): ``eFirstQuest = 0``, ``eQuestsNum = 400``,
  ``eFirstQuestUnit = 0``, ``eQuestUnitsNum = 698``. ``ParseQuestNumber`` and
  ``ParseGiverNumber`` return "none" for everything outside, so a quest
  Q_700 and an NPC NPC_700 are dropped while loading. Retail NPCs of the
  single player go up to NPC_506.
- ``PQuestsMulti.ec``: ``eFirstQuest = 699``, ``eQuestsNum = 300``,
  ``eFirstQuestUnit = 699``. Q_700 to Q_819 (120 quests) and NPC_700 to
  NPC_830 belong to that script although they sit in the same quest file.
- The multiplayer blocks have ``(null)`` where the single player needs a
  map tile (``NPC`` block columns 3 and 4, ``OBJECT_CREATE``,
  ``ENEMY_CREATE``, ``CLEAR_AREA``); ``ParseMissionNumber("(null)")`` gives
  ``eNoMission`` in the single player build. Their markers are created at
  run time by the multiplayer script.

So a multiplayer quest needs: a free single player quest id, a free NPC id
below 698 for the giver, a tile for the giver and for every line with
``(null)``, and markers on those tiles.

4.3.0 (Marco 2026-09-21): all of it on one page. The markers are set on the
map (placewin), the tile of every line comes from where its marker went,
"Take over" builds the quest, writes the markers and saves the project;
only the export is left. The giver talks to the hero on his own (ACTIVE)
and the quest is there from the start of the game (level 0) unless another
quest is picked. A missing journal text gets a standard text.
"""

import re
import tkinter as tk
from tkinter import messagebox, ttk

from . import data, model, mods, retail, theme
from .i18n import get_lang, t

NL = chr(10)
MP_FIRST_QUEST = 700          # PQuestsMulti.ec eFirstQuest 699 + 1
MAX_NPC_ID = 697              # PQuests.ec eQuestUnitsNum 698
DEFAULT_PARTY = 25            # humans (SDK Enums.ech); MP records say (null)
GIVER_MARKER = mods.NPC_MARKER


def is_mp_quest(qid):
    return isinstance(qid, int) and qid >= MP_FIRST_QUEST


def free_npc_id(index, project=None):
    """Smallest unused NPC id above the highest single player NPC of the
    game (so new ids never sit inside the retail range), below 698."""
    used = set()
    if index:
        used |= {int(k) for k in index.npcs}
    if project is not None:
        for q in project.quests:
            used |= {s['id'] for s in q.speakers if isinstance(s['id'], int)}
    retail_max = max([i for i in used if i <= MAX_NPC_ID] + [0])
    for i in range(retail_max + 1, MAX_NPC_ID + 1):
        if i not in used:
            return i
    for i in range(1, MAX_NPC_ID + 1):
        if i not in used:
            return i
    return None


def marker_refs(quest):
    """Lines of the quest that address a marker: [{'where', 'label',
    'kind', 'name', 'num', 'tile', 'args'}]. ``where`` is 'task',
    ('action', i) or ('node', nid); ``args`` is the live dict."""
    out = []

    def add(where, label, spec, args):
        kind = tile_key = num_key = None
        for f in spec:
            if f[1].startswith('marker:'):
                kind, num_key = f[1].split(':', 1)[1], f[0]
            elif f[1] == 'tile':
                tile_key = f[0]
        if not kind or tile_key is None:
            return
        num = args.get(num_key)
        try:
            num = int(num)
        except (TypeError, ValueError):
            num = None
        out.append({'where': where, 'label': label, 'kind': kind,
                    'name': mods.MARKER_NAMES.get(kind, kind), 'num': num,
                    'tile': (args.get(tile_key) or '').upper(),
                    'args': args, 'num_key': num_key, 'tile_key': tile_key})
    task = quest.task()
    if task.get('fc'):
        add('task', 'FC ' + task['fc'], model.FC_SPECS[task['fc']],
            task['args'])
    for i, a in enumerate(quest.actions):
        key = (a['kind'], a['verb'])
        add(('action', i), f"{a['kind']} {a['verb']} {a.get('when') or ''}",
            model.ACTION_SPECS[key], a['args'])
    for nid, n in quest.graph_actions():
        key = (n['kind'], n['verb'])
        add(('node', nid), f"{n['kind']} {n['verb']}",
            model.ACTION_SPECS[key], n['args'])
    return out


def _max_num(retail_tiles, tile, name):
    ids = mods.marker_ids(retail_tiles.get(tile), name)
    return max(ids) if ids else 0


def plan(quest, npc_id, tile, retail_tiles, tiles=None, numbers=None):
    """What has to happen on the maps. Returns (items, mapping).

    items: [{'name', 'num', 'tile', 'why', 'exists'}] in checklist order,
    the giver first. Marker numbers: the multiplayer numbers are kept
    where the retail tile does not have that number yet; otherwise the next
    free number on that tile, the same for every line that shared the old
    number. ``tiles`` {ref index: tile} and ``numbers`` {ref index: num}
    override the proposal per line.
    """
    tiles = tiles or {}
    numbers = numbers or {}
    items = [{'name': GIVER_MARKER, 'num': npc_id, 'tile': tile,
              'why': t('mp.why.giver', id=npc_id),
              'exists': npc_id in mods.marker_ids(retail_tiles.get(tile),
                                                  GIVER_MARKER)}]
    mapping = {}
    next_free = {}
    for i, ref in enumerate(marker_refs(quest)):
        tl = (tiles.get(i) or ref['tile'] or tile).upper()
        # a line without a number (MP "(null)") needs a marker of its own
        key = (ref['name'], tl, ref['num'] if ref['num'] is not None
               else ('line', i))
        if i in numbers:
            num = numbers[i]
        elif key in mapping:
            num = mapping[key]
        else:
            have = mods.marker_ids(retail_tiles.get(tl), ref['name'])
            if ref['num'] is not None and ref['num'] not in have:
                num = ref['num']
            else:
                start = next_free.get((ref['name'], tl),
                                      _max_num(retail_tiles, tl, ref['name']))
                num = start + 1
            next_free[(ref['name'], tl)] = max(
                num, next_free.get((ref['name'], tl), 0))
        mapping[key] = num
        mapping[('line', i)] = num
        if not any(x['name'] == ref['name'] and x['num'] == num
                   and x['tile'] == tl for x in items):
            items.append({'name': ref['name'], 'num': num, 'tile': tl,
                          'why': ref['label'],
                          'exists': num in mods.marker_ids(
                              retail_tiles.get(tl), ref['name'])})
    return items, mapping


def recover_null_lines(quest):
    """Multiplayer lines with "(null)" in number fields (e.g. FC CLEAR_AREA
    (null) (null) 60 21, ENEMY_CREATE ... (null) (null) (null) (null) 21)
    the importer could not read and would drop. The MP script places those
    markers at run time; for the single player they become lines with the
    spec default for counts and levels and an open marker number that
    plan() then gives out. Returns the number of lines taken back."""
    info = quest.extra.get('qtx') or {}
    raw = info.get('raw') or []
    keep, n = [], 0
    task = quest.task()
    for kw, toks in raw:
        spec = body = when = None
        if kw == 'FC' and toks and toks[0] in model.FC_SPECS and \
                not task.get('fc'):
            spec, body = model.FC_SPECS[toks[0]], toks[1:]
        elif kw == 'ACTION' and len(toks) >= 2 and \
                ('ACTION', toks[0]) in model.ACTION_SPECS and \
                toks[1] in model.ACTION_WHEN:
            spec, body, when = model.ACTION_SPECS[('ACTION', toks[0])], \
                toks[2:], toks[1]
        if spec is None or '(null)' not in body or len(spec) != len(body):
            keep.append([kw, toks])
            continue
        fixed = []
        for f, tok in zip(spec, body):
            if tok == '(null)' and f[1] in ('int', 'party'):
                tok = str(f[2] if len(f) > 2 else 1)
            fixed.append(tok)
        args = retail.args_from_tokens(spec, fixed)
        if args is None:
            keep.append([kw, toks])
            continue
        for f in spec:
            if f[1].startswith('marker:') and not isinstance(args.get(f[0]),
                                                             int):
                args[f[0]] = None          # plan() gives out a number
        if kw == 'FC':
            model.set_task(quest.graph, toks[0])['args'] = args
            task = quest.task()
        else:
            quest.actions.append({'kind': 'ACTION', 'verb': toks[0],
                                  'args': args, 'when': when})
        n += 1
    info['raw'] = keep
    return n


def current_todo(quest):
    """The marker checklist without entries the quest no longer uses
    (giver renumbered or moved, a line given another marker or tile). The
    ticks of the remaining entries stay."""
    todo = quest.extra.get('markers_todo') or []
    if not todo:
        return []
    used = set()
    for s in quest.speakers:
        if s.get('new') and isinstance(s.get('id'), int):
            used.add((GIVER_MARKER, str(s.get('tile') or '').upper(),
                      s.get('marker') or s['id']))
    for ref in marker_refs(quest):
        used.add((ref['name'], ref['tile'], ref['num']))
    return [x for x in todo if isinstance(x, dict) and
            (x.get('name'), str(x.get('tile')).upper(), x.get('num')) in used]


def apply(quest, new_id, npc_id, npc_name, tile, retail_tiles, tiles=None,
          numbers=None, group=None, party=DEFAULT_PARTY):
    """The single player quest: own quest with the new id, the giver as a
    new speaker (NPC block gets tile, marker = NPC id, party), every marker
    line with its tile and number, the checklist in ``extra``."""
    old_giver = quest.giver
    new = retail.make_own(quest, new_id)
    items, mapping = plan(new, npc_id, tile, retail_tiles, tiles, numbers)
    for i, ref in enumerate(marker_refs(new)):
        tl = (tiles.get(i) if tiles else None) or ref['tile'] or tile
        ref['args'][ref['tile_key']] = tl.upper()
        ref['args'][ref['num_key']] = mapping[('line', i)]
    # the giver: new id everywhere, one new speaker with the NPC block data
    old_spk = next((s for s in new.speakers if s['id'] == old_giver), None)
    new.speakers = [s for s in new.speakers if s['id'] != old_giver]
    new.speakers.insert(0, {
        'id': npc_id, 'name': npc_name, 'lector': (old_spk or {}).get('lector'),
        'tile': tile.upper(), 'marker': npc_id, 'angle': 0, 'new': True,
        'template': old_giver, 'party': party})
    # MP dialog lines carry no lector, the import made a placeholder speaker
    # "Lector -1" for them: they are the giver's lines
    placeholders = {s['id'] for s in new.speakers
                    if isinstance(s['id'], str) and s['id'].startswith('L')}
    new.speakers = [s for s in new.speakers if s['id'] not in placeholders]
    for n in new.graph['nodes'].values():
        if n.get('speaker') == old_giver or n.get('speaker') in placeholders:
            n['speaker'] = npc_id
    new.giver = npc_id
    if group is not None:
        new.group = group
    for n in new.graph['nodes'].values():
        if n.get('type') == 'condition' and n.get('cond') == 'level' \
                and not n.get('level'):
            n['level'] = 1
            new.enable_level = 1
    new.extra['mp_source'] = quest.id
    new.extra['markers_todo'] = [
        {'name': x['name'], 'num': x['num'], 'tile': x['tile'],
         'why': x['why'], 'done': bool(x['exists'])} for x in items]
    return new


def checklist_lines(items, lang=None):
    lang = lang or get_lang()
    return [t('mp.item', name=mods.editor_name(x['name']), num=x['num'],
                   tile=x['tile'])
            + ('   ' + t('mp.exists') if x.get('exists') or x.get('done')
               else '') for x in items]


# ---------------------------------------------------------------------------
# one window (4.3.0, Marco 2026-09-21): everything on one page, the markers
# set on the map, "Take over" - and the quest is done, only the export is
# left. The pieces below are pure, the window and the tests use them alike.

START, AFTER = 'start', 'after'
GIVER_KEY = ('giver',)
EVENTS = ('TAKE', 'SOLVE', 'CLOSE')


def marker_targets(quest, npc_id, retail_tiles):
    """What has to go on the map, one entry per marker: [{'key', 'name',
    'label', 'num' (fixed number or None), 'refs' (indexes into
    marker_refs), 'exists' (the game has that marker already), 'tile',
    'game_num', 'placed'}]. The giver comes first; lines that share a
    marker (two OBJECT_CREATE on marker 1) share one entry."""
    out = [{'key': GIVER_KEY, 'name': GIVER_MARKER,
            'label': t('mp.why.giver', id=npc_id), 'num': npc_id,
            'refs': [], 'exists': False, 'tile': None, 'game_num': None,
            'placed': None}]
    groups = {}
    for i, ref in enumerate(marker_refs(quest)):
        tile, num = ref['tile'], ref['num']
        exists = bool(tile in retail_tiles and num is not None and num in
                      mods.marker_ids(retail_tiles.get(tile), ref['name']))
        key = (('game', ref['name'], tile, num) if exists else
               (ref['name'], num if num is not None else ('line', i)))
        tg = groups.get(key)
        if tg is None:
            tg = {'key': key, 'name': ref['name'], 'label': ref['label'],
                  'num': None, 'refs': [], 'exists': exists,
                  'tile': tile if exists else None,
                  'game_num': num if exists else None, 'placed': None}
            groups[key] = tg
            out.append(tg)
        tg['refs'].append(i)
    return out


def target_ready(tg):
    return bool(tg.get('exists') or tg.get('placed'))


def placement_settings(targets):
    """(giver tile, {ref index: tile}, {ref index: number}) from the
    targets: the placed ones and those the game has already."""
    giver_tile = None
    tiles, numbers = {}, {}
    for tg in targets:
        p = tg.get('placed')
        if tg['key'] == GIVER_KEY:
            if p:
                giver_tile = p['tile']
            continue
        if tg.get('exists'):
            tile, num = tg['tile'], tg['game_num']
        elif p:
            tile, num = p['tile'], int(p['num'])
        else:
            continue
        for i in tg['refs']:
            tiles[i], numbers[i] = tile, num
    return giver_tile, tiles, numbers


def set_availability(quest, mode, pred=4, event='TAKE'):
    """From the start of the game (level 0, no "after" condition) or after
    another quest (level 1, one "after" condition). SDK: StartQuests
    promotes every loaded quest once when the game starts
    (eQuestInitialLevel -1), so level 0 needs no unlock and level 1 needs
    exactly one AOQ PROMOTE (measured 2026-09-21, Kunibert)."""
    g = quest.graph
    model.remove_nodes(g, [k for k, n in g['nodes'].items()
                           if n.get('type') == 'condition'
                           and n.get('cond') == 'after'])
    level = 0 if mode == START else 1
    lv = [n for n in g['nodes'].values()
          if n.get('type') == 'condition' and n.get('cond') == 'level']
    for n in lv:
        n['level'] = level
    if not lv:
        model.add_node(g, model.make_condition('level', level=level))
    if mode != START:
        model.add_node(g, model.make_condition('after', quest=int(pred),
                                               event=event))
    quest.enable_level = level
    model.restack(g)


def default_journal(journal):
    """Journal texts the multiplayer quest lacks get a standard text (30 of
    the 120 have no "solved" text and the export refuses an empty one).
    Changes ``journal`` in place, returns the keys filled in."""
    filled = []
    for key in ('take', 'solve', 'close'):
        if not (journal.get(key) or '').strip():
            journal[key] = t('mp.journal.default.' + key)
            filled.append(key)
    return filled


def take_over(src, new_id, npc_id, npc_name, targets, retail_tiles,
              group=None, active=True, availability=START, pred=4,
              event='TAKE', title=None, journal=None):
    """The single player quest from the multiplayer quest and the targets
    of the map."""
    giver_tile, tiles, numbers = placement_settings(targets)
    new = apply(src, new_id, npc_id, npc_name, giver_tile or 'E1',
                retail_tiles, tiles, numbers, group)
    new.giver_type = 'ACTIVE' if active else 'PASSIVE'
    if title is not None:
        new.title = title
    if journal:
        new.journal.update(journal)
    set_availability(new, availability, pred, event)
    return new


def commit_targets(targets):
    """The placed targets as placewin.commit wants them after take_over:
    the lines point at the placed markers already."""
    out = []
    for tg in targets:
        p = tg.get('placed')
        if p and not tg.get('exists'):
            out.append({'key': (tg['name'], p['tile'], int(p['num'])),
                        'name': tg['name'], 'placed': p, 'orig': None})
    return out


# ---------------------------------------------------------------------------
# window

class MpMergeWindow:
    """One page: pick the multiplayer quest, fill in giver, availability
    and journal, set the markers on the map, take over. Red is still open,
    green is done; "Take over" waits for all green."""
    _open = None

    @classmethod
    def show(cls, app, qid=None):
        if not app.project or not app.cfg.get('game_dir'):
            return None
        win = cls._open
        if win is not None:
            try:
                win.win.lift()
                if qid is not None:
                    win.pick(qid)
                return win
            except tk.TclError:
                cls._open = None
        cls._open = cls(app, qid)
        return cls._open

    def __init__(self, app, qid=None):
        self.app = app
        self.src = None             # quest built from the game
        self.targets = []           # markers to set (marker_targets)
        self.filled = []            # journal keys with a standard text
        self.taken = None           # the new quest after "Take over"
        self.place_win = None
        game = app.cfg.get('game_dir')
        self.retail_tiles = (app.modset.retail_tiles if app.modset
                             else mods.retail_markers(game))
        self.win = tk.Toplevel(app.root)
        self.win.title(t('mp.title'))
        self.win.geometry('1120x800')
        self.win.minsize(960, 680)
        theme.dark_titlebar(self.win)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.win.bind('<Escape>', lambda e: self.close())
        style = ttk.Style(self.win)
        style.configure('Confirm.TButton', background=theme.OK,
                        foreground='#0b1a0f', font=theme.FONT_BOLD)
        style.map('Confirm.TButton',
                  background=[('active', theme.mix(theme.OK, '#ffffff', 0.2)),
                              ('disabled', theme.MUT)])
        outer = ttk.Frame(self.win, padding=14)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text=t('mp.head'), style='Brand.TLabel'
                  ).pack(anchor='w')
        ttk.Label(outer, text=t('mp.intro'), style='Muted.TLabel',
                  wraplength=1080, justify='left').pack(anchor='w',
                                                        pady=(2, 8))
        bottom = ttk.Frame(outer)
        bottom.pack(fill='x', side='bottom', pady=(10, 0))
        body = ttk.Frame(outer)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=2, uniform='c')
        body.columnconfigure(1, weight=3, uniform='c')
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 14))
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky='nsew')
        self.take_btn = None
        self._build_pick(left)
        self._build_giver(right)
        self._build_when(right)
        self._build_journal(right)
        self._build_markers(right)
        self.take_btn = ttk.Button(bottom, text='✓ ' + t('mp.take'),
                                   style='Confirm.TButton', command=self.take)
        ttk.Button(bottom, text=t('cancel'), command=self.close
                   ).pack(side='right')
        self.take_btn.pack(side='right', padx=6)
        ttk.Button(bottom, text=t('mp.tour'),
                   command=lambda: app.coach.start('mp')
                   ).pack(side='left', padx=(0, 10))
        self.status = ttk.Label(bottom, text='', style='Muted.TLabel',
                                wraplength=760, justify='left')
        self.status.pack(side='left', fill='x', expand=True)
        self._refresh()
        if qid is not None:
            self.pick(qid)

    def close(self):
        MpMergeWindow._open = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    @staticmethod
    def _section(parent, key, n):
        ttk.Label(parent, text=f'{n}  ' + t(key), style='Brand.TLabel'
                  ).pack(anchor='w', pady=(8, 2))
        f = ttk.Frame(parent)
        f.pack(fill='x')
        return f

    # -- 1: the multiplayer quest ------------------------------------------------

    def _build_pick(self, parent):
        ttk.Label(parent, text='1  ' + t('mp.sec.pick'), style='Brand.TLabel'
                  ).pack(anchor='w', pady=(8, 2))
        top = ttk.Frame(parent)
        top.pack(fill='x')
        ttk.Label(top, text=t('map.search')).pack(side='left')
        self.q = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.q)
        ent.pack(side='left', fill='x', expand=True, padx=6)
        ent.bind('<KeyRelease>', lambda e: self._fill_list())
        box = ttk.Frame(parent)
        box.pack(fill='both', expand=True, pady=(6, 0))
        cols = ('id', 'title')
        self.tree = ttk.Treeview(box, columns=cols, show='headings',
                                 selectmode='browse')
        for c, w in zip(cols, (70, 300)):
            self.tree.heading(c, text=t('mp.col.' + c))
            self.tree.column(c, width=w, anchor='w', stretch=c != 'id')
        sb = ttk.Scrollbar(box, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._load())
        self.preview = ttk.Label(parent, text='', style='Muted.TLabel',
                                 wraplength=400, justify='left')
        self.preview.pack(anchor='w', fill='x', pady=(6, 0))
        self._fill_list()

    def _fill_list(self):
        idx = self.app.index
        needle = self.q.get().strip().lower()
        keep = self._selected_qid()
        self.tree.delete(*self.tree.get_children())
        for k in sorted(idx.quests, key=int) if idx else []:
            qid = int(k)
            if not is_mp_quest(qid):
                continue
            info = idx.quests[k]
            row = (f'Q_{qid}', info.get('title') or '-')
            if needle and needle not in ' '.join(row).lower() and \
                    needle not in ' '.join(info.get('fc') or []).lower():
                continue
            self.tree.insert('', 'end', iid=str(qid), values=row)
        if keep is not None and self.tree.exists(str(keep)):
            self.tree.selection_set(str(keep))

    def pick(self, qid):
        if self.tree.exists(str(qid)):
            self.tree.selection_set(str(qid))
            self.tree.see(str(qid))
            self._load()

    def _selected_qid(self):
        tree = getattr(self, 'tree', None)
        sel = tree.selection() if tree is not None else ()
        return int(sel[0]) if sel else None

    def _load(self):
        qid = self._selected_qid()
        if qid is None or (self.src is not None and self.src.id == qid):
            return
        src = self.app.build_game_quest(qid)
        if src is None:
            return
        recover_null_lines(src)
        self.src = src
        app = self.app
        free = app.index.free_ids({x.id for x in app.project.quests}
                                  | (app.modset.quest_ids()
                                     if app.modset else set()))
        self.newid_cb.configure(values=[f'Q_{i}' for i in free])
        self.newid.set(f'Q_{free[0]}' if free else '')
        name = ''
        if src.giver is not None:
            spk = next((s for s in src.speakers if s['id'] == src.giver), None)
            name = (spk or {}).get('name') or ''
            if name in ('', f'NPC_{src.giver}', f'NPC {src.giver}') or \
                    name.startswith('Lector'):
                name = ''
        journal = dict(src.journal)
        self.filled = default_journal(journal)
        self.targets = []
        self.npcid.set(str(free_npc_id(app.index, app.project) or ''))
        self.targets = marker_targets(src, self._npc(), self.retail_tiles)
        self.npcname.set(name)
        self.title_v.set(src.title or '')
        for key, var in self.jvars.items():
            var.set(journal.get(key) or '')
        task = src.task()
        lines = sum(len(n.get('lines') or []) for n in src.graph['nodes']
                    .values() if n.get('type') in ('npc', 'player'))
        self.preview.configure(text=t(
            'mp.preview', title=src.title or '-',
            task=' '.join([task.get('fc') or '-'] + [
                str(v) for v in (task.get('args') or {}).values()]),
            lines=lines, markers=len(self.targets)))
        self._refresh()

    # -- 2: the quest giver ----------------------------------------------------

    def _build_giver(self, parent):
        f = self._section(parent, 'mp.sec.giver', 2)
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text=t('mp.npcname')).grid(row=0, column=0, sticky='w',
                                                pady=2)
        self.npcname = tk.StringVar()
        self.name_ent = ttk.Entry(f, textvariable=self.npcname, width=28)
        self.name_ent.grid(row=0, column=1, sticky='w', padx=8)
        self.npcname.trace_add('write', lambda *_: self._refresh())
        ttk.Label(f, text=t('mp.npcid')).grid(row=1, column=0, sticky='w',
                                              pady=2)
        sub = ttk.Frame(f)
        sub.grid(row=1, column=1, sticky='w', padx=8)
        self.npcid = tk.StringVar()
        self.npc_ent = ttk.Entry(sub, textvariable=self.npcid, width=8)
        self.npc_ent.pack(side='left')
        self.npcid.trace_add('write', lambda *_: self._npc_changed())
        ttk.Label(sub, text=t('mp.newid')).pack(side='left', padx=(16, 6))
        self.newid = tk.StringVar()
        self.newid_cb = ttk.Combobox(sub, textvariable=self.newid, width=9,
                                     state='readonly')
        self.newid_cb.pack(side='left')
        self.active = tk.BooleanVar(value=True)
        self.active_cb = ttk.Checkbutton(f, text=t('mp.active'),
                                         variable=self.active)
        self.active_cb.grid(row=2, column=0, columnspan=2, sticky='w',
                            pady=(4, 0))

    def _npc(self):
        try:
            return int(self.npcid.get().strip())
        except ValueError:
            return None

    def _npc_changed(self):
        """The giver's marker number is the NPC number."""
        npc = self._npc()
        for tg in self.targets:
            if tg['key'] == GIVER_KEY and npc is not None:
                tg['num'] = npc
                tg['label'] = t('mp.why.giver', id=npc)
                if tg.get('placed'):
                    tg['placed']['num'] = npc
        self._refresh()

    # -- 3: when the quest is there -----------------------------------------------

    def _build_when(self, parent):
        f = self._section(parent, 'mp.sec.when', 3)
        self.when = tk.StringVar(value=START)
        self.when_start = ttk.Radiobutton(f, text=t('mp.when.start'),
                                          value=START, variable=self.when,
                                          command=self._refresh)
        self.when_start.grid(row=0, column=0, columnspan=3, sticky='w')
        ttk.Radiobutton(f, text=t('mp.when.after'), value=AFTER,
                        variable=self.when, command=self._refresh
                        ).grid(row=1, column=0, sticky='w')
        self.pred = tk.StringVar()
        idx = self.app.index
        preds = []
        for k in sorted(idx.quests, key=int) if idx else []:
            qid = int(k)
            if 0 < qid < MP_FIRST_QUEST and idx.quests[k].get('title'):
                preds.append(f"Q_{qid}  {idx.quests[k]['title']}")
        self.pred_cb = ttk.Combobox(f, textvariable=self.pred, width=34,
                                    values=preds, state='readonly')
        self.pred_cb.grid(row=1, column=1, sticky='w', padx=6)
        self.pred.set(next((p for p in preds if p.startswith('Q_4 ')),
                           preds[0] if preds else ''))
        self.event = tk.StringVar(value='TAKE')
        ttk.Combobox(f, textvariable=self.event, width=8, values=EVENTS,
                     state='readonly').grid(row=1, column=2, sticky='w')

    # -- 4: journal ------------------------------------------------------------

    def _build_journal(self, parent):
        f = self._section(parent, 'mp.sec.journal', 4)
        f.columnconfigure(1, weight=1)
        self.title_v = tk.StringVar()
        self.jvars, self.jents, self.jnotes = {}, {}, {}
        rows = [('title', 'mp.j.title', self.title_v)]
        for key in ('take', 'solve', 'close'):
            self.jvars[key] = tk.StringVar()
            rows.append((key, 'mp.j.' + key, self.jvars[key]))
        for r, (key, label, var) in enumerate(rows):
            ttk.Label(f, text=t(label)).grid(row=r, column=0, sticky='w',
                                             pady=2)
            ent = ttk.Entry(f, textvariable=var)
            ent.grid(row=r, column=1, sticky='ew', padx=8)
            note = ttk.Label(f, text='', foreground='#e0a050')
            note.grid(row=r, column=2, sticky='w')
            self.jents[key], self.jnotes[key] = ent, note
            var.trace_add('write', lambda *_: self._refresh())
        ttk.Label(f, text=t('mp.group')).grid(row=len(rows), column=0,
                                              sticky='w', pady=2)
        self.group = tk.StringVar()
        idx = self.app.index
        groups = sorted(((int(k), v) for k, v in idx.groups.items()),
                        key=lambda kv: kv[0]) if idx else []
        self.group_cb = ttk.Combobox(f, textvariable=self.group, width=30,
                                     values=[f'{g}  {n}' for g, n in groups],
                                     state='readonly')
        self.group_cb.grid(row=len(rows), column=1, sticky='w', padx=8)
        pred = idx.quest(4) if idx else None
        default = pred['group'] if pred else (groups[0][0] if groups else 0)
        for g, n in groups:
            if g == default:
                self.group.set(f'{g}  {n}')

    # -- 5: markers ----------------------------------------------------------------

    def _build_markers(self, parent):
        f = self._section(parent, 'mp.sec.markers', 5)
        self.place_btn = ttk.Button(f, text=t('mp.place'),
                                    style='Accent.TButton', command=self.place)
        self.place_btn.pack(anchor='w')
        self.marker_box = ttk.Frame(f)
        self.marker_box.pack(fill='x', pady=(6, 0))

    def _marker_rows(self):
        for w in self.marker_box.winfo_children():
            w.destroy()
        if not self.targets:
            ttk.Label(self.marker_box, text=t('mp.markers.none'),
                      style='Muted.TLabel').pack(anchor='w')
            return
        for tg in self.targets:
            ok = target_ready(tg)
            row = tk.Frame(self.marker_box, bg=theme.PANEL)
            row.pack(fill='x', pady=1)
            tk.Label(row, text='✓' if ok else '○', width=2,
                     bg=theme.OK if ok else theme.ERR, fg='#0b1a0f',
                     font=theme.FONT_BOLD).pack(side='left', fill='y')
            p = tg.get('placed')
            if tg['exists']:
                num = tg['game_num']
            else:
                num = (p or {}).get('num', tg.get('num'))
            name = mods.editor_name(tg['name']) + (
                f' {num}' if num is not None else '')
            if tg['exists']:
                where = t('mp.m.game', tile=tg['tile'])
            elif p:
                where = t('place.on', tile=p['tile'])
            else:
                where = t('mp.m.open')
            lines = len(tg['refs'])
            label = tg['label'] + (f'  ({t("mp.m.lines", n=lines)})'
                                   if lines > 1 else '')
            tk.Label(row, text=f'{name}  -  {where}\n{label}', justify='left',
                     anchor='w', bg=theme.PANEL,
                     fg=theme.OK if ok else theme.INK, font=theme.FONT
                     ).pack(side='left', fill='x', expand=True, padx=6)

    # -- state ------------------------------------------------------------------

    def missing(self):
        """[(key, widget)] of what is still open (the tour marks them red)."""
        if self.src is None:
            return [('quest', self.tree)]
        out = []
        if not self.npcname.get().strip():
            out.append(('name', self.name_ent))
        npc = self._npc()
        idx = self.app.index
        used = {int(k) for k in idx.npcs} if idx else set()
        used |= {s['id'] for q in self.app.project.quests for s in q.speakers
                 if isinstance(s['id'], int)}
        if npc is None or not 1 <= npc <= MAX_NPC_ID or npc in used:
            out.append(('npc', self.npc_ent))
        if not self.title_v.get().strip():
            out.append(('title', self.jents['title']))
        for key in ('take', 'solve', 'close'):
            if not self.jvars[key].get().strip():
                out.append((key, self.jents[key]))
        if self.when.get() == AFTER and not self.pred.get():
            out.append(('pred', self.pred_cb))
        if any(not target_ready(tg) for tg in self.targets):
            out.append(('markers', self.place_btn))
        return out

    def _refresh(self):
        if self.take_btn is None:
            return
        for key, note in self.jnotes.items():
            var = self.title_v if key == 'title' else self.jvars[key]
            std = key in self.filled and var.get() == t(
                'mp.journal.default.' + key)
            note.configure(text=t('mp.j.std') if std else '')
        self._marker_rows()
        miss = self.missing()
        self.take_btn.state(['disabled'] if miss else ['!disabled'])
        if self.src is None:
            self.status.configure(text=t('mp.st.pick'), foreground=theme.MUT)
        elif miss:
            names = []
            for key, _w in miss:
                if key == 'markers':
                    n = sum(1 for tg in self.targets if not target_ready(tg))
                    names.append(t('mp.miss.markers', n=n))
                else:
                    names.append(t('mp.miss.' + key))
            self.status.configure(text=t('mp.st.open', items=', '.join(names)),
                                  foreground=theme.ERR)
        else:
            self.status.configure(text=t('mp.st.ready'), foreground=theme.OK)

    # -- map -------------------------------------------------------------------

    def ensure_saved(self):
        """The markers go into a folder next to the project file: an unsaved
        project is saved on its own, in Documents, named after the quest
        (Marco: no extra clicks)."""
        from . import editormaps
        app = self.app
        if editormaps.levels_dir(app.project):
            return True
        # the file name becomes the name of the mod archive, which keeps
        # only A-Z, 0-9, _ and -: "Großer Hunger" -> "Grosser Hunger"
        title = self.title_v.get() or 'Quest'
        for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('Ä', 'Ae'),
                     ('Ö', 'Oe'), ('Ü', 'Ue'), ('ß', 'ss')):
            title = title.replace(a, b)
        base = re.sub(r'[^A-Za-z0-9_\- ]+', '', title).strip() or 'Quest'
        path = data.default_project_path(base)
        if not app._write_project(path):
            return False
        app.set_info(t('mp.saved', path=path), 'StatusOk.TLabel')
        return True

    def place(self):
        """The markers still open (and those set before, to move them) on
        the map; "Confirm" there brings them back here."""
        from . import placewin
        if self.src is None:
            return
        if not self.ensure_saved():
            return
        self._npc_changed()
        targets = []
        for tg in self.targets:
            if tg['exists']:
                continue
            p = tg.get('placed')
            targets.append({
                'key': tg['key'], 'name': tg['name'], 'label': tg['label'],
                'num': tg['num'], 'tile': (p or {}).get('tile'),
                'orig': None, 'placed': dict(p) if p else None,
                '_prev': dict(p) if p else {}, 'src': tg})
        if not targets:
            return
        self.place_win = placewin.PlaceWindow(self.app, targets, self._placed)

    def _placed(self, targets):
        for tg in targets:
            tg['src']['placed'] = tg.get('placed')
        self.place_win = None
        self._refresh()
        try:
            self.win.lift()
        except tk.TclError:
            pass

    # -- take over -----------------------------------------------------------------

    def take(self):
        if self.missing():
            self._refresh()
            return
        from . import placewin
        app = self.app
        m = re.fullmatch(r'Q_(\d+)', self.newid.get().strip())
        if not m:
            return
        try:
            group = int(self.group.get().split()[0])
        except (ValueError, IndexError):
            group = None
        try:
            pred = int(self.pred.get().split()[0][2:])
        except (ValueError, IndexError):
            pred = 4
        new = take_over(
            self.src, int(m.group(1)), self._npc(),
            self.npcname.get().strip(), self.targets, self.retail_tiles,
            group=group, active=self.active.get(),
            availability=self.when.get(), pred=pred, event=self.event.get(),
            title=self.title_v.get().strip(),
            journal={k: v.get().strip() for k, v in self.jvars.items()})
        app.project.quests.append(new)
        app.mark_dirty()
        report = placewin.safe_commit(app, new, commit_targets(self.targets),
                                      self.win)
        app.open_quest(new)
        if app.project.path:
            app._write_project(app.project.path)
        clash = [c for r in (report or {}).values() for c in r['clash']]
        if report is not None and clash:
            placewin._report(app, report)
        app.set_info(t('mp.done2', old=self.src.id, new=new.id),
                     'StatusOk.TLabel')
        self.taken = new
        self.close()
