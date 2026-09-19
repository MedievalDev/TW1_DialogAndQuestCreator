"""Place markers on the map (3.9.0, Marco's design 2026-09-19).

The map without the existing markers (they only confuse here) and a list of
the markers to place on the left. Click a marker in the list: it hangs at
the mouse. Click on the map: it is set there and its row turns green with a
tick. Click a green row again: the marker is lifted, the row turns black
and the marker hangs at the mouse again. Esc or the right mouse button
puts the hanging marker back. The green button at the bottom left
confirms.

The tile comes from the click; the height from the heightmap of that tile
(lndmap.Terrain, measured to hit 97.5 % of the game's markers within 16
units); ground the passable field marks as blocked (trees, rocks, walls)
is tinted red when zoomed in and asks before a marker goes there.
Interiors are not on this map, so nothing lands in a room with two floors.

``targets``: [{'key', 'name' (engine name), 'label', 'num' (fixed number,
e.g. the NPC number of a giver, else None), 'placed' ({'tile', 'x', 'y',
'z', 'num'} or None), 'tile' (suggested tile)}]. ``on_done(targets)`` gets
the list back with 'placed' filled in.
"""

import tkinter as tk
from tkinter import messagebox, ttk

from . import mapdata, mods, placed, theme
from .i18n import t
from .mapwin import SMOOTH, MapWindow

if SMOOTH:
    from PIL import Image, ImageTk

NL = chr(10)
OVERLAY_FROM_PX = 256          # blocked tint only when a few tiles show
TINT_PX = 512                  # the tinted tile is made once at this size


_T0 = bytes(0 if b & 1 else 120 for b in range(256))
_T4 = bytes(0 if b & 16 else 120 for b in range(256))


def _mask_image(ter):
    """Blocked ground as an 'L' image 256 x 256, north up, 120 where
    blocked - the same samples as lndmap.Terrain.blocked_mask(256) (bit 0
    of every 4th row and column), read straight from the bytes of the
    passable field: 0.2 ms instead of 20 ms a tile."""
    if ter.pass_per_row == 32 and len(ter.pass_raw) == 1024 * 128:
        raw, out = ter.pass_raw, bytearray(65536)
        for r in range(256):
            row = raw[r * 512:r * 512 + 128]
            o = (255 - r) * 256
            out[o:o + 256:2] = row.translate(_T0)
            out[o + 1:o + 256:2] = row.translate(_T4)
        return Image.frombytes('L', (256, 256), bytes(out))
    return Image.frombytes('L', (256, 256), bytes(
        120 * v for v in ter.blocked_mask(256))).transpose(
            Image.FLIP_TOP_BOTTOM)


