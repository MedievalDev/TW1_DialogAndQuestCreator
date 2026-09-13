"""Main window: menu bar, panels, status bar, project handling, graph.

Milestone 1 built the frame; milestone 2 adds the node graph (graph.py),
the conversation tabs above it, undo/redo and the clipboard. Panels that
belong to later milestones are still placeholders; their menu entries
exist but are disabled so the final structure (plan section 3) is visible.
"""

import json
import os
import random
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, VERSION, data, model, theme
from .graph import GraphView
from .i18n import t, set_lang, get_lang, detect_lang
from .model import Project, Quest, ModelError, PROJECT_EXT

GUIDE_URL = 'https://alchemy-fox.de/game/TW1_DialogAndQuestCreator/'
GITHUB_URL = 'https://github.com/MedievalDev/TW1_DialogAndQuestCreator'
COMMUNITY_URL = 'https://twmp.alchemy-fox.de/'
DEBUG = not getattr(sys, 'frozen', False)


class App:
    def __init__(self, start_time=None):
        self.t_start = start_time or time.perf_counter()
        self.cfg = data.Config()
        set_lang(self.cfg.get('lang') or detect_lang())
        self.index = None
        self.project = None
        self.quest = None
        self.tab_key = model.DEFAULT_TABS[0]
        self.undo = model.UndoStack()
        self.clipboard = None

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.geometry(self.cfg.get('window') or '1280x800')
        self.root.minsize(960, 600)
        theme.apply_dark_theme(self.root)
        self.root.protocol('WM_DELETE_WINDOW', self.quit)

        self.vars = {k: tk.BooleanVar(value=v)
                     for k, v in self.cfg.get('panels').items()}
        self.lang_var = tk.StringVar(value=get_lang())
        self.grid_var = tk.BooleanVar(value=True)
        self.edge_var = tk.StringVar(value='curve')

        self._build_menubar()
        self._build_body()
        self._build_statusbar()
        self._bind_keys()
        self.new_project(ask=False)
        self.root.deiconify()
        self.root.after(50, self._startup)

    # -- menu bar -----------------------------------------------------------

    def _build_menubar(self):
        bar = ttk.Frame(self.root, style='Menubar.TFrame')
        bar.pack(fill='x')
        for key, filler in (('menu.file', self._fill_file),
                            ('menu.edit', self._fill_edit),
                            ('menu.view', self._fill_view),
                            ('menu.quest', self._fill_quest),
                            ('menu.help', self._fill_help)):
            item = ttk.Label(bar, text=t(key), style='Menubar.TLabel')
            item.pack(side='left')
            item.bind('<Button-1>',
                      lambda ev, f=filler, w=item: self._popup(f, w))
            item.bind('<Enter>', lambda ev, w=item: w.state(['active']))
            item.bind('<Leave>', lambda ev, w=item: w.state(['!active']))
        self.lbl_brand = ttk.Label(bar, text='QUEST CREATOR',
                                   style='Menubar.TLabel')
        self.lbl_brand.pack(side='right', padx=(0, 6))

    def _popup(self, filler, widget):
        menu = tk.Menu(self.root, tearoff=0)
        filler(menu)
        try:
            menu.tk_popup(widget.winfo_rootx(),
                          widget.winfo_rooty() + widget.winfo_height())
        finally:
            menu.grab_release()

    @staticmethod
    def _acc(keys):
        return keys.replace('Ctrl', t('ctrl'))

    def _state(self, cond):
        return 'normal' if cond else 'disabled'

    def _fill_file(self, m):
        m.add_command(label=t('file.new'), accelerator=self._acc('Ctrl+N'),
                      command=self.new_project)
        m.add_command(label=t('file.open'), accelerator=self._acc('Ctrl+O'),
                      command=self.open_project)
        recent = tk.Menu(m, tearoff=0)
        paths = self.cfg.get('recent_projects') or []
        for p in paths:
            recent.add_command(label=p,
                               command=lambda p=p: self.open_project(p))
        if not paths:
            recent.add_command(label=t('file.recent.none'), state='disabled')
        m.add_cascade(label=t('file.recent'), menu=recent)
        m.add_command(label=t('file.save'), accelerator=self._acc('Ctrl+S'),
                      command=self.save_project)
        m.add_command(label=t('file.saveas'),
                      accelerator=self._acc('Ctrl+Shift+S'),
                      command=self.save_project_as)
        m.add_separator()
        m.add_command(label=t('file.gamepath'), command=self.change_game_dir)
        m.add_separator()
        m.add_command(label=t('file.export'), accelerator=self._acc('Ctrl+E'),
                      state='disabled')
        m.add_command(label=t('file.exportfiles'), state='disabled')
        m.add_separator()
        m.add_command(label=t('file.quit'), command=self.quit)

    def _fill_edit(self, m):
        g = self.graph
        has_q = self.quest is not None
        has_sel = has_q and bool(g.selected - {model.ENTRY_ID})
        m.add_command(label=t('edit.undo'), accelerator=self._acc('Ctrl+Z'),
                      command=self.do_undo,
                      state=self._state(has_q and self.undo.can_undo()))
        m.add_command(label=t('edit.redo'), accelerator=self._acc('Ctrl+Y'),
                      command=self.do_redo,
                      state=self._state(has_q and self.undo.can_redo()))
        m.add_separator()
        m.add_command(label=t('edit.cut'), accelerator=self._acc('Ctrl+X'),
                      command=self.cut, state=self._state(has_sel))
        m.add_command(label=t('edit.copy'), accelerator=self._acc('Ctrl+C'),
                      command=self.copy, state=self._state(has_sel))
        m.add_command(label=t('edit.paste'), accelerator=self._acc('Ctrl+V'),
                      command=self.paste,
                      state=self._state(has_q and bool(self.clipboard)))
        m.add_command(label=t('edit.duplicate'),
                      accelerator=self._acc('Ctrl+D'),
                      command=g.duplicate_selection,
                      state=self._state(has_sel))
        m.add_command(label=t('edit.delete'),
                      accelerator='Entf' if get_lang() == 'de' else 'Del',
                      command=g.delete_selection,
                      state=self._state(has_sel or (has_q and
                                                    g.selected_edge)))
        m.add_command(label=t('edit.selectall'),
                      accelerator=self._acc('Ctrl+A'),
                      command=g.select_all, state=self._state(has_q))
        m.add_separator()
        m.add_command(label=t('edit.autolayout'),
                      accelerator=self._acc('Ctrl+L'),
                      command=g.auto_layout, state=self._state(has_q))

    def _fill_view(self, m):
        g = self.graph
        m.add_command(label=t('view.zoomin'), accelerator=self._acc('Ctrl++'),
                      command=g.zoom_in)
        m.add_command(label=t('view.zoomout'), accelerator=self._acc('Ctrl+-'),
                      command=g.zoom_out)
        m.add_command(label=t('view.zoom100'), accelerator=self._acc('Ctrl+0'),
                      command=g.zoom_reset)
        m.add_command(label=t('view.fit'), accelerator='F', command=g.fit)
        m.add_separator()
        for key, var in (('view.timeline', 'timeline'),
                         ('view.palette', 'palette'),
                         ('view.inspector', 'inspector'),
                         ('view.coach', 'coach')):
            m.add_checkbutton(label=t(key), variable=self.vars[var],
                              command=self._apply_panels)
        m.add_separator()
        m.add_checkbutton(label=t('view.grid'), variable=self.grid_var,
                          command=lambda: g.set_grid(self.grid_var.get()))
        edges = tk.Menu(m, tearoff=0)
        for key, val in (('view.edges.curve', 'curve'),
                         ('view.edges.line', 'line')):
            edges.add_radiobutton(
                label=t(key), value=val, variable=self.edge_var,
                command=lambda: g.set_edge_style(self.edge_var.get()))
        m.add_cascade(label=t('view.edges'), menu=edges)
        m.add_separator()
        lang = tk.Menu(m, tearoff=0)
        for code in ('de', 'en'):
            lang.add_radiobutton(label=t(f'view.lang.{code}'), value=code,
                                 variable=self.lang_var,
                                 command=self._change_lang)
        m.add_cascade(label=t('view.lang'), menu=lang)

    def _fill_quest(self, m):
        m.add_command(label=t('quest.new'), command=self.new_quest,
                      state=self._state(self.project is not None))
        m.add_command(label=t('quest.duplicate'), state='disabled')
        m.add_command(label=t('quest.delete'), state='disabled')
        m.add_separator()
        m.add_command(label=t('quest.validate'), accelerator='F7',
                      state='disabled')
        m.add_command(label=t('quest.preview'), state='disabled')
        m.add_command(label=t('quest.template'), state='disabled')
        if DEBUG:
            m.add_separator()
            m.add_command(label=t('quest.debug300'), command=self.debug_nodes,
                          state=self._state(self.quest is not None))

    def _fill_help(self, m):
        m.add_command(label=t('help.tour'), state='disabled')
        m.add_command(label=t('help.tutorial'), state='disabled')
        m.add_command(label=t('help.docs'), state='disabled')
        m.add_separator()
        m.add_command(label=t('help.about'), command=self.show_about)

    # -- body ---------------------------------------------------------------

    def _build_body(self):
        self.vpane = ttk.PanedWindow(self.root, orient='vertical')
        self.vpane.pack(fill='both', expand=True)

        self.timeline = self._placeholder(self.vpane, 'panel.timeline', 6)
        self.hpane = ttk.PanedWindow(self.vpane, orient='horizontal')

        self.palette = ttk.PanedWindow(self.hpane, orient='vertical')
        self.speakers = self._placeholder(self.palette, 'panel.speakers', 3)
        self.actions = self._placeholder(self.palette, 'panel.actions', 5)
        self.palette.add(self.speakers, weight=1)
        self.palette.add(self.actions, weight=1)

        # centre: tab strip above the graph canvas
        self.center = ttk.Frame(self.hpane)
        self.tabstrip = ttk.Frame(self.center, style='Panel.TFrame')
        self.tabstrip.pack(fill='x')
        self.tab_labels = {}
        self.graph = GraphView(self.center)
        self.graph.pack(fill='both', expand=True)
        self.graph.before_change = self.push_undo
        self.graph.after_change = self._after_change
        self.graph.on_select = self._update_status
        self.graph.on_edge_drop_empty = self._edge_drop_empty
        self.graph.bind('<Configure>', self._draw_graph_placeholder, add='+')

        self.side = ttk.PanedWindow(self.hpane, orient='vertical')
        self.inspector = self._placeholder(self.side, 'panel.inspector', 3)
        self.coach = self._placeholder(self.side, 'panel.coach', 8)
        self.side.add(self.inspector, weight=2)
        self.side.add(self.coach, weight=1)

        self._apply_panels(initial=True)

    def _placeholder(self, parent, title_key, milestone):
        f = ttk.Frame(parent, style='Panel.TFrame')
        ttk.Label(f, text=t(title_key), style='PanelTitle.TLabel'
                  ).pack(anchor='w', fill='x')
        ttk.Label(f, text=t('panel.placeholder', m=milestone),
                  style='PanelMuted.TLabel').pack(padx=10, pady=4, anchor='w')
        return f

    def _apply_panels(self, initial=False):
        v = self.vars
        for w in (self.timeline, self.hpane):
            if str(w) in self.vpane.panes():
                self.vpane.forget(w)
        if v['timeline'].get():
            self.vpane.add(self.timeline, weight=0)
        self.vpane.add(self.hpane, weight=1)
        for w in (self.palette, self.center, self.side):
            if str(w) in self.hpane.panes():
                self.hpane.forget(w)
        if v['palette'].get():
            self.hpane.add(self.palette, weight=0)
        self.hpane.add(self.center, weight=1)
        show_side = v['inspector'].get() or v['coach'].get()
        if show_side:
            self.hpane.add(self.side, weight=0)
            for w in (self.inspector, self.coach):
                if str(w) in self.side.panes():
                    self.side.forget(w)
            if v['inspector'].get():
                self.side.add(self.inspector, weight=2)
            if v['coach'].get():
                self.side.add(self.coach, weight=1)
        if initial:
            self.root.update_idletasks()
            try:
                if v['timeline'].get():
                    self.vpane.sashpos(0, 130)
                if v['palette'].get():
                    self.hpane.sashpos(0, 240)
                if show_side:
                    self.hpane.sashpos(len(self.hpane.panes()) - 2,
                                       self.root.winfo_width() - 300)
            except tk.TclError:
                pass
        self.cfg.set('panels', {k: var.get() for k, var in v.items()})

    def _draw_graph_placeholder(self, ev=None):
        c = self.graph
        c.delete('placeholder')
        if self.quest is None:
            c.create_text(c.canvasx(c.winfo_width() // 2),
                          c.canvasy(c.winfo_height() // 2),
                          text=t('graph.empty'), fill=theme.MUT,
                          font=theme.FONT, justify='center',
                          tags='placeholder')

    def _build_tabs(self):
        for w in self.tabstrip.winfo_children():
            w.destroy()
        self.tab_labels = {}
        if not self.quest:
            return
        for key in self.quest.tab_keys():
            lbl = ttk.Label(self.tabstrip, text=t('tab.' + key),
                            style='Menubar.TLabel', cursor='hand2')
            lbl.pack(side='left')
            lbl.bind('<Button-1>', lambda e, k=key: self.show_tab(k))
            self.tab_labels[key] = lbl
        self._mark_tab()

    def _mark_tab(self):
        for key, lbl in self.tab_labels.items():
            on = key == self.tab_key
            lbl.configure(foreground=theme.GOLD if on else theme.MUT,
                          font=theme.FONT_BOLD if on else theme.FONT)

    def show_tab(self, key):
        if not self.quest or key not in self.quest.tabs:
            return
        self.tab_key = key
        self._mark_tab()
        self.graph.set_graph(self.quest.tabs[key])
        self._update_status()

    # -- quest --------------------------------------------------------------

    def open_quest(self, quest):
        self.quest = quest
        self.undo.clear()
        self.tab_key = model.DEFAULT_TABS[0]
        self._build_tabs()
        self.graph.set_graph(quest.tabs[self.tab_key] if quest else None)
        self._draw_graph_placeholder()
        self._update_status()

    def new_quest(self):
        if not self.project:
            return
        taken = {q.id for q in self.project.quests if q.id}
        free = self.index.free_ids(taken) if self.index else [
            i for i in range(data.MIN_QUEST_ID, data.MAX_QUEST_ID + 1)
            if i not in taken]
        if not free:
            messagebox.showwarning(APP_NAME, t('quest.noid'), parent=self.root)
            return
        q = Quest(free[0])
        self.project.quests.append(q)
        self.mark_dirty()
        self.open_quest(q)

    def debug_nodes(self):
        """300 chained nodes to prove the canvas stays fluid (plan M2)."""
        if not self.quest:
            return
        tab = self.quest.tabs[self.tab_key]
        self.push_undo('debug')
        rnd = random.Random(1)
        prev = model.ENTRY_ID
        words = ('Hallo', 'Held', 'Gold', 'Yamalin', 'Zwerge', 'Turm',
                 'Sumpf', 'Ferid', 'Tago', 'Gandohar')
        for i in range(300):
            n = model.make_node('node', 0, 0, f'Node {i + 1}')
            n['lines'] = [{'text': ' '.join(rnd.choice(words)
                                            for _ in range(rnd.randint(2, 7)))}
                          for _ in range(rnd.randint(1, 3))]
            n['color'] = theme.SPEAKER_COLORS[i % len(theme.SPEAKER_COLORS)]
            nid = model.add_node(tab, n)
            model.connect(tab, prev, rnd.randrange(model.out_port_count(
                tab['nodes'][prev])), nid)
            if rnd.random() < 0.3:
                prev = rnd.choice(list(tab['nodes']))
                if tab['nodes'][prev]['type'] == 'comment':
                    prev = nid
            else:
                prev = nid
        model.auto_layout(tab)
        t0 = time.perf_counter()
        self.graph.set_graph(tab)
        ms = (time.perf_counter() - t0) * 1000
        self.graph.fit()
        self._after_change()
        self.set_info(f'300 nodes: redraw {ms:.0f} ms', 'StatusOk.TLabel')

    def _edge_drop_empty(self, frm, port, wx, wy):
        """Dragging an edge into the void creates a node there and connects
        it (plan 5.3; milestone 3 turns this into the speaker popup)."""
        tab = self.quest.tabs[self.tab_key]
        self.push_undo('add')
        node = model.make_node('node', int(wx), int(wy - model.HEADER_H / 2))
        nid = model.add_node(tab, node)
        model.connect(tab, frm, port, nid)
        self.graph.draw_node(nid)
        self.graph.draw_node(frm)
        self.graph.draw_edge(frm, port, nid)
        self._after_change()
        self.graph.select([nid])

    # -- undo / clipboard ---------------------------------------------------

    def push_undo(self, label=''):
        if self.quest:
            self.undo.push(self.quest.tabs, label)

    def _after_change(self):
        self.mark_dirty()
        self._update_status()

    def _restore(self, state):
        if state is None:
            return
        self.quest.tabs = state
        if self.tab_key not in state:
            self.tab_key = model.DEFAULT_TABS[0]
        self._build_tabs()
        self.graph.set_graph(state[self.tab_key])
        self._after_change()

    def do_undo(self):
        if self.quest:
            self._restore(self.undo.undo(self.quest.tabs))

    def do_redo(self):
        if self.quest:
            self._restore(self.undo.redo(self.quest.tabs))

    def copy(self):
        if not self.quest:
            return
        clip = model.copy_nodes(self.quest.tabs[self.tab_key],
                                self.graph.selected)
        if clip['nodes']:
            self.clipboard = clip

    def cut(self):
        self.copy()
        self.graph.delete_selection()

    def paste(self):
        if self.quest and self.clipboard:
            self.graph.paste(self.clipboard)

    # -- status bar ---------------------------------------------------------

    def _build_statusbar(self):
        bar = ttk.Frame(self.root, style='Status.TFrame')
        bar.pack(fill='x', side='bottom')
        self.status = {}
        for i, key in enumerate(('project', 'game', 'quest', 'nodes',
                                 'validation')):
            if i:
                ttk.Label(bar, text='|', style='StatusSep.TLabel'
                          ).pack(side='left')
            lbl = ttk.Label(bar, text='', style='Status.TLabel')
            lbl.pack(side='left')
            self.status[key] = lbl
        self.status['info'] = ttk.Label(bar, text='', style='Status.TLabel')
        self.status['info'].pack(side='right')
        self._update_status()

    def _update_status(self):
        s = self.status
        if self.project:
            name = self.project.display_name() or t('project.untitled')
            s['project'].configure(text=name + (' *' if self.project.dirty
                                                else ''))
        else:
            s['project'].configure(text=t('status.noproject'))
        s['game'].configure(text=self.cfg.get('game_dir')
                            or t('status.nogame'))
        s['quest'].configure(text=f'Q_{self.quest.id}' if self.quest
                             and self.quest.id else t('status.noquest'))
        n = self.quest.node_count() if self.quest else 0
        text = t('status.nodes', n=n)
        if DEBUG and self.graph.last_frame_ms:
            text += '   ' + t('status.frame', ms=self.graph.last_frame_ms)
        s['nodes'].configure(text=text)
        s['validation'].configure(text=t('status.validation.none'))
        self._update_title()

    def _update_title(self):
        name = (self.project.display_name() or t('project.untitled')
                if self.project else '')
        star = ' *' if self.project and self.project.dirty else ''
        self.root.title(f'{name}{star} - {APP_NAME}' if name else APP_NAME)

    def set_info(self, text, style='Status.TLabel'):
        self.status['info'].configure(text=text, style=style)

    # -- keys ---------------------------------------------------------------

    def _typing(self):
        w = self.root.focus_get()
        return isinstance(w, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox))

    def _key(self, fn):
        def handler(ev):
            if self._typing():
                return None
            fn()
            return 'break'
        return handler

    def _bind_keys(self):
        r = self.root
        r.bind('<Control-n>', lambda e: self.new_project())
        r.bind('<Control-o>', lambda e: self.open_project())
        r.bind('<Control-s>', lambda e: self.save_project())
        r.bind('<Control-S>', lambda e: self.save_project_as())
        g = self.graph
        for seq, fn in (('<Control-z>', self.do_undo),
                        ('<Control-y>', self.do_redo),
                        ('<Control-x>', self.cut), ('<Control-c>', self.copy),
                        ('<Control-v>', self.paste),
                        ('<Control-d>', g.duplicate_selection),
                        ('<Control-l>', g.auto_layout),
                        ('<Control-plus>', g.zoom_in),
                        ('<Control-minus>', g.zoom_out),
                        ('<Control-0>', g.zoom_reset)):
            r.bind(seq, self._key(fn))

    # -- start-up -----------------------------------------------------------

    def _startup(self):
        game = data.find_game_dir(self.cfg)
        if not game:
            messagebox.showinfo(t('game.ask.title'), t('game.ask.msg'),
                                parent=self.root)
            game = self._ask_game_dir()
            if not game:
                self.set_info(t('status.nogame'), 'StatusErr.TLabel')
                return
        self.cfg.set('game_dir', game)
        self.cfg.save()
        self._update_status()
        self._load_index(game)

    def _ask_game_dir(self):
        current = self.cfg.get('game_dir')
        while True:
            path = filedialog.askdirectory(
                title=t('game.ask.title'), parent=self.root,
                initialdir=current or 'C:\\')
            if not path:
                return None
            path = os.path.normpath(path)
            if data.valid_game_dir(path):
                return path
            if not messagebox.askretrycancel(t('game.ask.title'),
                                             t('game.invalid'),
                                             parent=self.root):
                return None

    def change_game_dir(self):
        path = self._ask_game_dir()
        if not path:
            return
        self.cfg.set('game_dir', path)
        self.cfg.save()
        self._update_status()
        messagebox.showinfo(APP_NAME, t('game.set', path=path),
                            parent=self.root)
        self._load_index(path)

    def _load_index(self, game):
        """Read the cache, or rebuild it in a thread with a progress window."""
        self.set_info(t('status.index.loading'))
        if self._try_cache(game):
            return
        win = _ProgressWindow(self.root)
        result = {}

        def progress(step, frac):
            if isinstance(step, tuple):
                text = t('index.step.' + step[0], name=step[1])
            else:
                text = t('index.step.' + step)
            self.root.after(0, win.update, text, frac)

        def work():
            try:
                result['idx'] = data.load_index(game, progress)
            except Exception as e:      # shown to the user below
                result['err'] = e

        def poll():
            if th.is_alive():
                self.root.after(100, poll)
                return
            win.close()
            if 'err' in result:
                messagebox.showerror(t('error'),
                                     t('index.error', err=result['err']),
                                     parent=self.root)
                self.set_info(t('status.nogame'), 'StatusErr.TLabel')
                return
            self._index_ready(*result['idx'])

        th = threading.Thread(target=work, daemon=True)
        th.start()
        poll()

    def _try_cache(self, game):
        t0 = time.perf_counter()
        try:
            with open(data.cache_path(), encoding='utf-8') as f:
                idx = json.load(f)
        except (OSError, ValueError):
            return False
        if not data.cache_valid(idx, game):
            return False
        self._index_ready(data.Index(idx), True, time.perf_counter() - t0)
        return True

    def _index_ready(self, index, from_cache, seconds):
        self.index = index
        total = time.perf_counter() - self.t_start
        how = (t('status.index.cache', s=seconds) if from_cache
               else t('status.index.built', s=seconds))
        stats = t('stats', q=len(index.quests), n=len(index.npcs),
                  c=len(index.cues), f=len(index.free_ids()))
        self.set_info(f'{stats}   {how}   {t("status.start", s=total)}',
                      'StatusOk.TLabel')

    # -- project ------------------------------------------------------------

    def _confirm_discard(self):
        """True when the current project may be replaced."""
        p = self.project
        if not p or not p.dirty:
            return True
        ans = messagebox.askyesnocancel(
            t('project.unsaved.title'),
            t('project.unsaved.q', name=p.display_name()
              or t('project.untitled')), parent=self.root)
        if ans is None:
            return False
        if ans:
            return self.save_project()
        return True

    def _set_project(self, project):
        self.project = project
        self.clipboard = None
        self.open_quest(project.quests[0] if project.quests else None)

    def new_project(self, ask=True):
        if ask and not self._confirm_discard():
            return
        self._set_project(Project())

    def open_project(self, path=None):
        if not self._confirm_discard():
            return
        if not path:
            path = filedialog.askopenfilename(
                title=t('file.open'), parent=self.root,
                filetypes=[(t('project.filter'), '*' + PROJECT_EXT)],
                defaultextension=PROJECT_EXT)
            if not path:
                return
        if not os.path.isfile(path):
            self.cfg.remove_recent(path)
            self.cfg.save()
            messagebox.showerror(t('error'), t('project.missing', path=path),
                                 parent=self.root)
            return
        try:
            project = Project.load(path)
        except (OSError, ModelError) as e:
            messagebox.showerror(t('error'),
                                 t('project.open.error', err=e),
                                 parent=self.root)
            return
        self.cfg.add_recent(path)
        self.cfg.save()
        self._set_project(project)

    def save_project(self):
        if not self.project:
            return False
        if not self.project.path:
            return self.save_project_as()
        return self._write_project(self.project.path)

    def save_project_as(self):
        if not self.project:
            return False
        initial = self.project.path or (
            (self.project.name or t('project.untitled')) + PROJECT_EXT)
        path = filedialog.asksaveasfilename(
            title=t('file.saveas'), parent=self.root,
            initialfile=os.path.basename(initial),
            initialdir=os.path.dirname(self.project.path) if self.project.path
            else None,
            filetypes=[(t('project.filter'), '*' + PROJECT_EXT)],
            defaultextension=PROJECT_EXT)
        if not path:
            return False
        return self._write_project(path)

    def _write_project(self, path):
        try:
            self.project.save(path)
        except OSError as e:
            messagebox.showerror(t('error'),
                                 t('project.save.error', err=e),
                                 parent=self.root)
            return False
        self.cfg.add_recent(path)
        self.cfg.save()
        self._update_status()
        return True

    def mark_dirty(self):
        if self.project and not self.project.dirty:
            self.project.dirty = True
            self._update_status()

    # -- misc ---------------------------------------------------------------

    def _change_lang(self):
        self.cfg.set('lang', self.lang_var.get())
        self.cfg.save()
        messagebox.showinfo(t('view.lang'), t('view.lang.restart'),
                            parent=self.root)

    def show_about(self):
        win = tk.Toplevel(self.root)
        win.title(t('about.title', app=APP_NAME))
        win.resizable(False, False)
        win.transient(self.root)
        theme.dark_titlebar(win)
        f = ttk.Frame(win, padding=24)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=APP_NAME, style='Brand.TLabel').pack(anchor='w')
        ttk.Label(f, text=t('about.version', v=VERSION), style='Muted.TLabel'
                  ).pack(anchor='w', pady=(0, 12))
        ttk.Label(f, text=t('about.links') + ':').pack(anchor='w')
        for key, url in (('about.guide', GUIDE_URL),
                         ('about.github', GITHUB_URL),
                         ('about.community', COMMUNITY_URL)):
            lnk = ttk.Label(f, text=f'{t(key)}: {url}', foreground=theme.GOLD,
                            cursor='hand2')
            lnk.pack(anchor='w', padx=(12, 0))
            lnk.bind('<Button-1>', lambda e, u=url: webbrowser.open(u))
        ttk.Label(f, text=t('about.credits'), wraplength=420,
                  style='Muted.TLabel').pack(anchor='w', pady=(12, 2))
        ttk.Label(f, text=t('about.nodata'), wraplength=420,
                  style='Muted.TLabel').pack(anchor='w')
        ttk.Button(f, text=t('close'), command=win.destroy
                   ).pack(anchor='e', pady=(16, 0))
        win.grab_set()

    def quit(self):
        if not self._confirm_discard():
            return
        try:
            self.cfg.set('window', self.root.geometry())
            self.cfg.save()
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


