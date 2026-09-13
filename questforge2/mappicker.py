"""Tile picker (plan section 7): a grid of map tiles as a filter for ids.

Modes: 'npc', 'location', 'object', 'tile', 'marker' (with a marker kind).
The tile grid is derived from the tile names in the index (NPC, LOCATION
and marker usage); outdoor tiles like ``F5`` form the grid, interiors like
``B8_1`` are listed below it. There is no map image (game data).
Result: ``{'value': str|int, 'tile': str}`` or None.
"""

import re
import tkinter as tk
from tkinter import ttk

from . import theme
from .i18n import t

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
        for key, nums in idx.markers.items():
            k, tl = key.split('|')
            self._count(tl, 2, len(nums))
        tiles = [tl for tl in idx.tiles if tl and tl != '(null)']
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
            self.note.configure(text=t('picker.lnd') + '  '
                                + t('field.reads', kind=kind))
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
        elif self.mode == 'location':
            for key, loc in sorted(idx.locations.items()):
                if tile and loc['tile'] != tile:
                    continue
                warn = '  !' if loc['type'] == 10 and loc['radius'] == 0 else ''
                rows.append((f"{loc['name']}  ({key}, {loc['tile']}, Typ "
                             f"{loc['type']}, r {loc['radius']}){warn}", key,
                             loc['tile']))
        elif self.mode == 'object':
            names = idx.object_names
            for obj in idx.objects:
                rows.append((f'{names.get(obj) or obj}  ({obj})', obj, None))
        elif self.mode == 'tile':
            for tl in idx.tiles:
                n, l, m = self.counts.get(tl, [0, 0, 0])
                rows.append((t('picker.counts', t=tl, n=n, l=l, m=m), tl, tl))
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
        for label, value, tl in rows:
            if q and q not in label.lower():
                continue
            self.rows_data.append((value, tl))
            self.lst.insert('end', label)
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
        value, tl = self.rows_data[sel[0]]
        self.result = {'value': value, 'tile': tl or self.tile or ''}
        self.win.destroy()