class PlaceWindow(MapWindow):

    def __init__(self, app, targets, on_done, title=None):
        # no MapWindow.__init__: this window has its own side panel and no
        # filters; only the drawing, zoom and drag are shared
        self.app = app
        self.targets = targets
        self.on_done = on_done
        self.store = None
        self.game = app.cfg.get('game_dir')
        try:
            self.store = mapdata.TileStore(self.game, mapdata.tile_cache_dir(
                app.project))
            self.store.prepare(3)
            self.store.prepare(2)
        except Exception as e:
            messagebox.showerror(t('map.title'), t('map.error', err=e),
                                 parent=app.root)
            return
        self.px = 128
        self.images, self._sources, self._terrain, self._bases = {}, {}, {}, {}
        self._masks = {}
        self._tinted = {}
        self.points, self.visible, self.focus_keys = [], [], set()
        self.selected = self.on_pick = self.kind = None
        self._blink_job = self._draw_job = None
        self._zoom_target, self._zoom_anchor = self.px, (None, None)
        self.held = None                  # target hanging at the mouse
        self.changed = False
        self.win = tk.Toplevel(app.root)
        self.win.title(title or t('place.title'))
        self.win.geometry('1280x820')
        self.win.minsize(900, 560)
        self.win.transient(app.root)
        theme.dark_titlebar(self.win)
        self.win.protocol('WM_DELETE_WINDOW', self.cancel)
        self.win.bind('<Escape>', lambda e: self._drop())
        self.tip = theme.FloatTip(self.win)
        self.labels = tk.BooleanVar(value=True)
        self.layer = tk.StringVar(value='surface')
        self.tint = tk.BooleanVar(value=True)

        side = ttk.Frame(self.win, padding=(10, 8), width=300)
        side.pack(side='left', fill='y')
        mid = ttk.Frame(self.win)
        mid.pack(side='left', fill='both', expand=True)
        ttk.Label(side, text=t('place.head'), style='Brand.TLabel'
                  ).pack(anchor='w')
        ttk.Label(side, text=t('place.hint'), style='Muted.TLabel',
                  wraplength=280, justify='left').pack(anchor='w', pady=(2, 8))
        self.rows_box = ttk.Frame(side)
        self.rows_box.pack(fill='x')
        ttk.Checkbutton(side, text=t('place.tint'), variable=self.tint,
                        command=self._retint).pack(anchor='w', pady=(10, 0))
        self.status = ttk.Label(side, text='', style='Muted.TLabel',
                                wraplength=280, justify='left')
        self.status.pack(anchor='w', pady=(8, 0))
        bottom = ttk.Frame(side)
        bottom.pack(side='bottom', fill='x')
        style = ttk.Style(self.win)
        style.configure('Confirm.TButton', background=theme.OK,
                        foreground='#0b1a0f', font=theme.FONT_BOLD)
        style.map('Confirm.TButton',
                  background=[('active', theme.mix(theme.OK, '#ffffff', 0.2)),
                              ('disabled', theme.MUT)])
        self.ok_btn = ttk.Button(bottom, text='✓ ' + t('place.confirm'),
                                 style='Confirm.TButton', command=self.confirm)
        self.ok_btn.pack(side='left')
        ttk.Button(bottom, text=t('cancel'), command=self.cancel
                   ).pack(side='right')

        self.c = tk.Canvas(mid, bg=theme.CANVAS_BG, highlightthickness=0,
                           cursor='crosshair')
        self.c.pack(fill='both', expand=True)
        bar = ttk.Frame(mid)
        bar.pack(fill='x', padx=6, pady=(2, 0))
        for text, cmd in (('−', lambda: self.zoom_step(-1)),
                          ('+', lambda: self.zoom_step(1)),
                          (t('map.zoom.fit'), self.zoom_fit)):
            ttk.Button(bar, text=text, width=3 if len(text) < 3 else 12,
                       command=cmd).pack(side='left', padx=(0, 4))
        self.zoom_lbl = ttk.Label(bar, text='', style='Muted.TLabel')
        self.zoom_lbl.pack(side='left', padx=(6, 0))
        self.info = ttk.Label(mid, text='', style='Muted.TLabel')
        self.info.pack(fill='x', padx=6, pady=(2, 0))
        self.c.bind('<ButtonPress-1>', self._press)
        self.c.bind('<B1-Motion>', self._drag)
        self.c.bind('<ButtonRelease-1>', self._release)
        self.c.bind('<Button-3>', lambda e: self._drop())
        self.c.bind('<MouseWheel>', self._wheel)
        self.c.bind('<Shift-MouseWheel>',
                    lambda e: self._wheel(e, sideways=True))
        self.c.bind('<Motion>', self._hover)
        self.c.bind('<Configure>', lambda e: self._schedule_draw())
        self._rows()
        self.win.update_idletasks()
        self._start_view()
        self.win.grab_set()

    # -- list -------------------------------------------------------------

    def _rows(self):
        for w in self.rows_box.winfo_children():
            w.destroy()
        for tg in self.targets:
            done = tg.get('placed') is not None
            hanging = self.held is tg
            row = tk.Frame(self.rows_box, bg=theme.PANEL, cursor='hand2',
                           highlightthickness=1,
                           highlightbackground=theme.GOLD_HI if hanging
                           else theme.LINE)
            row.pack(fill='x', pady=2)
            mark = tk.Label(row, text='✓' if done else '○',
                            width=2, bg=theme.OK if done else theme.PANEL,
                            fg='#0b1a0f' if done else theme.INK,
                            font=theme.FONT_BOLD)
            mark.pack(side='left', fill='y')
            dot = tk.Canvas(row, width=14, height=14, bg=theme.PANEL,
                            highlightthickness=0)
            dot.create_oval(2, 2, 12, 12, outline='#000000',
                            fill=self._colour(tg['name']))
            dot.pack(side='left', padx=(4, 4))
            num = (tg['placed'] or {}).get('num', tg.get('num'))
            text = mods.editor_name(tg['name']) + (
                f' {num}' if num is not None else '')
            where = (t('place.on', tile=tg['placed']['tile'])
                     if done else t('place.open'))
            lbl = tk.Label(row, text=f'{text}\n{tg.get("label") or ""}  '
                                     f'{where}',
                           justify='left', anchor='w', bg=theme.PANEL,
                           fg=theme.OK if done else theme.INK,
                           font=theme.FONT)
            lbl.pack(side='left', fill='x', expand=True, padx=(0, 4), pady=2)
            for w in (row, mark, dot, lbl):
                w.bind('<Button-1>', lambda e, g=tg: self._pick(g))
        n = sum(1 for tg in self.targets if tg.get('placed') is not None)
        self.status.configure(text=t('place.count', n=n,
                                     total=len(self.targets)))

    @staticmethod
    def _colour(name):
        return mapdata.GROUP_COLORS.get(mapdata.group_of(name), '#cccccc')

    def _pick(self, tg):
        """Take a marker from the list (lifts a placed one again)."""
        if self.held is not None and self.held is not tg:
            self._drop()                     # the lifted one back first
        if tg.get('placed') is not None:
            tg['_prev'] = tg['placed']       # same tile keeps its number
            tg['placed'] = None
            self.changed = True
        self.held = tg
        self._rows()
        self._draw_points()

    def _drop(self):
        tg = self.held
        prev = (tg or {}).get('_prev') or {}
        if tg is not None and tg.get('placed') is None and \
                prev.get('x') is not None:
            tg['placed'] = prev          # lifted by mistake: back in place
            self._draw_points()
        self._drop_hand()

    def _drop_hand(self):
        """The hanging marker goes back unplaced (Esc, right click)."""
        self.held = None
        self.c.delete('ghost')
        self._rows()

    # -- terrain -----------------------------------------------------------

    def _base(self, tile):
        """(marker head of the tile as generate() will write it, source).
        Only the head is kept: the whole map is 4 MB a tile."""
        if tile not in self._bases:
            body, _phx, src = placed.base_of(self.app.project,
                                             self.app.modset, self.game, tile)
            if body:
                try:
                    self._terrain[tile] = placed.lndmap.Terrain(body)
                except Exception:            # a map we cannot read
                    self._terrain[tile] = None
                # the game markers generate() puts back count for numbers
                retail = placed.retail_body(self.game, self.app.modset, tile)
                if retail:
                    body = placed.build_body(body, retail, [])[0]
                body = placed.marker_head(body)
            self._bases[tile] = (body, src)
        return self._bases[tile]

    def terrain(self, tile):
        if tile not in self._terrain:
            self._base(tile)                 # reads the map once
            self._terrain.setdefault(tile, None)
        return self._terrain[tile]

    def _image(self, tile, px):
        img = self.images.get((tile, px))
        if img is not None:
            return img
        if not SMOOTH or not self.tint.get() or px < OVERLAY_FROM_PX:
            return super()._image(tile, px)
        mask = self._mask(tile)
        if mask is None:
            return super()._image(tile, px)
        tinted = self._tinted.get(tile)
        if tinted is None:
            pil = self._pil_tile(tile, TINT_PX)
            if pil is None:
                return None
            red = Image.new('RGB', (TINT_PX, TINT_PX), (200, 40, 30))
            tinted = Image.composite(red, pil, mask.resize(
                (TINT_PX, TINT_PX), Image.NEAREST))
            if len(self._tinted) >= 32:          # 0.75 MB a tile
                self._tinted.pop(next(iter(self._tinted)))
            self._tinted[tile] = tinted
        if px != TINT_PX:
            tinted = tinted.resize((px, px), Image.LANCZOS
                                   if px < TINT_PX else Image.BILINEAR)
        img = ImageTk.PhotoImage(tinted)
        self.images[(tile, px)] = img
        return img

    def _mask(self, tile):
        """Blocked ground of a tile as a PIL mask (map orientation: north
        up, so world y = 0 is the bottom row), cached."""
        if tile not in self._masks:
            ter = self.terrain(tile)
            if ter is None or not ter.pass_per_row:
                self._masks[tile] = None
            else:
                self._masks[tile] = _mask_image(ter)
        return self._masks[tile]

    def _retint(self):
        self._tiles_view = None
        self.images.clear()
        self._draw_tiles()
        self._draw_points()

    # -- drawing ------------------------------------------------------------

    def redraw_all(self):
        self._draw_tiles()
        self._draw_points()

    def _draw_points(self):
        c = self.c
        c.delete('pt')
        r = 6 if self.px < 256 else 8
        for tg in self.targets:
            p = tg.get('placed')
            if not p:
                continue
            pos = mapdata.world_to_map(p['tile'], p['x'], p['y'], self.px)
            if pos is None:
                continue
            x, y = pos
            c.create_oval(x - r, y - r, x + r, y + r,
                          fill=self._colour(tg['name']), outline='#000000',
                          width=2, tags=('pt',))
            c.create_text(x + r + 3, y, anchor='w', fill='#ffffff',
                          font=theme.FONT_BOLD, tags=('pt',),
                          text=f"{mods.editor_name(tg['name'])} {p['num']}")

    def _start_view(self):
        done = [tg['placed'] for tg in self.targets if tg.get('placed')]
        tile = (done[0]['tile'] if done else
                next((tg.get('tile') for tg in self.targets
                      if tg.get('tile')), None))
        tile = (tile or '').split('_')[0]
        if tile and mapdata.split_tile(tile):
            self.px = 256
            self._zoom_target = 256
            self.center_tile(tile)
        else:
            self.zoom_fit()

    # -- mouse -----------------------------------------------------------------

    def _where(self, ev):
        mx, my = self.c.canvasx(ev.x), self.c.canvasy(ev.y)
        return mapdata.map_to_world(mx, my, self.px)

    def _hover(self, ev):
        where = self._where(ev)
        if not where:
            self.info.configure(text='')
            self.c.delete('ghost')
            return
        tile, x, y = where
        ter = self.terrain(tile) if self.px >= OVERLAY_FROM_PX or \
            self.held else None
        extra = ''
        if ter is not None:
            ok = ter.passable(x, y)
            extra = '  ' + t('place.height', z=ter.height(x, y)) + '  ' + (
                t('place.free') if ok or ok is None else t('place.blocked'))
        self.info.configure(text=t('map.cursor', tile=tile, x=x, y=y) + extra)
        self.c.delete('ghost')
        if self.held is not None:
            gx, gy = self.c.canvasx(ev.x), self.c.canvasy(ev.y)
            r = 8
            self.c.create_oval(gx - r, gy - r, gx + r, gy + r,
                               fill=self._colour(self.held['name']),
                               outline=theme.GOLD_HI, width=2, tags=('ghost',))
            self.c.create_text(gx + r + 4, gy, anchor='w', fill='#ffffff',
                               font=theme.FONT_BOLD, tags=('ghost',),
                               text=mods.editor_name(self.held['name']))

    def _release(self, ev):
        if getattr(self, '_moved', False):
            self._clamp_view()
            return
        if self.held is None:
            return
        where = self._where(ev)
        if not where:
            return
        tile, x, y = where
        ter = self.terrain(tile)
        if ter is None:
            self.status.configure(text=t('place.nomap', tile=tile))
            return
        if ter.passable(x, y) is False and not messagebox.askyesno(
                t('place.title'), t('place.blocked.q'), parent=self.win):
            return
        tg = self.held
        body, _src = self._base(tile)
        # numbers already given out: the other quests' placements and the
        # markers set in this window (not the one in the hand)
        mine = {id(o.get('orig')) for o in self.targets if o.get('orig')}
        others = [p for p in placed.placements(self.app.project)
                  if id(p) not in mine]
        others += [dict(o['placed'], name=o['name'])
                   for o in self.targets if o.get('placed') and o is not tg]

        def taken(n):
            return placed.marker_exists(body, tg['name'], n) or any(
                o['tile'] == tile and o['name'] == tg['name']
                and int(o['num']) == int(n) for o in others)
        num = tg.get('num')
        prev = tg.get('_prev') or {}
        if num is None and prev.get('tile') == tile and prev.get('num') \
                and not taken(prev['num']):
            num = prev['num']
        if num is None:
            num = placed.free_number(tg['name'], tile, body, others)
        elif taken(num):
            # the map or another quest has it already: a second one would
            # not be written
            messagebox.showwarning(t('place.title'), t(
                'place.clash', marker=mods.editor_name(tg['name']), num=num,
                tile=tile), parent=self.win)
            return
        tg['placed'] = {'tile': tile, 'x': int(x), 'y': int(y),
                        'z': ter.height(x, y), 'num': int(num)}
        self.held = None
        self.changed = True
        self.c.delete('ghost')
        self._rows()
        self._draw_points()

    # -- finish ------------------------------------------------------------------

    def confirm(self):
        open_n = sum(1 for tg in self.targets if tg.get('placed') is None)
        if open_n and not messagebox.askyesno(
                t('place.title'), t('place.open.q', n=open_n),
                parent=self.win):
            return
        self._close()
        self.on_done(self.targets)

    def cancel(self):
        if self.changed and not messagebox.askyesno(
                t('place.title'), t('place.discard.q'), parent=self.win):
            return
        self._close()

    def _close(self):
        if self._draw_job:
            try:
                self.win.after_cancel(self._draw_job)
            except tk.TclError:
                pass
            self._draw_job = None
        self.tip.hide()
        self.images.clear()
        self._sources.clear()
        self.win.destroy()

    def close(self):
        self.cancel()


