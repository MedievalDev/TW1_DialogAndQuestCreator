"""Tile picker (plan section 7): a grid of map tiles as a filter for ids.

Modes: 'npc', 'location', 'object', 'tile', 'marker' (with a marker kind).
The tile grid is derived from the tile names in the index (NPC, LOCATION
and marker usage) and the game maps; outdoor tiles like ``F5`` form the grid,
interiors like ``B8_1`` are listed below it. There is no map image yet.
Result: ``{'value': str|int, 'tile': str}`` or None.

Markers come from the maps themselves (``mods.retail_markers``) plus the
maps of the project's mods (update 5b): mod entries carry a blue dot and a
tooltip with their origin. A mod tile that lost markers of the game is red;
its markers are blocked for quests outside that mod. Picking a mod marker
for another quest asks first, because the tile goes into the build.
"""

import re
import tkinter as tk
from tkinter import messagebox, ttk

from . import data, mods, theme
from .i18n import t
from .modswin import missing_text, origin_text

NL = chr(10)

CELL = 30


def _split(tile):
    m = re.fullmatch(r'([A-Z])(\d+)', tile or '')
    return (m.group(1), int(m.group(2))) if m else None


class MapPicker:
    def __init__(self, app, mode, kind=None, tile=None):
        self.app = app
        self.mode = mode
        self.kind = kind
        self.result = None
        idx = app.index
        self.idx = idx
        self.modset = ms = app.modset
        self.for_mod = app.is_mod_quest(app.quest)
        self.mkname = mods.MARKER_NAMES.get(kind) if kind else None
        self.tile = (tile or '').upper() or None
        self.win = tk.Toplevel(app.root)
        self.win.title(t('picker.title'))
        self.win.transient(app.root)
        self.win.geometry('860x560')
        theme.dark_titlebar(self.win)
        root = ttk.Frame(self.win, padding=10)
        root.pack(fill='both', expand=True)

        # counts per tile
        self.counts = {}
        for n in idx.npcs.values():
            self._count(n.get('tile'), 0)
        for loc in idx.locations.values():
            self._count(loc.get('tile'), 1)
        if mode == 'marker' and ms and self.mkname:
            for tl, info in ms.retail_tiles.items():
                self._count(tl, 2, len(mods.marker_ids(info, self.mkname)))
        else:
            for key, nums in idx.markers.items():
                k, tl = key.split('|')
                self._count(tl, 2, len(nums))
        # tiles the mods bring: blue dot; red when game markers are gone
        self.mod_tiles, self.red = {}, {}
        for info in (ms.enabled() if ms else []):
            for tl, rec in info['tiles'].items():
                self.mod_tiles.setdefault(tl, []).append(info['name'])
                if rec.get('missing'):
                    self.red.setdefault(tl, []).append(
                        (info['name'], rec['missing']))
                if mode == 'marker' and self.mkname:
                    base = mods.marker_ids(ms.retail_tiles.get(tl),
                                           self.mkname)
                    self._count(tl, 2, len(mods.marker_ids(rec, self.mkname)
                                           - base))
            for n in info['npcs'].values():
                self._count(n.get('tile'), 0)
            for loc in info['locations'].values():
                self._count(loc.get('tile'), 1)
        tiles = [tl for tl in idx.tiles if tl and tl != '(null)']
        if ms:
            tiles = sorted(set(tiles) | set(ms.retail_tiles)
                           | set(self.mod_tiles), key=data._tile_key)
        outdoor = [tl for tl in tiles if _split(tl)]
        self.interior = sorted(tl for tl in tiles if not _split(tl))
        cols = sorted({_split(tl)[0] for tl in outdoor})
        rows = sorted({_split(tl)[1] for tl in outdoor})
        self.cols, self.rows = cols, rows

        left = ttk.Frame(root)
        left.pack(side='left', fill='y')
        self.grid_c = tk.Canvas(left, width=CELL * (len(cols) + 1) + 4,
                                height=CELL * (len(rows) + 1) + 4,
                                bg=theme.CANVAS_BG, highlightthickness=0)
        self.grid_c.pack(anchor='nw')
        self.grid_c.bind('<Button-1>', self._grid_click)
        self.grid_c.bind('<Motion>', self._grid_hover)
        self.tip = theme.FloatTip(self.win)
        self.grid_c.bind('<Leave>', lambda e: self.tip.hide())
        self.win.bind('<Destroy>', lambda e: self.tip.hide(), add='+')
        self.hover = ttk.Label(left, text='', style='Muted.TLabel')
        self.hover.pack(anchor='w', pady=(4, 2))
        ttk.Button(left, text=t('picker.all'),
                   command=lambda: self._set_tile(None)).pack(anchor='w')
        ttk.Label(left, text=t('picker.interior')).pack(anchor='w', pady=(8, 2))
        ib = ttk.Frame(left)
        ib.pack(anchor='w', fill='x')
        self.int_list = tk.Listbox(ib, height=8, width=16, font=theme.FONT,
                                   activestyle='none', exportselection=False)
        self.int_list.pack(side='left', fill='y')
        for tl in self.interior:
            self.int_list.insert('end', f'{tl}  ({self._total(tl)})')
        self.int_list.bind('<<ListboxSelect>>', self._interior_pick)
        self._draw_grid()

        right = ttk.Frame(root)
        right.pack(side='left', fill='both', expand=True, padx=(12, 0))
        top = ttk.Frame(right)
        top.pack(fill='x')
        ttk.Label(top, text=t('picker.search')).pack(side='left')
        self.q = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.q)
        ent.pack(side='left', fill='x', expand=True, padx=6)
        ent.bind('<KeyRelease>', lambda e: self._fill())
        self.tile_lbl = ttk.Label(top, text='', foreground=theme.GOLD)
        self.tile_lbl.pack(side='left')
        box = ttk.Frame(right)
        box.pack(fill='both', expand=True, pady=6)
        self.lst = tk.Listbox(box, font=theme.FONT, activestyle='none')
        sb = ttk.Scrollbar(box, orient='vertical', command=self.lst.yview)
        self.lst.configure(yscrollcommand=sb.set)
        self.lst.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.lst.bind('<Double-Button-1>', lambda e: self._ok())
        self.lst.bind('<Return>', lambda e: self._ok())
        self.lst.bind('<Motion>', self._list_hover)
        self.lst.bind('<Leave>', lambda e: self.tip.hide())
        self.note = ttk.Label(right, text='', style='Muted.TLabel',
                              wraplength=520)
        self.note.pack(anchor='w')
        if mode == 'marker':
            own = ttk.Frame(right)
            own.pack(fill='x', pady=(6, 0))
            ttk.Label(own, text=t('picker.own')).pack(side='left')
            self.own = tk.StringVar()
            ttk.Entry(own, textvariable=self.own, width=8).pack(side='left',
                                                                padx=6)
            reads = t('field.reads', kind=kind)
            if self.mkname:
                reads = t('field.reads', kind=self.mkname)
            self.note.configure(text=(t('picker.maps') if ms and self.mkname
                                      else t('picker.lnd')) + '  ' + reads)
        elif mode == 'object':
            self.note.configure(text=t('picker.notile'))
        b = ttk.Frame(right)
        b.pack(anchor='e', pady=(8, 0))
        ttk.Button(b, text=t('ok'), style='Accent.TButton',
                   command=self._ok).pack(side='left', padx=(0, 6))
        ttk.Button(b, text=t('cancel'), command=self.win.destroy
                   ).pack(side='left')
        self.win.bind('<Escape>', lambda e: self.win.destroy())
        self.rows_data = []
        self._set_tile(self.tile)
        ent.focus_set()
        self.win.grab_set()

    # -- tiles ------------------------------------------------------------------

    def _count(self, tile, slot, n=1):
        if not tile or tile == '(null)':
            return
        c = self.counts.setdefault(tile, [0, 0, 0])
        c[slot] += n

    def _total(self, tile):
        return sum(self.counts.get(tile, [0, 0, 0]))

    def _draw_grid(self):
        c = self.grid_c
        c.delete('all')
        mx = max([self._total(tl) for tl in self.counts] + [1])
        for i, col in enumerate(self.cols):
            c.create_text(CELL * (i + 1) + CELL / 2 + 2, CELL / 2, text=col,
                          fill=theme.MUT, font=theme.FONT_SMALL)
        for j, row in enumerate(self.rows):
            c.create_text(CELL / 2, CELL * (j + 1) + CELL / 2 + 2,
                          text=str(row), fill=theme.MUT, font=theme.FONT_SMALL)
        for i, col in enumerate(self.cols):
            for j, row in enumerate(self.rows):
                tl = f'{col}{row}'
                n = self._total(tl)
                x, y = CELL * (i + 1) + 2, CELL * (j + 1) + 2
                if n:
                    k = 0.25 + 0.75 * min(1.0, n / mx) ** 0.5
                    shade = '#%02x%02x%02x' % (int(0x35 + (0xd2 - 0x35) * k * .5),
                                               int(0x2f + (0xa0 - 0x2f) * k * .5),
                                               int(0x26 + (0x44 - 0x26) * k * .3))
                else:
                    shade = theme.BG
                sel = tl == self.tile
                c.create_rectangle(x, y, x + CELL - 2, y + CELL - 2, fill=shade,
                                   outline=theme.GOLD if sel else theme.LINE,
                                   width=2 if sel else 1,
                                   tags=('cell', 't:' + tl))
                if tl in self.red and not sel:
                    c.create_rectangle(x + 1, y + 1, x + CELL - 3,
                                       y + CELL - 3, outline=theme.ERR,
                                       width=2, tags=('cell', 't:' + tl))
                if tl in self.mod_tiles:
                    c.create_oval(x + CELL - 10, y + 3, x + CELL - 5, y + 8,
                                  fill=theme.MOD, outline='',
                                  tags=('cell', 't:' + tl))

    def _cell_at(self, ev):
        i = int((ev.x - 2) // CELL) - 1
        j = int((ev.y - 2) // CELL) - 1
        if 0 <= i < len(self.cols) and 0 <= j < len(self.rows):
            return f'{self.cols[i]}{self.rows[j]}'
        return None

    def _grid_click(self, ev):
        tl = self._cell_at(ev)
        if tl:
            self._set_tile(tl)

    def _grid_hover(self, ev):
        tl = self._cell_at(ev)
        if tl:
            n, l, m = self.counts.get(tl, [0, 0, 0])
            self.hover.configure(text=t('picker.counts', t=tl, n=n, l=l, m=m))
            lines = []
            if tl in self.mod_tiles:
                lines.append(t('picker.modtile', mods=', '.join(
                    self.mod_tiles[tl])))
            for name, missing in self.red.get(tl, []):
                lines.append(name + ': ' + missing_text(missing))
            if lines:
                self.tip.show(NL.join(lines), ev.x_root, ev.y_root)
            else:
                self.tip.hide()
        else:
            self.tip.hide()

    def _list_hover(self, ev):
        i = self.lst.nearest(ev.y)
        box = self.lst.bbox(i) if 0 <= i < len(self.rows_data) else None
        meta = self.rows_data[i][2] if box and box[1] <= ev.y <= \
            box[1] + box[3] else None
        if not meta:
            self.tip.hide()
            return
        extra = []
        if meta.get('missing'):
            extra.append(missing_text(meta['missing']))
        if meta.get('blocked'):
            extra.append(t('picker.blocked.why'))
        if meta.get('mod'):
            text = origin_text(meta['mod'], meta.get('inner'),
                               meta.get('tile'), meta.get('state'), extra)
        else:
            text = NL.join(extra + [meta.get('note', '')]).strip()
        self.tip.show(text, ev.x_root, ev.y_root)

    def _interior_pick(self, ev):
        sel = self.int_list.curselection()
        if sel:
            self._set_tile(self.interior[sel[0]])

    def _set_tile(self, tile):
        self.tile = tile
        self.tile_lbl.configure(text=tile or t('picker.all'))
        self._draw_grid()
        self._fill()

    # -- list -------------------------------------------------------------------

    def _fill(self):
        idx = self.idx
        q = self.q.get().strip().lower()
        tile = self.tile
        rows = []
        if self.mode == 'npc':
            own = {s['id']: s for s in self.app.quest.speakers
                   if isinstance(s['id'], int)} if self.app.quest else {}
            for sid, s in own.items():
                if s.get('new') and (not tile or s.get('tile', '').upper() == tile):
                    rows.append((f"{s['name']}  (NPC_{sid}, {s.get('tile')})",
                                 sid, s.get('tile')))
            for key, n in sorted(idx.npcs.items(),
                                 key=lambda kv: kv[1]['name'].lower()):
                if tile and n['tile'] != tile:
                    continue
                rows.append((f"{n['name']}  (NPC_{key}, {n['tile']})",
                             int(key), n['tile']))
            for info in (self.modset.enabled() if self.modset else []):
                for key, n in sorted(info['npcs'].items(),
                                     key=lambda kv: kv[1]['name'].lower()):
                    if tile and n['tile'] != tile:
                        continue
                    rows.append((f"{theme.MOD_DOT}{n['name']}  (NPC_{key}, "
                                 f"{n['tile']})   {info['name']}", int(key),
                                 n['tile'], {'mod': info, 'inner': info['qtx'],
                                             'state': n['state']}))
        elif self.mode == 'location':
            for key, loc in sorted(idx.locations.items()):
                if tile and loc['tile'] != tile:
                    continue
                warn = '  !' if loc['type'] == 10 and loc['radius'] == 0 else ''
                rows.append((f"{loc['name']}  ({key}, {loc['tile']}, Typ "
                             f"{loc['type']}, r {loc['radius']}){warn}", key,
                             loc['tile']))
            for info in (self.modset.enabled() if self.modset else []):
                for key, loc in sorted(info['locations'].items()):
                    if tile and loc['tile'] != tile:
                        continue
                    rows.append((f"{theme.MOD_DOT}{key}  ({loc['tile']})   "
                                 f"{info['name']}", key, loc['tile'],
                                 {'mod': info, 'inner': info['qtx'],
                                  'state': loc['state']}))
        elif self.mode == 'object':
            names = idx.object_names
            for obj in idx.objects:
                rows.append((f'{names.get(obj) or obj}  ({obj})', obj, None))
        elif self.mode == 'tile':
            for tl in idx.tiles:
                n, l, m = self.counts.get(tl, [0, 0, 0])
                rows.append((t('picker.counts', t=tl, n=n, l=l, m=m), tl, tl))
        elif self.mode == 'marker' and self.modset and self.mkname:
            use = idx.d.get('marker_use', {})
            listed = set()
            for num, tl, info, missing in self.modset.marker_rows(self.kind,
                                                                  tile):
                qs = use.get(f'{self.kind}|{tl}|{num}', [])
                used = t('picker.used', q=', '.join(f'Q_{x}' for x in qs[:6]))
                listed.add((tl, num))
                if info is None:
                    rows.append((f'{num}  ({tl})   {used}', num, tl))
                    continue
                blocked = bool(missing) and not self.for_mod
                label = f"{theme.MOD_DOT}{num}  ({tl})   {info['name']}"
                if blocked:
                    label += '   ' + t('picker.blocked')
                rows.append((label, num, tl, {
                    'mod': info, 'inner': info['tiles'][tl]['inner'],
                    'tile': tl, 'state': 'new', 'missing': missing,
                    'blocked': blocked}))
            # numbers quests use that no loaded map has (other mods)
            for key, nums in sorted(idx.markers.items()):
                k, tl = key.split('|')
                if k != self.kind or (tile and tl != tile):
                    continue
                for num in nums:
                    if (tl, num) in listed or not tl:
                        continue
                    qs = use.get(f'{k}|{tl}|{num}', [])
                    rows.append((f"{num}  ({tl})   " + t(
                        'picker.used', q=', '.join(f'Q_{x}' for x in qs[:6]))
                        + '   ' + t('picker.nomap'), num, tl,
                        {'note': t('picker.nomap.why'), 'dim': True}))
        elif self.mode == 'marker':
            use = idx.d.get('marker_use', {})
            for key, nums in sorted(idx.markers.items()):
                k, tl = key.split('|')
                if k != self.kind or (tile and tl != tile):
                    continue
                for num in nums:
                    qs = use.get(f'{k}|{tl}|{num}', [])
                    rows.append((f"{num}  ({tl or '-'})   " + t(
                        'picker.used', q=', '.join(f'Q_{x}' for x in qs[:6])),
                        num, tl))
        self.lst.delete(0, 'end')
        self.rows_data = []
        for row in rows:
            label, value, tl = row[:3]
            meta = row[3] if len(row) > 3 else None
            if q and q not in label.lower():
                continue
            self.rows_data.append((value, tl, meta))
            self.lst.insert('end', label)
            if meta:
                self.lst.itemconfigure('end', foreground=(
                    theme.DIM if meta.get('blocked') or meta.get('dim')
                    else theme.MOD))
            if len(self.rows_data) >= 1500:
                break
        if self.rows_data:
            self.lst.selection_set(0)
        if self.mode == 'location':
            self.note.configure(text=t('hint.location.type10'))

    def _ok(self):
        if self.mode == 'marker' and self.own.get().strip():
            try:
                num = int(self.own.get().strip())
            except ValueError:
                return
            self.result = {'value': num, 'tile': self.tile or ''}
            self.win.destroy()
            return
        if self.mode == 'tile' and not self.lst.curselection() and self.tile:
            self.result = {'value': self.tile, 'tile': self.tile}
            self.win.destroy()
            return
        sel = self.lst.curselection()
        if not sel:
            return
        value, tl, meta = self.rows_data[sel[0]]
        if meta and meta.get('blocked'):
            messagebox.showwarning(t('picker.title'), t('picker.blocked.why')
                                   + NL + NL + missing_text(meta['missing']),
                                   parent=self.win)
            return
        if meta and meta.get('mod') and self.mode == 'marker' and \
                not self.for_mod:
            name = meta['mod']['name']
            if not messagebox.askokcancel(t('picker.title'), t(
                    'mod.dep.confirm', tile=tl, mod=name), parent=self.win):
                return
            project = self.app.project
            if project is not None and len(
                    self.modset.tile_providers(tl)) > 1 and \
                    project.mod_tiles.get(tl) != name:
                project.mod_tiles[tl] = name
                self.app.mods_changed(rescan=False)
        self.tip.hide()
        self.result = {'value': value, 'tile': tl or self.tile or ''}
        self.win.destroy()
