"""Interactive map (update 5c): minimap tiles of the game, markers, locations
and chests as points, filters, search, and "use in quest".

Non-modal. The wheel zooms around the mouse, smoothly and without steps
(40 to 2048 px per tile, an eighth per notch, scaled with Pillow), shift and
the wheel scroll sideways, the buttons under the map zoom and fit the whole
map, the left mouse button drags, a click selects in the list, the right
button offers "use in quest" when the map was opened from a marker field.
The data and what is proven about positions are in ``mapdata.py``.
"""

import tkinter as tk
from tkinter import messagebox, ttk

from . import mapdata, mods, theme
from .i18n import t

NL = chr(10)
# Pixels per tile. With Pillow every size is possible (smooth scaling like
# an image viewer, a wheel notch changes the size by an eighth); without it
# Tk can only scale by whole numbers, then these steps are used.
MIN_PX, MAX_PX = 40, 2048
WHEEL_FACTOR = 1.125
BUTTON_FACTOR = 1.5
STEPS = (48, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048)
try:
    from PIL import Image, ImageTk
    SMOOTH = True
except ImportError:                         # falls back to whole numbers
    Image = ImageTk = None
    SMOOTH = False
LEVEL_PX = (512, 256, 128, 64)


def scale_of(px):
    """(level, zoom, subsample) for one tile size.

    The picture is zoomed first and subsampled afterwards (see _image), so
    the detail of the level survives. Blowing up a level costs memory and
    time, so only levels at or below the wanted size are used and the blown
    up picture stays inside a budget - a far view of 108 tiles then works
    from the small levels and stays fast."""
    budget = 2048
    for level, base in enumerate(LEVEL_PX):
        if base > px and base != LEVEL_PX[-1] and px < 384:
            continue        # far view: small levels, they are quick
        for s in (1, 2, 4, 8):
            z, rest = divmod(px * s, base)
            if rest or not 1 <= z <= 8 or base * z > budget:
                continue
            return level, z, s
    return len(LEVEL_PX) - 1, 1, 1


def tile_font(px):
    """Tile name size: small plates when zoomed out."""
    if px <= 80:
        return ('Segoe UI', 7, 'bold')
    return ('Segoe UI', 9, 'bold') if px <= 160 else ('Segoe UI', 11, 'bold')


def source_level(px):
    """Index of the minimap level to scale from: the smallest one that is
    still at least as large as the wanted size, so shrinking keeps the
    detail and growing starts from the sharpest picture there is."""
    for i in range(len(LEVEL_PX) - 1, -1, -1):
        if LEVEL_PX[i] >= px:
            return i
    return 0


DEFAULT_GROUPS = ('quest_enemy', 'quest_object', 'quest_point', 'quest_walk',
                  'quest_teleport', 'quest_clear', 'quest_kill', 'npc_start',
                  'chest', 'gate', 'teleport', 'locations', 'containers')


def confirm_mod_marker(app, parent, point):
    """Before a quest outside a mod takes a marker only that mod has: refuse
    red tiles, ask about the map going into the build, remember the mod
    when several bring the tile. True = go on."""
    info = point.get('mod')
    if info is None or app.is_mod_quest(app.quest):
        return True
    tile = point['tile']
    rec = info['tiles'].get(tile) or {}
    if rec.get('missing'):
        from .modswin import missing_text
        messagebox.showwarning(t('map.title'), t('picker.blocked.why') + NL
                               + NL + missing_text(rec['missing']),
                               parent=parent)
        return False
    if not messagebox.askokcancel(t('map.title'), t(
            'mod.dep.confirm', tile=tile, mod=info['name']), parent=parent):
        return False
    ms = app.modset
    if app.project is not None and ms and len(ms.tile_providers(tile)) > 1 \
            and app.project.mod_tiles.get(tile) != info['name']:
        app.project.mod_tiles[tile] = info['name']
        app.mods_changed(rescan=False)
    return True