# ---------------------------------------------------------------------------
# quest side: which markers a quest still needs, and taking placements over

def _key(name, tile, num):
    return (name, str(tile or '').upper(), num)


def quest_targets(project, q):
    """Targets for the markers a taken over quest needs: the open entries
    of its checklist and those placed with this window before (a ticked
    entry without placement was done in the Two Worlds editor)."""
    from .mpmerge import GIVER_MARKER, current_todo
    mine = [p for p in placed.placements(project) if p.get('quest') == q.id]
    out = []
    for item in current_todo(q):
        key = _key(item.get('name'), item.get('tile'), item.get('num'))
        orig = next((p for p in mine if _key(p['name'], p['tile'], p['num'])
                     == key), None)
        if item.get('done') and orig is None:
            continue
        if is_interior(key[1]):
            continue
        giver = item.get('name') == GIVER_MARKER
        out.append({
            'key': key, 'name': key[0], 'label': item.get('why') or '',
            'num': key[2] if giver else None, 'tile': key[1], 'orig': orig,
            '_prev': {'tile': key[1], 'num': key[2]},
            'placed': None if orig is None else {
                k: orig[k] for k in ('tile', 'x', 'y', 'z', 'num')}})
    return out


def is_interior(tile):
    s = mapdata.split_tile(tile or '')
    return bool(s and s[2])


