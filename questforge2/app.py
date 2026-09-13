"""Main window: menu bar, timeline, speaker/action box, node graph,
property panel, coach, status bar, project handling and export.
"""

import glob
import json
import os
import queue
import random
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, VERSION, data, export, model, retail, theme, validate
from .graph import GraphView
from .guide import Coach, show_docs
from .i18n import t, set_lang, get_lang, detect_lang
from .inspector import Inspector
from .model import Project, Quest, ModelError, PROJECT_EXT
from .palette import ActionBox, SpeakerBox
from .timeline import Timeline

GUIDE_URL = 'https://alchemy-fox.de/game/TW1_DialogAndQuestCreator/'
GITHUB_URL = 'https://github.com/MedievalDev/TW1_DialogAndQuestCreator'
COMMUNITY_URL = 'https://twmp.alchemy-fox.de/'
SITE_URL = 'https://alchemy-fox.de/'
LINKS = (('about.github', GITHUB_URL), ('about.site', SITE_URL),
         ('about.guide', GUIDE_URL), ('about.community', COMMUNITY_URL))
DEBUG = not getattr(sys, 'frozen', False)


class App:
    def __init__(self, start_time=None, carry=None):
        self.t_start = start_time or time.perf_counter()
        self.restart = None            # state handed to the next window
        self._carry = carry
        self.cfg = data.Config()
        set_lang(self.cfg.get('lang') or detect_lang())
        self.index = None
        self.project = None
        self.quest = None
        self.tab_state = model.DEFAULT_STATES[0]
        self.undo = model.UndoStack()
        self.clipboard = None
        self.preview = None            # game quest shown but not in the project
        self._preview_snap = None
        self._val_job = None

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.geometry(self.cfg.get('window') or '1280x800')
        self.root.minsize(960, 600)
        theme.apply_dark_theme(self.root)
        self.selftest = os.environ.get('QF2_SELFTEST')
        try:
            self._icon = tk.PhotoImage(file=data.resource_path(
                'questforge2', 'assets', 'icon64.png'))
            self.root.iconphoto(True, self._icon)
        except tk.TclError:
            pass
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
        if carry:
            self._restore_carry(carry)
        else:
            self.new_project(ask=False)
        if not self.selftest:
            self.root.deiconify()
        self.root.after(50, self._startup)

    # -- menu bar -----------------------------------------------------------

    def _build_menubar(self):
        bar = ttk.Frame(self.root, style='Menubar.TFrame')
        bar.pack(fill='x')
        self.menubar = bar
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
        self._build_lang_toggle(bar).pack(side='right', padx=(0, 10))

    def _build_lang_toggle(self, bar):
        """DE · EN at the right of the menu bar: active language in gold,
        a click switches at once (design template 5.3)."""
        box = ttk.Frame(bar, style='Menubar.TFrame')
        self.lang_labels = {}
        for i, code in enumerate(('de', 'en')):
            if i:
                ttk.Label(box, text='·', style='Menubar.TLabel',
                          padding=(2, 5), foreground=theme.MUT
                          ).pack(side='left')
            lbl = ttk.Label(box, text=code.upper(), style='Menubar.TLabel',
                            padding=(4, 5), cursor='hand2')
            lbl.pack(side='left')
            lbl.bind('<Button-1>', lambda ev, c=code: self.switch_lang(c))
            lbl.bind('<Enter>', lambda ev, w=lbl: w.state(['active']))
            lbl.bind('<Leave>', lambda ev, w=lbl: w.state(['!active']))
            self.lang_labels[code] = lbl
        for code, lbl in self.lang_labels.items():
            lbl.configure(foreground=theme.GOLD if code == get_lang()
                          else theme.MUT)
        return box

    def _popup(self, filler, widget):
        menu = theme.Menu(self.root, tearoff=0)
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
        recent = theme.Menu(m, tearoff=0)
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
        can = self._state(bool(self.project and self.project.quests
                               and self.cfg.get('game_dir')))
        m.add_command(label=t('file.export'), accelerator=self._acc('Ctrl+E'),
                      command=self.export_ui, state=can)
        m.add_command(label=t('file.exportfiles'),
                      command=lambda: self.export_ui(files_only=True),
                      state=can)
        m.add_separator()
        m.add_command(label=t('file.quit'), command=self.quit)

    def _fill_edit(self, m):
        g = self.graph
        has_q = self.quest is not None
        has_sel = has_q and any(not model.is_entry(i) for i in g.selected)
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
        edges = theme.Menu(m, tearoff=0)
        for key, val in (('view.edges.curve', 'curve'),
                         ('view.edges.line', 'line')):
            edges.add_radiobutton(
                label=t(key), value=val, variable=self.edge_var,
                command=lambda: g.set_edge_style(self.edge_var.get()))
        m.add_cascade(label=t('view.edges'), menu=edges)
        m.add_separator()
        lang = theme.Menu(m, tearoff=0)
        for code in ('de', 'en'):
            lang.add_radiobutton(label=t(f'view.lang.{code}'), value=code,
                                 variable=self.lang_var,
                                 command=lambda c=code: self.switch_lang(c))
        m.add_cascade(label=t('view.lang'), menu=lang)

    def _fill_quest(self, m):
        m.add_command(label=t('quest.new'), command=self.new_quest,
                      state=self._state(self.project is not None))
        m.add_command(label=t('quest.loadretail'), command=self.load_retail,
                      state=self._state(self.project is not None
                                        and self.cfg.get('game_dir')))
        if self.project and len(self.project.quests) > 1:
            sub = theme.Menu(m, tearoff=0)
            for qq in self.project.quests:
                sub.add_radiobutton(
                    label=f'Q_{qq.id}  {qq.title}', value=id(qq),
                    variable=tk.IntVar(value=id(self.quest)),
                    command=lambda qq=qq: self.open_quest(qq))
            m.add_cascade(label=t('quest.switch'), menu=sub)
        tpls = data.list_templates()
        sub_t = theme.Menu(m, tearoff=0)
        for name, path in tpls:
            sub_t.add_command(label=name,
                              command=lambda p=path: self.new_from_template(p))
        if not tpls:
            sub_t.add_command(label=t('file.recent.none'), state='disabled')
        m.add_cascade(label=t('quest.fromtemplate'), menu=sub_t,
                      state=self._state(self.project is not None))
        in_project = bool(self.quest and self.project
                          and self.quest in self.project.quests)
        m.add_command(label=t('quest.duplicate'),
                      command=lambda: self.duplicate_quest(self.quest),
                      state=self._state(self.quest is not None))
        m.add_command(label=t('quest.delete'),
                      command=lambda: self.delete_quest(self.quest),
                      state=self._state(in_project))
        m.add_separator()
        m.add_command(label=t('quest.validate'), accelerator='F7',
                      command=self.validate_ui,
                      state=self._state(self.quest is not None))
        m.add_command(label=t('quest.preview'), command=self.show_preview,
                      state=self._state(self.quest is not None))
        m.add_command(label=t('quest.template'), command=self.save_template,
                      state=self._state(self.quest is not None))
        if DEBUG:
            m.add_separator()
            m.add_command(label=t('quest.debug300'), command=self.debug_nodes,
                          state=self._state(self.quest is not None))

    def _fill_help(self, m):
        m.add_command(label=t('help.tour'),
                      command=lambda: self.coach.start('tour'))
        m.add_command(label=t('help.tutorial'),
                      command=lambda: self.coach.start('tutorial'))
        m.add_command(label=t('help.docs'), command=lambda: show_docs(self))
        m.add_separator()
        for key, url in LINKS:
            m.add_command(label=f'{t(key)}  ({url})',
                          command=lambda u=url: webbrowser.open(u))
        m.add_separator()
        m.add_command(label=t('help.about'), command=self.show_about)

    # -- body ---------------------------------------------------------------

    def _build_body(self):
        self.vpane = ttk.PanedWindow(self.root, orient='vertical')
        self.vpane.pack(fill='both', expand=True)

        self.timeline = Timeline(self.vpane, self)
        self.hpane = ttk.PanedWindow(self.vpane, orient='horizontal')

        # centre: tab strip above the graph canvas (built before the boxes
        # that reference the graph)
        self.center = ttk.Frame(self.hpane)
        self.tabstrip = ttk.Frame(self.center, style='Panel.TFrame')
        self.tabstrip.pack(fill='x')
        self.tab_labels = {}
        self.graph = GraphView(self.center)
        self.graph.pack(fill='both', expand=True)
        self.graph.before_change = self.push_undo
        self.graph.after_change = self.changed
        self.graph.on_select = self._selection_changed
        self.graph.on_edge_drop_empty = self._edge_drop_empty
        self.graph.on_open_node = self._open_node
        self.graph.fill_add_menu = self._fill_add_menu
        self.graph.node_style = self.node_style
        self.graph.docked_text = self.docked_text
        self.graph.fill_docked_menu = self._fill_docked_menu
        self.graph.get_clipboard = lambda: self.clipboard
        self.graph.bind('<Configure>', self._draw_graph_placeholder, add='+')

        self.palette = ttk.PanedWindow(self.hpane, orient='vertical')
        self.speakers = SpeakerBox(self.palette, self)
        self.actions = ActionBox(self.palette, self)
        self.palette.add(self.speakers, weight=1)
        self.palette.add(self.actions, weight=1)

        self.side = ttk.PanedWindow(self.hpane, orient='vertical')
        self.inspector = Inspector(self.side, self)
        self.coach = Coach(self.side, self)
        self.side.add(self.inspector, weight=3)
        self.side.add(self.coach, weight=1)

        self._apply_panels(initial=True)

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
                self.side.add(self.inspector, weight=3)
            if v['coach'].get():
                self.side.add(self.coach, weight=1)
        if initial:
            self.root.update_idletasks()
            try:
                if v['timeline'].get():
                    self.vpane.sashpos(0, 110)
                if v['palette'].get():
                    self.hpane.sashpos(0, 240)
                if show_side:
                    self.hpane.sashpos(len(self.hpane.panes()) - 2,
                                       self.root.winfo_width() - 320)
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

    # -- tabs (level filters) -----------------------------------------------

    def _build_tabs(self):
        for w in self.tabstrip.winfo_children():
            w.destroy()
        self.tab_labels = {}
        if not self.quest:
            return
        for key in self.quest.states_present():
            lbl = ttk.Label(self.tabstrip, text=t('state.' + key),
                            style='Menubar.TLabel', cursor='hand2')
            lbl.pack(side='left')
            lbl.bind('<Button-1>', lambda e, k=key: self.show_tab(k))
            self.tab_labels[key] = lbl
        more = ttk.Label(self.tabstrip, text=t('tab.more'),
                         style='Menubar.TLabel', cursor='hand2')
        more.pack(side='left')
        more.bind('<Button-1>', self._more_tabs)
        alls = ttk.Label(self.tabstrip, text=t('tab.all'),
                         style='Menubar.TLabel', cursor='hand2')
        alls.pack(side='right')
        alls.bind('<Button-1>', lambda e: self.show_tab(None))
        self.tab_labels[None] = alls
        self._mark_tab()

    def _more_tabs(self, ev):
        menu = theme.Menu(self.root, tearoff=0)
        present = self.quest.states_present()
        for s in model.STATES:
            if s not in present:
                menu.add_command(label=t('state.' + s),
                                 command=lambda s=s: self._add_level(s))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _add_level(self, state):
        if state != 'neutral':
            self.push_undo('level')
            model.ensure_entry(self.quest.graph, state)
            self.changed()
        self.show_tab(state)

    def _mark_tab(self):
        for key, lbl in self.tab_labels.items():
            on = key == self.tab_state
            lbl.configure(foreground=theme.GOLD if on else theme.MUT,
                          font=theme.FONT_BOLD if on else theme.FONT)

    def show_tab(self, state):
        if not self.quest:
            return
        self.tab_state = state
        if state and state not in self.tab_labels:
            self._build_tabs()
        self._mark_tab()
        self.graph.set_filter(state)
        if state == 'solved':
            self.graph.scroll_to_node(model.TASK_ID)
        elif state:
            self.graph.scroll_to_node(model.entry_id(state))
        self._update_status()

    # -- quest --------------------------------------------------------------

    def open_quest(self, quest):
        self.quest = quest
        self.undo.clear()
        self.tab_state = model.DEFAULT_STATES[0]
        self.graph.filter_state = self.tab_state if quest else None
        self._build_tabs()
        self.graph.set_graph(quest.graph if quest else None)
        if quest:
            self.graph.scroll_to_node(model.entry_id(self.tab_state))
        self._draw_graph_placeholder()
        self.speakers.refresh()
        self.inspector.show(set())
        self._update_status()
        self.timeline.refresh()
        self.timeline.show_current()
        self.schedule_validation(10)

    def new_quest(self):
        if not self.project:
            return
        qid = self._free_id()
        if qid is None:
            return
        q = Quest(qid)
        model.add_default_conditions(q)
        # journal group of the default predecessor (Q_4), group 0 has no name
        pred = self.index.quest(4) if self.index else None
        if pred and str(pred['group']) in self.index.groups:
            q.group = pred['group']
        self.project.quests.append(q)
        self.mark_dirty()
        self.open_quest(q)

    def load_retail(self):
        """Pick a dialog of the game (or a mod) and open its quest."""
        game = self.cfg.get('game_dir')
        if not self.project or not game:
            return
        trees = self._game_trees()
        if trees is None:
            return
        dlg = RetailDialog(self, trees)
        self.root.wait_window(dlg.win)
        if dlg.result:
            self.open_any_quest(int(dlg.result.split('_')[1]))

    def _game_trees(self):
        game = self.cfg.get('game_dir')
        self.root.configure(cursor='watch')
        self.root.update_idletasks()
        try:
            return data.load_trees(game)
        except Exception as e:
            messagebox.showerror(t('error'), t('index.error', err=e),
                                 parent=self.root)
            return None
        finally:
            self.root.configure(cursor='')

    def quest_for(self, qid):
        """Project quest with this id, else the quest built from the game."""
        if self.project:
            q = self.project.quest_by_id(qid)
            if q:
                return q
        if self.preview and self.preview.id == qid:
            return self.preview
        return self.build_game_quest(qid)

    def build_game_quest(self, qid):
        """Quest of the game install (qtx block, texts, dialog tree)."""
        game = self.cfg.get('game_dir')
        if not game:
            return None
        trees = self._game_trees()
        if trees is None:
            return None
        blocks = data.load_qtx_blocks(game)
        tr = data.load_translations(game)
        q = Quest(qid, tr.get(f'translateQ_{qid}', ''))
        q.retail = True
        q.journal = {'take': tr.get(f'translateQ_{qid}_QTD', ''),
                     'solve': tr.get(f'translateQ_{qid}_QSD', ''),
                     'close': tr.get(f'translateQ_{qid}_QCD', '')}
        info = self.index.quest(qid) if self.index else None
        giver = info['giver'] if info else None
        if giver is not None and self.index and self.index.npc(giver):
            npc = self.index.npc(giver)
            q.add_speaker({'id': giver, 'name': npc['name'],
                           'lector': npc['lector'], 'tile': npc['tile'],
                           'new': False})
        tid = f'translateDQ_{qid}'
        rep_ = None
        if tid in trees:
            tree, ttr, _src = trees[tid]
            rep_ = export.tree_to_graph(q, tree, ttr, self.index, qid)
        if qid in blocks:
            retail.import_block(q, blocks[qid][0])
        else:
            q.extra['qtx'] = {'block': '', 'raw': [], 'sig': ''}
        model.auto_layout(q.graph)
        q.extra['import'] = {'lines': rep_.entries if rep_ else 0,
                             'menus': rep_.menus if rep_ else 0,
                             'notes': len(rep_.lossy) if rep_ else 0,
                             'source': blocks[qid][1] if qid in blocks else ''}
        return q

    def open_any_quest(self, qid):
        """Timeline click: project quest, or a read-only view of a game
        quest that joins the project on its first change (plan 10)."""
        if self.project:
            q = self.project.quest_by_id(qid)
            if q:
                if q is not self.quest:
                    self.open_quest(q)
                return
        if self.preview and self.preview.id == qid and self.quest is self.preview:
            return
        q = self.build_game_quest(qid)
        if q is None:
            return
        self.preview = q
        self._preview_snap = q.snapshot()
        self.open_quest(q)
        self.show_tab(None)
        self.graph.fit()
        imp = q.extra.get('import', {})
        self.set_info(t('retail.view', id=qid, src=imp.get('source') or '-',
                        n=imp.get('lines', 0), menus=imp.get('menus', 0)),
                      'Status.TLabel')

    def _confirm_game_edit(self):
        """First change of a viewed game quest: ask, then add it to the
        project or roll the change back. Returns True when kept."""
        q = self.quest
        if not (self.preview is not None and q is self.preview):
            return True
        ok = messagebox.askyesno(APP_NAME, t('retail.confirm', id=q.id),
                                 parent=self.root)
        if ok:
            self.project.quests.append(q)
            self.preview = None
            self._preview_snap = None
            self.timeline.schedule(50)
            return True
        q.restore(self._preview_snap)
        self.undo.clear()
        self.graph.set_graph(q.graph)
        self.inspector.show(set())
        self.speakers.refresh()
        return False

    def duplicate_any_quest(self, qid):
        q = self.quest_for(qid)
        if q is not None:
            self.duplicate_quest(q)

    def _free_id(self):
        taken = {q.id for q in self.project.quests if q.id}
        free = self.index.free_ids(taken) if self.index else [
            i for i in range(data.MIN_QUEST_ID, data.MAX_QUEST_ID + 1)
            if i not in taken]
        if not free:
            messagebox.showwarning(APP_NAME, t('quest.noid'), parent=self.root)
            return None
        return free[0]

    def duplicate_quest(self, quest):
        if not self.project or quest is None:
            return
        qid = self._free_id()
        if qid is None:
            return
        new = retail.make_own(quest, qid)
        new.title = (quest.title or '') + t('quest.copysuffix')
        self.project.quests.append(new)
        self.mark_dirty()
        self.open_quest(new)

    def delete_quest(self, quest):
        if not self.project or quest not in self.project.quests:
            return
        if not messagebox.askyesno(APP_NAME, t('quest.delete.q', id=quest.id,
                                               title=quest.title),
                                   parent=self.root):
            return
        self.project.quests.remove(quest)
        self.mark_dirty()
        if quest is self.quest:
            self.open_quest(self.project.quests[0] if self.project.quests
                            else None)
        else:
            self.timeline.refresh()

    def save_template(self):
        q = self.quest
        if not q:
            return
        from .palette import _AskString
        dlg = _AskString(self.root, t('quest.template'), q.title or 'Vorlage')
        self.root.wait_window(dlg.win)
        if dlg.result:
            path = data.save_template(dlg.result, q.to_dict())
            self.set_info(t('quest.template.saved', path=path),
                          'StatusOk.TLabel')

    def new_from_template(self, path):
        if not self.project:
            return
        qid = self._free_id()
        if qid is None:
            return
        try:
            d = data.load_template(path)
        except (OSError, ValueError) as e:
            messagebox.showerror(t('error'), str(e), parent=self.root)
            return
        q = retail.make_own(Quest.from_dict(d), qid)
        self.project.quests.append(q)
        self.mark_dirty()
        self.open_quest(q)

    def show_preview(self, quest=None):
        quest = quest or self.quest
        if not quest:
            return
        win = tk.Toplevel(self.root)
        win.title(t('preview.title', id=quest.id))
        win.geometry('900x640')
        win.transient(self.root)
        theme.dark_titlebar(win)
        f = ttk.Frame(win, padding=8)
        f.pack(fill='both', expand=True)
        txt = tk.Text(f, wrap='none', font=theme.FONT_MONO)
        sy = ttk.Scrollbar(f, orient='vertical', command=txt.yview)
        sx = ttk.Scrollbar(f, orient='horizontal', command=txt.xview)
        txt.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side='right', fill='y')
        sx.pack(side='bottom', fill='x')
        txt.pack(fill='both', expand=True)
        txt.insert('1.0', export.preview_text(quest, self.index, t))
        txt.configure(state='disabled')
        ttk.Button(win, text=t('close'), command=win.destroy
                   ).pack(anchor='e', padx=8, pady=(0, 8))

    # -- task / actions / conditions ------------------------------------------

    def npc_label(self, nid):
        if nid in ('', None):
            return ''
        if self.quest:
            spk = self.quest.speaker(nid)
            if spk:
                return f"{spk['name']}  (NPC_{nid})"
        if self.index and self.index.npc(nid):
            return self.index.npc_label(nid)
        return f'NPC_{nid}'

    def parse_npc(self, text):
        import re
        m = re.search(r'NPC_(\d+)', str(text)) or re.fullmatch(
            r'\s*(\d+)\s*', str(text))
        return int(m.group(1)) if m else str(text).strip()

    def _value_text(self, kind, v):
        if v in ('', None):
            return '?'
        idx = self.index
        if kind == 'npc':
            return self.npc_label(v).split('  (')[0]
        if kind == 'object' and idx:
            return idx.object_names.get(str(v)) or str(v)
        if kind == 'location' and idx and str(v) in idx.locations:
            return idx.locations[str(v)]['name']
        if kind.startswith('marker:'):
            return f'#{v}'
        return str(v)

    def _args_text(self, spec, values):
        parts = []
        for f in spec:
            v = values.get(f[0])
            if f[1] == 'tile' and not v:
                continue
            parts.append(self._value_text(f[1], v))
        return ' '.join(parts)

    def action_summary(self, a, when=None):
        spec = model.ACTION_SPECS[(a['kind'], a['verb'])]
        text = t(f"op.{a['kind']}.{a['verb']}") + ' ' + self._args_text(
            spec, a['args'])
        return text + (f'  [{when}]' if when else '')

    def docked_text(self, node):
        kind = node['type']
        if kind == 'task':
            fc = node.get('fc')
            if not fc:
                return t('node.task'), t('op.none'), True
            try:
                model.op_tokens(model.FC_SPECS[fc], node['args'])
                bad = False
            except model.ModelError:
                bad = True
            return t('node.task'), t('op.FC.' + fc) + ' ' + self._args_text(
                model.FC_SPECS[fc], node['args']), bad
        if kind == 'action':
            when = model.action_when(self.quest.graph, node)
            try:
                model.op_tokens(model.ACTION_SPECS[(node['kind'],
                                                    node['verb'])],
                                node['args'])
                bad = when is None
            except model.ModelError:
                bad = True
            return t('node.action'), self.action_summary(node, when), bad
        cond = node.get('cond')
        if cond == 'after':
            text = t('cond.after.sum', q=node.get('quest'),
                     ev=t('ev.' + node.get('event', 'TAKE')))
        elif cond == 'level':
            text = t('cond.level.sum', n=node.get('level'))
        else:
            text = t('cond.guild.sum', g=node.get('guild'),
                     r=node.get('min_rep'))
        return t('node.condition'), text, False

    def quest_choices(self):
        out = []
        if self.index:
            for key, q in sorted(self.index.quests.items(),
                                 key=lambda kv: int(kv[0])):
                out.append((int(key), f"Q_{key}  {q['title']}"))
        if self.project:
            known = {q for q, _ in out}
            for q in self.project.quests:
                if q.id not in known and q is not self.quest:
                    out.append((q.id, f'Q_{q.id}  {q.title}'))
        return out

    def select_task(self):
        if not self.quest:
            return
        self.show_tab('solved')
        self.graph.select([model.TASK_ID])

    def selected_dialog_node(self):
        if not self.quest:
            return None
        sel = [i for i in self.graph.selected
               if self.quest.graph['nodes'].get(i, {}).get('type')
               in ('npc', 'player')]
        return sel[0] if len(sel) == 1 else None

    def fill_action_menu(self, menu, parent):
        for k, v in model.ACTION_MAIN:
            menu.add_command(label=t(f'op.{k}.{v}'), command=lambda k=k, v=v:
                             self.graph.add_docked(model.make_action(k, v,
                                                                     parent)))
        more = theme.Menu(menu, tearoff=0)
        for k, v in model.ACTION_MORE:
            more.add_command(label=t(f'op.{k}.{v}'), command=lambda k=k, v=v:
                             self.graph.add_docked(model.make_action(k, v,
                                                                     parent)))
        menu.add_cascade(label=t('op.more'), menu=more)

    def fill_condition_menu(self, menu):
        for cond in ('after', 'level', 'guild'):
            menu.add_command(label=t('cond.' + cond), command=lambda c=cond:
                             self._add_condition(c))

    def _add_condition(self, cond):
        if not self.quest:
            return
        self.show_tab('first')
        self.graph.add_docked(model.make_condition(cond))

    def _fill_docked_menu(self, menu, kind, nid):
        if kind in ('npc', 'player'):
            sub = theme.Menu(menu, tearoff=0)
            self.fill_action_menu(sub, nid)
            menu.add_cascade(label=t('ctx.addaction'), menu=sub)
        elif kind == 'entry':
            sub = theme.Menu(menu, tearoff=0)
            self.fill_condition_menu(sub)
            menu.add_cascade(label=t('ctx.addcond'), menu=sub)
        elif kind == 'task':
            sub = theme.Menu(menu, tearoff=0)
            for fc in model.FC_MAIN + model.FC_MORE:
                sub.add_command(label=t('op.FC.' + fc),
                                command=lambda fc=fc: self._set_task(fc))
            menu.add_cascade(label=t('ctx.settask'), menu=sub)

    def _set_task(self, fc):
        self.push_undo('task')
        model.set_task(self.quest.graph, fc)
        self.graph.redraw_node(model.TASK_ID)
        self.changed()

    def add_enemy_for_cleararea(self):
        """Plan 6.2: create the ENEMY_CREATE that CLEAR_AREA needs, docked
        at the first offer line (TAKE), same marker, tile and party."""
        q = self.quest
        task = q.task()
        first = model.edge_from(q.graph, model.entry_id('first'), 0)
        a = model.make_action('ACTION', 'ENEMY_CREATE',
                              first[2] if first else None)
        for key in ('marker', 'tile', 'party'):
            if task['args'].get(key) not in ('', None):
                a['args'][key] = task['args'][key]
        if first:
            self.graph.add_docked(a)
        else:
            self.push_undo('qaction')
            for k in ('attached_to', 'x', 'y', 'slot', 'type'):
                a.pop(k, None)
            a['when'] = 'TAKE'
            q.actions.append(a)
            self.changed()

    # -- export ---------------------------------------------------------------

    def export_ui(self, files_only=False, quests=None):
        p = self.project
        if quests is not None and p:
            sub = Project(p.name)
            sub.path, sub.target_archive = p.path, p.target_archive
            sub.quests = [q for q in quests if q is not None]
            p = sub
        game = self.cfg.get('game_dir')
        if not p or not p.quests:
            messagebox.showinfo(t('export.title'), t('export.nothing'),
                                parent=self.root)
            return
        if not game:
            messagebox.showerror(t('export.title'), t('export.nogame'),
                                 parent=self.root)
            return
        name = export.archive_name(p)
        errors, warnings = validate.validate_project(p, self.index, name, t)
        if errors:
            ProblemWindow(self, t('export.errors', n=len(errors)), errors,
                          warnings)
            return
        target = None
        if files_only:
            target = filedialog.askdirectory(title=t('file.exportfiles'),
                                             parent=self.root)
            if not target:
                return
        else:
            if export.game_running():
                messagebox.showerror(t('export.title'), t('export.running'),
                                     parent=self.root)
                return
            conf = export.conflicts(game, name)
            if conf:
                if not messagebox.askyesno(t('export.title'), t(
                        'export.conflict', target=name,
                        mods=', '.join(c[0] for c in conf)),
                        icon='warning', parent=self.root):
                    return
            elif not messagebox.askyesno(t('export.title'),
                                         t('export.target', name=name),
                                         parent=self.root):
                return
        if warnings:
            text = t('export.warnings', n=len(warnings)) + '\n\n' + '\n'.join(
                f'Q_{q.id}: {m}' for q, m, _ in warnings[:12])
            if not messagebox.askyesno(t('export.title'), text, icon='warning',
                                       parent=self.root):
                return
        win = ExportWindow(self)
        result = {}
        logq = queue.Queue()

        def work():
            try:
                result['res'] = export.export_mod(
                    p, game, data.base_dir(), self.index, logq.put,
                    files_only=target)
            except Exception as e:          # shown in the log window
                result['err'] = e

        def poll():
            while True:
                try:
                    win.log(logq.get_nowait())
                except queue.Empty:
                    break
            if th.is_alive():
                self.root.after(100, poll)
                return
            if 'err' in result:
                win.finish(t('export.failed', err=result['err']), ok=False)
            elif target:
                win.finish(t('export.done.files', path=target))
            else:
                win.finish(t('export.done', path=result['res']['archive'])
                           + '\n\n' + t('export.next'))
            if 'err' not in result and self.coach.tutorial.quest in p.quests:
                self.coach.tutorial.exported = True

        th = threading.Thread(target=work, daemon=True)
        th.start()
        poll()

    def schedule_validation(self, ms=600):
        if self._val_job:
            self.root.after_cancel(self._val_job)
        self._val_job = self.root.after(ms, self._auto_validate)

    def _auto_validate(self):
        self._val_job = None
        q = self.quest
        lbl = self.status['validation']
        if not q:
            lbl.configure(text=t('status.validation.none'),
                          style='Status.TLabel')
            return
        E, W = validate.validate_quest(q, self.index, self.project,
                                       export.archive_name(self.project)
                                       if self.project else None, t)
        self.last_validation = (E, W)
        if not E and not W:
            lbl.configure(text=t('status.validation.ok'),
                          style='StatusOk.TLabel')
        else:
            lbl.configure(text=t('status.validation.bad', e=len(E),
                                 w=len(W)),
                          style='StatusErr.TLabel' if E else 'Status.TLabel')

    def validate_ui(self):
        q = self.quest
        if not q:
            return
        E, W = validate.validate_quest(q, self.index, self.project,
                                       export.archive_name(self.project)
                                       if self.project else None, t)
        self._auto_validate()
        ProblemWindow(self, t('val.window', id=q.id),
                      [(q, m, x) for m, x in E], [(q, m, x) for m, x in W])

    def goto_problem(self, quest, nid):
        if quest is not self.quest:
            self.open_quest(quest)
        if isinstance(nid, str) and nid.startswith('qaction:'):
            self.graph.select([])
            self.inspector.show_qaction(int(nid.split(':')[1]))
            return
        if nid and nid in quest.graph['nodes']:
            node = quest.graph['nodes'][nid]
            st = node.get('state')
            if node.get('type') == 'task':
                st = 'solved'
            elif node.get('type') in ('action', 'condition'):
                st = quest.graph['nodes'].get(node.get('attached_to'), {}).get(
                    'state', st)
            self.show_tab(st if st in model.STATES and st != 'neutral'
                          else None)
            self.graph.scroll_to_node(nid, 120)
            self.graph.select([nid])
        else:
            self.graph.select([])

    def node_style(self, node):
        """(title, header colour) for a dialog node."""
        if node.get('type') == 'player' or node.get('speaker') == model.PLAYER:
            return t('node.player'), theme.PLAYER_COLOR
        return self.speaker_style(node.get('speaker'))

    def speaker_style(self, sid):
        if sid == model.PLAYER:
            return t('node.player'), theme.PLAYER_COLOR
        if not self.quest:
            return '?', theme.SPEAKER_COLORS[0]
        for i, s in enumerate(self.quest.speakers):
            if s['id'] == sid:
                return s['name'], theme.SPEAKER_COLORS[
                    i % len(theme.SPEAKER_COLORS)]
        return f'NPC_{sid}' if sid is not None else '?', theme.MUT

    def add_speaker(self, spk):
        if not self.quest:
            return
        self.push_undo('speaker')
        self.quest.add_speaker(spk)
        if self.quest.giver is None and isinstance(spk['id'], int) \
                and not self.quest.retail:
            self.quest.giver = spk['id']
        self.changed()

    def add_speaker_node(self, sid, wx, wy, connect_from=None):
        if not self.quest:
            return None
        ntype = 'player' if sid == model.PLAYER else 'npc'
        return self.graph.add_node_at(ntype, wx, wy, speaker=sid,
                                      state=self.tab_state or 'first',
                                      connect_from=connect_from)

    def insert_speaker_node(self, sid):
        """Double click in the speaker box: right of the selected node,
        connected to its first free out port (plan 5.3)."""
        if not self.quest:
            return
        g = self.quest.graph
        sel = [i for i in self.graph.selected if i in g['nodes']]
        src = sel[0] if len(sel) == 1 else None
        if src is None or g['nodes'][src]['type'] == 'comment':
            ent = model.entry_id(self.tab_state or 'first')
            src = ent if ent in g['nodes'] else None
        if src is None:
            self.add_speaker_node(sid, 300, 200)
            return
        n = g['nodes'][src]
        w, h = model.node_size(n)
        port = 0
        for p in range(model.out_port_count(n)):
            if model.edge_from(g, src, p) is None:
                port = p
                break
        self.add_speaker_node(sid, n['x'] + w + 80, n['y'] + port * 40,
                              connect_from=(src, port))

    def mark_speaker_lines(self, sid):
        if self.quest:
            ids = [i for i, n in self.quest.graph['nodes'].items()
                   if n.get('speaker') == sid]
            self.graph.select(ids)

    def _fill_add_menu(self, menu, wx, wy):
        menu.add_command(label=t('node.player'), command=lambda:
                         self.add_speaker_node(model.PLAYER, wx, wy))
        for s in self.quest.speakers:
            menu.add_command(label=self.speaker_style(s['id'])[0],
                             command=lambda s=s: self.add_speaker_node(
                                 s['id'], wx, wy))

    def _edge_drop_empty(self, frm, port, wx, wy, ev):
        """Dragging an edge into the void: popup Spieler / speakers /
        Kommentar, the new node is connected at once (plan 5.3)."""
        menu = theme.Menu(self.root, tearoff=0)
        x, y = int(wx), int(wy - model.HEADER_H / 2)
        menu.add_command(label=t('node.player'), command=lambda:
                         self.add_speaker_node(model.PLAYER, x, y, (frm, port)))
        for s in self.quest.speakers:
            menu.add_command(label=self.speaker_style(s['id'])[0],
                             command=lambda s=s: self.add_speaker_node(
                                 s['id'], x, y, (frm, port)))
        menu.add_separator()
        menu.add_command(label=t('node.comment'), command=lambda:
                         self.graph.add_node_at('comment', x, y))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _open_node(self, nid):
        self.graph.select([nid])
        self.inspector.focus_text()

    def _selection_changed(self):
        self.inspector.show(self.graph.selected)
        self._update_status()

    def mod_archives(self):
        game = self.cfg.get('game_dir')
        if not game:
            return []
        return sorted(os.path.basename(p) for p in
                      glob.glob(os.path.join(game, 'Mods', '*.wd')))

    def debug_nodes(self):
        """300 chained nodes to prove the canvas stays fluid (plan M2)."""
        if not self.quest:
            return
        g = self.quest.graph
        self.push_undo('debug')
        rnd = random.Random(1)
        state = self.tab_state or 'first'
        prev = model.entry_id(state)
        model.ensure_entry(g, state)
        words = ('Hallo', 'Held', 'Gold', 'Yamalin', 'Zwerge', 'Turm',
                 'Sumpf', 'Ferid', 'Tago', 'Gandohar')
        if not self.quest.speakers:
            self.quest.add_speaker({'id': 3, 'name': 'Tago', 'lector': 4,
                                    'tile': 'F5', 'new': False})
        for i in range(300):
            if i % 2:
                n = model.make_node('player', 0, 0, state)
                n['kind'] = 'question'
                n['lines'] = [dict(model.new_line(state), text=' '.join(
                    rnd.choice(words) for _ in range(rnd.randint(2, 6))))
                    for _ in range(rnd.randint(1, 3))]
            else:
                n = model.make_node('npc', 0, 0, state,
                                    self.quest.speakers[0]['id'])
                n['lines'][0]['text'] = ' '.join(
                    rnd.choice(words) for _ in range(rnd.randint(3, 9)))
            nid = model.add_node(g, n)
            model.connect(g, prev, rnd.randrange(model.out_port_count(
                g['nodes'][prev])), nid)
            if rnd.random() < 0.3:
                # only nodes with out ports (not comments, task, actions)
                prev = rnd.choice([k for k, v in g['nodes'].items()
                                   if model.out_port_count(v) > 0])
            else:
                prev = nid
        model.auto_layout(g)
        t0 = time.perf_counter()
        self.graph.set_graph(g)
        ms = (time.perf_counter() - t0) * 1000
        self.graph.fit()
        self.changed()
        self.set_info(f'300 nodes: redraw {ms:.0f} ms', 'StatusOk.TLabel')

    # -- undo / clipboard ---------------------------------------------------

    def push_undo(self, label=''):
        if self.quest:
            self.undo.push(self.quest.snapshot(), label)

    def changed(self, from_inspector=False):
        """Model changed: dirty flag, status, panels."""
        if not self._confirm_game_edit():
            return
        self.timeline.schedule()
        self.schedule_validation()
        self.mark_dirty()
        self._update_status()
        if not from_inspector:
            self.inspector.refresh()
        self.speakers.refresh()
        if self.quest and set(self.tab_labels) - {None} != set(
                self.quest.states_present()):
            self._build_tabs()

    def _restore(self, snap):
        if snap is None:
            return
        self.quest.restore(snap)
        self.graph.set_graph(self.quest.graph)
        self.changed()

    def do_undo(self):
        if self.quest:
            self._restore(self.undo.undo(self.quest.snapshot()))

    def do_redo(self):
        if self.quest:
            self._restore(self.undo.redo(self.quest.snapshot()))

    def copy(self):
        if not self.quest:
            return
        clip = model.copy_nodes(self.quest.graph, self.graph.selected)
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
        self.status['validation'].configure(cursor='hand2',
                                            text=t('status.validation.none'))
        self.status['validation'].bind('<Button-1>',
                                       lambda e: self.validate_ui())
        self.status['info'] = ttk.Label(bar, text='', style='Status.TLabel')
        self.status['info'].pack(side='right')
        self.status['hint'] = ttk.Label(bar, text='', style='Status.TLabel')
        self.status['hint'].pack(side='right')
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
        qtext = t('status.noquest')
        if self.quest and self.quest.id:
            qtext = f'Q_{self.quest.id}'
            if self.preview is not None and self.quest is self.preview:
                qtext += '  ' + t('status.gameview')
            elif self.quest.retail:
                qtext += '  ' + t('status.gameedit')
        s['quest'].configure(text=qtext)
        n = self.quest.node_count() if self.quest else 0
        text = t('status.nodes', n=n)
        if DEBUG and self.graph.last_frame_ms:
            text += '   ' + t('status.frame', ms=self.graph.last_frame_ms)
        s['nodes'].configure(text=text)
        if not self.quest:
            s['validation'].configure(text=t('status.validation.none'),
                                      style='Status.TLabel')
        self._update_title()

    def _update_title(self):
        name = (self.project.display_name() or t('project.untitled')
                if self.project else '')
        star = ' *' if self.project and self.project.dirty else ''
        self.root.title(f'{name}{star} - {APP_NAME}' if name else APP_NAME)

    def set_info(self, text, style='Status.TLabel'):
        self.status['info'].configure(text=text, style=style)

    def set_hint(self, text):
        self.status['hint'].configure(text=text[:140])

    def timeline_height(self, h):
        try:
            if self.vars['timeline'].get():
                self.vpane.sashpos(0, h)
        except tk.TclError:
            pass

    # -- keys ---------------------------------------------------------------

    def _typing(self):
        w = self.root.focus_get()
        return isinstance(w, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox,
                              ttk.Spinbox, tk.Listbox))

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
        r.bind('<Control-e>', lambda e: self.export_ui())
        r.bind('<F7>', lambda e: self.validate_ui())
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
        if self._carry and self.index is not None:
            self._update_status()
            self._index_ready(self.index, True, 0.0)
            return
        game = data.find_game_dir(self.cfg)
        if not game and self.selftest:
            with open(self.selftest, 'w', encoding='utf-8') as f:
                f.write('no game dir\n')
            self.root.after(50, self.root.destroy)
            return
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
        q = queue.Queue()

        def progress(step, frac):
            # worker thread: only hand the step to the main thread
            q.put((step, frac))

        def work():
            try:
                result['idx'] = data.load_index(game, progress)
            except Exception as e:      # shown to the user below
                result['err'] = e

        def drain():
            while True:
                try:
                    step, frac = q.get_nowait()
                except queue.Empty:
                    break
                if isinstance(step, tuple):
                    text = t('index.step.' + step[0], name=step[1])
                else:
                    text = t('index.step.' + step)
                win.update(text, frac)

        def poll():
            drain()
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
        self.inspector.refresh()
        self.timeline.refresh()
        if self.selftest:
            # QF2_SELFTEST=<file>: write the start-up time and quit
            try:
                with open(self.selftest, 'w', encoding='utf-8') as f:
                    f.write(f'version={VERSION} start={total:.3f} '
                            f'index={seconds:.3f} cache={from_cache} '
                            f'quests={len(index.quests)} '
                            f'frozen={getattr(sys, "frozen", False)}\n')
                    deep = os.environ.get('QF2_SELFTEST_EXPORT')
                    if deep:
                        f.write(self._selftest_export(deep) + '\n')
            except Exception as e:           # reported in the file
                with open(self.selftest, 'a', encoding='utf-8') as f:
                    f.write(f'selftest failed: {e!r}\n')
            finally:
                self.root.after(50, self.root.destroy)
            return
        if not self.cfg.get('guide_seen') and not getattr(self, '_tour_done',
                                                          False):
            self._tour_done = True
            self.root.after(300, lambda: self.coach.start('tour'))

    def _selftest_export(self, spec):
        """QF2_SELFTEST_EXPORT=<project>|<empty game dir>: validate and export
        a project without registry change, read the archive back."""
        import tw1_wd
        project_path, game = spec.split('|', 1)
        p = Project.load(project_path)
        errors, warnings = validate.validate_project(
            p, self.index, export.archive_name(p), t)
        os.makedirs(os.path.join(game, 'Mods'), exist_ok=True)
        res = export.export_mod(p, game, data.base_dir(), self.index,
                                lambda m: None, register=False)
        paths = sorted(e.path for e in tw1_wd.read(res['archive']))
        return (f'export ok errors={len(errors)} warnings={len(warnings)} '
                f'files={paths}')

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
        self.preview = None
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

    def switch_lang(self, code):
        """Rebuild the window in the other language right away. Project,
        open quest, undo history, index and view go to the new window, so
        nothing is lost and nothing is read again (design template 5.3)."""
        if code == get_lang():
            self.lang_var.set(code)
            return
        self.cfg.set('lang', code)
        self.cfg.set('window', self.root.geometry())
        self.cfg.save()
        g = self.graph
        self.restart = {
            'index': self.index, 'project': self.project,
            'quest': self.quest, 'undo': self.undo,
            'preview': self.preview, 'preview_snap': self._preview_snap,
            'clipboard': self.clipboard, 'tab': self.tab_state,
            'zoom': g.zoom_i, 'view': (g.xview()[0], g.yview()[0]),
            'grid': self.grid_var.get(), 'edges': self.edge_var.get(),
            'sash': self._sash_positions(),
        }
        # timers of this window must not fire into the next one
        # (plain Tcl cancel: after_cancel would delete the Python callback
        # commands that destroy() deletes again)
        for job in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
            try:
                self.root.tk.call('after', 'cancel', job)
            except tk.TclError:
                pass
        self.root.destroy()

    def _sash_positions(self):
        out = {}
        for name in ('vpane', 'hpane', 'side'):
            pane = getattr(self, name)
            try:
                out[name] = [pane.sashpos(i)
                             for i in range(len(pane.panes()) - 1)]
            except tk.TclError:
                out[name] = []
        return out

    def _restore_carry(self, c):
        """Counterpart of switch_lang in the new window."""
        self.index = c['index']
        self.project = c['project']
        self.clipboard = c['clipboard']
        self.preview = c['preview']
        self._preview_snap = c['preview_snap']
        self._tour_done = True
        self.grid_var.set(c['grid'])
        self.graph.set_grid(c['grid'])
        self.edge_var.set(c['edges'])
        self.graph.set_edge_style(c['edges'])
        self.open_quest(c['quest'])
        self.undo = c['undo']
        if c['quest'] is not None and c['tab'] != self.tab_state:
            self.show_tab(c['tab'])

        def later():
            for name, positions in c['sash'].items():
                pane = getattr(self, name)
                for i, pos in enumerate(positions):
                    try:
                        pane.sashpos(i, pos)
                    except tk.TclError:
                        pass
            if c['quest'] is not None:
                self.graph.set_zoom(c['zoom'])
                self.graph.xview_moveto(c['view'][0])
                self.graph.yview_moveto(c['view'][1])
        self.root.after(80, later)

    def show_about(self):
        win = tk.Toplevel(self.root)
        win.title(t('about.title', app=APP_NAME))
        win.resizable(False, False)
        win.transient(self.root)
        theme.dark_titlebar(win)
        f = ttk.Frame(win, padding=24)
        f.pack(fill='both', expand=True)
        head = ttk.Frame(f)
        head.pack(anchor='w', fill='x', pady=(0, 12))
        if getattr(self, '_icon', None) is not None:
            ttk.Label(head, image=self._icon).pack(side='left', padx=(0, 12))
        names = ttk.Frame(head)
        names.pack(side='left')
        ttk.Label(names, text=APP_NAME, style='Brand.TLabel').pack(anchor='w')
        ttk.Label(names, text=t('about.version', v=VERSION) +
                  '   TW1QuestCreator.exe', style='Muted.TLabel'
                  ).pack(anchor='w')
        ttk.Label(f, text=t('about.links') + ':').pack(anchor='w')
        for key, url in LINKS:
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


