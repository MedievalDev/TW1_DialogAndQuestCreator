"""Quest > Enemy levels: levels, kill experience, health, damage, strike
pause, blows a minute and resistances per creature type, the hero's
experience curve on top (enemylevel.py, enemystats.py, expcurve.py,
rpgcompute.py).

4.5.0 (Marco 2026-09-22): every value shows what it is now and takes an
edit; a bulk row on top changes all rows the filter shows: "-10" takes 10
away, "+25%" adds a quarter, "50" sets 50. Units that two types share
(Orc and Orc Archer) are changed once, not twice. "Kill experience not
below 0" keeps a kill worth at least nothing; off, a kill can take
experience away.

The table is drawn on a canvas, because every column group has its own
colour (Marco: "alles was zum Level gehoert blau, EXP gruen, HP rot,
Schaden und Schlagpause lila, Schutz orange, Attack Speed cyan, zwischen
jeder Spalte eine schwarze Trennlinie"; then "Damage-Spalte gelb") - a
ttk.Treeview colours rows only. A click on a value lays an entry over the cell, Enter or leaving it
takes the edit. The header canvas carries the bulk row and scrolls
sideways with the table.
"""

import threading
import tkinter as tk
import tkinter.font as tkfont
from collections import Counter
from tkinter import messagebox, ttk

from . import data, enemylevel, enemystats, expcurve, export, questlimit, \
    theme
from .i18n import t

NL = chr(10)
STATS = enemystats.STATS
LEVEL_KEYS = ('min', 'max')
# (column, width in pixels) in the order of the table
COLUMNS = (('name', 190), ('sdk', 116), ('min', 80), ('max', 80),
           ('orig', 74), ('exp', 84), ('hp', 84), ('dmg', 112),
           ('strike', 96), ('speed', 104), ('phys', 80), ('cold', 70),
           ('fire', 70), ('elec', 82))
WIDTH = dict(COLUMNS)
KEYS = tuple(k for k, _w in COLUMNS)
X = {}                    # left edge of every column
_x = 0
for _k, _w in COLUMNS:
    X[_k] = _x
    _x += _w
TABLE_W = _x
EDITABLE = tuple(k for k in KEYS if k in LEVEL_KEYS + STATS + ('speed',))
PAR_STATS = ('hp', 'dmg', 'strike', 'speed', 'phys', 'cold', 'fire', 'elec')
ROW_H = 22
HEAD_H = 26
BULK_H = 32
WEAPON = ' + W'           # the share of a carried weapon (people)

# the colour of every column group (theme.py); name and SDK name stay plain
COLOURS = {'min': theme.ENEMY_LEVEL, 'max': theme.ENEMY_LEVEL,
           'orig': theme.ENEMY_LEVEL, 'exp': theme.ENEMY_EXP,
           'hp': theme.ENEMY_HP, 'dmg': theme.ENEMY_DAMAGE,
           'strike': theme.ENEMY_STRIKE, 'speed': theme.ENEMY_SPEED,
           'phys': theme.ENEMY_PROTECT, 'cold': theme.ENEMY_PROTECT,
           'fire': theme.ENEMY_PROTECT, 'elec': theme.ENEMY_PROTECT}
SEPARATOR = theme.ENEMY_SEPARATOR


def _tint(key, odd):
    """Background of a cell: its column colour on the dark ground, every
    second row a little stronger."""
    col = COLOURS.get(key)
    if col is None:
        return theme.mix(theme.INK, theme.BG, 0.05) if odd else theme.BG
    return theme.mix(col, theme.BG, 0.26 if odd else 0.19)


def _key_at(x):
    for key, w in COLUMNS:
        if X[key] <= x < X[key] + w:
            return key
    return None


