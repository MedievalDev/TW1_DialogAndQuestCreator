"""Left box: the speaker list (plan 6.1) and the tasks/actions area (M5).

Speakers are per quest. "Spieler" is always there. Dragging a speaker
into the graph creates a node at the mouse position; a double click puts
it right of the selected node and connects it.
"""

import re
import tkinter as tk
from tkinter import messagebox, ttk

from . import model, theme
from .i18n import t


class SpeakerBox(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, style='Panel.TFrame')
        self.app = app
        self._drag = None
        ttk.Label(self, text=t('panel.speakers'), style='PanelTitle.TLabel'
                  ).pack(anchor='w', fill='x')
        self.btn = ttk.Button(self, text=t('speaker.new'),
                              command=self.new_speaker)
        self.btn.pack(fill='x', padx=8, pady=(2, 6))
        self.rows = ttk.Frame(self, style='Panel.TFrame')
        self.rows.pack(fill='both', expand=True, padx=8)
        self.refresh()

    # -- rows ---------------------------------------------------------------

    def refresh(self):
        for w in self.rows.winfo_children():
            w.destroy()
        q = self.app.quest
        self.btn.state(['!disabled'] if q else ['disabled'])
        if not q:
            ttk.Label(self.rows, text=t('quest.noquest'),
                      style='PanelMuted.TLabel').pack(anchor='w')
            return
        self._row(model.PLAYER, t('speaker.player'), theme.PLAYER_COLOR)
        for spk in q.speakers:
            title, color = self.app.speaker_style(spk['id'])
            self._row(spk['id'], title, color)

    def _row(self, sid, title, color):
        f = ttk.Frame(self.rows, style='Panel.TFrame', cursor='hand2')
        f.pack(fill='x', pady=1)
        sw = tk.Canvas(f, width=14, height=14, bg=theme.PANEL,
                       highlightthickness=0)
        sw.create_rectangle(1, 1, 13, 13, fill=color, outline='')
        sw.pack(side='left', padx=(0, 6))
        lbl = ttk.Label(f, text=title, style='Panel.TLabel')
        lbl.pack(side='left', fill='x', expand=True)
        for w in (f, sw, lbl):
            w.bind('<ButtonPress-1>', lambda e, s=sid: self._press(e, s))
            w.bind('<B1-Motion>', self._motion)
            w.bind('<ButtonRelease-1>', self._release)
            w.bind('<Double-Button-1>',
                   lambda e, s=sid: self.app.insert_speaker_node(s))
            if sid != model.PLAYER:
                w.bind('<ButtonPress-3>', lambda e, s=sid: self._menu(e, s))

    # -- drag into the graph ------------------------------------------------

    def _press(self, ev, sid):
        self._drag = {'sid': sid, 'x': ev.x_root, 'y': ev.y_root,
                      'active': False}

    def _motion(self, ev):
        d = self._drag
        if not d:
            return
        if not d['active'] and (abs(ev.x_root - d['x']) > 4
                                or abs(ev.y_root - d['y']) > 4):
            d['active'] = True
            self.app.root.configure(cursor='hand2')

    def _release(self, ev):
        d = self._drag
        self._drag = None
        if not d or not d['active']:
            return
        self.app.root.configure(cursor='')
        g = self.app.graph
        gx, gy = ev.x_root - g.winfo_rootx(), ev.y_root - g.winfo_rooty()
        if 0 <= gx < g.winfo_width() and 0 <= gy < g.winfo_height():
            wx, wy = g.c2w(g.canvasx(gx), g.canvasy(gy))
            self.app.add_speaker_node(d['sid'], wx - model.NODE_W / 2,
                                      wy - model.HEADER_H / 2)

    def _menu(self, ev, sid):
        menu = theme.Menu(self, tearoff=0)
        menu.add_command(label=t('speaker.rename'),
                         command=lambda: self.rename(sid))
        menu.add_command(label=t('speaker.remove'),
                         command=lambda: self.remove(sid))
        menu.add_command(label=t('speaker.mark'),
                         command=lambda: self.app.mark_speaker_lines(sid))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    # -- actions ------------------------------------------------------------

    def new_speaker(self):
        if not self.app.quest:
            return
        dlg = SpeakerDialog(self.app)
        self.app.root.wait_window(dlg.win)
        if dlg.result:
            self.app.add_speaker(dlg.result)

    def rename(self, sid):
        spk = self.app.quest.speaker(sid)
        if not spk:
            return
        dlg = _AskString(self.app.root, t('speaker.rename'), spk['name'])
        self.app.root.wait_window(dlg.win)
        if dlg.result and dlg.result != spk['name']:
            self.app.push_undo('rename')
            spk['name'] = dlg.result
            self.app.changed()

    def remove(self, sid):
        q = self.app.quest
        if q.speaker_used(sid):
            messagebox.showwarning(t('speaker.remove'), t('speaker.remove.used'),
                                   parent=self.app.root)
            return
        self.app.push_undo('remove speaker')
        q.remove_speaker(sid)
        self.app.changed()