class ProblemWindow:
    """Errors and warnings; double click jumps to the node (plan 8)."""

    def __init__(self, app, title, errors, warnings=()):
        self.app = app
        self.rows = []
        win = tk.Toplevel(app.root)
        win.title(title)
        win.transient(app.root)
        win.geometry('700x420')
        theme.dark_titlebar(win)
        f = ttk.Frame(win, padding=10)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=title, style='Brand.TLabel').pack(anchor='w')
        ttk.Label(f, text=t('export.gotonode'), style='Muted.TLabel'
                  ).pack(anchor='w', pady=(0, 6))
        self.lst = tk.Listbox(f, font=theme.FONT, activestyle='none')
        self.lst.pack(fill='both', expand=True)
        if not errors and not warnings:
            self.lst.insert('end', t('val.ok'))
            self.lst.itemconfigure(0, foreground=theme.OK)
        for head, items, color in ((t('val.errors'), errors, theme.ERR),
                                   (t('val.warnings'), warnings, theme.GOLD)):
            if not items:
                continue
            self.lst.insert('end', f'{head} ({len(items)})')
            self.lst.itemconfigure('end', foreground=color)
            self.rows.append(None)
            for q, msg, nid in items:
                self.lst.insert('end', f'   Q_{q.id}: {msg}')
                self.rows.append((q, nid))
        if not errors and not warnings:
            self.rows.append(None)
        self.lst.bind('<Double-Button-1>', self._go)
        ttk.Button(f, text=t('close'), command=win.destroy
                   ).pack(anchor='e', pady=(8, 0))
        self.win = win

    def _go(self, ev):
        sel = self.lst.curselection()
        if sel and sel[0] < len(self.rows) and self.rows[sel[0]]:
            q, nid = self.rows[sel[0]]
            self.app.goto_problem(q, nid)