def _ref_map(q):
    """{(name, tile, num): [line refs or giver speakers]} taken ONCE before
    anything moves: moving A onto the old place of B must not drag B's
    lines along (or A's along with B)."""
    from .mpmerge import GIVER_MARKER, marker_refs
    out = {}
    for s in q.speakers:
        if s.get('new') and isinstance(s.get('id'), int):
            out.setdefault(_key(GIVER_MARKER, s.get('tile'),
                                s.get('marker') or s['id']), []).append(
                ('giver', s))
    for ref in marker_refs(q):
        out.setdefault(_key(ref['name'], ref['tile'], ref['num']),
                       []).append(('line', ref))
    return out


def _retarget(q, old, new, refs=None):
    """Point the quest lines (or the giver) from marker ``old`` to ``new``,
    both (name, tile, num)."""
    for kind, obj in (refs if refs is not None else _ref_map(q)).get(old, []):
        if kind == 'giver':
            obj['tile'], obj['marker'] = new[1], new[2]
        else:
            obj['args'][obj['tile_key']] = new[1]
            obj['args'][obj['num_key']] = new[2]


def commit(app, q, targets, log=lambda *a: None):
    """Placements into the quest, the checklist and the project, then the
    tiles of the levels folder rebuilt and the mods read again. Returns
    the report of placed.generate."""
    project = app.project
    lst = placed.placements(project)
    todo = q.extra.setdefault('markers_todo', [])
    refs = _ref_map(q)
    # checklist items by their key BEFORE anything moves (same reason as
    # _ref_map: A moved onto the old place of B must not take B's item)
    items = {}
    for x in todo:
        items.setdefault(_key(x.get('name'), x.get('tile'), x.get('num')),
                         []).append(x)
    for tg in targets:
        old = tg['key']
        if tg.get('orig') is not None:
            lst[:] = [p for p in lst if p is not tg['orig']]
        p = tg.get('placed')
        match = items.get(old, [])
        if p is None:                   # lifted and not set again
            for x in match:
                x['done'] = False
                x.pop('placed', None)
            continue
        new = _key(tg['name'], p['tile'], int(p['num']))
        _retarget(q, old, new, refs)
        for x in match:
            x.update(tile=new[1], num=new[2], done=True, placed=True)
        entry = {'name': tg['name'], 'num': new[2], 'tile': new[1],
                 'x': p['x'], 'y': p['y'], 'z': p['z'], 'angle': 0,
                 'quest': q.id}
        lst.append(entry)
        tg['orig'], tg['key'] = entry, new
    app.mark_dirty()
    # the maps on disk cannot be undone: an older snapshot of the quest
    # would point its lines back at markers that are no longer written
    if getattr(app, 'quest', None) is q and hasattr(app, 'undo'):
        app.undo.clear()
    report = placed.generate(project, app.modset, app.cfg.get('game_dir'),
                             log)
    # a marker the map had already was not written: its item stays open
    for r in report.values():
        for c in r['clash']:
            for x in todo:
                if _key(x.get('name'), x.get('tile'), x.get('num')) == \
                        _key(c['name'], c['tile'], int(c['num'])):
                    x['done'] = False
                    x.pop('placed', None)
    app.load_modset(force=True)
    return report