class MapWindow:
    _open = None

    @classmethod
    def show(cls, app, focus=None, kind=None, on_pick=None, quest=None,
             tile=None):
        """Open (or reuse) the map. ``focus``: (name, tile, id) to center
        and blink; ``kind``: marker name to filter on; ``on_pick``:
        callback(point) for "use in quest"; ``quest``: highlight its
        markers; ``tile``: center on a tile."""
        game = app.cfg.get('game_dir')
        if not game:
            messagebox.showinfo(t('map.title'), t('export.nogame'),
                                parent=app.root)
            return None
        win = cls._open
        if win is not None:
            try:
                win.win.deiconify()
                win.win.lift()
            except tk.TclError:
                win = cls._open = None
        if win is None:
            win = cls._open = cls(app)
            if win.store is None:
                cls._open = None
                return None
        win.configure(focus, kind, on_pick, quest, tile)
        return win

    def __init__(self, app):
        self.app = app
        self.store = None
        game = app.cfg.get('game_dir')
        app.root.configure(cursor='watch')
        app.root.update_idletasks()
        try:
            self.store = mapdata.TileStore(game, mapdata.tile_cache_dir(
                app.project))
            self.store.prepare(3)
            self.store.prepare(2)
        except Exception as e:           # no archives, unreadable dds
            messagebox.showerror(t('map.title'), t('map.error', err=e),
                                 parent=app.root)
            self.store = None
            return
        finally:
            app.root.configure(cursor='')
        self.px = 64
        self.images = {}
        self._sources = {}
        self.points = []
        self.visible = []
        self.focus_keys = set()
        self.on_pick = None
        self.kind = None
        self.selected = None
        self._blink_job = None
        self._draw_job = None
        self._zoom_target = 64
        self._zoom_anchor = (None, None)
        self.zoom_lbl = None

        self.win = tk.Toplevel(app.root)
        self.win.title(t('map.title'))
        self.win.geometry('1320x840')
        self.win.minsize(900, 560)
        theme.dark_titlebar(self.win)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.win.bind('<Escape>', lambda e: self.close())
        self.win.bind('<Control-plus>', lambda e: self.zoom_step(1))
        self.win.bind('<Control-minus>', lambda e: self.zoom_step(-1))
        self.tip = theme.FloatTip(self.win)

        side = ttk.Frame(self.win, padding=(10, 8), width=250)
        side.pack(side='left', fill='y')
        right = ttk.Frame(self.win, padding=(0, 8, 10, 8), width=300)
        right.pack(side='right', fill='y')
        mid = ttk.Frame(self.win)
        mid.pack(side='left', fill='both', expand=True)

        # -- filters ------------------------------------------------------
        ttk.Label(side, text=t('map.search')).pack(anchor='w')
        self.q = tk.StringVar()
        ent = ttk.Entry(side, textvariable=self.q)
        ent.pack(fill='x', pady=(2, 8))
        ent.bind('<Return>', lambda e: self.refilter(jump=True))
        ent.bind('<KeyRelease>', lambda e: self._schedule_filter())
        self.pick_lbl = ttk.Label(side, text='', foreground=theme.GOLD,
                                  wraplength=230, justify='left')
        self.pick_lbl.pack(anchor='w')
        ttk.Label(side, text=t('map.origin'), style='Brand.TLabel'
                  ).pack(anchor='w', pady=(6, 2))
        self.src = {k: tk.BooleanVar(value=True)
                    for k in ('game', 'own', 'mods')}
        for key in ('game', 'own', 'mods'):
            ttk.Checkbutton(side, text=t('map.src.' + key),
                            variable=self.src[key],
                            command=self.refilter).pack(anchor='w')
        self.mod_box = ttk.Frame(side)
        self.mod_box.pack(anchor='w', fill='x', padx=(16, 0))
        self.mod_vars = {}
        ttk.Label(side, text=t('map.layer'), style='Brand.TLabel'
                  ).pack(anchor='w', pady=(8, 2))
        self.layer = tk.StringVar(value='surface')
        for key in ('surface', 'interior'):
            ttk.Radiobutton(side, text=t('map.layer.' + key), value=key,
                            variable=self.layer,
                            command=self.redraw_all).pack(anchor='w')
        ttk.Label(side, text=t('map.types'), style='Brand.TLabel'
                  ).pack(anchor='w', pady=(8, 2))
        self.group_vars = {}
        self.group_checks = {}
        for key in mapdata.GROUP_KEYS + list(mapdata.EXTRA_LAYERS):
            var = tk.BooleanVar(value=key in DEFAULT_GROUPS)
            row = ttk.Frame(side)
            row.pack(anchor='w', fill='x')
            dot = tk.Canvas(row, width=14, height=14, bg=theme.BG,
                            highlightthickness=0, cursor='hand2')
            if key == 'locations':
                dot.create_rectangle(3, 3, 11, 11, width=2,
                                     outline=mapdata.GROUP_COLORS[key])
            else:
                dot.create_oval(2, 2, 12, 12, outline='#000000',
                                fill=mapdata.GROUP_COLORS[key])
            dot.pack(side='left', padx=(0, 4))
            dot.bind('<Button-1>', lambda e, v=var: (v.set(not v.get()),
                                                     self.refilter()))
            cb = ttk.Checkbutton(row, text=t('map.group.' + key),
                                 variable=var, command=self.refilter)
            cb.pack(side='left')
            self.group_vars[key] = var
            self.group_checks[key] = cb
        ttk.Label(side, text=t('map.use'), style='Brand.TLabel'
                  ).pack(anchor='w', pady=(8, 2))
        self.use = tk.StringVar(value='all')
        for key in ('all', 'used', 'unused'):
            ttk.Radiobutton(side, text=t('map.use.' + key), value=key,
                            variable=self.use,
                            command=self.refilter).pack(anchor='w')
        self.labels = tk.BooleanVar(value=True)
        ttk.Checkbutton(side, text=t('map.labels'), variable=self.labels,
                        command=self.redraw_all).pack(anchor='w', pady=(8, 0))
        ttk.Label(side, text=t('map.checked') if mapdata.POSITIONS_CHECKED
                  else t('map.unchecked'), style='Muted.TLabel',
                  wraplength=230, justify='left').pack(anchor='w',
                                                       pady=(10, 0))

        # -- canvas -------------------------------------------------------
        self.c = tk.Canvas(mid, bg=theme.CANVAS_BG, highlightthickness=0)
        self.c.pack(fill='both', expand=True)
        bar = ttk.Frame(mid)
        bar.pack(fill='x', padx=6, pady=(2, 0))
        for text, cmd, key in (
                ('\u2212', lambda: self.zoom_step(-1), 'map.zoom.out'),
                ('+', lambda: self.zoom_step(1), 'map.zoom.in'),
                (t('map.zoom.fit'), self.zoom_fit, 'map.zoom.fit.tip')):
            b = ttk.Button(bar, text=text, width=3 if len(text) < 3 else 12,
                           command=cmd)
            b.pack(side='left', padx=(0, 4))
            theme.Tooltip(b, t(key))
        self.zoom_lbl = ttk.Label(bar, text='', style='Muted.TLabel')
        self.zoom_lbl.pack(side='left', padx=(6, 0))
        ttk.Label(bar, text=t('map.zoom.tip'), style='Muted.TLabel'
                  ).pack(side='right')
        self.info = ttk.Label(mid, text='', style='Muted.TLabel')
        self.info.pack(fill='x', padx=6, pady=(2, 0))
        self.c.bind('<ButtonPress-1>', self._press)
        self.c.bind('<B1-Motion>', self._drag)
        self.c.bind('<ButtonRelease-1>', self._release)
        self.c.bind('<Button-3>', self._context)
        self.c.bind('<MouseWheel>', self._wheel)
        self.c.bind('<Shift-MouseWheel>',
                    lambda e: self._wheel(e, sideways=True))
        self.c.bind('<Motion>', self._hover)
        self.c.bind('<Leave>', lambda e: self.tip.hide())
        self.c.bind('<Configure>', lambda e: self._schedule_draw())

        # -- list ---------------------------------------------------------
        self.count = ttk.Label(right, text='', style='Muted.TLabel')
        self.count.pack(anchor='w')
        box = ttk.Frame(right)
        box.pack(fill='both', expand=True, pady=(4, 0))
        cols = ('name', 'id', 'tile', 'src')
        self.tree = ttk.Treeview(box, columns=cols, show='headings',
                                 selectmode='browse')
        for col, w in zip(cols, (150, 40, 50, 70)):
            self.tree.heading(col, text=t('map.col.' + col))
            self.tree.column(col, width=w, anchor='w', stretch=col == 'name')
        self.tree.tag_configure('mod', foreground=theme.MOD)
        self.tree.tag_configure('own', foreground=theme.GOLD)
        sb = ttk.Scrollbar(box, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.tree.pack(side='left', fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self._list_select)
        self.tree.bind('<Button-3>', self._list_context)
        self.use_btn = ttk.Button(right, text=t('map.usebtn'),
                                  style='Accent.TButton',
                                  command=self._use_selected)
        self._filter_job = None
        self.reload()

    # -- data -------------------------------------------------------------

    def reload(self):
        app = self.app
        ms = app.modset
        tiles = ms.retail_tiles if ms else mods.retail_markers(
            app.cfg.get('game_dir'))
        self.points = mapdata.collect(tiles, ms, app.index, app.project)
        for w in self.mod_box.winfo_children():
            w.destroy()
        old = self.mod_vars
        self.mod_vars = {}
        for info in (ms.enabled() if ms else []):
            var = old.get(info['name']) or tk.BooleanVar(value=True)
            self.mod_vars[info['name']] = var
            ttk.Checkbutton(self.mod_box, text=theme.MOD_DOT + info['name'],
                            variable=var, command=self.refilter
                            ).pack(anchor='w')
        counts = {}
        for p in self.points:
            counts[p['group']] = counts.get(p['group'], 0) + 1
        for key, cb in self.group_checks.items():
            cb.configure(text=f"{t('map.group.' + key)}  ({counts.get(key, 0)})")
        self.refilter()

    def configure(self, focus=None, kind=None, on_pick=None, quest=None,
                  tile=None):
        self.on_pick = on_pick
        self.kind = kind
        if on_pick:
            self.pick_lbl.configure(text=t('map.pickmode', kind=kind or '-'))
            self.use_btn.pack(fill='x', pady=(6, 0))
        else:
            self.pick_lbl.configure(text='')
            self.use_btn.pack_forget()
        if kind:
            grp = mapdata.group_of(kind)
            for key, var in self.group_vars.items():
                var.set(key == grp)
            self.q.set(kind)
        self.focus_keys = set()
        if quest is not None:
            try:
                refs = mods.marker_refs(mods.quest_block(quest))
            except Exception:
                refs = []
            self.focus_keys = {(mods.MARKER_NAMES.get(k), tl, n)
                               for k, tl, n in refs}
            for s in quest.speakers:
                if s.get('tile') and s['tile'] != '(null)' and isinstance(
                        s.get('id'), int):
                    self.focus_keys.add((mods.NPC_MARKER, s['tile'].upper(),
                                         s.get('marker') or s['id']))
            for name, tl, _n in self.focus_keys:
                grp = mapdata.group_of(name)
                if grp in self.group_vars:
                    self.group_vars[grp].set(True)
            self.q.set('')
        self.reload()
        if focus:
            self.show_point(*focus)
        elif quest is not None and self.focus_keys:
            self.fit_points([p for p in self.points if self._key(p)
                             in self.focus_keys])
        elif tile:
            self.center_tile(tile)
        else:
            self.redraw_all()
            self.win.update_idletasks()
            w, h = self.world_size()
            self.center_on(w / 2, h / 2)
            self._draw_points()

    @staticmethod
    def _key(p):
        return (p['name'], p['tile'], p['id'])

    def _interior(self, tile):
        s = mapdata.split_tile(tile)
        return bool(s and s[2])

    def _schedule_filter(self):
        if self._filter_job:
            self.win.after_cancel(self._filter_job)
        self._filter_job = self.win.after(250, self.refilter)

    def refilter(self, jump=False):
        self._filter_job = None
        q = self.q.get().strip().lower()
        interior = self.layer.get() == 'interior'
        use = self.use.get()
        groups = {k for k, v in self.group_vars.items() if v.get()}
        src = {k: v.get() for k, v in self.src.items()}
        mods_off = {k for k, v in self.mod_vars.items() if not v.get()}
        shown = []
        for p in self.points:
            if p['group'] not in groups:
                continue
            if self._interior(p['tile']) != interior:
                continue
            if p['mod'] is not None:
                if not src['mods'] or p['mod']['name'] in mods_off:
                    continue
            elif p['own']:
                if not src['own']:
                    continue
            elif not src['game']:
                continue
            if use == 'used' and not p['used']:
                continue
            if use == 'unused' and p['used']:
                continue
            if q and q not in (f"{p['name']} {p.get('label', '')} "
                               f"{p['id']} {p['tile']}".lower()):
                continue
            shown.append(p)
        self.visible = shown
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(shown[:3000]):
            tag = 'mod' if p['mod'] else ('own' if p['own'] else '')
            src = p['mod']['name'] if p['mod'] else (
                t('map.src.own') if p['own'] else t('map.src.game'))
            name = p.get('label') or p['name']
            self.tree.insert('', 'end', iid=str(i), values=(
                (theme.MOD_DOT if p['mod'] else '') + name,
                '' if p['id'] is None else p['id'], p['tile'], src),
                tags=(tag,))
        self.count.configure(text=t('map.count', n=len(shown),
                                    all=len(self.points)))
        self._draw_points()
        if jump and q and shown:
            self.select_index(0, center=True)

    # -- drawing ----------------------------------------------------------

    def redraw_all(self):
        self.c.delete('tile')
        self.refilter()
        self._draw_tiles()

    def _schedule_draw(self):
        if self._draw_job:
            self.win.after_cancel(self._draw_job)
        self._draw_job = self.win.after_idle(self._redraw_view)

    def _redraw_view(self):
        self._clamp_view()
        self._draw_tiles()
        self._draw_points()

    def _clamp_view(self):
        """Back into the frame after dragging: an axis that fits stays in
        the middle, a larger world does not scroll past its edge."""
        c = self.c
        self._scroll_to(c.canvasx(0), c.canvasy(0))

    def _source(self, tile, level):
        """Decoded minimap of one level (PIL), cached."""
        src = self._sources.get((tile, level))
        if src is None:
            path = self.store.png(tile, level)
            if not path:
                return None
            src = Image.open(path).convert('RGB')
            src.load()
            self._sources[(tile, level)] = src
        return src

    def _image(self, tile, px):
        key = (tile, px)
        img = self.images.get(key)
        if img is not None:
            return img
        if SMOOTH:
            level = source_level(px)
            src = None
            while src is None and level < len(LEVEL_PX):
                src = self._source(tile, level)
                level += 1
            if src is None:
                return None
            if src.size != (px, px):
                # shrinking looks better with a proper filter, growing is
                # cheap and bilinear is enough
                src = src.resize((px, px), Image.LANCZOS
                                 if px < src.size[0] else Image.BILINEAR)
            img = ImageTk.PhotoImage(src)
            self.images[key] = img
            return img
        level, z, s = scale_of(px)
        path = self.store.png(tile, level)
        while path is None and level < len(LEVEL_PX) - 1:
            level += 1                     # tile missing on that level
            path = self.store.png(tile, level)
            z, s = px * s // LEVEL_PX[level] or 1, s
        if not path:
            return None
        img = tk.PhotoImage(file=path)
        if z != 1:
            img = img.zoom(z, z)
        if s != 1:
            out = tk.PhotoImage(width=px, height=px)
            out.tk.call(out, 'copy', img, '-subsample', s, s)
            img = out
        self.images[key] = img
        return img

    def world_size(self):
        return len(mapdata.COLS) * self.px, mapdata.ROWS * self.px

    def _set_region(self):
        """Scroll region around the world. Is the world smaller than the
        canvas, the same padding is put on both sides so it sits in the
        middle instead of the top left corner."""
        c = self.c
        w, h = self.world_size()
        cw, ch = c.winfo_width(), c.winfo_height()
        px_pad = max(0, (cw - w) / 2)
        py_pad = max(0, (ch - h) / 2)
        c.configure(scrollregion=(-px_pad, -py_pad, w + px_pad, h + py_pad))
        return px_pad, py_pad

    def _draw_tiles(self):
        self._draw_job = None
        c = self.c
        px = self.px
        self._set_region()
        for key in [k for k in self.images if k[1] != px]:
            del self.images[key]
        x0, y0 = c.canvasx(0), c.canvasy(0)
        x1, y1 = x0 + c.winfo_width(), y0 + c.winfo_height()
        interior = self.layer.get() == 'interior'
        # the old tiles stay until the new ones are there, otherwise the
        # canvas is black for a moment on every zoom step
        new = 'tile_new'
        for ci, col in enumerate(mapdata.COLS):
            for row in range(1, mapdata.ROWS + 1):
                tx, ty = ci * px, (row - 1) * px
                if tx + px < x0 or tx > x1 or ty + px < y0 or ty > y1:
                    continue
                tile = f'{col}{row}'
                img = self._image(tile, px)
                if img is not None:
                    c.create_image(tx, ty, image=img, anchor='nw',
                                   tags=(new,))
                if interior:
                    inner = f'{tile}_1'
                    if self.store.has(inner, scale_of(px)[0]):
                        c.create_image(tx, ty, image=self._image(inner, px),
                                       anchor='nw', tags=(new,))
                    else:
                        c.create_rectangle(tx, ty, tx + px, ty + px,
                                           fill='#000000', stipple='gray75',
                                           outline='', tags=(new,))
                c.create_rectangle(tx, ty, tx + px, ty + px,
                                   outline=theme.mix(theme.LINE, '#000000',
                                                     0.8),
                                   tags=(new,))
                if self.labels.get():
                    # light parchment map: white text on a dark plate
                    small = px <= 80
                    txt = c.create_text(
                        tx + (4 if small else 8), ty + (3 if small else 5),
                        anchor='nw', text=tile, fill='#ffffff',
                        font=tile_font(px),
                        tags=(new,))
                    bx0, by0, bx1, by1 = c.bbox(txt)
                    pad = 2 if small else 4
                    plate = c.create_rectangle(
                        bx0 - pad, by0 - 1, bx1 + pad, by1 + 1, fill=theme.BG,
                        outline=theme.GOLD, tags=(new,))
                    c.tag_lower(plate, txt)
        c.delete('tile')
        for item in c.find_withtag(new):
            c.addtag_withtag('tile', item)
        c.dtag(new, new)
        c.tag_lower('tile')
        # keep memory bounded when panning at high zoom (a tile costs
        # px * px * 4 bytes in Tk, so 512 px and up are pruned hard)
        if len(self._sources) > 160:
            self._sources.clear()
        if len(self.images) > (8 if px >= 512 else 48):
            shown = {c.itemcget(i, 'image') for i in c.find_withtag('tile')
                     if c.type(i) == 'image'}
            for key in [k for k, img in self.images.items()
                        if str(img) not in shown]:
                del self.images[key]

    def _draw_points(self):
        c = self.c
        c.delete('pt')
        px = self.px
        r = 4 if px <= 64 else (5 if px <= 256 else 6)
        dim = bool(self.focus_keys)
        for i, p in enumerate(self.visible):
            pos = mapdata.world_to_map(p['tile'], p['x'], p['y'], px)
            if pos is None:
                continue
            x, y = pos
            colour = mapdata.GROUP_COLORS.get(p['group'], '#8a8a8a')
            # the source shows as a ring: mods blue, own quests gold
            if p['mod'] is not None:
                ring, width = theme.MOD, 2
            elif p['own']:
                ring, width = theme.GOLD, 2
            else:
                ring, width = '#000000', 1
            rr = r
            if dim:
                if self._key(p) in self.focus_keys:
                    rr = r + 3
                    ring, width = theme.GOLD_HI, 2
                else:
                    colour = theme.mix(colour, '#000000', 0.45)
            if p['group'] == 'locations':
                c.create_rectangle(x - rr, y - rr, x + rr, y + rr,
                                   outline=colour, width=2,
                                   tags=('pt', f'p:{i}'))
            else:
                c.create_oval(x - rr, y - rr, x + rr, y + rr, fill=colour,
                              outline=ring, width=width,
                              tags=('pt', f'p:{i}'))
        self._draw_selection()

    def _draw_selection(self):
        c = self.c
        c.delete('sel')
        p = self.selected
        if p is None:
            return
        pos = mapdata.world_to_map(p['tile'], p['x'], p['y'], self.px)
        if pos is None:
            return
        x, y = pos
        c.create_oval(x - 12, y - 12, x + 12, y + 12, outline=theme.GOLD_HI,
                      width=2, tags=('sel',))

    # -- navigation -------------------------------------------------------

    def _press(self, ev):
        self._moved = False
        self._start = (ev.x, ev.y)
        self.c.scan_mark(ev.x, ev.y)

    def _drag(self, ev):
        if abs(ev.x - self._start[0]) + abs(ev.y - self._start[1]) > 3:
            self._moved = True
        self.c.scan_dragto(ev.x, ev.y, gain=1)
        self._schedule_draw()

    def _release(self, ev):
        if getattr(self, '_moved', False):
            self._clamp_view()
            return
        i = self._point_at(ev)
        if i is not None:
            self.select_index(i, center=False)

    def _wheel(self, ev, sideways=False):
        """Wheel zooms around the mouse, shift scrolls sideways."""
        if sideways:
            self.c.xview_scroll(-1 if ev.delta > 0 else 1, 'units')
            self._schedule_draw()
            return 'break'
        self.zoom_step(1 if ev.delta > 0 else -1, ev.x, ev.y,
                       factor=WHEEL_FACTOR)
        return 'break'

    def zoom_step(self, direction, sx=None, sy=None, factor=None):
        """One notch: a free factor with Pillow, else the next step."""
        # build on a step that is still waiting, so notches add up
        base = self._zoom_target if self._draw_job else self.px
        if SMOOTH:
            f = factor or BUTTON_FACTOR
            px = base * (f if direction > 0 else 1 / f)
            px = int(max(MIN_PX, min(MAX_PX, round(px))))
            if px == base:
                px += direction
            if not MIN_PX <= px <= MAX_PX:
                return
        else:
            near = min(range(len(STEPS)),
                       key=lambda i: abs(STEPS[i] - base))
            step = near + direction
            if not 0 <= step < len(STEPS):
                return
            px = STEPS[step]
        self.zoom_to(px, sx, sy, smooth=True)

    def zoom_fit(self):
        """Whole map into the window."""
        c = self.c
        fit = min(c.winfo_width() / len(mapdata.COLS),
                  c.winfo_height() / mapdata.ROWS)
        if SMOOTH:
            px = int(max(MIN_PX, min(MAX_PX, fit)))
        else:
            px = max([s for s in STEPS if s <= fit] or [STEPS[0]])
        self.zoom_to(px)

    def zoom_to(self, px, sx=None, sy=None, smooth=False):
        """Scroll and redraw happen in ONE go. Scrolling first and drawing
        later let the canvas paint the old tiles at the new place for a
        moment (a visible jump), because its own repaint sits in the idle
        queue before a redraw scheduled afterwards. With ``smooth`` the
        whole step waits for the idle queue, so a fast turn of the wheel
        collapses into one step; the target size is kept in _zoom_target
        so every notch builds on the last one."""
        self._zoom_target = px
        if smooth:
            self._zoom_anchor = (sx, sy)
            if self._draw_job:
                self.win.after_cancel(self._draw_job)
            self._draw_job = self.win.after_idle(self._apply_zoom)
        else:
            self._zoom_anchor = (sx, sy)
            self._apply_zoom()

    def _apply_zoom(self):
        self._draw_job = None
        px = self._zoom_target
        sx, sy = self._zoom_anchor
        c = self.c
        w, h = len(mapdata.COLS) * px, mapdata.ROWS * px
        if sx is None or w <= c.winfo_width() or h <= c.winfo_height():
            # a map that fits sits in the middle anyway: zoom around the
            # centre, so the picture does not jump sideways
            sx, sy = c.winfo_width() / 2, c.winfo_height() / 2
        mx = (c.canvasx(sx)) / self.px
        my = (c.canvasy(sy)) / self.px
        self.px = px
        self._set_region()
        self._scroll_to(mx * px - sx, my * px - sy)
        if self.zoom_lbl is not None:
            self.zoom_lbl.configure(text=t('map.zoom.now', px=px))
        self._draw_tiles()
        self._draw_points()

    def _scroll_to(self, left, top):
        c = self.c
        w, h = self.world_size()
        px_pad, py_pad = self._set_region()
        total_w, total_h = w + 2 * px_pad, h + 2 * py_pad
        left = 0 if px_pad else max(0.0, min(left, w - c.winfo_width()))
        top = 0 if py_pad else max(0.0, min(top, h - c.winfo_height()))
        c.xview_moveto((left + px_pad) / total_w)
        c.yview_moveto((top + py_pad) / total_h)

    def center_on(self, mx, my):
        c = self.c
        self._scroll_to(mx - c.winfo_width() / 2, my - c.winfo_height() / 2)
        self._draw_tiles()

    def center_tile(self, tile):
        s = mapdata.split_tile(tile)
        if s is None:
            return
        if self.px < 256:
            self.px = 256
        if s[2]:
            self.layer.set('interior')
        self.redraw_all()
        self.win.update_idletasks()
        self.center_on((s[0] + 0.5) * self.px, (s[1] - 0.5) * self.px)
        self._draw_points()

    def fit_points(self, pts):
        if not pts:
            self.redraw_all()
            return
        xs, ys = [], []
        for p in pts:
            x, y = mapdata.world_to_map(p['tile'], p['x'], p['y'], 1)
            xs.append(x)
            ys.append(y)
        self.win.update_idletasks()
        span = max(max(xs) - min(xs), max(ys) - min(ys), 0.3)
        view = min(self.c.winfo_width(), self.c.winfo_height()) or 600
        px = STEPS[0]
        for s in STEPS:
            if span * s <= view * 0.8:
                px = s
        self.px = px
        if any(self._interior(p['tile']) for p in pts):
            self.layer.set('interior')
        self.redraw_all()
        self.center_on((min(xs) + max(xs)) / 2 * px,
                       (min(ys) + max(ys)) / 2 * px)
        self._draw_points()

    def show_point(self, name, tile, ident):
        """Center, zoom and blink one marker (``Show in map``)."""
        grp = mapdata.group_of(name) if name else None
        if grp in self.group_vars:
            self.group_vars[grp].set(True)
        s = mapdata.split_tile(tile)
        if s is not None:
            self.layer.set('interior' if s[2] else 'surface')
        self.q.set('')
        self.refilter()
        for i, p in enumerate(self.visible):
            if p['name'] == name and p['tile'] == tile and (
                    ident is None or p['id'] == ident):
                self.px = max(self.px, 512)
                self.redraw_all()
                self.select_index(i, center=True)
                self.blink(p)
                return True
        self.center_tile(tile)
        self.info.configure(text=t('map.notfound', name=name, id=ident,
                                   tile=tile))
        return False

    def blink(self, p, n=6):
        if self._blink_job:
            self.win.after_cancel(self._blink_job)
        pos = mapdata.world_to_map(p['tile'], p['x'], p['y'], self.px)
        if pos is None:
            return
        x, y = pos

        def step(k):
            self.c.delete('blink')
            if k <= 0:
                self._blink_job = None
                return
            if k % 2:
                self.c.create_oval(x - 16, y - 16, x + 16, y + 16,
                                   outline=theme.ERR, width=3,
                                   tags=('blink',))
            self._blink_job = self.win.after(220, lambda: step(k - 1))
        step(n)

    # -- selection and hover ----------------------------------------------

    def _point_at(self, ev):
        x, y = self.c.canvasx(ev.x), self.c.canvasy(ev.y)
        for item in reversed(self.c.find_overlapping(x - 4, y - 4, x + 4,
                                                     y + 4)):
            for tg in self.c.gettags(item):
                if tg.startswith('p:'):
                    return int(tg[2:])
        return None

    def describe(self, p):
        lines = [p.get('label') or p['name']]
        if p.get('label'):
            lines.append(p['name'])
        lines.append(t('map.tip.group', group=t('map.group.' + p['group'])))
        if p['id'] is not None:
            lines.append(t('map.tip.id', id=p['id']))
        lines.append(t('map.tip.pos', tile=p['tile'], x=p['x'], y=p['y']))
        if p['mod'] is not None:
            rec = p['mod']['tiles'].get(p['tile']) or {}
            lines.append(t('mod.origin', mod=p['mod']['name']) + ' - '
                         + t('mod.origin.file', file=rec.get('inner')
                             or p['mod'].get('qtx') or '-'))
        else:
            lines.append(t('map.tip.game'))
        lines.append(t('map.tip.used') if p['used'] else t('map.tip.unused'))
        return NL.join(lines)

    def _hover(self, ev):
        i = self._point_at(ev)
        mx, my = self.c.canvasx(ev.x), self.c.canvasy(ev.y)
        where = mapdata.map_to_world(mx, my, self.px)
        self.info.configure(text=t('map.cursor', tile=where[0], x=where[1],
                                   y=where[2]) if where else '')
        if i is None or i >= len(self.visible):
            self.tip.hide()
            return
        self.tip.show(self.describe(self.visible[i]), ev.x_root, ev.y_root)

    def select_index(self, i, center=False):
        if not 0 <= i < len(self.visible):
            return
        self.selected = p = self.visible[i]
        iid = str(i)
        self._sel_iid = iid
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)
        if center:
            pos = mapdata.world_to_map(p['tile'], p['x'], p['y'], self.px)
            self.center_on(*pos)
            self._draw_points()
        else:
            self._draw_selection()
        self.info.configure(text=self.describe(p).replace(NL, '   '))

    def _list_select(self, ev=None):
        sel = self.tree.selection()
        if sel and sel[0] != getattr(self, '_sel_iid', None):
            i = int(sel[0])
            if self.px < 256:
                self.px = 256
                self._draw_tiles()
            self.select_index(i, center=True)

    # -- use in quest ------------------------------------------------------

    def _use(self, p):
        if not self.on_pick or p is None:
            return
        if p['group'] in ('locations',):
            return
        if self.kind and p['name'] != self.kind:
            if not messagebox.askyesno(t('map.title'), t(
                    'map.wrongkind', name=p['name'], kind=self.kind),
                    icon='warning', parent=self.win):
                return
        cb = self.on_pick
        self.on_pick = None
        self.pick_lbl.configure(text='')
        self.use_btn.pack_forget()
        cb(p)

    def _use_selected(self):
        self._use(self.selected)

    def _context(self, ev):
        i = self._point_at(ev)
        if i is None:
            return
        self.select_index(i)
        self._menu(ev, self.visible[i])

    def _list_context(self, ev):
        iid = self.tree.identify_row(ev.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        self._menu(ev, self.visible[int(iid)])

    def _menu(self, ev, p):
        menu = theme.Menu(self.win, tearoff=0)
        can = self.on_pick is not None and p['group'] != 'locations'
        menu.add_command(label=t('map.usebtn'),
                         command=lambda: self._use(p),
                         state='normal' if can else 'disabled')
        menu.add_command(label=t('map.center'),
                         command=lambda: (self.select_index(
                             self.visible.index(p), center=True),
                             self.blink(p)))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def close(self):
        MapWindow._open = None
        self._sources.clear()
        self.tip.hide()
        self.images.clear()
        self.win.destroy()
