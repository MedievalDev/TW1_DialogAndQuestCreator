"""The guides in the coach panel (plan section 9) and the docs window.

The guides run inside the coach panel, not as modal dialogs, so the tool
stays usable. The third one (4.3.0) leads through taking a multiplayer quest
over, across the windows it opens, with green frames on what to click and
red ones on what is missing (Marks). A step has a heading, a short text and a gold frame around the
element it talks about. The tour only explains. The tutorial checks the
state after every step: "Next" stays disabled until the step is done and
the coach moves on by itself once it is; every step also offers a button
that does the step for the user.
"""

import os
import re
import sys
import tkinter as tk
from tkinter import ttk

from . import data, model, theme
from .i18n import t
from .model import entry_id

POLL_MS = 700
BORDER = 3
MARK_BORDER = 4
GREEN, RED = theme.OK, theme.ERR


# ---------------------------------------------------------------------------
# step definitions

def tour_steps(app):
    return [
        {'key': 'tour.welcome', 'target': lambda: app.graph},
        {'key': 'tour.timeline', 'target': lambda: app.timeline.canvas},
        {'key': 'tour.newquest', 'target': lambda: app.timeline.new_btn},
        {'key': 'tour.speakers', 'target': lambda: app.speakers},
        {'key': 'tour.player', 'target': lambda: app.graph},
        {'key': 'tour.npc', 'target': lambda: app.graph},
        {'key': 'tour.edges', 'target': lambda: app.graph},
        {'key': 'tour.levels', 'target': lambda: app.tabstrip},
        {'key': 'tour.task', 'target': lambda: app.actions.task},
        {'key': 'tour.actions', 'target': lambda: app.actions.action},
        {'key': 'tour.conditions', 'target': lambda: app.actions.cond},
        {'key': 'tour.inspector', 'target': lambda: app.inspector},
        {'key': 'tour.validate', 'target': lambda: app.status['validation']},
        {'key': 'tour.export', 'target': lambda: app.menubar},
        {'key': 'tour.end', 'target': None, 'final': True},
    ]