class ExportWindow:
    """Log of a running export (plan 2.2: build in a thread with log)."""

    def __init__(self, app):
        self.win = tk.Toplevel(app.root)
        self.win.title(t('export.title'))
        self.win.transient(app.root)
        self.win.geometry('720x420')
        theme.dark_titlebar(self.win)
        f = ttk.Frame(self.win, padding=10)
        f.pack(fill='both', expand=True)
        self.txt = tk.Text(f, wrap='word', font=theme.FONT_MONO, height=16)
        self.txt.pack(fill='both', expand=True)
        self.txt.tag_configure('ok', foreground=theme.OK)
        self.txt.tag_configure('err', foreground=theme.ERR)
        self.btn = ttk.Button(f, text=t('close'), command=self.win.destroy)
        self.btn.pack(anchor='e', pady=(8, 0))
        self.btn.state(['disabled'])

    def _put(self, text, tag=None):
        try:
            self.txt.insert('end', text + '\n', tag)
            self.txt.see('end')
        except tk.TclError:
            pass

    def log(self, msg):
        kind = msg[0]
        if kind == 'base':
            text = t('export.log.base', kind=msg[1], src=msg[2])
        elif kind == 'file':
            text = t('export.log.file', inner=msg[1], n=msg[2])
        elif kind == 'unpack':
            text = t('export.log.unpack', name=msg[1], n=msg[2])
        elif kind == 'pack':
            text = t('export.log.pack', name=msg[1])
        elif kind == 'verified':
            text = t('export.log.verified', n=msg[1])
        elif kind == 'backup':
            text = t('export.log.backup', name=msg[1])
        elif kind == 'registry':
            text = t('export.log.registry', name=msg[1], old=msg[2])
        elif kind == 'overlay_cleaned':
            text = t('export.log.overlay', inner=msg[1])
        elif kind == 'removed':
            text = t('export.log.removed', inner=msg[1])
        else:
            text = ' '.join(str(x) for x in msg)
        self._put(text)

    def finish(self, text, ok=True):
        self._put('')
        self._put(text, 'ok' if ok else 'err')
        try:
            self.btn.state(['!disabled'])
        except tk.TclError:
            pass


