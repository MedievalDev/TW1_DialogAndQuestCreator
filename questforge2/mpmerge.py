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
``(null)``, and markers on those tiles the user places in the Two Worlds
editor. The tool cannot write markers; it lists which ones, with name,
number and tile, as a checklist the user ticks off.
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
        key = (ref['name'], tl, ref['num'])
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
        if not any(x['name'] == ref['name'] and x['num'] == num
                   and x['tile'] == tl for x in items):
            items.append({'name': ref['name'], 'num': num, 'tile': tl,
                          'why': ref['label'],
                          'exists': num in mods.marker_ids(
                              retail_tiles.get(tl), ref['name'])})
    return items, mapping


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
        ref['args'][ref['num_key']] = mapping[(ref['name'], tl.upper(),
                                               ref['num'])]
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
    return [t('mp.item', name=x['name'], num=x['num'], tile=x['tile'])
            + ('   ' + t('mp.exists') if x.get('exists') or x.get('done')
               else '') for x in items]


# ---------------------------------------------------------------------------
# window

class MpMergeWindow:
    """Three steps: pick the multiplayer quest, choose ids and tiles, read
    the marker checklist and take the quest over."""
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
        self.src = None            # quest built from the game
        self.step = 0
        self.rows = []             # per marker line: (ref, tile var, num var)
        game = app.cfg.get('game_dir')
        self.retail_tiles = (app.modset.retail_tiles if app.modset
                             else mods.retail_markers(game))
        self.win = tk.Toplevel(app.root)
        self.win.title(t('mp.title'))
        self.win.geometry('820x640')
        self.win.minsize(700, 520)
        theme.dark_titlebar(self.win)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.win.bind('<Escape>', lambda e: self.close())
        outer = ttk.Frame(self.win, padding=14)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text=t('mp.head'), style='Brand.TLabel'
                  ).pack(anchor='w')
        self.steplbl = ttk.Label(outer, text='', style='Muted.TLabel',
                                 wraplength=780, justify='left')
        self.steplbl.pack(anchor='w', pady=(2, 8))
        self.pages = [ttk.Frame(outer) for _ in range(3)]
        self._build_page1(self.pages[0])
        self._build_page2(self.pages[1])
        self._build_page3(self.pages[2])
        btns = ttk.Frame(outer)
        btns.pack(fill='x', side='bottom', pady=(10, 0))
        ttk.Button(btns, text=t('cancel'), command=self.close
                   ).pack(side='right')
        self.next_btn = ttk.Button(btns, text=t('mp.next'),
                                   style='Accent.TButton', command=self.next)
        self.next_btn.pack(side='right', padx=6)
        self.back_btn = ttk.Button(btns, text=t('mp.back'), command=self.back)
        self.back_btn.pack(side='right')
        self._show_step(0)
        if qid is not None:
            self.pick(qid)

    def close(self):
        MpMergeWindow._open = None
        self.win.destroy()

    # -- page 1: pick ----------------------------------------------------------

    def _build_page1(self, f):
        top = ttk.Frame(f)
        top.pack(fill='x')
        ttk.Label(top, text=t('map.search')).pack(side='left')
        self.q = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.q)
        ent.pack(side='left', fill='x', expand=True, padx=6)
        ent.bind('<KeyRelease>', lambda e: self._fill_list())
        box = ttk.Frame(f)
        box.pack(fill='both', expand=True, pady=(6, 0))
        cols = ('id', 'title', 'task', 'giver')
        self.tree = ttk.Treeview(box, columns=cols, show='headings',
                                 selectmode='browse')
        for c, w in zip(cols, (60, 260, 260, 120)):
            self.tree.heading(c, text=t('mp.col.' + c))
            self.tree.column(c, width=w, anchor='w', stretch=c != 'id')
        sb = ttk.Scrollbar(box, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<Double-Button-1>', lambda e: self.next())
        self.mp_ids = []
        self._fill_list()

    def _fill_list(self):
        idx = self.app.index
        needle = self.q.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        self.mp_ids = []
        for k in sorted(idx.quests, key=int) if idx else []:
            qid = int(k)
            if not is_mp_quest(qid):
                continue
            info = idx.quests[k]
            giver = info.get('giver')
            gname = idx.npc_label(giver) if giver is not None else '-'
            row = (f'Q_{qid}', info.get('title') or '-',
                   ' '.join(info.get('fc') or []) or '-', gname)
            if needle and needle not in ' '.join(row).lower():
                continue
            self.tree.insert('', 'end', iid=str(qid), values=row)
            self.mp_ids.append(qid)

    def pick(self, qid):
        self._show_step(0)
        if self.tree.exists(str(qid)):
            self.tree.selection_set(str(qid))
            self.tree.see(str(qid))
            self.next()

    def _selected_qid(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    # -- page 2: ids and tiles -------------------------------------------------

    def _build_page2(self, f):
        grid = ttk.Frame(f)
        grid.pack(fill='x')
        grid.columnconfigure(1, weight=1)
        r = 0
        ttk.Label(grid, text=t('mp.newid')).grid(row=r, column=0, sticky='w',
                                                 pady=3)
        self.newid = tk.StringVar()
        self.newid_cb = ttk.Combobox(grid, textvariable=self.newid, width=12,
                                     state='readonly')
        self.newid_cb.grid(row=r, column=1, sticky='w', padx=8)
        r += 1
        ttk.Label(grid, text=t('mp.npcid')).grid(row=r, column=0, sticky='w',
                                                 pady=3)
        self.npcid = tk.StringVar()
        ttk.Entry(grid, textvariable=self.npcid, width=12).grid(
            row=r, column=1, sticky='w', padx=8)
        ttk.Label(grid, text=t('mp.npcid.hint', max=MAX_NPC_ID),
                  style='Muted.TLabel', wraplength=520, justify='left'
                  ).grid(row=r, column=2, sticky='w')
        r += 1
        ttk.Label(grid, text=t('mp.npcname')).grid(row=r, column=0,
                                                   sticky='w', pady=3)
        self.npcname = tk.StringVar()
        ttk.Entry(grid, textvariable=self.npcname, width=30).grid(
            row=r, column=1, sticky='w', padx=8)
        r += 1
        ttk.Label(grid, text=t('mp.tile')).grid(row=r, column=0, sticky='w',
                                                pady=3)
        self.tile = tk.StringVar()
        tiles = sorted(self.retail_tiles, key=data._tile_key)
        self.tile_cb = ttk.Combobox(grid, textvariable=self.tile, width=12,
                                    values=tiles)
        self.tile_cb.grid(row=r, column=1, sticky='w', padx=8)
        self.tile_cb.bind('<<ComboboxSelected>>', lambda e: self._tile_all())
        self.tile_cb.bind('<KeyRelease>', lambda e: self._tile_all())
        tb = ttk.Frame(grid)
        tb.grid(row=r, column=2, sticky='w')
        ttk.Button(tb, text='...', width=3, command=self._pick_tile
                   ).pack(side='left')
        ttk.Button(tb, text=t('map.button'), command=self._map
                   ).pack(side='left', padx=4)
        ttk.Label(tb, text=t('mp.tile.hint'), style='Muted.TLabel',
                  wraplength=380, justify='left').pack(side='left')
        r += 1
        ttk.Label(grid, text=t('mp.group')).grid(row=r, column=0, sticky='w',
                                                 pady=3)
        self.group = tk.StringVar()
        self.group_cb = ttk.Combobox(grid, textvariable=self.group, width=30,
                                     state='readonly')
        self.group_cb.grid(row=r, column=1, sticky='w', padx=8)
        ttk.Label(f, text=t('mp.lines'), style='Brand.TLabel'
                  ).pack(anchor='w', pady=(12, 2))
        ttk.Label(f, text=t('mp.lines.hint'), style='Muted.TLabel',
                  wraplength=780, justify='left').pack(anchor='w')
        self.lines_box = ttk.Frame(f)
        self.lines_box.pack(fill='both', expand=True, pady=(6, 0))

    def _fill_page2(self):
        app = self.app
        q = self.src
        free = app.index.free_ids({x.id for x in app.project.quests}
                                  | (app.modset.quest_ids()
                                     if app.modset else set()))
        self.newid_cb.configure(values=[f'Q_{i}' for i in free])
        self.newid.set(f'Q_{free[0]}' if free else '')
        self.npcid.set(str(free_npc_id(app.index, app.project) or ''))
        name = ''
        if q.giver is not None:
            spk = next((s for s in q.speakers if s['id'] == q.giver), None)
            name = (spk or {}).get('name') or ''
            if not name or name == f'NPC_{q.giver}':
                name = t('mp.npcname.default', id=q.giver)
        self.npcname.set(name)
        groups = sorted(((int(k), v) for k, v in app.index.groups.items()),
                        key=lambda kv: kv[0])
        self.groups = groups
        self.group_cb.configure(values=[f'{g}  {n}' for g, n in groups])
        pred = app.index.quest(4)
        default = pred['group'] if pred else (groups[0][0] if groups else 0)
        for g, n in groups:
            if g == default:
                self.group.set(f'{g}  {n}')
        if not self.tile.get():
            self.tile.set('')
        for w in self.lines_box.winfo_children():
            w.destroy()
        self.rows = []
        refs = marker_refs(q)
        if not refs:
            ttk.Label(self.lines_box, text=t('mp.lines.none'),
                      style='Muted.TLabel').pack(anchor='w')
        head = ttk.Frame(self.lines_box)
        head.pack(fill='x')
        for text, w in ((t('mp.col.line'), 40), (t('mp.col.marker'), 28),
                        (t('mp.col.tile'), 8), (t('mp.col.num'), 8)):
            ttk.Label(head, text=text, style='Muted.TLabel', width=w
                      ).pack(side='left')
        tiles = sorted(self.retail_tiles, key=data._tile_key)
        for ref in refs:
            row = ttk.Frame(self.lines_box)
            row.pack(fill='x', pady=1)
            vals = ' '.join(str(v) for k, v in ref['args'].items()
                            if k not in (ref['tile_key'], ref['num_key']))
            lbl = ttk.Label(row, text=f"{ref['label']} {vals}"[:38], width=40)
            lbl.pack(side='left')
            theme.Tooltip(lbl, f"{ref['label']} {vals}")
            ttk.Label(row, text=ref['name'], width=28).pack(side='left')
            tv = tk.StringVar(value=ref['tile'] or self.tile.get())
            ttk.Combobox(row, textvariable=tv, values=tiles, width=7
                         ).pack(side='left')
            nv = tk.StringVar(value='' if ref['num'] is None else
                              str(ref['num']))
            ttk.Entry(row, textvariable=nv, width=7).pack(side='left',
                                                          padx=(6, 0))
            self.rows.append((ref, tv, nv))
        self._tile_all(only_empty=True)

    def _tile_all(self, only_empty=False):
        tile = self.tile.get().strip().upper()
        if not tile:
            return
        for _ref, tv, _nv in self.rows:
            if not only_empty or not tv.get().strip():
                tv.set(tile)
        self._renumber()

    def _renumber(self):
        """Proposed numbers for the chosen tiles (kept unless they clash)."""
        tiles = {i: tv.get().strip().upper() for i, (_r, tv, _n)
                 in enumerate(self.rows)}
        try:
            npc = int(self.npcid.get())
        except ValueError:
            npc = 0
        _items, mapping = plan(self.src, npc, self.tile.get().strip().upper()
                               or 'E1', self.retail_tiles, tiles)
        for i, (ref, tv, nv) in enumerate(self.rows):
            key = (ref['name'], tiles[i], ref['num'])
            if key in mapping:
                nv.set(str(mapping[key]))

    def _pick_tile(self):
        from .mappicker import MapPicker
        dlg = MapPicker(self.app, 'tile', None, self.tile.get())
        self.win.wait_window(dlg.win)
        if dlg.result and dlg.result.get('tile'):
            self.tile.set(dlg.result['tile'].upper())
            self._tile_all()

    def _map(self):
        self.app.show_map(tile=self.tile.get().strip().upper() or None)

    # -- page 3: checklist -----------------------------------------------------

    def _build_page3(self, f):
        self.summary = tk.Text(f, wrap='word', font=theme.FONT_MONO, height=18)
        self.summary.pack(fill='both', expand=True)
        for tag, colour in (('head', theme.GOLD), ('ok', theme.OK),
                            ('warn', '#e0a050'), ('mut', theme.MUT)):
            self.summary.tag_configure(tag, foreground=colour)
        self.summary.configure(state='disabled')

    def _settings(self):
        """(new id, npc id, name, tile, group, tiles, numbers) or None with
        the error shown."""
        m = re.fullmatch(r'Q_(\d+)', self.newid.get().strip())
        if not m:
            messagebox.showwarning(t('mp.title'), t('mp.err.id'),
                                   parent=self.win)
            return None
        new_id = int(m.group(1))
        try:
            npc = int(self.npcid.get().strip())
        except ValueError:
            npc = 0
        used = {int(k) for k in self.app.index.npcs}
        used |= {s['id'] for q in self.app.project.quests for s in q.speakers
                 if isinstance(s['id'], int)}
        if not 1 <= npc <= MAX_NPC_ID or npc in used:
            messagebox.showwarning(t('mp.title'), t('mp.err.npc',
                                                    max=MAX_NPC_ID),
                                   parent=self.win)
            return None
        tile = self.tile.get().strip().upper()
        if tile not in self.retail_tiles:
            messagebox.showwarning(t('mp.title'), t('mp.err.tile'),
                                   parent=self.win)
            return None
        tiles, numbers = {}, {}
        for i, (_ref, tv, nv) in enumerate(self.rows):
            tl = tv.get().strip().upper()
            if tl not in self.retail_tiles:
                messagebox.showwarning(t('mp.title'), t('mp.err.linetile',
                                                        line=i + 1),
                                       parent=self.win)
                return None
            tiles[i] = tl
            try:
                numbers[i] = int(nv.get().strip())
            except ValueError:
                messagebox.showwarning(t('mp.title'), t('mp.err.num',
                                                        line=i + 1),
                                       parent=self.win)
                return None
        try:
            group = int(self.group.get().split()[0])
        except (ValueError, IndexError):
            group = None
        name = self.npcname.get().strip() or t('mp.npcname.default',
                                                id=self.src.giver)
        return new_id, npc, name, tile, group, tiles, numbers

    def _fill_page3(self, settings):
        new_id, npc, name, tile, group, tiles, numbers = settings
        items, _m = plan(self.src, npc, tile, self.retail_tiles, tiles,
                         numbers)
        self.items = items
        s = self.summary
        s.configure(state='normal')
        s.delete('1.0', 'end')
        s.insert('end', t('mp.sum.quest', old=self.src.id, new=new_id) + NL,
                 'head')
        s.insert('end', t('mp.sum.npc', old=self.src.giver, new=npc,
                          name=name, tile=tile, party=DEFAULT_PARTY) + NL)
        s.insert('end', t('mp.sum.group', group=self.group.get()) + NL)
        raw = self.src.extra.get('qtx', {}).get('raw') or []
        if raw:
            s.insert('end', t('mp.sum.raw', n=len(raw)) + NL, 'warn')
            for kw, toks in raw[:6]:
                s.insert('end', '   ' + kw + ' ' + ' '.join(toks) + NL, 'mut')
        s.insert('end', NL + t('mp.sum.markers') + NL, 'head')
        s.insert('end', t('mp.sum.markers.hint') + NL + NL, 'mut')
        for x in items:
            line = t('mp.item', name=x['name'], num=x['num'], tile=x['tile'])
            s.insert('end', ('  [x] ' if x['exists'] else '  [ ] ') + line
                     + NL, 'ok' if x['exists'] else None)
            s.insert('end', '        ' + x['why'] + NL, 'mut')
        s.insert('end', NL + t('mp.sum.after') + NL, 'mut')
        s.configure(state='disabled')

    # -- flow ------------------------------------------------------------------

    def _show_step(self, i):
        self.step = i
        for k, p in enumerate(self.pages):
            if k == i:
                p.pack(fill='both', expand=True)
            else:
                p.pack_forget()
        self.steplbl.configure(text=t(f'mp.step{i + 1}'))
        self.back_btn.state(['!disabled'] if i else ['disabled'])
        self.next_btn.configure(text=t('mp.take') if i == 2 else t('mp.next'))

    def back(self):
        if self.step:
            self._show_step(self.step - 1)

    def next(self):
        if self.step == 0:
            qid = self._selected_qid()
            if qid is None:
                return
            src = self.app.build_game_quest(qid)
            if src is None:
                return
            self.src = src
            self._fill_page2()
            self._show_step(1)
        elif self.step == 1:
            settings = self._settings()
            if settings is None:
                return
            self.settings = settings
            self._fill_page3(settings)
            self._show_step(2)
        else:
            self.take()

    def take(self):
        new_id, npc, name, tile, group, tiles, numbers = self.settings
        app = self.app
        new = apply(self.src, new_id, npc, name, tile, self.retail_tiles,
                    tiles, numbers, group)
        app.project.quests.append(new)
        app.mark_dirty()
        app.open_quest(new)
        open_items = [x for x in new.extra['markers_todo'] if not x['done']]
        app.set_info(t('mp.done', old=self.src.id, new=new_id,
                       n=len(open_items)), 'StatusOk.TLabel')
        self.close()