class Tutorial:
    """State checks and "do it for me" actions of the test quest."""

    GIVER = 3                # Tago, stands at the game start
    GOLD_TASK = 100
    GOLD_REWARD = 500

    def __init__(self, app):
        self.app = app
        self.quest = None
        self.exported = False

    # -- helpers --------------------------------------------------------------

    def q(self):
        app = self.app
        if self.quest is not None and app.project and \
                self.quest in app.project.quests:
            return self.quest
        if app.project:
            own = [q for q in app.project.quests if not q.retail]
            if app.quest in own:
                self.quest = app.quest
            elif own:
                self.quest = own[-1]
            else:
                self.quest = None
        return self.quest

    def _show(self):
        q = self.q()
        if q is not None and self.app.quest is not q:
            self.app.open_quest(q)
        return q

    @staticmethod
    def _npc_after(g, frm, port=0, state=None):
        e = model.edge_from(g, frm, port)
        if not e:
            return None
        n = g['nodes'].get(e[2])
        if n and n['type'] == 'npc' and (n['lines'][0].get('text') or '').strip() \
                and (state is None or n.get('state') == state):
            return e[2]
        return None

    @staticmethod
    def _question_after(g, frm):
        e = model.edge_from(g, frm, 0)
        if not e:
            return None
        n = g['nodes'].get(e[2])
        if n and n['type'] == 'player' and n.get('kind') == 'question' and \
                len(n['lines']) >= 2 and all((ln.get('text') or '').strip()
                                             for ln in n['lines'][:2]):
            return e[2]
        return None

    def _add_npc(self, frm, port, state, text):
        app = self.app
        g = self.q().graph
        src = g['nodes'][frm]
        w, h = model.node_size(src)
        app.push_undo('tutorial')
        node = model.make_node('npc', src['x'] + w + 80, src['y'], state,
                               self.GIVER)
        node['lines'][0]['text'] = text
        nid = model.add_node(g, node)
        model.connect(g, frm, port, nid)
        return nid

    def _done(self):
        app = self.app
        app.graph.set_graph(app.quest.graph)
        app.changed()

    # -- checks ---------------------------------------------------------------

    def check_new(self):
        return self.q() is not None

    def check_texts(self):
        q = self.q()
        return bool(q and q.title.strip() and all(
            (q.journal.get(k) or '').strip() for k in ('take', 'solve', 'close')))

    def check_speaker(self):
        q = self.q()
        return bool(q and q.speaker(self.GIVER) and any(
            c.get('cond') == 'after' for c in q.conditions_list()))

    def check_offer(self):
        q = self.q()
        return bool(q and self._npc_after(q.graph, entry_id('first')))

    def check_question(self):
        q = self.q()
        if not q:
            return False
        n1 = self._npc_after(q.graph, entry_id('first'))
        return bool(n1 and self._question_after(q.graph, n1))

    def check_answer(self):
        q = self.q()
        if not q:
            return False
        g = q.graph
        n1 = self._npc_after(g, entry_id('first'))
        p = n1 and self._question_after(g, n1)
        return bool(p and g['nodes'][p]['lines'][0].get('take')
                    and self._npc_after(g, p, 0))

    def check_solved(self):
        q = self.q()
        if not q:
            return False
        g = q.graph
        task = q.task()
        if task.get('fc') != 'BRING_GOLD' or str(task['args'].get('gold')) \
                != str(self.GOLD_TASK):
            return False
        s = self._npc_after(g, entry_id('solved'))
        return bool(s and any(
            n.get('verb') == 'GLD' and n.get('attached_to') == s and
            str(n['args'].get('amount')) == str(self.GOLD_REWARD)
            for _, n in q.graph_actions()))

    def check_levels(self):
        q = self.q()
        return bool(q and self._npc_after(q.graph, entry_id('running'))
                    and self._npc_after(q.graph, entry_id('closed')))

    def check_validate(self):
        q = self.q()
        if not q:
            return False
        from .validate import validate_quest
        from .export import archive_name
        E, _ = validate_quest(q, self.app.index, self.app.project,
                              archive_name(self.app.project))
        return not E

    def check_export(self):
        return self.exported

    # -- do it for me ---------------------------------------------------------

    def do_new(self):
        self.app.new_quest()
        self.quest = self.app.quest

    def do_texts(self):
        q = self._show()
        if not q:
            return
        self.app.push_undo('tutorial')
        q.title = q.title.strip() or t('tut.sugg.title')
        for k in ('take', 'solve', 'close'):
            if not (q.journal.get(k) or '').strip():
                q.journal[k] = t('tut.sugg.' + k)
        self.app.changed()

    def do_speaker(self):
        q = self._show()
        idx = self.app.index
        if not q:
            return
        npc = idx.npc(self.GIVER) if idx else None
        self.app.add_speaker({'id': self.GIVER,
                              'name': npc['name'] if npc else 'Tago',
                              'lector': npc['lector'] if npc else 123,
                              'tile': npc['tile'] if npc else 'E1',
                              'new': False})
        if not any(c.get('cond') == 'after' for c in q.conditions_list()):
            self.app.push_undo('tutorial')
            model.add_node(q.graph, model.make_condition('after', quest=4))
            model.restack(q.graph)
        q.giver = self.GIVER
        self._done()

    def do_offer(self):
        q = self._show()
        if not q:
            return
        if not q.speaker(self.GIVER):
            self.do_speaker()
        self.app.show_tab('first')
        g = q.graph
        e = model.edge_from(g, entry_id('first'), 0)
        if e and g['nodes'][e[2]]['type'] == 'npc':
            self.app.push_undo('tutorial')
            g['nodes'][e[2]]['lines'][0]['text'] = t('tut.sugg.offer')
        else:
            self._add_npc(entry_id('first'), 0, 'first', t('tut.sugg.offer'))
        self._done()

    def do_question(self):
        q = self._show()
        if not q:
            return
        if not self.check_offer():
            self.do_offer()
        g = q.graph
        n1 = self._npc_after(g, entry_id('first'))
        src = g['nodes'][n1]
        self.app.push_undo('tutorial')
        node = model.make_node('player', src['x'] + model.NODE_W + 80,
                               src['y'], 'first')
        node['kind'] = 'question'
        node['lines'] = [dict(model.new_line('first'), text=t('tut.sugg.yes')),
                         dict(model.new_line('first'), text=t('tut.sugg.no'))]
        pid = model.add_node(g, node)
        model.connect(g, n1, 0, pid)
        self._done()

    def do_answer(self):
        q = self._show()
        if not q:
            return
        if not self.check_question():
            self.do_question()
        g = q.graph
        n1 = self._npc_after(g, entry_id('first'))
        p = self._question_after(g, n1)
        self.app.push_undo('tutorial')
        g['nodes'][p]['lines'][0]['take'] = True
        if not self._npc_after(g, p, 0):
            self._add_npc(p, 0, 'first', t('tut.sugg.thanks'))
        self._done()

    def do_solved(self):
        q = self._show()
        if not q:
            return
        if not q.speaker(self.GIVER):
            self.do_speaker()
        g = q.graph
        self.app.show_tab('solved')
        self.app.push_undo('tutorial')
        model.set_task(g, 'BRING_GOLD')
        q.task()['args']['gold'] = self.GOLD_TASK
        s = self._npc_after(g, entry_id('solved'))
        if not s:
            s = self._add_npc(entry_id('solved'), 0, 'solved',
                              t('tut.sugg.reward'))
        if not any(n.get('verb') == 'GLD' and n.get('attached_to') == s
                   for _, n in q.graph_actions()):
            a = model.make_action('REWARD', 'GLD', s)
            a['args']['amount'] = str(self.GOLD_REWARD)
            model.add_node(g, a)
        model.restack(g)
        self._done()

    def do_levels(self):
        q = self._show()
        if not q:
            return
        if not q.speaker(self.GIVER):
            self.do_speaker()
        g = q.graph
        for st, key in (('running', 'tut.sugg.running'),
                        ('closed', 'tut.sugg.closed')):
            if not self._npc_after(g, entry_id(st)):
                self._add_npc(entry_id(st), 0, st, t(key))
        self._done()

    def do_validate(self):
        self._show()
        self.app.validate_ui()

    def do_export(self):
        self._show()
        self.app.export_ui()