def safe_commit(app, q, targets, parent=None):
    """commit with the error shown instead of a half written state left
    silently. Returns the report or None."""
    try:
        return commit(app, q, targets)
    except Exception as e:
        messagebox.showerror(t('place.title'), t('place.error', err=e),
                             parent=parent or app.root)
        return None


def can_place(app, parent):
    """The levels folder sits next to the project file: saved first."""
    from . import editormaps
    if editormaps.levels_dir(app.project):
        return True
    messagebox.showwarning(t('place.title'), t('place.save'), parent=parent)
    return False


def place_for_quest(app, q):
    """Quest panel: open the window for the markers of ``q``."""
    if not can_place(app, app.root):
        return None
    targets = quest_targets(app.project, q)
    if not targets:
        messagebox.showinfo(t('place.title'), t('place.none'),
                            parent=app.root)
        return None

    def done(tgs):
        report = safe_commit(app, q, tgs)
        if report is not None:
            _report(app, report)
        if app.inspector:
            app.inspector.refresh()
    return PlaceWindow(app, targets, done)


def _report(app, report):
    clash = [c for r in report.values() for c in r['clash']]
    lost = [tile for tile, r in report.items() if r['source'] is None]
    added = sum(len(r['added']) for r in report.values())
    text = t('place.written', tiles=', '.join(sorted(report)) or '-',
             added=added)
    if clash:
        text += NL + t('place.clashes', items=', '.join(
            f"{mods.editor_name(c['name'])} {c['num']} ({c['tile']})"
            for c in clash))
    if lost:
        text += NL + t('place.nobase', tiles=', '.join(lost))
    messagebox.showinfo(t('place.title'), text + NL + NL + t('em.lhc'),
                        parent=app.root)