class RetailDialog:
    """Pick one ``translateDQ_<n>`` tree: filter by text, single/multi
    player, source."""

    def __init__(self, app, trees):
        self.result = None
        self.win = tk.Toplevel(app.root)
        self.win.title(t('retail.title'))
        self.win.transient(app.root)
        self.win.geometry('680x560')
        theme.dark_titlebar(self.win)
        f = ttk.Frame(self.win, padding=10)
        f.pack(fill='both', expand=True)
        top = ttk.Frame(f)
        top.pack(fill='x')
        ttk.Label(top, text=t('retail.filter')).pack(side='left')
        self.q = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.q)
        ent.pack(side='left', fill='x', expand=True, padx=6)
        ent.bind('<KeyRelease>', lambda e: self._filter())
        ent.bind('<Down>', lambda e: self.lst.focus_set())
        self.kind = tk.StringVar(value='sp')
        for key in ('sp', 'mp', 'all'):
            ttk.Radiobutton(top, text=t('retail.kind.' + key), value=key,
                            variable=self.kind, command=self._filter
                            ).pack(side='left')
        box = ttk.Frame(f)
        box.pack(fill='both', expand=True, pady=6)
        self.lst = tk.Listbox(box, font=theme.FONT, activestyle='none')
        sb = ttk.Scrollbar(box, orient='vertical', command=self.lst.yview)
        self.lst.configure(yscrollcommand=sb.set)
        self.lst.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.lst.bind('<Double-Button-1>', lambda e: self._ok())
        self.lst.bind('<Return>', lambda e: self._ok())
        self.rows = []
        for tid, (tree, tr, src) in trees.items():
            if not tid.startswith('translateDQ_'):
                continue
            try:
                qid = int(tid.split('_')[1])
            except ValueError:
                continue
            title = tr.get(f'translateQ_{qid}', '')
            label = (f'Q_{qid:<4} {title}   ({len(tree.entries)} '
                     f'{t("retail.lines")}, {src})')
            self.rows.append((qid, tid, label))
        self.rows.sort()
        self.shown = []
        b = ttk.Frame(f)
        b.pack(anchor='e')
        ttk.Button(b, text=t('ok'), style='Accent.TButton',
                   command=self._ok).pack(side='left', padx=(0, 6))
        ttk.Button(b, text=t('cancel'), command=self.win.destroy
                   ).pack(side='left')
        self.win.bind('<Escape>', lambda e: self.win.destroy())
        self._filter()
        ent.focus_set()
        self.win.grab_set()

    def _filter(self):
        q = self.q.get().strip().lower()
        kind = self.kind.get()
        self.lst.delete(0, 'end')
        self.shown = []
        for qid, tid, label in self.rows:
            mp = qid >= 700
            if (kind == 'sp' and mp) or (kind == 'mp' and not mp):
                continue
            if q and q not in label.lower():
                continue
            self.shown.append(tid)
            self.lst.insert('end', label)
        if self.shown:
            self.lst.selection_set(0)

    def _ok(self):
        sel = self.lst.curselection()
        if sel:
            self.result = self.shown[sel[0]]
            self.win.destroy()


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
    carry = None
    while True:
        app = App(start_time, carry)
        app.run()
        if not app.restart:
            break
        carry, start_time = app.restart, None