# ---------------------------------------------------------------------------
# guided tour: a multiplayer quest into the single player (4.3.0)

def mp_steps(app, coach):
    """Step by step through the one-page window, the map and the export.
    Every step says with green frames where to click and with red ones
    what is still missing; the coach finds the current step from the state
    of the windows (Coach._mp_current), so closing a window goes back."""
    from .app import ExportConfirm, NewQuestDialog
    from .mpmerge import MpMergeWindow, target_ready

    def alive(obj):
        try:
            return obj is not None and bool(obj.win.winfo_exists())
        except tk.TclError:
            return False

    def dlg():
        d = NewQuestDialog._open
        return d if alive(d) else None

    def mpw():
        w = MpMergeWindow._open
        return w if alive(w) else None

    def pw():
        w = mpw()
        p = getattr(w, 'place_win', None) if w else None
        return p if alive(p) else None

    def exp():
        d = ExportConfirm._open
        return d if alive(d) else None

    def markers_ok():
        w = mpw()
        return bool(w and w.src is not None and
                    all(target_ready(tg) for tg in w.targets))

    def fill_ok():
        w = mpw()
        return bool(w and w.src is not None and
                    not [k for k, _w in w.missing() if k != 'markers'])

    def map_ok():
        p = pw()
        if p is not None:
            return all(tg.get('placed') for tg in p.targets)
        return markers_ok()

    def taken():
        return MpMergeWindow._open is None and any(
            q.extra.get('mp_source') and id(q) not in coach.mp_before
            for q in (app.project.quests if app.project else []))

    def new_btn():
        return [(app.timeline.new_btn, GREEN, t('mpt.c.click'))]

    def m_mode():
        d = dlg()
        if d is None:
            return new_btn()
        if d.how.get() != 'mp':
            return [(d.radios['mp'], GREEN, t('mpt.c.click'))]
        return [(d.ok_btn, GREEN, t('mpt.c.click'))]

    def m_pick():
        w = mpw()
        return [(w.tree, GREEN, t('mpt.c.pick'))] if w else []

    def m_fill():
        w = mpw()
        if not w:
            return []
        miss = [(wid, RED, None) for k, wid in w.missing() if k != 'markers']
        if miss:
            miss[0] = (miss[0][0], RED, t('mpt.c.missing'))
        return miss

    def m_place():
        w = mpw()
        return [(w.place_btn, GREEN, t('mpt.c.click'))] if w else []

    def m_map():
        p = pw()
        if p is None:
            return []
        if p.held is None:
            for tg in p.targets:
                if not tg.get('placed'):
                    row = getattr(p, 'row_of', {}).get(id(tg))
                    return [(row, GREEN, t('mpt.c.take'))]
            return []
        return [(p.c, GREEN, t('mpt.c.drop'))]

    def m_confirm():
        p = pw()
        return [(p.ok_btn, GREEN, t('mpt.c.confirm'))] if p else []

    def m_take():
        w = mpw()
        if not w:
            return []
        out = [(w.take_btn, GREEN, t('mpt.c.take2'))]
        out += [(wid, RED, None) for _k, wid in w.missing()]
        return out

    def m_export():
        return [(app.menu_items.get('menu.file'), GREEN, t('mpt.c.export'))]

    def m_exportok():
        d = exp()
        return [(d.ok_btn, GREEN, t('mpt.c.click'))] if d else m_export()

    return [
        {'key': 'mpt.new', 'marks': new_btn,
         'check': lambda: dlg() is not None or mpw() is not None},
        {'key': 'mpt.mode', 'marks': m_mode,
         'check': lambda: mpw() is not None},
        {'key': 'mpt.pick', 'marks': m_pick,
         'check': lambda: bool(mpw() and mpw().src is not None)},
        {'key': 'mpt.fill', 'marks': m_fill, 'check': fill_ok},
        {'key': 'mpt.place', 'marks': m_place,
         'check': lambda: pw() is not None or markers_ok()},
        {'key': 'mpt.map', 'marks': m_map, 'check': map_ok},
        {'key': 'mpt.confirm', 'marks': m_confirm,
         'check': lambda: pw() is None and markers_ok()},
        {'key': 'mpt.take', 'marks': m_take, 'check': taken,
         'milestone': True},
        {'key': 'mpt.export', 'marks': m_export,
         'check': lambda: exp() is not None or bool(
             getattr(app, 'exported_ok', False))},
        {'key': 'mpt.exportok', 'marks': m_exportok,
         'check': lambda: bool(getattr(app, 'exported_ok', False)),
         'milestone': True},
        {'key': 'mpt.done', 'final': True},
    ]


