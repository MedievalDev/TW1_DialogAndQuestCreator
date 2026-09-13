"""Main window: menu bar, panels, status bar, project handling.

Milestone 1: the frame of the tool. Panels that belong to later milestones
are placeholders; their menu entries exist but are disabled so the final
structure (plan section 3) is visible from the first start.
"""

import json
import os
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, VERSION, data, theme
from .i18n import t, set_lang, get_lang, detect_lang
from .model import Project, ModelError, PROJECT_EXT

GUIDE_URL = 'https://alchemy-fox.de/game/TW1_DialogAndQuestCreator/'
GITHUB_URL = 'https://github.com/MedievalDev/TW1_DialogAndQuestCreator'
COMMUNITY_URL = 'https://twmp.alchemy-fox.de/'


class App:
    def __init__(self, start_time=None):
        self.t_start = start_time or time.perf_counter()
        self.cfg = data.Config()
        set_lang(self.cfg.get('lang') or detect_lang())
        self.index = None
        self.project = None
        self.quest = None

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
        for entry in (('edit.undo', 'Ctrl+Z'), ('edit.redo', 'Ctrl+Y'),
                      None, ('edit.cut', 'Ctrl+X'), ('edit.copy', 'Ctrl+C'),
                      ('edit.paste', 'Ctrl+V'), ('edit.duplicate', 'Ctrl+D'),
                      ('edit.delete', 'Entf' if get_lang() == 'de'
                       else 'Del'), ('edit.selectall', 'Ctrl+A'),
                      None, ('edit.autolayout', 'Ctrl+L')):
            if entry is None:
                m.add_separator()
            else:
                m.add_command(label=t(entry[0]),
                              accelerator=self._acc(entry[1]),
                              state='disabled')

    def _fill_view(self, m):
        m.add_command(label=t('view.zoomin'), accelerator=self._acc('Ctrl++'),
                      state='disabled')
        m.add_command(label=t('view.zoomout'), accelerator=self._acc('Ctrl+-'),
                      state='disabled')
        m.add_command(label=t('view.zoom100'), accelerator=self._acc('Ctrl+0'),
                      state='disabled')
        m.add_command(label=t('view.fit'), accelerator='F', state='disabled')
        m.add_separator()
        for key, var in (('view.timeline', 'timeline'),
                         ('view.palette', 'palette'),
                         ('view.inspector', 'inspector'),
                         ('view.coach', 'coach')):
            m.add_checkbutton(label=t(key), variable=self.vars[var],
                              command=self._apply_panels)
        m.add_separator()
        m.add_checkbutton(label=t('view.grid'), variable=self.grid_var,
                          state='disabled')
        edges = tk.Menu(m, tearoff=0)
        edges.add_radiobutton(label=t('view.edges.curve'), value='curve',
                              variable=self.edge_var, state='disabled')
        edges.add_radiobutton(label=t('view.edges.line'), value='line',
                              variable=self.edge_var, state='disabled')
        m.add_cascade(label=t('view.edges'), menu=edges)
        m.add_separator()
        lang = tk.Menu(m, tearoff=0)
        for code in ('de', 'en'):
            lang.add_radiobutton(label=t(f'view.lang.{code}'), value=code,
                                 variable=self.lang_var,
                                 command=self._change_lang)
        m.add_cascade(label=t('view.lang'), menu=lang)

    def _fill_quest(self, m):
        m.add_command(label=t('quest.new'), state='disabled')
        m.add_command(label=t('quest.duplicate'), state='disabled')
        m.add_command(label=t('quest.delete'), state='disabled')
        m.add_separator()
        m.add_command(label=t('quest.validate'), accelerator='F7',
                      state='disabled')
        m.add_command(label=t('quest.preview'), state='disabled')
        m.add_command(label=t('quest.template'), state='disabled')

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

        self.graph = tk.Canvas(self.hpane, bg=theme.CANVAS_BG,
                               highlightthickness=0)
        self.graph.bind('<Configure>', self._draw_graph_placeholder)

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
        # vertical: timeline above, hpane below
        for w in (self.timeline, self.hpane):
            if str(w) in self.vpane.panes():
                self.vpane.forget(w)
        if v['timeline'].get():
            self.vpane.add(self.timeline, weight=0)
        self.vpane.add(self.hpane, weight=1)
        # horizontal: palette | graph | side
        for w in (self.palette, self.graph, self.side):
            if str(w) in self.hpane.panes():
                self.hpane.forget(w)
        if v['palette'].get():
            self.hpane.add(self.palette, weight=0)
        self.hpane.add(self.graph, weight=1)
        show_side = v['inspector'].get() or v['coach'].get()
        if show_side:
            self.hpane.add(self.side, weight=0)
            for w, key in ((self.inspector, 'inspector'), (self.coach, 'coach')):
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
            c.create_text(c.winfo_width() // 2, c.winfo_height() // 2,
                          text=t('graph.empty'), fill=theme.MUT,
                          font=theme.FONT, justify='center',
                          tags='placeholder')

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
        s['nodes'].configure(text=t('status.nodes', n=n))
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

    def _bind_keys(self):
        r = self.root
        r.bind('<Control-n>', lambda e: self.new_project())
        r.bind('<Control-o>', lambda e: self.open_project())
        r.bind('<Control-s>', lambda e: self.save_project())
        r.bind('<Control-S>', lambda e: self.save_project_as())

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
        cached = self._try_cache(game)
        if cached:
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
        self.quest = None
        self._update_status()
        self._draw_graph_placeholder()

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