class ActionBox(ttk.Frame):
    """Lower part of the left box (plan 6.2): the task block, new actions
    (drag onto a dialog node or double click for the selected node) and
    new conditions (always docked at the offer entry)."""

    def __init__(self, parent, app):
        super().__init__(parent, style='Panel.TFrame')
        self.app = app
        self._drag = None
        ttk.Label(self, text=t('panel.actions'), style='PanelTitle.TLabel'
                  ).pack(anchor='w', fill='x')
        self.rows = ttk.Frame(self, style='Panel.TFrame')
        self.rows.pack(fill='both', expand=True, padx=8)
        self.task = self._row(t('palette.task'), theme.STATE_COLORS['solved'],
                              '\u25ce')
        self.task.bind('<Button-1>', lambda e: self.app.select_task())
        for w in self.task.winfo_children():
            w.bind('<Button-1>', lambda e: self.app.select_task())
        self.action = self._row(t('palette.action'), theme.GOLD, '\u26a1')
        for w in [self.action] + list(self.action.winfo_children()):
            w.bind('<ButtonPress-1>', self._press)
            w.bind('<B1-Motion>', self._motion)
            w.bind('<ButtonRelease-1>', self._release)
            w.bind('<Double-Button-1>', lambda e: self._verb_menu(
                e.x_root, e.y_root, self.app.selected_dialog_node()))
        self.cond = self._row(t('palette.condition'), '#9a8fe0', '\u25c9')
        for w in [self.cond] + list(self.cond.winfo_children()):
            w.bind('<Button-1>', lambda e: self._cond_menu(e.x_root, e.y_root))
        ttk.Label(self.rows, text=t('palette.hint'), style='PanelMuted.TLabel',
                  wraplength=210).pack(anchor='w', pady=(8, 0))

    def _row(self, text, color, glyph):
        f = ttk.Frame(self.rows, style='Panel.TFrame', cursor='hand2')
        f.pack(fill='x', pady=2)
        tk.Label(f, text=glyph, fg=color, bg=theme.PANEL,
                 font=theme.FONT_BOLD).pack(side='left', padx=(0, 6))
        ttk.Label(f, text=text, style='Panel.TLabel').pack(side='left')
        return f

    def _press(self, ev):
        self._drag = {'x': ev.x_root, 'y': ev.y_root, 'active': False}

    def _motion(self, ev):
        d = self._drag
        if d and not d['active'] and (abs(ev.x_root - d['x']) > 4
                                      or abs(ev.y_root - d['y']) > 4):
            d['active'] = True
            self.app.root.configure(cursor='hand2')

    def _release(self, ev):
        d = self._drag
        self._drag = None
        if not d or not d['active']:
            return
        self.app.root.configure(cursor='')
        nid, _ = self.app.graph.node_at(ev.x_root, ev.y_root)
        node = self.app.quest.graph['nodes'].get(nid) if (
            self.app.quest and nid) else None
        if node and node.get('type') == 'action':
            nid = node.get('attached_to')
            node = self.app.quest.graph['nodes'].get(nid)
        if node and node.get('type') in ('npc', 'player'):
            self._verb_menu(ev.x_root, ev.y_root, nid)

    def _verb_menu(self, x, y, parent):
        if not self.app.quest or not parent:
            return
        menu = theme.Menu(self, tearoff=0)
        self.app.fill_action_menu(menu, parent)
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _cond_menu(self, x, y):
        if not self.app.quest:
            return
        menu = theme.Menu(self, tearoff=0)
        self.app.fill_condition_menu(menu)
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()