class Marks:
    """Frames around widgets in whatever window they sit in (4.3.0, Marco:
    green = click here, red = still missing) and a small label next to a
    green one that says what to do. They pulse, so the eye finds them."""

    def __init__(self):
        self.items = []             # (frames, label, colour)
        self.sig = None
        self.phase = False

    def clear(self):
        for frames, label, _c in self.items:
            for w in frames + ([label] if label is not None else []):
                try:
                    w.destroy()
                except tk.TclError:
                    pass
        self.items = []
        self.sig = None

    @staticmethod
    def _geo(widget):
        top = widget.winfo_toplevel()
        return (top, widget.winfo_rootx() - top.winfo_rootx(),
                widget.winfo_rooty() - top.winfo_rooty(),
                widget.winfo_width(), widget.winfo_height())

    def show(self, marks):
        """``marks``: [(widget, colour, text or None)]. Built again only
        when something moved; otherwise the frames just pulse."""
        todo, sig = [], []
        for widget, colour, text in marks:
            try:
                if widget is None or not widget.winfo_exists() or \
                        not widget.winfo_ismapped():
                    continue
                geo = self._geo(widget)
            except tk.TclError:
                continue
            todo.append((geo, colour, text))
            sig.append((str(geo[0]), geo[1:], colour, text))
        if sig == self.sig:
            self.pulse()
            return
        self.clear()
        self.sig = sig
        b = MARK_BORDER
        for (top, x, y, w, h), colour, text in todo:
            frames = []
            for fx, fy, fw, fh in ((x - b, y - b, w + 2 * b, b),
                                   (x - b, y + h, w + 2 * b, b),
                                   (x - b, y, b, h), (x + w, y, b, h)):
                f = tk.Frame(top, bg=colour)
                f.place(x=fx, y=fy, width=fw, height=fh)
                f.lift()
                frames.append(f)
            label = None
            if text:
                label = tk.Label(top, text=text, bg=colour, fg='#0b1a0f',
                                 font=theme.FONT_BOLD, padx=8, pady=3)
                lw, lh = label.winfo_reqwidth(), label.winfo_reqheight()
                tw, th = top.winfo_width(), top.winfo_height()
                # right of the widget, else below, else above, else inside
                lx, ly = x + w + b + 8, y + max(0, (h - lh) // 2)
                if lx + lw > tw - 4:
                    lx, ly = max(4, min(x, tw - lw - 4)), y + h + b + 6
                    if ly + lh > th - 4:
                        ly = y - b - lh - 6
                        if ly < 4:
                            lx, ly = x + 10, y + 10
                label.place(x=lx, y=ly)
                label.lift()
            self.items.append((frames, label, colour))

    def pulse(self):
        self.phase = not self.phase
        for frames, label, colour in self.items:
            c = theme.mix(colour, '#ffffff', 0.45) if self.phase else colour
            for w in frames + ([label] if label is not None else []):
                try:
                    w.configure(bg=c)
                except tk.TclError:
                    pass


def tutorial_steps(app, tut):
    s = []
    for key in ('new', 'texts', 'speaker', 'offer', 'question', 'answer',
                'solved', 'levels', 'validate', 'export'):
        s.append({'key': 'tut.' + key, 'check': getattr(tut, 'check_' + key),
                  'do': getattr(tut, 'do_' + key),
                  'target': _tut_target(app, key)})
    s.append({'key': 'tut.done', 'target': None, 'final': True})
    return s


def _tut_target(app, key):
    return {
        'new': lambda: app.timeline.new_btn,
        'texts': lambda: app.inspector,
        'speaker': lambda: app.speakers,
        'offer': lambda: app.graph, 'question': lambda: app.graph,
        'answer': lambda: app.graph, 'solved': lambda: app.graph,
        'levels': lambda: app.tabstrip,
        'validate': lambda: app.status['validation'],
        'export': lambda: app.menubar,
    }[key]


# ---------------------------------------------------------------------------
# coach panel

class Coach(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, style='Panel.TFrame')
        self.app = app
        self.mode = None
        self.steps = []
        self.i = 0
        self.tutorial = Tutorial(app)
        self.marks = Marks()
        self.mp_before = set()
        self._frames = []
        self._job = None
        self._advance_job = None
        self.dont_show = tk.BooleanVar(value=True)
        self.title = ttk.Label(self, text=t('panel.coach'),
                               style='PanelTitle.TLabel')
        self.title.pack(anchor='w', fill='x')
        self.body = ttk.Frame(self, style='Panel.TFrame', padding=(10, 2))
        self.body.pack(fill='both', expand=True)
        self.bind('<Configure>', self._wrap)
        self.idle()

    # -- views ----------------------------------------------------------------

    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def _wrap(self, ev=None):
        width = max(160, self.winfo_width() - 30)
        for w in self.body.winfo_children():
            if isinstance(w, ttk.Label) and str(w.cget('wraplength')) != '0':
                w.configure(wraplength=width)

    def idle(self):
        self.mode = None
        self._stop_poll()
        self._highlight(None)
        self.marks.clear()
        self._clear()
        self.title.configure(text=t('panel.coach'))
        ttk.Label(self.body, text=t('coach.idle'), style='PanelMuted.TLabel',
                  wraplength=260).pack(anchor='w', pady=(2, 8))
        row = ttk.Frame(self.body, style='Panel.TFrame')
        row.pack(anchor='w')
        ttk.Button(row, text=t('help.tour'), command=lambda: self.start('tour')
                   ).pack(side='left', padx=(0, 6))
        ttk.Button(row, text=t('coach.tutorial'),
                   command=lambda: self.start('tutorial')).pack(side='left')
        ttk.Button(self.body, text=t('coach.mptour'),
                   command=lambda: self.start('mp')).pack(anchor='w',
                                                          pady=(6, 0))
        self._wrap()

    def start(self, mode):
        self.mode = mode
        self.i = 0
        if mode == 'tour':
            self.steps = tour_steps(self.app)
        elif mode == 'mp':
            app = self.app
            self.mp_before = {id(q) for q in (app.project.quests
                                              if app.project else [])}
            app.exported_ok = False
            self.steps = mp_steps(app, self)
            self.i = self._mp_current()
            if not app.vars['coach'].get():
                app.vars['coach'].set(True)
                app._apply_panels()
        else:
            self.tutorial = Tutorial(self.app)
            self.steps = tutorial_steps(self.app, self.tutorial)
            if not self.app.vars['coach'].get():
                self.app.vars['coach'].set(True)
                self.app._apply_panels()
        self.show()

    def show(self):
        self._stop_poll()
        step = self.steps[self.i]
        key = step['key']
        self._clear()
        head = {'tour': t('coach.tour'), 'mp': t('coach.mptour')}.get(
            self.mode, t('coach.tutorial'))
        self.title.configure(text=f'{head}  ·  ' + t(
            'coach.step', i=self.i + 1, n=len(self.steps)))
        ttk.Label(self.body, text=t(key + '.title'), foreground=theme.GOLD,
                  background=theme.PANEL, font=theme.FONT_H2
                  ).pack(anchor='w', pady=(2, 2))
        ttk.Label(self.body, text=t(key + '.text'), style='Panel.TLabel',
                  wraplength=260, justify='left').pack(anchor='w', fill='x')
        self.state_lbl = None
        if step.get('check'):
            self.state_lbl = ttk.Label(self.body, text='', wraplength=260,
                                       background=theme.PANEL)
            self.state_lbl.pack(anchor='w', pady=(6, 0))
        if step.get('do'):
            ttk.Button(self.body, text=t('coach.doit'),
                       command=self._do).pack(anchor='w', pady=(6, 0))
        nav = ttk.Frame(self.body, style='Panel.TFrame')
        nav.pack(fill='x', pady=(10, 0))
        if self.mode == 'mp':
            ttk.Button(nav, text=t('coach.finish') if step.get('final')
                       else t('coach.end'), command=self.finish,
                       style='Accent.TButton' if step.get('final')
                       else 'TButton').pack(side='right')
        elif step.get('final') and self.mode == 'tour':
            ttk.Button(nav, text=t('coach.tut.yes'), style='Accent.TButton',
                       command=self._tour_to_tutorial).pack(side='left',
                                                            padx=(0, 6))
            ttk.Button(nav, text=t('coach.tut.no'),
                       command=self.finish).pack(side='left')
        else:
            self.back_btn = ttk.Button(nav, text=t('coach.back'),
                                       command=self.back)
            self.back_btn.pack(side='left', padx=(0, 6))
            if self.i == 0:
                self.back_btn.state(['disabled'])
            last = self.i == len(self.steps) - 1
            self.next_btn = ttk.Button(
                nav, text=t('coach.finish') if last else t('coach.next'),
                style='Accent.TButton',
                command=self.finish if last else self.next)
            self.next_btn.pack(side='left', padx=(0, 6))
            ttk.Button(nav, text=t('coach.end'), command=self.finish
                       ).pack(side='right')
        if self.mode == 'tour':
            ttk.Checkbutton(self.body, text=t('coach.dontshow'),
                            variable=self.dont_show,
                            style='Panel.TCheckbutton').pack(anchor='w',
                                                             pady=(8, 0))
        self._wrap()
        target = step.get('target')
        self._highlight(target() if target else None)
        if not step.get('marks'):
            self.marks.clear()
        self._poll()

    def _do(self):
        step = self.steps[self.i]
        try:
            step['do']()
        finally:
            self._poll()

    def next(self):
        if self.i < len(self.steps) - 1:
            self.i += 1
            self.show()

    def back(self):
        if self.i > 0:
            self.i -= 1
            self.show()

    def _tour_to_tutorial(self):
        self._save_seen()
        self.start('tutorial')

    def _save_seen(self):
        if self.mode == 'tour':
            self.app.cfg.set('guide_seen', bool(self.dont_show.get()))
            self.app.cfg.save()

    def finish(self):
        self._save_seen()
        self.idle()

    # -- state polling ----------------------------------------------------------

    def _stop_poll(self):
        for job in (self._job, self._advance_job):
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        self._job = self._advance_job = None

    def _mp_current(self):
        """The step the state of the windows asks for: after the last
        milestone reached (quest taken, export done), the first step whose
        check fails."""
        def ok(st):
            try:
                return bool(st['check']())
            except Exception:
                return False
        start = 0
        for k, st in enumerate(self.steps):
            if st.get('milestone') and ok(st):
                start = k + 1
        for k in range(start, len(self.steps)):
            st = self.steps[k]
            if st.get('final') or not ok(st):
                return k
        return len(self.steps) - 1

    def _poll(self):
        self._job = None
        if not self.mode or not self.steps:
            return
        if self.mode == 'mp':
            j = self._mp_current()
            if j != self.i:
                self.i = j
                self.show()
                return
            step = self.steps[self.i]
            try:
                marks = step['marks']() if step.get('marks') else []
            except Exception:
                marks = []
            self.marks.show(marks)
            if self.state_lbl is not None:
                self.state_lbl.configure(text=t('coach.open'),
                                         foreground=theme.MUT)
            self._job = self.after(POLL_MS // 2, self._poll)
            return
        step = self.steps[self.i]
        target = step.get('target')
        self._highlight(target() if target else None)
        check = step.get('check')
        if check:
            try:
                ok = bool(check())
            except Exception:
                ok = False
            if self.state_lbl is not None:
                self.state_lbl.configure(
                    text=t('coach.done') if ok else t('coach.open'),
                    foreground=theme.OK if ok else theme.MUT)
            if hasattr(self, 'next_btn'):
                try:
                    self.next_btn.state(['!disabled'] if ok else ['disabled'])
                except tk.TclError:
                    pass
            if ok and self._advance_job is None and \
                    self.i < len(self.steps) - 1:
                self._advance_job = self.after(900, self._auto_next)
        self._job = self.after(POLL_MS, self._poll)

    def _auto_next(self):
        self._advance_job = None
        step = self.steps[self.i]
        if step.get('check') and step['check']():
            self.next()

    # -- gold frame ---------------------------------------------------------------

    def _highlight(self, widget):
        root = self.app.root
        if not self._frames:
            self._frames = [tk.Frame(root, bg=theme.GOLD) for _ in range(4)]
        try:
            if widget is None or not widget.winfo_ismapped():
                raise tk.TclError
            x = widget.winfo_rootx() - root.winfo_rootx()
            y = widget.winfo_rooty() - root.winfo_rooty()
            w, h = widget.winfo_width(), widget.winfo_height()
        except tk.TclError:
            for f in self._frames:
                f.place_forget()
            return
        b = BORDER
        geo = ((x - b, y - b, w + 2 * b, b), (x - b, y + h, w + 2 * b, b),
               (x - b, y, b, h), (x + w, y, b, h))
        for f, (fx, fy, fw, fh) in zip(self._frames, geo):
            f.place(x=fx, y=fy, width=fw, height=fh)
            f.lift()


# ---------------------------------------------------------------------------
# documentation window (plan 3.1, Hilfe > Dokumentation)

def readme_path():
    base = getattr(sys, '_MEIPASS', None) or data.ROOT
    return os.path.join(base, 'README.md')


def show_docs(app):
    path = readme_path()
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except OSError as e:
        text = f'# README\n\n{e}'
    win = tk.Toplevel(app.root)
    win.title(t('help.docs'))
    win.geometry('860x700')
    theme.dark_titlebar(win)
    frame = ttk.Frame(win, padding=1)
    frame.pack(fill='both', expand=True)
    sb = ttk.Scrollbar(frame, orient='vertical')
    txt = tk.Text(frame, wrap='word', bd=0, padx=26, pady=20, cursor='arrow',
                  spacing1=2, spacing3=4, yscrollcommand=sb.set,
                  font=('Segoe UI', 10))
    sb.configure(command=txt.yview)
    sb.pack(side='right', fill='y')
    txt.pack(fill='both', expand=True)
    txt.tag_configure('h1', font=theme.FONT_H1, foreground=theme.GOLD,
                      spacing1=18)
    txt.tag_configure('h2', font=theme.FONT_H2, foreground=theme.GOLD_HI,
                      spacing1=14)
    txt.tag_configure('h3', font=('Segoe UI Semibold', 10),
                      foreground=theme.GOLD_HI, spacing1=8)
    txt.tag_configure('li', lmargin1=20, lmargin2=34)
    txt.tag_configure('code', font=theme.FONT_MONO, background=theme.FIELD,
                      lmargin1=16, lmargin2=16)
    txt.tag_configure('inline', font=theme.FONT_MONO, foreground=theme.GOLD_HI)
    txt.tag_configure('bold', font=('Segoe UI Semibold', 10))
    render_markdown(txt, text)
    txt.configure(state='disabled')
    ttk.Button(win, text=t('close'), command=win.destroy
               ).pack(anchor='e', padx=8, pady=8)
    return win


def render_markdown(txt, text):
    """Headings, bullets, code blocks, tables (monospace), inline code and
    bold. Enough for README.md."""
    in_code = False
    for line in text.split('\n'):
        if line.startswith('```'):
            in_code = not in_code
            continue
        if in_code or line.startswith('|'):
            txt.insert('end', line + '\n', 'code')
            continue
        m = re.match(r'(#{1,3}) (.*)', line)
        if m:
            txt.insert('end', m.group(2) + '\n', 'h%d' % len(m.group(1)))
            continue
        tag = None
        if re.match(r'\s*[-*] ', line):
            line = '• ' + re.sub(r'^\s*[-*] ', '', line)
            tag = 'li'
        for part in re.split(r'(`[^`]+`|\*\*[^*]+\*\*)', line):
            if part.startswith('`') and part.endswith('`') and len(part) > 1:
                txt.insert('end', part[1:-1], ('inline',) + ((tag,) if tag
                                                            else ()))
            elif part.startswith('**') and part.endswith('**'):
                txt.insert('end', part[2:-2], ('bold',) + ((tag,) if tag
                                                          else ()))
            else:
                part = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', part)
                txt.insert('end', part, tag)
        txt.insert('end', '\n', tag)