class _ProgressWindow:
    def __init__(self, parent):
        self.win = tk.Toplevel(parent)
        self.win.title(t('index.title'))
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.protocol('WM_DELETE_WINDOW', lambda: None)
        theme.dark_titlebar(self.win)
        f = ttk.Frame(self.win, padding=20)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=t('index.title'), style='Brand.TLabel'
                  ).pack(anchor='w')
        ttk.Label(f, text=t('index.intro'), wraplength=380,
                  style='Muted.TLabel').pack(anchor='w', pady=(2, 10))
        self.var = tk.DoubleVar(value=0)
        ttk.Progressbar(f, variable=self.var, maximum=1.0, length=380
                        ).pack(fill='x')
        self.lbl = ttk.Label(f, text='', style='Muted.TLabel')
        self.lbl.pack(anchor='w', pady=(6, 0))
        self.win.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()
                                    - self.win.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height()
                                    - self.win.winfo_height()) // 2
        self.win.geometry(f'+{max(x, 0)}+{max(y, 0)}')
        self.win.grab_set()

    def update(self, text, frac):
        try:
            self.lbl.configure(text=text)
            self.var.set(frac)
        except tk.TclError:
            pass

    def close(self):
        try:
            self.win.grab_release()
            self.win.destroy()
        except tk.TclError:
            pass


def main(start_time=None):
    App(start_time).run()
