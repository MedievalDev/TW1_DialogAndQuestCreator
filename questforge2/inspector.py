"""Right side bar: property forms per node type and the quest panel.

Every edit goes through the undo stack (one snapshot per field focus),
then the node is redrawn in the graph.
"""

import tkinter as tk
from tkinter import ttk

from . import data, model, theme
from .i18n import t

CAMS = ((None, 'cam.default'), (2, 'cam.npc'), (1, 'cam.npc2'),
        (7, 'cam.hero'), (6, 'cam.hero2'))
GIVER_TYPES = ('ACTIVE', 'PASSIVE')
MAP_SIGNS = ('BACK_TO_GIVER_MAP_SIGN', 'AUTO_CLOSE_ON_SOLVE', 'BACK_TO_GIVER',
             'NONE')


class Inspector(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, style='Panel.TFrame')
        self.app = app
        self.current = None            # ('quest',) | ('node', nid) | ('multi', n)
        self._undo_for = None          # widget that already pushed a snapshot
        self.title = ttk.Label(self, text=t('panel.inspector'),
                               style='PanelTitle.TLabel')
        self.title.pack(anchor='w', fill='x')
        # scrollable body
        outer = ttk.Frame(self, style='Panel.TFrame')
        outer.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(outer, bg=theme.PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = ttk.Frame(self.canvas, style='Panel.TFrame', padding=(10, 4))
        self._win = self.canvas.create_window((0, 0), window=self.body,
                                              anchor='nw')
        self.body.bind('<Configure>', lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(
            self._win, width=e.width))
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.text_widget = None
        self.show(set())

    def _wheel(self, ev):
        self.canvas.yview_scroll(-1 if ev.delta > 0 else 1, 'units')

    # -- dispatch -----------------------------------------------------------

    def show(self, selected):
        q = self.app.quest
        if not q:
            self.current = None
            self._clear()
            ttk.Label(self.body, text=t('quest.noquest'),
                      style='PanelMuted.TLabel').pack(anchor='w')
            return
        ids = [i for i in selected if i in q.graph['nodes']]
        if len(ids) == 1:
            self.current = ('node', ids[0])
        elif len(ids) > 1:
            self.current = ('multi', len(ids))
        else:
            self.current = ('quest',)
        self.refresh()

    def refresh(self):
        self._clear()
        self._undo_for = None
        self.text_widget = None
        cur = self.current
        if not cur or not self.app.quest:
            return
        if cur[0] == 'quest':
            self._quest_form()
        elif cur[0] == 'multi':
            ttk.Label(self.body, text=t('insp.multi', n=cur[1]),
                      style='PanelMuted.TLabel').pack(anchor='w')
        else:
            node = self.app.quest.graph['nodes'].get(cur[1])
            if node is None:
                self.current = ('quest',)
                self._quest_form()
            elif node['type'] == 'entry':
                self._entry_form(cur[1], node)
            elif node['type'] == 'comment':
                self._comment_form(cur[1], node)
            else:
                self._dialog_form(cur[1], node)
        self.canvas.yview_moveto(0)

    def focus_text(self):
        if self.text_widget:
            self.text_widget.focus_set()

    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    # -- helpers ------------------------------------------------------------

    def _edit(self, widget, fn, nid=None, redraw=True):
        """Apply a change from a field: one undo snapshot per widget focus."""
        if self._undo_for is not widget:
            self.app.push_undo('edit')
            self._undo_for = widget
        fn()
        if nid and redraw:
            self.app.graph.redraw_node(nid)
        self.app.changed(from_inspector=True)

    def _label(self, text, muted=False):
        ttk.Label(self.body, text=text,
                  style='PanelMuted.TLabel' if muted else 'Panel.TLabel'
                  ).pack(anchor='w', pady=(8, 1))

    def _entry(self, value, on_change, nid=None):
        var = tk.StringVar(value=value)
        e = ttk.Entry(self.body, textvariable=var)
        e.pack(fill='x')
        e.bind('<FocusIn>', lambda ev: self._reset_undo(e))
        e.bind('<KeyRelease>', lambda ev: self._edit(
            e, lambda: on_change(var.get()), nid))
        return e

    def _text(self, value, on_change, nid=None, height=4):
        tw = tk.Text(self.body, height=height, wrap='word', font=theme.FONT,
                     undo=False)
        tw.insert('1.0', value or '')
        tw.pack(fill='x')
        tw.bind('<FocusIn>', lambda ev: self._reset_undo(tw))
        tw.bind('<KeyRelease>', lambda ev: self._edit(
            tw, lambda: on_change(tw.get('1.0', 'end-1c')), nid))
        return tw

    def _combo(self, values, current, on_change, nid=None, labels=None):
        labels = labels or [str(v) for v in values]
        var = tk.StringVar(value=labels[values.index(current)]
                           if current in values else '')
        cb = ttk.Combobox(self.body, textvariable=var, state='readonly',
                          values=labels)
        cb.pack(fill='x')
        cb.bind('<<ComboboxSelected>>', lambda ev: self._edit(
            cb, lambda: on_change(values[labels.index(var.get())]), nid))
        return cb

    def _check(self, text, current, on_change, nid=None, parent=None):
        var = tk.BooleanVar(value=bool(current))
        cb = ttk.Checkbutton(parent or self.body, text=text, variable=var,
                             style='Panel.TCheckbutton')
        cb.pack(anchor='w')
        cb.configure(command=lambda: self._edit(
            cb, lambda: on_change(var.get()), nid))
        return cb

    def _reset_undo(self, widget):
        if self._undo_for is not widget:
            self._undo_for = None

    # -- forms --------------------------------------------------------------

    def _quest_form(self):
        q = self.app.quest
        idx = self.app.index
        self.title.configure(text=t('insp.quest'))
        taken = {qq.id for qq in self.app.project.quests if qq is not q}
        free = (idx.free_ids(taken) if idx else
                [i for i in range(data.MIN_QUEST_ID, data.MAX_QUEST_ID + 1)
                 if i not in taken])
        if q.id and q.id not in free:
            free = sorted(free + [q.id])
        self._label(t('insp.id'))
        self._combo(free, q.id, lambda v: setattr(q, 'id', v),
                    labels=[f'Q_{i}' for i in free])
        ttk.Label(self.body, text=t('insp.id.hint'), style='PanelMuted.TLabel',
                  wraplength=260).pack(anchor='w')
        self._label(t('insp.title'))
        self._entry(q.title, lambda v: setattr(q, 'title', v))
        self._label(t('insp.group'))
        groups = sorted(((int(k), v) for k, v in idx.groups.items()), key=lambda kv: kv[0]) \
            if idx else []
        gvals = [g for g, _ in groups]
        glabels = [f'{g}  {name}' for g, name in groups]
        if q.group not in gvals:
            gvals.insert(0, q.group)
            glabels.insert(0, str(q.group))
        self._combo(gvals, q.group, lambda v: setattr(q, 'group', v),
                    labels=glabels)
        for key, lk in (('take', 'insp.journal.take'),
                        ('solve', 'insp.journal.solve'),
                        ('close', 'insp.journal.close')):
            self._label(t(lk))
            self._text(q.journal.get(key, ''),
                       lambda v, k=key: q.journal.__setitem__(k, v), height=3)
        self._label(t('insp.giver'))
        svals = [None] + [s['id'] for s in q.speakers]
        slabels = ['-'] + [self.app.speaker_style(s['id'])[0] for s in q.speakers]
        self._combo(svals, q.giver, lambda v: setattr(q, 'giver', v),
                    labels=slabels)
        self._label(t('insp.giver_type'))
        self._combo(list(GIVER_TYPES), q.giver_type,
                    lambda v: setattr(q, 'giver_type', v))
        self._label(t('insp.map_sign'))
        self._combo(list(MAP_SIGNS), q.map_sign,
                    lambda v: setattr(q, 'map_sign', v))
        ttk.Label(self.body, text=t('insp.map_sign.hint'),
                  style='PanelMuted.TLabel', wraplength=260).pack(anchor='w')
        self._label(t('insp.offered'))
        self._check(t('insp.offered.check'), q.offered,
                    lambda v: setattr(q, 'offered', v))
        self._label(t('insp.archive'))
        archives = self.app.mod_archives()
        var = tk.StringVar(value=self.app.project.target_archive)
        cb = ttk.Combobox(self.body, textvariable=var, values=archives)
        cb.pack(fill='x')
        cb.bind('<<ComboboxSelected>>', lambda ev: self._edit(
            cb, lambda: setattr(self.app.project, 'target_archive', var.get())))
        cb.bind('<KeyRelease>', lambda ev: self._edit(
            cb, lambda: setattr(self.app.project, 'target_archive', var.get())))

    def _entry_form(self, nid, node):
        self.title.configure(text=t('node.entry') + ' ' + t('state.' + node['state']))
        ttk.Label(self.body, text=t('insp.entry.' + node['state']),
                  style='Panel.TLabel', wraplength=260).pack(anchor='w', pady=4)
        ttk.Label(self.body, text=t('insp.entry.cond'),
                  style='PanelMuted.TLabel', wraplength=260).pack(anchor='w', pady=4)

    def _comment_form(self, nid, node):
        self.title.configure(text=t('node.comment'))
        self._label(t('insp.text'))
        self.text_widget = self._text(node.get('text', ''),
                                      lambda v: node.__setitem__('text', v), nid)
        self._label(t('insp.color'))
        row = ttk.Frame(self.body, style='Panel.TFrame')
        row.pack(anchor='w')
        for c in [theme.COMMENT_COLOR] + theme.SPEAKER_COLORS:
            b = tk.Canvas(row, width=18, height=18, bg=c, highlightthickness=1,
                          highlightbackground=theme.LINE, cursor='hand2')
            b.pack(side='left', padx=2)
            b.bind('<Button-1>', lambda e, c=c: self._edit(
                b, lambda: node.__setitem__('color', c), nid))

    def _dialog_form(self, nid, node):
        q = self.app.quest
        is_player = node['type'] == 'player'
        self.title.configure(text=self.app.speaker_style(node.get('speaker'))[0]
                             if not is_player else t('node.player'))
        if not is_player:
            self._label(t('insp.speaker'))
            svals = [s['id'] for s in q.speakers]
            slabels = [self.app.speaker_style(s['id'])[0] for s in q.speakers]
            if node.get('speaker') not in svals:
                svals.insert(0, node.get('speaker'))
                slabels.insert(0, '-')
            self._combo(svals, node.get('speaker'),
                        lambda v: node.__setitem__('speaker', v), nid,
                        labels=slabels)
        self._label(t('insp.state'))
        self._combo(list(model.STATES), node.get('state'),
                    lambda v: node.__setitem__('state', v), nid,
                    labels=[t('state.' + s) for s in model.STATES])
        ttk.Label(self.body, text=t('state.help.' + node.get('state', 'first')),
                  style='PanelMuted.TLabel', wraplength=260).pack(anchor='w')
        if is_player:
            self._label(t('insp.kind'))
            self._combo(['answer', 'question'], node.get('kind', 'answer'),
                        lambda v: self.app.graph.set_kind(nid, v), nid,
                        labels=[t('insp.kind.answer'), t('insp.kind.question')])
        lines = node.get('lines') or []
        many = is_player and node.get('kind') == 'question'
        for i, line in enumerate(lines):
            if many:
                self._label(t('insp.line', n=i + 1))
            else:
                self._label(t('insp.text'))
            tw = self._text(line.get('text', ''),
                            lambda v, ln=line: ln.__setitem__('text', v), nid,
                            height=3 if not many else 2)
            if i == 0:
                self.text_widget = tw
            self._line_flags(nid, line, node)
            self._cue_row(nid, line, node)
        if many:
            ttk.Button(self.body, text='+ ' + t('insp.addline'),
                       command=lambda: self.app.graph._add_line(nid)
                       ).pack(anchor='w', pady=(6, 0))
        self._label(t('insp.advanced'), muted=True)
        self._label(t('insp.cam'))
        cams = [c for c, _ in CAMS]
        line0 = lines[0] if lines else model.new_line()
        self._combo(cams, line0.get('cam'),
                    lambda v: [ln.__setitem__('cam', v) for ln in lines], nid,
                    labels=[t(k) for _, k in CAMS])
        self._label(t('insp.anim'))
        var = tk.StringVar(value=str(line0.get('anim', 0)))
        sp = ttk.Spinbox(self.body, from_=0, to=17, textvariable=var, width=6)
        sp.pack(anchor='w')
        sp.bind('<KeyRelease>', lambda ev: self._edit(
            sp, lambda: [ln.__setitem__('anim', _int(var.get())) for ln in lines],
            nid, redraw=False))
        sp.configure(command=lambda: self._edit(
            sp, lambda: [ln.__setitem__('anim', _int(var.get())) for ln in lines],
            nid, redraw=False))

    def _line_flags(self, nid, line, node):
        row = ttk.Frame(self.body, style='Panel.TFrame')
        row.pack(fill='x')
        self._check(t('insp.take'), line.get('take'),
                    lambda v: line.__setitem__('take', v), nid, parent=row)
        self._check(t('insp.close'), line.get('close'),
                    lambda v: line.__setitem__('close', v), nid, parent=row)
        self._check(t('insp.fight'), line.get('fight'),
                    lambda v: line.__setitem__('fight', v), nid, parent=row)

    def _cue_row(self, nid, line, node):
        idx = self.app.index
        row = ttk.Frame(self.body, style='Panel.TFrame')
        row.pack(fill='x', pady=(2, 0))
        cue = line.get('cue') or ''
        ttk.Label(row, text=t('insp.cue') + ': ' + (cue or '-'),
                  style='Panel.TLabel').pack(side='left')
        ttk.Button(row, text=t('insp.cue.search'), width=10,
                   command=lambda: self._search_cue(nid, line, node)
                   ).pack(side='right')
        if cue:
            ttk.Button(row, text='×', width=2, command=lambda: self._edit(
                row, lambda: (line.__setitem__('cue', ''), self.refresh()), nid)
                       ).pack(side='right', padx=2)
        if cue and idx and cue in idx.cues:
            orig = idx.cues[cue][1]
            ttk.Label(self.body, text=t('insp.cue.text') + ' ' + orig,
                      style='PanelMuted.TLabel', wraplength=260).pack(anchor='w')
            if _norm(orig) != _norm(line.get('text', '')):
                ttk.Label(self.body, text=t('insp.cue.mismatch'),
                          foreground=theme.ERR, background=theme.PANEL,
                          wraplength=260).pack(anchor='w')

    def _search_cue(self, nid, line, node):
        if not self.app.index:
            return
        lector = 1
        if node['type'] == 'npc':
            spk = self.app.quest.speaker(node.get('speaker'))
            lector = spk.get('lector') if spk else None
        dlg = CueDialog(self.app, lector, line.get('cue') or '')
        self.app.root.wait_window(dlg.win)
        if dlg.result is not None:
            self._edit(dlg, lambda: line.__setitem__('cue', dlg.result), nid)
            self.refresh()


def _int(s):
    try:
        return max(0, int(s))
    except ValueError:
        return 0


def _norm(s):
    return ' '.join((s or '').split()).lower()


class CueDialog:
    """Search the cue index (plan 5.2): filter by the speaker's lector and
    by text, preview the recorded line."""

    def __init__(self, app, lector, current):
        self.app = app
        self.result = None
        idx = app.index
        self.win = tk.Toplevel(app.root)
        self.win.title(t('cue.title'))
        self.win.transient(app.root)
        self.win.geometry('640x520')
        theme.dark_titlebar(self.win)
        f = ttk.Frame(self.win, padding=10)
        f.pack(fill='both', expand=True)
        top = ttk.Frame(f)
        top.pack(fill='x')
        ttk.Label(top, text=t('cue.filter')).pack(side='left')
        self.q = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.q)
        ent.pack(side='left', fill='x', expand=True, padx=6)
        ent.bind('<KeyRelease>', lambda e: self._filter())
        self.only = tk.BooleanVar(value=lector is not None)
        chk = ttk.Checkbutton(top, text=t('cue.lector.speaker', n=lector
                                          if lector is not None else '-'),
                              variable=self.only, command=self._filter)
        chk.pack(side='left')
        if lector is None:
            chk.state(['disabled'])
        box = ttk.Frame(f)
        box.pack(fill='both', expand=True, pady=6)
        self.lst = tk.Listbox(box, font=theme.FONT, activestyle='none')
        sb = ttk.Scrollbar(box, orient='vertical', command=self.lst.yview)
        self.lst.configure(yscrollcommand=sb.set)
        self.lst.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.lst.bind('<<ListboxSelect>>', lambda e: self._preview())
        self.lst.bind('<Double-Button-1>', lambda e: self._ok())
        self.preview = ttk.Label(f, text='', wraplength=600, style='Muted.TLabel')
        self.preview.pack(anchor='w')
        self.count = ttk.Label(f, text='', style='Muted.TLabel')
        self.count.pack(anchor='w')
        b = ttk.Frame(f)
        b.pack(anchor='e', pady=(8, 0))
        ttk.Button(b, text=t('ok'), style='Accent.TButton',
                   command=self._ok).pack(side='left', padx=(0, 6))
        ttk.Button(b, text=t('cancel'), command=self.win.destroy).pack(side='left')
        self.win.bind('<Escape>', lambda e: self.win.destroy())
        self.lector = lector
        # (cue, lector, text) sorted by cue
        self.all = sorted((c, v[0], v[1]) for c, v in idx.cues.items())
        self.shown = []
        self._filter()
        ent.focus_set()
        self.win.grab_set()

    def _filter(self):
        q = self.q.get().strip().lower()
        only = self.only.get() and self.lector is not None
        self.lst.delete(0, 'end')
        self.shown = []
        for cue, lec, text in self.all:
            if only and lec != self.lector:
                continue
            if q and q not in text.lower() and q not in cue.lower():
                continue
            self.shown.append((cue, lec, text))
            self.lst.insert('end', f'{cue}  [{lec}]  {text[:90]}')
            if len(self.shown) >= 500:
                break
        self.count.configure(text=t('cue.count', n=len(self.shown)))
        if self.shown:
            self.lst.selection_set(0)
            self._preview()

    def _preview(self):
        sel = self.lst.curselection()
        if sel:
            self.preview.configure(text=self.shown[sel[0]][2])

    def _ok(self):
        sel = self.lst.curselection()
        if sel:
            self.result = self.shown[sel[0]][0]
            self.win.destroy()