class _AskString:
    def __init__(self, parent, title, initial=''):
        self.result = None
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.transient(parent)
        self.win.resizable(False, False)
        theme.dark_titlebar(self.win)
        f = ttk.Frame(self.win, padding=16)
        f.pack()
        self.var = tk.StringVar(value=initial)
        e = ttk.Entry(f, textvariable=self.var, width=40)
        e.pack()
        e.focus_set()
        e.select_range(0, 'end')
        b = ttk.Frame(f)
        b.pack(anchor='e', pady=(10, 0))
        ttk.Button(b, text=t('ok'), style='Accent.TButton',
                   command=self._ok).pack(side='left', padx=(0, 6))
        ttk.Button(b, text=t('cancel'), command=self.win.destroy).pack(side='left')
        self.win.bind('<Return>', lambda e: self._ok())
        self.win.bind('<Escape>', lambda e: self.win.destroy())
        self.win.grab_set()

    def _ok(self):
        self.result = self.var.get().strip()
        self.win.destroy()


class SpeakerDialog:
    """Two cards: existing NPC (autocomplete over the index) and new NPC."""

    def __init__(self, app):
        self.app = app
        self.result = None
        idx = app.index
        self.win = tk.Toplevel(app.root)
        self.win.title(t('speaker.dialog.title'))
        self.win.transient(app.root)
        self.win.geometry('560x520')
        theme.dark_titlebar(self.win)
        nb = ttk.Notebook(self.win)
        nb.pack(fill='both', expand=True, padx=10, pady=10)
        self.nb = nb

        # -- existing --------------------------------------------------------
        ex = ttk.Frame(nb, padding=10)
        nb.add(ex, text=' ' + t('speaker.existing') + ' ')
        ttk.Label(ex, text=t('speaker.search')).pack(anchor='w')
        self.q = tk.StringVar()
        ent = ttk.Entry(ex, textvariable=self.q)
        ent.pack(fill='x', pady=(2, 6))
        ent.bind('<KeyRelease>', lambda e: self._filter())
        ent.bind('<Down>', lambda e: self.lst.focus_set())
        box = ttk.Frame(ex)
        box.pack(fill='both', expand=True)
        self.lst = tk.Listbox(box, font=theme.FONT, activestyle='none')
        sb = ttk.Scrollbar(box, orient='vertical', command=self.lst.yview)
        self.lst.configure(yscrollcommand=sb.set)
        self.lst.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.lst.bind('<Double-Button-1>', lambda e: self._ok())
        self.lst.bind('<Return>', lambda e: self._ok())
        # all candidates: own NPCs of the project first, then the index
        self.cands = []
        own = {}
        for qq in app.project.quests:
            for s in qq.speakers:
                if s.get('new'):
                    own[s['id']] = s
        for sid, s in sorted(own.items()):
            self.cands.append((f"{s['name']}  (NPC_{sid}, {s.get('tile', '?')})"
                               f"  [{t('speaker.own')}]", dict(s)))
        if idx:
            for key, n in sorted(idx.npcs.items(),
                                 key=lambda kv: kv[1]['name'].lower()):
                nid = int(key)
                if nid in own:
                    continue
                self.cands.append(
                    (f"{n['name']}  (NPC_{nid}, {n['tile']})",
                     {'id': nid, 'name': n['name'], 'lector': n['lector'],
                      'tile': n['tile'], 'new': False}))
        self.shown = []
        self._filter()
        ent.focus_set()

        # -- new ---------------------------------------------------------------
        nw = ttk.Frame(nb, padding=10)
        nb.add(nw, text=' ' + t('speaker.newnpc') + ' ')
        nw.columnconfigure(1, weight=1)
        self.v_id = tk.StringVar()
        self.v_name = tk.StringVar()
        self.v_tile = tk.StringVar()
        self.v_lector = tk.StringVar(value=t('speaker.lector.none'))
        self.v_marker = tk.StringVar()
        self.v_template = tk.StringVar()
        tile_row = ttk.Frame(nw)
        ttk.Entry(tile_row, textvariable=self.v_tile).pack(side='left',
                                                           fill='x',
                                                           expand=True)
        ttk.Button(tile_row, text='...', width=3, command=self._pick_tile
                   ).pack(side='left', padx=(4, 0))
        tpl_row = ttk.Frame(nw)
        ttk.Entry(tpl_row, textvariable=self.v_template).pack(
            side='left', fill='x', expand=True)
        ttk.Button(tpl_row, text='...', width=3, command=self._pick_template
                   ).pack(side='left', padx=(4, 0))
        rows = ((t('speaker.id'), ttk.Entry(nw, textvariable=self.v_id)),
                (t('speaker.name'), ttk.Entry(nw, textvariable=self.v_name)),
                (t('speaker.tile'), tile_row),
                (t('insp.speaker.marker'),
                 ttk.Entry(nw, textvariable=self.v_marker)),
                (t('insp.speaker.template'), tpl_row))
        for r, (label, w) in enumerate(rows):
            ttk.Label(nw, text=label).grid(row=r, column=0, sticky='w',
                                           pady=3, padx=(0, 8))
            w.grid(row=r, column=1, sticky='ew', pady=3)
        self.lectors = [(t('speaker.lector.none'), None)]
        if idx:
            for lec, ids in sorted(idx.lectors.items(), key=lambda kv: int(kv[0])):
                names = ', '.join(idx.npcs[str(i)]['name'] for i in ids[:3]
                                  if str(i) in idx.npcs)
                self.lectors.append((t('speaker.lector.of', names=names,
                                       n=lec), int(lec)))
        ttk.Label(nw, text=t('speaker.lector')).grid(row=5, column=0,
                                                     sticky='w', pady=3)
        cb = ttk.Combobox(nw, textvariable=self.v_lector, state='readonly',
                          values=[l for l, _ in self.lectors])
        cb.grid(row=5, column=1, sticky='ew', pady=3)
        ttk.Label(nw, text=t('speaker.hint'), wraplength=480,
                  style='Muted.TLabel').grid(row=6, column=0, columnspan=2,
                                             sticky='w', pady=(12, 0))
        self.err = ttk.Label(nw, text='', foreground=theme.ERR, wraplength=480)
        self.err.grid(row=7, column=0, columnspan=2, sticky='w', pady=(8, 0))

        b = ttk.Frame(self.win)
        b.pack(anchor='e', padx=10, pady=(0, 10))
        ttk.Button(b, text=t('ok'), style='Accent.TButton',
                   command=self._ok).pack(side='left', padx=(0, 6))
        ttk.Button(b, text=t('cancel'), command=self.win.destroy).pack(side='left')
        self.win.bind('<Escape>', lambda e: self.win.destroy())
        self.win.grab_set()

    def _pick_tile(self):
        if not self.app.index:
            return
        from .mappicker import MapPicker
        dlg = MapPicker(self.app, 'tile', None, self.v_tile.get())
        self.app.root.wait_window(dlg.win)
        if dlg.result:
            self.v_tile.set(str(dlg.result['value']))
        self.win.grab_set()

    def _pick_template(self):
        """NPC of the game whose record (look, party, guild) the new NPC
        copies; the picker also fills the home tile when it is empty."""
        if not self.app.index:
            return
        from .mappicker import MapPicker
        dlg = MapPicker(self.app, 'npc', None, self.v_tile.get())
        self.app.root.wait_window(dlg.win)
        if dlg.result:
            self.v_template.set(f"NPC_{dlg.result['value']}")
            if not self.v_tile.get().strip() and dlg.result.get('tile'):
                self.v_tile.set(dlg.result['tile'])
        self.win.grab_set()

    def _filter(self):
        q = self.q.get().strip().lower()
        self.lst.delete(0, 'end')
        self.shown = []
        for label, spk in self.cands:
            if not q or q in label.lower():
                self.shown.append(spk)
                self.lst.insert('end', label)
                if len(self.shown) >= 400:
                    break
        if self.shown:
            self.lst.selection_set(0)

    def _ok(self):
        if self.nb.index('current') == 0:
            sel = self.lst.curselection()
            if not sel:
                return
            self.result = dict(self.shown[sel[0]])
            self.win.destroy()
            return
        # new NPC
        m = re.fullmatch(r'(?:NPC_)?(\d+)', self.v_id.get().strip())
        if not m:
            self.err.configure(text=t('speaker.id.invalid'))
            return
        nid = int(m.group(1))
        if self.app.index and self.app.index.npc(nid):
            self.err.configure(text=t('speaker.id.taken', id=nid,
                                      name=self.app.index.npc(nid)['name']))
            return
        name = self.v_name.get().strip() or f'NPC_{nid}'
        lector = dict(self.lectors).get(self.v_lector.get())
        self.result = {'id': nid, 'name': name, 'lector': lector,
                       'tile': self.v_tile.get().strip().upper(), 'new': True}
        mk = re.fullmatch(r'\d+', self.v_marker.get().strip())
        if mk:
            self.result['marker'] = int(mk.group(0))
        tp = re.fullmatch(r'(?:NPC_)?(\d+)', self.v_template.get().strip())
        if tp:
            self.result['template'] = int(tp.group(1))
        self.win.destroy()