class EnemyLevelWindow:
    """Minimum and maximum level per creature type and, per type, the kill
    experience, health and damage at the maximum level, strike pause,
    blows a minute and the four resistances of its units."""

    _open = None              # the open window (one at a time; the tour)

    @classmethod
    def current(cls):
        w = cls._open
        try:
            return w if w is not None and w.win.winfo_exists() else None
        except tk.TclError:
            return None

    def __init__(self, app):
        self.app = app
        self.game = app.cfg.get('game_dir')
        self.state = None
        self.values = {}          # {type: (min, max)}
        self.mods = None          # {unit: {field: value}}
        self.rows = []            # per table row: ('group', grp) | ('type', num)
        self.row_of = {}          # type -> row index
        self.cells = {}           # (type, key) -> text item on the canvas
        self.shown = {}           # (type, key) -> text in the cell
        self.editor = None        # (entry, var, type, key, item) while editing
        self.hover = None
        self._search_job = None
        self._fits = {}
        self._names_loading = False
        self.game_names = getattr(app, '_enemy_names', None) or {}
        self.win = tk.Toplevel(app.root)
        self.win.title(t('enemy.title'))
        self.win.transient(app.root)
        self.win.geometry('1370x860')
        self.win.minsize(1000, 600)
        theme.dark_titlebar(self.win)
        self.win.bind('<Escape>', lambda e: self.close())
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        EnemyLevelWindow._open = self
        self.font = tkfont.Font(font=theme.FONT)
        self.font_bold = tkfont.Font(font=theme.FONT_BOLD)
        f = ttk.Frame(self.win, padding=14)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=t('enemy.head'), style='Brand.TLabel').pack(anchor='w')
        ttk.Label(f, text=t('enemy.sub'), style='Muted.TLabel',
                  wraplength=1320, justify='left').pack(anchor='w', pady=(2, 6))
        self.state_lbl = ttk.Label(f, style='Muted.TLabel', wraplength=1320,
                                   justify='left')
        self.state_lbl.pack(anchor='w', pady=(0, 8))

        # the hero's experience curve and the floor of the kill experience
        xp = ttk.Frame(f)
        xp.pack(fill='x', pady=(0, 8))
        ttk.Label(xp, text=t('enemy.exp.head'), font=theme.FONT_BOLD
                  ).pack(side='left')
        self.exp = tk.StringVar(value='1')
        self.exp_spin = ttk.Spinbox(xp, from_=0.1, to=10.0, increment=0.1,
                                    width=6, textvariable=self.exp,
                                    command=self._exp_changed)
        self.exp_spin.pack(side='left', padx=(10, 4))
        self.exp_spin.bind('<KeyRelease>', lambda e: self._exp_changed())
        theme.Tooltip(self.exp_spin, t('enemy.exp.tip'))
        ttk.Label(xp, text='x').pack(side='left')
        self.exp_lbl = ttk.Label(xp, style='Muted.TLabel')
        self.exp_lbl.pack(side='left', padx=(12, 0))
        self.floor = tk.BooleanVar(value=True)
        fl = ttk.Checkbutton(xp, text=t('enemy.floor'), variable=self.floor,
                             command=self.update_cells)
        fl.pack(side='right')
        theme.Tooltip(fl, t('enemy.floor.tip'))
        self.floor_cb = fl

        # filter row
        bar = ttk.Frame(f)
        bar.pack(fill='x')
        ttk.Label(bar, text=t('enemy.filter')).pack(side='left')
        self.search = tk.StringVar()
        ent = ttk.Entry(bar, textvariable=self.search, width=18)
        ent.pack(side='left', padx=(6, 10))
        ent.bind('<KeyRelease>', lambda e: self._search_later())
        self.search_entry = ent
        self.group = tk.StringVar(value=t('enemy.group.all'))
        groups = [t('enemy.group.all')] + [t('enemy.group.' + g)
                                           for g in enemylevel.GROUPS]
        self.group_keys = [None] + list(enemylevel.GROUPS)
        cb = ttk.Combobox(bar, textvariable=self.group, values=groups,
                          state='readonly', width=18)
        cb.pack(side='left')
        cb.bind('<<ComboboxSelected>>', lambda e: self.build_rows())
        self.group_cb = cb
        self.only_changed = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text=t('enemy.onlychanged'),
                        variable=self.only_changed,
                        command=self.build_rows).pack(side='left', padx=10)
        ttk.Button(bar, text=t('enemy.preset.hero'),
                   command=self.preset_hero).pack(side='left', padx=(16, 4))
        ttk.Button(bar, text=t('enemy.preset.retail'),
                   command=self.preset_retail).pack(side='left', padx=4)
        self.count_lbl = ttk.Label(bar, style='Muted.TLabel')
        self.count_lbl.pack(side='right')

        # buttons and log (packed before the table so they keep their room)
        self.txt = tk.Text(f, wrap='word', font=theme.FONT_MONO, height=5)
        self.txt.pack(side='bottom', fill='x', pady=(10, 0))
        self.txt.tag_configure('ok', foreground=theme.OK)
        self.txt.tag_configure('err', foreground=theme.ERR)
        self.txt.tag_configure('warn', foreground=theme.WARN)
        self.txt.configure(state='disabled')
        btns = ttk.Frame(f)
        btns.pack(side='bottom', fill='x', pady=(10, 0))
        self.btn_apply = ttk.Button(btns, text=t('enemy.apply'),
                                    style='Accent.TButton',
                                    command=self.apply_clicked)
        self.btn_apply.pack(side='left')
        self.btn_remove = ttk.Button(btns, text=t('enemy.remove'),
                                     command=self.remove_clicked)
        self.btn_remove.pack(side='left', padx=6)
        self.hint_lbl = ttk.Label(btns, style='Muted.TLabel')
        self.hint_lbl.pack(side='left', padx=12)
        ttk.Button(btns, text=t('close'), command=self.close
                   ).pack(side='right')

        # table: header with the bulk row, body, scroll bars
        box = ttk.Frame(f)
        box.pack(fill='both', expand=True, pady=(8, 0))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        self.head = tk.Canvas(box, height=HEAD_H + BULK_H, background=theme.BG,
                              highlightthickness=0, borderwidth=0,
                              xscrollincrement=1)
        self.head.grid(row=0, column=0, sticky='ew')
        self.body = tk.Canvas(box, background=theme.BG, highlightthickness=0,
                              borderwidth=0, xscrollincrement=1,
                              yscrollincrement=ROW_H)
        self.body.grid(row=1, column=0, sticky='nsew')
        vsb = ttk.Scrollbar(box, orient='vertical', command=self.body.yview)
        vsb.grid(row=1, column=1, sticky='ns')
        self.hsb = ttk.Scrollbar(box, orient='horizontal',
                                 command=self.body.xview)
        self.hsb.grid(row=2, column=0, sticky='ew')
        self.body.configure(yscrollcommand=vsb.set,
                            xscrollcommand=self._xset)
        self.body.bind('<Button-1>', self._click)
        self.body.bind('<Motion>', self._motion)
        self.body.bind('<Leave>', lambda e: self._leave())
        self.body.bind('<MouseWheel>', self._wheel)
        self.body.bind('<Shift-MouseWheel>', self._wheel_x)
        self.head.bind('<Motion>', self._head_motion)
        self.head.bind('<Leave>', lambda e: self.tip.hide())
        self.head.bind('<Shift-MouseWheel>', self._wheel_x)
        self.tip = theme.FloatTip(self.win)
        self._draw_head()
        self.refresh()

    # -- helpers ----------------------------------------------------------
    def close(self):
        self.tip.hide()
        if EnemyLevelWindow._open is self:
            EnemyLevelWindow._open = None
        self.win.destroy()

    def _xset(self, lo, hi):
        self.hsb.set(lo, hi)
        self.head.xview_moveto(lo)

    def _wheel(self, ev):
        self.body.yview_scroll(-3 if ev.delta > 0 else 3, 'units')
        return 'break'

    def _wheel_x(self, ev):
        self.body.xview_scroll(-60 if ev.delta > 0 else 60, 'units')
        return 'break'

    def _search_later(self):
        if self._search_job:
            self.win.after_cancel(self._search_job)
        self._search_job = self.win.after(250, self.build_rows)

    def _put(self, text, tag=None):
        self.txt.configure(state='normal')
        self.txt.insert('end', text + NL, tag)
        self.txt.see('end')
        self.txt.configure(state='disabled')

    def hint(self, text, error=False):
        self.hint_lbl.configure(text=text,
                                foreground=theme.ERR if error else theme.MUT)

    def _fit(self, text, width, bold=False):
        """The text, cut with an ellipsis where it would run into the next
        column."""
        if len(text) * 12 <= width:      # no character is wider than 12
            return text
        key = (text, width, bold)
        got = self._fits.get(key)
        if got is None:
            font = self.font_bold if bold else self.font
            got = text
            if font.measure(got) > width:
                while got and font.measure(got + '…') > width:
                    got = got[:-1]
                got += '…'
            self._fits[key] = got
        return got

    def log(self, msg):
        if isinstance(msg, str):
            msg = ('text', msg)
        kind = msg[0]
        tag = None
        if kind == 'patched':
            text = t('enemy.log.patched', file=msg[1], n=msg[2], src=msg[3])
        elif kind == 'regbackup':
            text = t('limit.log.regbackup', path=msg[1])
        elif kind == 'oldmod':
            text = t('limit.log.oldmod', name=msg[1])
        elif kind == 'written':
            text = t('enemy.log.written', name=msg[1], n=msg[2], guid=msg[3])
            tag = 'ok'
        elif kind == 'otheractive':
            text = t('limit.log.other', name=msg[1])
            tag = 'warn'
        elif kind == 'removed':
            text = t('limit.log.removed', name=msg[1])
        elif kind == 'switchedoff':
            text = t('limit.log.off', name=msg[1])
        elif kind == 'expcurve':
            text = t('enemy.log.expcurve', f=msg[1] / 100, p=msg[1])
        elif kind == 'enemystats':
            text = t('enemy.log.stats', n=msg[1]) + ' ' + t(
                'enemy.log.floor.on' if msg[2] else 'enemy.log.floor.off')
        elif kind == 'expother':
            text = t('enemy.log.expother', name=msg[1])
            tag = 'warn'
        else:
            text = ' '.join(str(x) for x in msg)
        self._put(text, tag)

    # -- the experience curve ---------------------------------------------
    def _exp_percent(self):
        try:
            return expcurve.to_percent(self.exp.get().replace(',', '.'))
        except ValueError:
            return None

    def _exp_changed(self):
        p = self._exp_percent()
        if p is None:
            self.exp_lbl.configure(text=t('enemy.exp.bad'))
            return
        parts = [t('enemy.exp.example', lvl=n, old=expcurve.points(n),
                   new=expcurve.points(n, p))
                 for n in expcurve.EXAMPLE_LEVELS]
        self.exp_lbl.configure(text=t('enemy.exp.percent', p=p) + '   '
                               + '   '.join(parts))

    # -- data per row -----------------------------------------------------
    @staticmethod
    def _entry(num):
        return enemylevel.entry(num)

    def _base(self):
        return self.state.base if self.state else {}

    def _units(self, num, key=None):
        """The units of a type, once each; for a par value only those the
        par knows (a few names of the SDK list are not in it), for the
        blows a minute only those with strike animations."""
        base = self._base()
        out = []
        for u in self._entry(num)[6]:
            if u in out:
                continue
            if key in PAR_STATS and u not in base:
                continue
            if key == 'speed' and not base[u].get('sets'):
                continue
            out.append(u)
        return out

    def _levels(self, num):
        return self.values.get(num, enemylevel.retail_values()[num])

    def _pa(self, unit, key):
        return enemystats.get(self.mods, unit, key)

    def _delay(self, unit, mods):
        """The strike pause of a unit under {unit: {field: value}} mods."""
        return enemystats.value(self._base()[unit]['strike'],
                                enemystats.get(mods, unit, 'strike'),
                                'strike')

    def _shown(self, num, key, mods):
        """The text of a stat cell for {unit: {field: value}} ``mods``."""
        lo, hi = self._levels(num)
        units = self._units(num, key)
        if not units:
            return '-'
        base = self._base()
        if key == 'exp':
            return enemystats.span(
                enemystats.exp_at(enemystats.get(mods, u, 'exp'), lvl,
                                  self.floor.get())
                for u in units for lvl in (lo, hi))
        if key == 'dmg':
            blows, own, pcts = [], [], []
            for u in units:
                pct = enemystats.get(mods, u, 'dmg')[0]
                pcts.append(pct)
                got = enemystats.blow_at(base[u], hi, pct)
                if got is None:
                    own.append(enemystats.unit_damage(base[u]['dmg'], hi)
                               * pct // 100)
                else:
                    blows.append(got)
            parts = []
            if blows:
                parts.append(enemystats.span(blows))
            if own:
                parts.append(enemystats.span(own) + WEAPON)
            text = ' / '.join(parts)
            if any(p != 100 for p in pcts):
                text += ' (' + enemystats.span(pcts) + ' %)'
            return text
        if key == 'speed':
            return enemystats.span(
                r for u in units
                for r in enemystats.strike_rates(base[u], hi,
                                                 self._delay(u, mods)))
        if key == 'hp':
            return enemystats.span(enemystats.hp_at(enemystats.value(
                base[u]['hp'], enemystats.get(mods, u, 'hp'), 'hp'), hi)
                for u in units)
        return enemystats.span(enemystats.value(
            base[u][key], enemystats.get(mods, u, key), key) for u in units)

    def cell_text(self, num, key):
        lo, hi = self._levels(num)
        if key == 'name':
            return self.game_names.get(num) or self._entry(num)[1]
        if key == 'min':
            return str(lo)
        if key == 'max':
            return str(hi)
        if key == 'orig':
            return enemystats.span(enemylevel.retail_values()[num])
        if key == 'sdk':
            name = self._entry(num)[1]
            return name if (self.game_names.get(num) or name) != name else ''
        return self._shown(num, key, self.mods)

    def cell_changed(self, num, key):
        if key in LEVEL_KEYS:
            lo, hi = self._levels(num)
            rlo, rhi = enemylevel.retail_values()[num]
            return (lo if key == 'min' else hi) != (rlo if key == 'min' else rhi)
        if key == 'speed':
            key = 'strike'
        if key not in STATS:
            return False
        return any(self._pa(u, key) != enemystats.NEUTRAL
                   for u in self._units(num, key))

    def row_changed(self, num):
        return any(self.cell_changed(num, k) for k in EDITABLE)

    def shared_with(self, num):
        """Other types that use one of this type's units."""
        mine = set(self._entry(num)[6])
        return [self.game_names.get(e[0]) or e[1]
                for e in enemylevel.all_entries()
                if e[0] != num and mine & set(e[6])]

    def filtered(self):
        needle = self.search.get().strip().lower()
        gi = 0
        for i, g in enumerate(self.group_keys):
            label = (t('enemy.group.all') if g is None
                     else t('enemy.group.' + g))
            if label == self.group.get():
                gi = i
                break
        group = self.group_keys[gi]
        out = []
        for num, name, _mark, _lo, _hi, grp, _units in \
                enemylevel.all_entries():
            if group and grp != group:
                continue
            shown = self.game_names.get(num) or ''
            if needle and needle not in name.lower() \
                    and needle not in shown.lower():
                continue
            if self.only_changed.get() and not self.row_changed(num):
                continue
            out.append((num, name, grp))
        order = {g: i for i, g in enumerate(enemylevel.GROUPS)}
        out.sort(key=lambda r: (order.get(r[2], 99), r[1]))
        return out

    # -- state ------------------------------------------------------------
    def load_names(self):
        """The name every type has in the game, from its language file, in
        a thread: without an open project that reads every dialogue tree
        (2.5 s, measured 2026-09-22). Until then the table shows the SDK
        names. Kept on the app."""
        box = {}

        def work():
            names = {}
            try:
                tr = data.load_translations(self.game)
                for e in enemylevel.all_entries():
                    name = enemylevel.game_name(e[0], tr)
                    if name:
                        names[e[0]] = name
            except Exception:            # the SDK names stay
                pass
            box['names'] = names

        def poll():
            try:
                if not self.win.winfo_exists():
                    return
                if 'names' not in box:
                    self.win.after(100, poll)
                    return
            except tk.TclError:
                return
            self.game_names = box['names']
            if self.game_names:
                self.app._enemy_names = self.game_names
                self.build_rows()

        def start():                     # after the window is drawn
            threading.Thread(target=work, daemon=True).start()
            self.win.after(100, poll)

        self.win.after(150, start)

    def refresh(self):
        if not self.game_names and not self._names_loading:
            self._names_loading = True
            self.load_names()
        try:
            self.state = enemylevel.State(self.game)
            err = self.state.error
            if not err:
                self.state.read_base()
        except Exception as e:           # shown in the window
            self.state, err = None, str(e)
        if self.state is None or err:
            self.state_lbl.configure(text=t('enemy.error', e=err))
            self.btn_apply.state(['disabled'])
            self.btn_remove.state(['disabled'])
            return
        st = self.state
        if self.mods is None:
            self.values = dict(st.values)
            self.mods = {u: dict(v) for u, v in st.stats.items()}
            self.floor.set(st.floor)
            self.exp.set(f'{st.exp_percent / 100:g}')
        why = expcurve.usable(self.game)
        if why == 'ok':
            self.exp_spin.state(['!disabled'])
            self._exp_changed()
        else:
            self.exp.set('1')
            self.exp_spin.state(['disabled'])
            self.exp_lbl.configure(text=t('enemy.exp.unusable', why=why))
        notes = []
        if st.mod_present and st.mod_active:
            notes.append(t('enemy.mod.on', name=enemylevel.MOD_NAME))
        elif st.mod_present:
            notes.append(t('enemy.mod.off', name=enemylevel.MOD_NAME))
        else:
            notes.append(t('enemy.retail'))
        if st.base_error:
            notes.append(t('enemy.par.error', e=st.base_error))
        elif st.base_label:
            notes.append(t('enemy.par.base', name=st.base_label))
        for name, active in st.others:
            if active:
                notes.append(t('limit.log.other', name=name))
        for name, active in st.exp_others:
            if active:
                notes.append(t('enemy.log.expother', name=name))
        notes.append(t('enemy.newgames'))
        self.state_lbl.configure(text=' '.join(notes))
        self.btn_apply.state(['!disabled'])
        can_remove = (st.mod_present
                      or enemylevel.MOD_NAME in questlimit.reg_mods())
        self.btn_remove.state(['!disabled'] if can_remove else ['disabled'])
        self.build_rows()

    # -- header and bulk row ----------------------------------------------
    def _separators(self, canvas, y0, y1):
        """The black line between every two columns."""
        for key, _w in COLUMNS[1:]:
            canvas.create_line(X[key], y0, X[key], y1, fill=SEPARATOR,
                               width=2)
        canvas.create_line(TABLE_W, y0, TABLE_W, y1, fill=SEPARATOR, width=2)

    def _draw_head(self):
        c = self.head
        c.configure(scrollregion=(0, 0, TABLE_W, HEAD_H + BULK_H))
        for key, w in COLUMNS:
            x = X[key]
            col = COLOURS.get(key)
            c.create_rectangle(x, 0, x + w, HEAD_H, outline='',
                               fill=theme.mix(col, theme.BG, 0.55) if col
                               else theme.PANEL)
            c.create_rectangle(x, HEAD_H, x + w, HEAD_H + BULK_H, outline='',
                               fill=theme.mix(col, theme.BG, 0.3) if col
                               else theme.PANEL)
            c.create_text(x + 6, HEAD_H // 2, anchor='w',
                          text=self._fit(t('enemy.col.' + key), w - 10, True),
                          fill=theme.INK if col else theme.GOLD,
                          font=theme.FONT_BOLD)
        self._separators(c, 0, HEAD_H + BULK_H)
        c.create_line(0, HEAD_H, TABLE_W, HEAD_H, fill=SEPARATOR)
        c.create_text(6, HEAD_H + BULK_H // 2, anchor='w',
                      text=t('enemy.bulk'), fill=theme.GOLD, font=theme.FONT)
        btn = ttk.Button(c, text=t('enemy.bulk.apply'),
                         command=self.bulk_apply)
        c.create_window(X['sdk'] + 4, HEAD_H + 3, window=btn, anchor='nw',
                        width=WIDTH['sdk'] - 8, height=BULK_H - 6)
        self.bulk_btn = btn
        self.bulk, self.bulk_entries = {}, {}
        for key in EDITABLE:
            var = tk.StringVar()
            e = ttk.Entry(c, textvariable=var)
            c.create_window(X[key] + 4, HEAD_H + 4, window=e, anchor='nw',
                            width=WIDTH[key] - 8, height=BULK_H - 8)
            e.bind('<Return>', lambda ev: self.bulk_apply())
            theme.Tooltip(e, t('enemy.bulk.tip'))
            self.bulk[key] = var
            self.bulk_entries[key] = e

    def _head_motion(self, ev):
        text = None
        if ev.y < HEAD_H:
            key = _key_at(self.head.canvasx(ev.x))
            if key:
                tip = t('enemy.tip.' + key)
                text = tip if tip != 'enemy.tip.' + key else None
        if text:
            self.tip.show(text, ev.x_root, ev.y_root)
        else:
            self.tip.hide()

    def _parse(self, key, text):
        if key == 'dmg':
            return enemystats.parse_dmg(text)
        return enemystats.parse_expr(text)

    def bulk_apply(self):
        self._end_edit(True)
        todo = []
        for key, var in self.bulk.items():
            text = var.get().strip()
            if not text:
                continue
            expr = self._parse(key, text)
            if expr is None:
                self.hint(t('enemy.bad', text=text), error=True)
                return
            todo.append((key, expr))
        if not todo:
            self.hint(t('enemy.bulk.empty'), error=True)
            return
        nums = [num for num, _n, _g in self.filtered()]
        for key, expr in todo:
            self.edit(nums, key, expr)
        for var in self.bulk.values():
            var.set('')
        self.hint(t('enemy.bulk.done', n=len(nums)))
        self.update_cells()

    # -- table ------------------------------------------------------------
    def build_rows(self):
        self._search_job = None
        self._end_edit(True)
        c = self.body
        c.delete('all')
        self.rows, self.row_of, self.cells = [], {}, {}
        rows = self.filtered()
        counts = Counter(grp for _num, _name, grp in rows)
        blocks = []                   # (y0, y1) of the rows between groups
        y = top = 0
        last = None
        odd = False
        for num, _name, grp in rows:
            if grp != last:
                if last is not None:
                    blocks.append((top, y))
                c.create_rectangle(0, y, TABLE_W, y + ROW_H, outline='',
                                   fill=theme.PANEL)
                c.create_text(8, y + ROW_H // 2, anchor='w',
                              text=t('enemy.group.' + grp)
                              + f'  ({counts[grp]})',
                              fill=theme.GOLD, font=theme.FONT_BOLD)
                self.rows.append(('group', grp))
                y += ROW_H
                top, last, odd = y, grp, False
            self.row_of[num] = len(self.rows)
            self.rows.append(('type', num))
            look = self._row_look(num)
            for key, w in COLUMNS:
                x = X[key]
                c.create_rectangle(x, y, x + w, y + ROW_H, outline='',
                                   fill=_tint(key, odd))
                text, fill, font = look[key]
                self.cells[(num, key)] = c.create_text(
                    x + (14 if key == 'name' else 6), y + ROW_H // 2,
                    anchor='w', text=text, fill=fill, font=font)
            odd = not odd
            y += ROW_H
        if last is not None:
            blocks.append((top, y))
        for y0, y1 in blocks:
            self._separators(c, y0, y1)
        self.hover = c.create_rectangle(0, 0, 0, 0, outline=theme.GOLD_HI,
                                        state='hidden')
        c.configure(scrollregion=(0, 0, TABLE_W, max(y, ROW_H)))
        self.count_lbl.configure(text=t('enemy.count', n=len(rows),
                                        all=len(enemylevel.all_entries())))
        c.yview_moveto(0)

    def _row_look(self, num):
        """{key: (text, colour, font)} of the cells of a row; changed
        values in gold and bold, the name too when anything changed."""
        out = {}
        changed = False
        for key in KEYS[1:]:
            text = self.cell_text(num, key)
            self.shown[(num, key)] = text
            mark = self.cell_changed(num, key)
            changed = changed or mark
            if key == 'sdk' or text == '-':
                fill = theme.MUT
            else:
                fill = theme.GOLD if mark else theme.INK
            out[key] = (self._fit(text, WIDTH[key] - 10, mark), fill,
                        theme.FONT_BOLD if mark else theme.FONT)
        name = self.cell_text(num, 'name')
        self.shown[(num, 'name')] = name
        out['name'] = (self._fit(name, WIDTH['name'] - 18, changed),
                       theme.GOLD if changed else theme.INK,
                       theme.FONT_BOLD if changed else theme.FONT)
        return out

    def _update_row(self, num):
        for key, (text, fill, font) in self._row_look(num).items():
            item = self.cells[(num, key)]
            if self.body.itemcget(item, 'text') != text                     or self.body.itemcget(item, 'fill') != fill:
                self.body.itemconfigure(item, text=text, fill=fill, font=font)

    def update_cells(self):
        for num in self.row_of:
            self._update_row(num)

    def _cell_at(self, ev):
        """(type, key) under the mouse, None elsewhere."""
        y = self.body.canvasy(ev.y)
        i = int(y // ROW_H)
        if y < 0 or i >= len(self.rows) or self.rows[i][0] != 'type':
            return None
        key = _key_at(self.body.canvasx(ev.x))
        return (self.rows[i][1], key) if key else None

    def _cell_tip(self, num, key):
        """What the cell means, what the game had, how to type."""
        lo, hi = enemylevel.retail_values()[num]
        text = t('enemy.tip.' + key)
        if text == 'enemy.tip.' + key:
            text = t('enemy.col.' + key)
        if key in LEVEL_KEYS:
            orig = str(lo if key == 'min' else hi)
        elif key in PAR_STATS and not self._units(num, key):
            return text + NL + NL + t('enemy.nopar')
        else:
            orig = self._shown(num, key, {})
        out = text + NL + NL + t('enemy.cell.orig', orig=orig)
        now = self.shown.get((num, key), '')
        if now != orig:
            out += NL + t('enemy.cell.now', now=now)
        shared = self.shared_with(num)
        if shared and key not in LEVEL_KEYS:
            out += NL + t('enemy.shared', names=', '.join(shared))
        return out + NL + t('enemy.bulk.tip')

    def _leave(self):
        self.tip.hide()
        if self.hover:
            self.body.itemconfigure(self.hover, state='hidden')

    def _motion(self, ev):
        cell = self._cell_at(ev)
        text = None
        if cell and cell[1] in EDITABLE:
            num, key = cell
            y = self.row_of[num] * ROW_H
            self.body.coords(self.hover, X[key] + 1, y + 1,
                             X[key] + WIDTH[key] - 2, y + ROW_H - 1)
            self.body.itemconfigure(self.hover, state='normal')
            self.body.tag_raise(self.hover)
            text = self._cell_tip(num, key)
        elif self.hover:
            self.body.itemconfigure(self.hover, state='hidden')
        if text:
            self.tip.show(text, ev.x_root, ev.y_root)
        else:
            self.tip.hide()

    # -- editing in place -------------------------------------------------
    def _click(self, ev):
        cell = self._cell_at(ev)
        self._end_edit(True)
        if not cell or cell[1] not in EDITABLE:
            return
        num, key = cell
        if key not in LEVEL_KEYS and not self._units(num, key):
            return             # a type without units (three shamans)
        self._begin_edit(num, key)
        return 'break'

    def _see(self, num, key):
        """Scroll so that a cell is in view."""
        c = self.body
        y = self.row_of[num] * ROW_H
        total = max(1, len(self.rows) * ROW_H)
        top, h = c.canvasy(0), c.winfo_height()
        if y < top:
            c.yview_moveto(y / total)
        elif y + ROW_H > top + h:
            c.yview_moveto((y + ROW_H - h + ROW_H - 1) / total)
        x, w = X[key], WIDTH[key]
        left, width = c.canvasx(0), c.winfo_width()
        if x < left:
            c.xview_moveto(x / TABLE_W)
        elif x + w > left + width:
            c.xview_moveto((x + w - width) / TABLE_W)

    def _begin_edit(self, num, key):
        if num not in self.row_of:
            return
        self._see(num, key)
        y = self.row_of[num] * ROW_H
        var = tk.StringVar(value=self.shown.get((num, key), ''))
        e = ttk.Entry(self.body, textvariable=var)
        item = self.body.create_window(X[key] + 1, y, window=e, anchor='nw',
                                       width=WIDTH[key] - 2, height=ROW_H)
        e.focus_set()
        e.select_range(0, 'end')
        e.bind('<Return>', lambda ev: self._end_edit(True))
        e.bind('<Escape>', lambda ev: (self._end_edit(False), 'break')[1])
        e.bind('<Tab>', lambda ev: self._next_cell(num, key, 1))
        e.bind('<Shift-Tab>', lambda ev: self._next_cell(num, key, -1))
        e.bind('<MouseWheel>', self._wheel)
        # only this entry's own focus loss ends it (not a later editor)
        e.bind('<FocusOut>', lambda ev, e=e: self._end_edit(True)
               if self.editor and self.editor[0] is e else None)
        self.editor = (e, var, num, key, item)
        self.tip.hide()

    def _next_cell(self, num, key, step):
        self._end_edit(True)
        keys = [k for k in EDITABLE if k in LEVEL_KEYS
                or self._units(num, k)]
        i = keys.index(key) + step
        if 0 <= i < len(keys):
            self._begin_edit(num, keys[i])
        return 'break'

    def _end_edit(self, take):
        if self.editor is None:
            return
        e, var, num, key, item = self.editor
        self.editor = None
        text = var.get().strip()
        try:
            self.body.delete(item)
            e.destroy()
        except tk.TclError:
            pass
        if take:
            self.commit(num, key, text)

    def commit(self, num, key, text):
        if text == self.shown.get((num, key)) or not text:
            return
        expr = self._parse(key, text)
        if expr is None:
            self.hint(t('enemy.bad', text=text), error=True)
            return
        self.edit([num], key, expr)
        self.hint('')
        self.update_cells()

    def edit(self, nums, key, expr):
        """One change for the given types; units that several of them share
        are changed once. The blows a minute are set through the pause."""
        if key in LEVEL_KEYS:
            for num in nums:
                lo, hi = self._levels(num)
                cur = lo if key == 'min' else hi
                new = enemystats.apply_expr(cur, expr, enemylevel.MIN_LEVEL,
                                            enemylevel.MAX_LEVEL)
                if key == 'min':
                    lo, hi = new, max(hi, new)
                else:
                    lo, hi = min(lo, new), new
                self.values[num] = (lo, hi)
            return
        base = self._base()
        done = set()
        for num in nums:
            _lo, hi = self._levels(num)
            for u in self._units(num, key):
                if u in done:
                    continue
                done.add(u)
                b = base.get(u, {})
                if key == 'speed':
                    d = enemystats.speed_edit(b, hi, self._delay(u, self.mods),
                                              expr)
                    if d is not None:
                        enemystats.put(self.mods, u, 'strike',
                                       enemystats.NEUTRAL
                                       if d == b['strike'] else (0, d))
                    continue
                new = enemystats.edit(key, self._pa(u, key), expr,
                                      b if key == 'dmg' else b.get(key), hi)
                enemystats.put(self.mods, u, key, new)

    # -- presets ----------------------------------------------------------
    def _types(self):
        return {num for num, _n, _g in self.filtered()}

    def preset_hero(self):
        self.values = enemylevel.preset_follow_hero(self.values, self._types())
        self.update_cells()

    def preset_retail(self):
        """Everything of the types shown back to the game's values."""
        types = self._types()
        self.values = enemylevel.preset_retail(self.values, types)
        for num in types:
            for u in self._entry(num)[6]:
                self.mods.pop(u, None)
        self.update_cells()

    # -- actions ----------------------------------------------------------
    def _guard(self):
        if export.game_running():
            messagebox.showerror(t('enemy.title'), t('export.running'),
                                 parent=self.win)
            return False
        return True

    def apply_clicked(self):
        self._end_edit(True)
        if not self._guard():
            return
        p = self._exp_percent()
        if p is None:
            self._put(t('enemy.exp.bad'), 'err')
            return
        if 'disabled' in self.exp_spin.state():
            p = 100
        try:
            enemylevel.apply(self.game, self.values, self.log, exp_percent=p,
                             stats=self.mods, floor=self.floor.get())
            self._put(t('enemy.done.apply'), 'ok')
        except Exception as e:           # shown in the log
            self._put(t('limit.failed', e=e), 'err')
        self.refresh()

    def remove_clicked(self):
        self._end_edit(True)
        if not self._guard():
            return
        if not messagebox.askyesno(t('enemy.title'),
                                   t('enemy.remove.q',
                                     name=enemylevel.MOD_NAME),
                                   parent=self.win):
            return
        try:
            enemylevel.remove(self.game, self.log)
            self.values, self.mods = {}, None
            self._put(t('enemy.done.remove'), 'ok')
        except Exception as e:           # shown in the log
            self._put(t('limit.failed', e=e), 'err')
        self.refresh()
