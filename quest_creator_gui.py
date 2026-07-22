"""TW1 Dialog & Quest Creator - desktop UI.

Point-and-click quest building for Two Worlds (2007): pick a giver and a
target from named NPC lists, write the journal and dialog texts, press
Build - the tool assembles qtx + lan, packs with the reference packer and
installs the mod into the game.

Everything this UI does follows the play-tested pipeline of
build_quest_tago.py; see README.md for the rules it enforces.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import webbrowser
import winreg
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

import questforge
import tw1_lan
import tw1_qtx
import tw1_wd
import wdio

APP = 'TW1 Dialog & Quest Creator'
GUIDE_URL = 'https://alchemy-fox.de/game/TW1_DialogAndQuestCreator/'
GITHUB_URL = 'https://github.com/MedievalDev/TW1_DialogAndQuestCreator'
REG_MODS = r'SOFTWARE\Reality Pump\TwoWorlds\Mods'

# Dialog-state flags (see README - 0.FT.AS is the offer, nothing else works)
F_FTAS = 0x20001
F_QNSAE = 0x100
F_QSAE = 0x40200
F_QC = 0x8

# ---------------------------------------------------------------------------
# Dark theme (same palette as the TW1MP server panel / website)

BG = '#14110e'; PANEL = '#1c1813'; FIELD = '#231e17'
INK = '#ece7db'; MUT = '#9a938a'; LINE = '#352f26'
GOLD = '#d2a044'; GOLD_HI = '#e3b45c'; SEL = '#3a3122'
OK = '#43b563'; ERR = '#e06c60'

# Distinct, dark-theme-legible colours cycled through for dialog branches.
BRANCH_COLORS = ['#e06c60', '#6ca0e0', '#7fbf7f', '#e0a050',
                 '#c090e0', '#5fc7c7', '#d4796b', '#a0b060']


class _TreeTip:
    """A hover tooltip for a Treeview. `text_for(item)` returns the tip
    string (or None) for the row under the cursor."""

    def __init__(self, tree, text_for):
        self.tree = tree
        self.text_for = text_for
        self.tip = None
        self.item = None
        tree.bind('<Motion>', self._move, add='+')
        tree.bind('<Leave>', lambda e: self._hide(), add='+')

    def _move(self, ev):
        item = self.tree.identify_row(ev.y)
        if item != self.item:
            self._hide()
            self.item = item
            text = self.text_for(item) if item else None
            if text:
                self._show(text, ev)

    def _show(self, text, ev):
        self.tip = tk.Toplevel(self.tree)
        self.tip.wm_overrideredirect(True)
        self.tip.attributes('-topmost', True)
        tk.Label(self.tip, text=text, bg=PANEL, fg=INK, bd=1,
                 relief='solid', justify='left', padx=6, pady=3,
                 font=('Segoe UI', 8)).pack()
        self.tip.wm_geometry(f'+{ev.x_root + 14}+{ev.y_root + 12}')

    def _hide(self):
        if self.tip:
            self.tip.destroy()
            self.tip = None
        self.item = None


def dark_titlebar(window):
    """Dark title bar on Windows.

    Immersive dark mode alone loses against the user's "accent colour on
    title bars" setting, so the caption colour is set explicitly too
    (Windows 11 22000+); both calls are no-ops on older builds.
    """
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        dwm = ctypes.windll.dwmapi
        flag = ctypes.c_int(1)
        for attr in (20, 19):        # DWMWA_USE_IMMERSIVE_DARK_MODE, pre-20H1
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(flag),
                                         ctypes.sizeof(flag)) == 0:
                break
        def bgr(hex_colour):
            r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
            return ctypes.c_int(b << 16 | g << 8 | r)
        for attr, colour in ((35, PANEL), (36, INK)):     # caption, text
            value = bgr(colour)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value),
                                      ctypes.sizeof(value))
    except Exception:
        pass


def apply_dark_theme(root):
    root.configure(background=BG)
    dark_titlebar(root)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=BG, foreground=INK, bordercolor=LINE,
                    darkcolor=BG, lightcolor=BG, troughcolor=PANEL,
                    fieldbackground=FIELD, selectbackground=SEL,
                    selectforeground=GOLD_HI, insertcolor=INK,
                    font=('Segoe UI', 9))
    style.configure('TLabelframe', bordercolor=LINE)
    style.configure('TLabelframe.Label', foreground=GOLD)
    style.configure('TButton', background=PANEL, padding=(12, 5),
                    borderwidth=1, focusthickness=1, focuscolor=LINE)
    style.map('TButton', background=[('pressed', SEL), ('active', '#282219')],
              foreground=[('disabled', '#5c564c')])
    style.configure('Accent.TButton', background=GOLD, foreground='#17130b')
    style.map('Accent.TButton',
              background=[('pressed', '#b88d3c'), ('active', GOLD_HI),
                          ('disabled', '#6d5b31')],
              foreground=[('disabled', '#3a3226')])
    style.configure('TNotebook', bordercolor=LINE, tabmargins=(8, 6, 8, 0))
    style.configure('TNotebook.Tab', background=PANEL, foreground=MUT,
                    padding=(16, 6), bordercolor=LINE)
    style.map('TNotebook.Tab', background=[('selected', BG)],
              foreground=[('selected', GOLD)])
    style.configure('Treeview', background=FIELD, fieldbackground=FIELD,
                    rowheight=22, bordercolor=LINE)
    style.map('Treeview', background=[('selected', SEL)],
              foreground=[('selected', GOLD_HI)])
    style.configure('Treeview.Heading', background=PANEL, foreground=MUT,
                    bordercolor=LINE, relief='flat', padding=(6, 4))
    style.map('Treeview.Heading',
              background=[('active', '#282219'), ('pressed', SEL)],
              foreground=[('active', INK)])
    # clam draws radio/check hover as a light fill; keep it dark and only
    # let the indicator dot pick up the gold accent.
    for cls in ('TCheckbutton', 'TRadiobutton'):
        style.configure(cls, background=BG, foreground=INK,
                        indicatorbackground=FIELD, indicatorforeground=GOLD,
                        bordercolor=LINE, focuscolor=BG, padding=(2, 2))
        style.map(cls,
                  background=[('active', BG), ('pressed', BG),
                              ('selected', BG)],
                  foreground=[('active', GOLD_HI), ('disabled', '#5c564c')],
                  indicatorbackground=[('selected', GOLD), ('pressed', SEL),
                                       ('active', FIELD)],
                  indicatorforeground=[('selected', '#17130b')])
    # Read-only comboboxes otherwise render their text in the *selection*
    # colours, which on a dark theme means dark-on-dark.
    style.configure('TCombobox', arrowcolor=MUT, foreground=INK,
                    fieldbackground=FIELD, background=PANEL,
                    selectbackground=FIELD, selectforeground=INK,
                    bordercolor=LINE, padding=(6, 3))
    style.map('TCombobox',
              fieldbackground=[('readonly', FIELD), ('disabled', PANEL)],
              foreground=[('readonly', INK), ('disabled', '#5c564c')],
              selectbackground=[('readonly', FIELD)],
              selectforeground=[('readonly', INK)],
              arrowcolor=[('active', GOLD)])
    for cls in ('Vertical.TScrollbar', 'Horizontal.TScrollbar'):
        style.configure(cls, background=PANEL, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUT,
                        darkcolor=PANEL, lightcolor=PANEL,
                        gripcount=0, relief='flat', arrowsize=13)
        style.map(cls, background=[('active', '#3a3226')],
                  arrowcolor=[('active', GOLD)])
    style.configure('Brand.TLabel', foreground=GOLD,
                    font=('Georgia', 12, 'bold'))
    # Themed stand-in for the native menu bar, which Windows always draws
    # light and which no ttk style can reach.
    style.configure('Menubar.TFrame', background=PANEL)
    style.configure('Menubar.TLabel', background=PANEL, foreground=MUT,
                    padding=(12, 5))
    style.map('Menubar.TLabel', background=[('active', SEL)],
              foreground=[('active', GOLD_HI)])
    for pattern, value in (
            ('*Text.background', '#0f0d0a'), ('*Text.foreground', INK),
            ('*Text.insertBackground', INK), ('*Text.selectBackground', SEL),
            ('*Text.borderWidth', 0), ('*Text.highlightThickness', 1),
            ('*Text.highlightBackground', LINE),
            ('*Text.highlightColor', GOLD),
            ('*Listbox.background', FIELD), ('*Listbox.foreground', INK),
            ('*Listbox.selectBackground', SEL),
            ('*Listbox.borderWidth', 0), ('*Listbox.highlightThickness', 1),
            ('*Listbox.highlightBackground', LINE),
            ('*Menu.background', PANEL), ('*Menu.foreground', INK),
            ('*Menu.activeBackground', SEL),
            ('*Menu.activeForeground', GOLD_HI),
            ('*TCombobox*Listbox.background', FIELD),
            ('*TCombobox*Listbox.foreground', INK),
            ('*TCombobox*Listbox.selectBackground', SEL),
            ('*Toplevel.background', BG)):
        root.option_add(pattern, value)


# ---------------------------------------------------------------------------
# Game data

class DataHub:
    """Loads everything the pickers need from the player's own install."""

    def __init__(self):
        self.game_dir = self._find_game_dir()
        self._ensure_base()
        self.qtx = open(questforge.BASE_QTX, 'rb').read().decode('latin-1')
        tr, _, _ = tw1_lan.read(open(questforge.BASE_LAN, 'rb').read())
        self.text = tr
        self._parse()

    @staticmethod
    def _find_game_dir():
        for root, key in ((winreg.HKEY_CURRENT_USER, r'SOFTWARE\Reality Pump\TwoWorlds'),):
            try:
                with winreg.OpenKey(root, key) as k:
                    path, _ = winreg.QueryValueEx(k, 'DataDir')
                    if os.path.isdir(path):
                        return path.rstrip('\\')
            except OSError:
                pass
        for cand in (r'F:\SteamLibrary\steamapps\common\Two Worlds - Epic Edition',
                     r'C:\Program Files (x86)\Steam\steamapps\common\Two Worlds - Epic Edition'):
            if os.path.isdir(cand):
                return cand
        return None

    def _ensure_base(self):
        if (os.path.exists(questforge.BASE_QTX)
                and os.path.exists(questforge.BASE_LAN)):
            return
        if not self.game_dir:
            raise SystemExit('Game not found - run extract_base.py manually.')
        os.makedirs('base', exist_ok=True)
        pairs = ((os.path.join(self.game_dir, 'WDFiles', 'Update16.wd'),
                  'Scripts\\Quests\\TwoWorldsQuests.qtx', questforge.BASE_QTX),
                 (os.path.join(self.game_dir, 'WDFiles', 'Language.wd'),
                  'Language\\TwoWorldsQuests.lan', questforge.BASE_LAN))
        for arc, inner, dest in pairs:
            entry = next(e for e in tw1_wd.read(arc) if e.path == inner)
            open(dest, 'wb').write(entry.data)

    def _parse(self):
        t = self.text
        # quests: id -> (title, group, body)
        self.quests = {}
        for qid, head, body in re.findall(
                r'^QUEST Q_(\d+)([^\n]*)\n(.*?)^END', self.qtx, re.M | re.S):
            qid = int(qid)
            title = t.get(f'translateQ_{qid}', '').strip()
            group = head.split()[1] if len(head.split()) > 1 else ''
            self.quests[qid] = (title, group, body)
        # Installed mods may already carry custom quests (a mod's qtx is a
        # full replacement) - their ids are taken, and builds must start
        # from that newer qtx, not the base one.
        self.mod_qtx = {}            # archive filename -> qtx bytes
        self.mod_lan = {}            # archive filename -> master lan bytes
        for name in self.mods():
            path = os.path.join(self.game_dir, 'Mods', name)
            try:
                entries = {e.path: e.data for e in tw1_wd.read(path)}
            except Exception:
                continue
            qtx = entries.get('Scripts\\Quests\\TwoWorldsQuests.qtx')
            lan = entries.get('Language\\TwoWorldsQuests.lan')
            if qtx:
                self.mod_qtx[name] = qtx
                names = {}
                if lan:
                    self.mod_lan[name] = lan
                    try:
                        names, _, _ = tw1_lan.read(lan)
                    except Exception:
                        pass
                for qid, head, body in re.findall(
                        r'^QUEST Q_(\d+)([^\n]*)\n(.*?)^END',
                        qtx.decode('latin-1'), re.M | re.S):
                    qid = int(qid)
                    if qid not in self.quests:
                        title = (names.get(f'translateQ_{qid}', '').strip()
                                 or f'(from {name})')
                        grp = (head.split()[1]
                               if len(head.split()) > 1 else '')
                        self.quests[qid] = (title, grp, body)
        # 1-380 is single-player, 700+ is multiplayer; everything between is
        # unused. The parser itself has no ceiling - the shipped multiplayer
        # map files use ids like 2001 and 4001 - so the whole gap is fair
        # game. (An engine-side array limit somewhere in that range cannot
        # be ruled out from the data alone; it would show up as a quest that
        # simply never appears.)
        self.free_ids = [i for i in range(381, 700) if i not in self.quests]
        # NPCs: id -> (name, sector, lector)
        self.npcs = {}
        for line in self.qtx.splitlines():
            if line.startswith('NPC NPC_'):
                p = line.split()
                nid = int(p[1][4:])
                name = t.get(f'translateNPC_{nid}', '').strip()
                self.npcs[nid] = (name or f'NPC_{nid}', p[4], p[6])
        # groups: id -> name
        self.groups = {}
        for k, v in t.items():
            m = re.fullmatch(r'translateGROUP_(\d+)', k)
            if m and v.strip():
                self.groups[int(m.group(1))] = v.strip()
        # objects seen in retail quests (BRING_OBJECT / item rewards)
        self.objects = sorted(
            set(re.findall(r'BRING_OBJECT (\S+)', self.qtx))
            | set(re.findall(r'REWARD ITM \d+ (\S+)', self.qtx)))
        # chainable quests: single-player, with a giver (the player will
        # meet them), sorted by id - Q_4 is the natural early hook
        self.chain_choices = [
            qid for qid, (_ti, _g, body) in sorted(self.quests.items())
            if qid < 400 and 'GIVER' in body]

    def npc_label(self, nid):
        name, sector, _ = self.npcs[nid]
        return f'{name}  (NPC_{nid}, {sector})'

    def quest_label(self, qid):
        title = self.quests[qid][0] or '(untitled)'
        return f'Q_{qid}  {title}'

    def mods(self):
        d = os.path.join(self.game_dir or '', 'Mods')
        if not os.path.isdir(d):
            return []
        return sorted(f for f in os.listdir(d) if f.lower().endswith('.wd'))


# ---------------------------------------------------------------------------
# Widgets

class NpcPicker(ttk.Frame):
    """Search box + list of named NPCs; get() returns the selected id."""

    def __init__(self, parent, hub, height=9):
        super().__init__(parent)
        self.hub = hub
        self.ids = []
        self.var = tk.StringVar()
        self.var.trace_add('write', lambda *_: self._fill())
        ent = ttk.Entry(self, textvariable=self.var)
        ent.pack(fill='x')
        wrap = ttk.Frame(self); wrap.pack(fill='both', expand=True, pady=(4, 0))
        self.lb = tk.Listbox(wrap, height=height, exportselection=False,
                             font=('Segoe UI', 9))
        sc = ttk.Scrollbar(wrap, command=self.lb.yview)
        self.lb.configure(yscrollcommand=sc.set)
        sc.pack(side='right', fill='y')
        self.lb.pack(side='left', fill='both', expand=True)
        self._fill()

    def _fill(self):
        needle = self.var.get().lower()
        self.lb.delete(0, 'end')
        self.ids = []
        for nid, (name, sector, _lect) in sorted(
                self.hub.npcs.items(), key=lambda kv: kv[1][0].lower()):
            label = f'{name}  (NPC_{nid}, {sector})'
            if needle in label.lower():
                self.ids.append(nid)
                self.lb.insert('end', label)

    def get(self):
        sel = self.lb.curselection()
        return self.ids[sel[0]] if sel else None

    def select(self, nid):
        if nid in self.ids:
            i = self.ids.index(nid)
            self.lb.selection_clear(0, 'end')
            self.lb.selection_set(i)
            self.lb.see(i)


def text_box(parent, height, initial=''):
    box = tk.Text(parent, height=height, wrap='word', font=('Segoe UI', 9),
                  padx=6, pady=4)
    box.insert('1.0', initial)
    return box


def get_text(widget):
    return widget.get('1.0', 'end').strip()


# ---------------------------------------------------------------------------

# The four conversations a quest NPC can hold, in the order the player
# meets them. Each is an independent graph; every line of a conversation
# carries that conversation's state flag (exactly how the retail trees do
# it - e.g. all 16 lines of Tago's offer are 0.FT.AS).
CONVERSATIONS = [
    ('offer', F_FTAS, 'Offer',
     'Plays until the quest is taken. The quest is accepted when this '
     'conversation ends.'),
    ('open', F_QNSAE, 'While open',
     'Plays when the player talks to the giver with the quest unfinished.'),
    ('solved', F_QSAE, 'On reward',
     'Plays once the objective is done - this is the hand-in conversation.'),
    ('closed', F_QC, 'After completion',
     'Plays whenever the player talks to the giver afterwards.'),
]

TEMPLATES = {
    'offer': [
        ('npc', 'You have proven yourself reliable. Perhaps you can help me '
                'once more.'),
        ('hero', 'Speak.'),
        ('npc', 'There is trouble I cannot handle myself.'),
        ('hero', 'And you want me to take care of it?'),
        ('npc', 'Do this for me and you will be rewarded.'),
        ('hero', 'Consider it done.'),
    ],
    'open': [('npc', 'You are not done yet. Hurry.')],
    'solved': [('npc', 'I knew I could count on you. Here, your reward.')],
    'closed': [('npc', 'Good work, friend.')],
}


class Conversation:
    """One dialog state as a graph of lines.

    A line with several successors becomes a reply menu in-game; the
    successors are the options the player picks from. An option may point
    back at a line that was already used, which is how retail dialogs let
    branches rejoin. `hide` marks an option that disappears once used (the
    negative indices in the shipped trees).
    """

    def __init__(self, key, flags, label, hint):
        self.key = key
        self.flags = flags
        self.label = label
        self.hint = hint
        self.nodes = {}          # nid -> {'who', 'text', 'next': [[nid, hide]]}
        self.root = None
        self._seq = 0

    def add(self, who, text):
        self._seq += 1
        nid = self._seq
        self.nodes[nid] = {'who': who, 'text': text, 'next': []}
        if self.root is None:
            self.root = nid
        return nid

    def remove(self, nid):
        self.nodes.pop(nid, None)
        for node in self.nodes.values():
            node['next'] = [e for e in node['next'] if e[0] != nid]
        if self.root == nid:
            self.root = next(iter(self.nodes), None)

    def link(self, src, dst, hide=False):
        if dst not in [e[0] for e in self.nodes[src]['next']]:
            self.nodes[src]['next'].append([dst, hide])

    def load(self, pairs):
        """Fill with a straight chain of (who, text) pairs."""
        self.nodes.clear(); self.root = None; self._seq = 0
        prev = None
        for who, text in pairs:
            nid = self.add(who, text)
            if prev is not None:
                self.link(prev, nid)
            prev = nid

    def order(self):
        """Reachable lines, root first - the export order."""
        out, seen, stack = [], set(), [self.root] if self.root else []
        while stack:
            nid = stack.pop(0)
            if nid is None or nid in seen or nid not in self.nodes:
                continue
            seen.add(nid); out.append(nid)
            stack.extend(e[0] for e in self.nodes[nid]['next'])
        # keep unreachable lines too so nothing silently vanishes
        out += [n for n in self.nodes if n not in seen]
        return out

    def to_json(self):
        return {'root': self.root, 'seq': self._seq,
                'nodes': {str(k): v for k, v in self.nodes.items()}}

    def from_json(self, data):
        self.nodes = {int(k): v for k, v in data.get('nodes', {}).items()}
        for node in self.nodes.values():
            node['next'] = [list(e) for e in node['next']]
        self.root = data.get('root')
        self._seq = data.get('seq', max(self.nodes or [0]))


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP)
        self.root.geometry('1080x760')
        self.root.minsize(940, 640)
        apply_dark_theme(self.root)

        try:
            self.hub = DataHub()
        except Exception as exc:
            messagebox.showerror(APP, f'Could not load game data:\n{exc}')
            raise

        self._build_menu()
        self._build_header()
        nb = ttk.Notebook(self.root)
        nb.pack(fill='both', expand=True, padx=12, pady=(0, 12))
        nb.add(self._tab_quest(nb), text=' Quest ')
        nb.add(self._tab_dialog(nb), text=' Dialog ')
        nb.add(self._tab_build(nb), text=' Build & Install ')
        self.notebook = nb

    # -- chrome ---------------------------------------------------------

    def _build_menu(self):
        bar = ttk.Frame(self.root, style='Menubar.TFrame')
        bar.pack(fill='x')
        for label, filler in (('File', self._fill_file_menu),
                              ('Links', self._fill_links_menu)):
            item = ttk.Label(bar, text=label, style='Menubar.TLabel')
            item.pack(side='left')
            item.bind('<Button-1>',
                      lambda ev, f=filler, w=item: self._popup_menu(f, w))
            item.bind('<Enter>', lambda ev, w=item: w.state(['active']))
            item.bind('<Leave>', lambda ev, w=item: w.state(['!active']))

    def _popup_menu(self, filler, widget):
        menu = tk.Menu(self.root, tearoff=0)
        filler(menu)
        try:
            menu.tk_popup(widget.winfo_rootx(),
                          widget.winfo_rooty() + widget.winfo_height())
        finally:
            menu.grab_release()

    def _fill_file_menu(self, menu):
        menu.add_command(label='Load draft…', command=self.load_draft)
        menu.add_command(label='Save draft…', command=self.save_draft)
        menu.add_separator()
        if self.hub.game_dir:
            menu.add_command(
                label='Open Mods folder',
                command=lambda: os.startfile(
                    os.path.join(self.hub.game_dir, 'Mods')))
        menu.add_command(label='Exit', command=self.root.destroy)

    def _fill_links_menu(self, menu):
        menu.add_command(label='Guide (alchemy-fox.de)',
                         command=lambda: webbrowser.open(GUIDE_URL))
        menu.add_command(label='GitHub',
                         command=lambda: webbrowser.open(GITHUB_URL))

    def _build_header(self):
        head = ttk.Frame(self.root, padding=(12, 10))
        head.pack(fill='x')
        ttk.Label(head, text='QUEST CREATOR', style='Brand.TLabel').pack(
            side='left')
        game = self.hub.game_dir or 'game not found!'
        ttk.Label(head, text=game, foreground=MUT).pack(side='left', padx=14)
        ttk.Label(head, foreground=MUT,
                  text=f'{len(self.hub.npcs)} NPCs · '
                       f'{len(self.hub.quests)} quests · '
                       f'{len(self.hub.free_ids)} free IDs').pack(side='right')

    # -- tab 1: quest ----------------------------------------------------

    def _tab_quest(self, parent):
        tab = ttk.Frame(parent, padding=12)
        tab.columnconfigure(0, weight=1, uniform='col')
        tab.columnconfigure(1, weight=1, uniform='col')
        tab.rowconfigure(0, weight=1)

        left = ttk.Frame(tab)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 10))

        basics = ttk.LabelFrame(left, text='Basics', padding=10)
        basics.pack(fill='x')
        basics.columnconfigure(1, weight=1)
        ttk.Label(basics, text='Quest ID').grid(row=0, column=0, sticky='w')
        self.var_qid = tk.StringVar(
            value=str(self.hub.free_ids[0]) if self.hub.free_ids else '')
        ttk.Combobox(basics, textvariable=self.var_qid, width=8,
                     values=[str(i) for i in self.hub.free_ids]).grid(
            row=0, column=1, sticky='w', padx=8, pady=2)
        ttk.Label(basics, text='Title').grid(row=1, column=0, sticky='w')
        self.var_title = tk.StringVar()
        ttk.Entry(basics, textvariable=self.var_title).grid(
            row=1, column=1, sticky='ew', padx=8, pady=2)
        ttk.Label(basics, text='Journal group').grid(row=2, column=0, sticky='w')
        self.groups = sorted(self.hub.groups.items(), key=lambda kv: kv[1])
        self.var_group = tk.StringVar()
        cb = ttk.Combobox(basics, textvariable=self.var_group, state='readonly',
                          values=[f'{name}  ({gid})' for gid, name in self.groups])
        cb.grid(row=2, column=1, sticky='ew', padx=8, pady=2)
        cb.current(0)
        ttk.Label(basics, text='Offered after').grid(row=3, column=0, sticky='w')
        self.var_chain = tk.StringVar()
        chain = ttk.Combobox(
            basics, textvariable=self.var_chain, state='readonly',
            values=[self.hub.quest_label(q) for q in self.hub.chain_choices])
        chain.grid(row=3, column=1, sticky='ew', padx=8, pady=2)
        chain.current(self.hub.chain_choices.index(4)
                      if 4 in self.hub.chain_choices else 0)
        ttk.Label(basics, text='Also after').grid(row=4, column=0, sticky='w')
        self.var_chain2 = tk.StringVar()
        chain2 = ttk.Combobox(
            basics, textvariable=self.var_chain2, state='readonly',
            values=['(none)'] + [self.hub.quest_label(q)
                                 for q in self.hub.chain_choices])
        chain2.grid(row=4, column=1, sticky='ew', padx=8, pady=2)
        chain2.current(0)
        ttk.Label(basics, foreground=MUT, wraplength=380, justify='left',
                  text='Taking either quest unlocks yours; the giver then '
                       'offers it in the next conversation (the retail '
                       'AOQ PROMOTE pattern). Use "Also after" for a quest '
                       'the player still has open in an old save, so the '
                       'quest can appear there too.').grid(
            row=5, column=0, columnspan=2, sticky='w', pady=(6, 0))

        giver = ttk.LabelFrame(left, text='Quest giver', padding=10)
        giver.pack(fill='both', expand=True, pady=(10, 0))
        self.pick_giver = NpcPicker(giver, self.hub)
        self.pick_giver.pack(fill='both', expand=True)
        self.pick_giver.select(3)

        right = ttk.Frame(tab)
        right.grid(row=0, column=1, sticky='nsew')

        obj = ttk.LabelFrame(right, text='Objective', padding=10)
        obj.pack(fill='both', expand=True)
        row = ttk.Frame(obj); row.pack(fill='x')
        ttk.Label(row, text='Type').pack(side='left')
        self.var_fc = tk.StringVar(value='KILL')
        fc = ttk.Combobox(row, textvariable=self.var_fc, state='readonly',
                          width=14, values=['KILL', 'TALK', 'BRING_OBJECT',
                                            'BRING_GOLD'])
        fc.pack(side='left', padx=8)
        fc.bind('<<ComboboxSelected>>', lambda ev: self._fc_changed())
        self.fc_area = ttk.Frame(obj)
        self.fc_area.pack(fill='both', expand=True, pady=(8, 0))
        self._fc_changed()

        rew = ttk.LabelFrame(right, text='Rewards (on completion)', padding=10)
        rew.pack(fill='x', pady=(10, 0))
        ttk.Label(rew, text='Gold').grid(row=0, column=0, sticky='w')
        self.var_gold = tk.StringVar(value='500')
        ttk.Entry(rew, textvariable=self.var_gold, width=8).grid(
            row=0, column=1, sticky='w', padx=8)
        ttk.Label(rew, text='Experience').grid(row=0, column=2, sticky='w',
                                               padx=(16, 0))
        self.var_exp = tk.StringVar(value='250')
        ttk.Entry(rew, textvariable=self.var_exp, width=8).grid(
            row=0, column=3, sticky='w', padx=8)
        return tab

    def _fc_changed(self):
        for w in self.fc_area.winfo_children():
            w.destroy()
        kind = self.var_fc.get()
        if kind in ('KILL', 'TALK'):
            verb = 'kill' if kind == 'KILL' else 'talk to'
            ttk.Label(self.fc_area,
                      text=f'Target NPC to {verb}:').pack(anchor='w')
            self.pick_target = NpcPicker(self.fc_area, self.hub, height=7)
            self.pick_target.pack(fill='both', expand=True, pady=(4, 0))
            if kind == 'KILL':
                ttk.Label(self.fc_area, foreground=MUT, wraplength=380,
                          justify='left',
                          text='Note: quest NPCs are very resistant - '
                               'killing one is a slog.').pack(
                    anchor='w', pady=(4, 0))
        elif kind == 'BRING_OBJECT':
            row = ttk.Frame(self.fc_area); row.pack(anchor='w')
            ttk.Label(row, text='Object').pack(side='left')
            self.var_obj = tk.StringVar(value=self.hub.objects[0])
            ttk.Combobox(row, textvariable=self.var_obj, width=26,
                         values=self.hub.objects).pack(side='left', padx=8)
            ttk.Label(row, text='Count').pack(side='left')
            self.var_obj_n = tk.StringVar(value='1')
            ttk.Entry(row, textvariable=self.var_obj_n, width=5).pack(
                side='left', padx=8)
        elif kind == 'BRING_GOLD':
            row = ttk.Frame(self.fc_area); row.pack(anchor='w')
            ttk.Label(row, text='Gold amount').pack(side='left')
            self.var_gold_n = tk.StringVar(value='500')
            ttk.Entry(row, textvariable=self.var_gold_n, width=8).pack(
                side='left', padx=8)

    # -- tab 2: dialog ---------------------------------------------------

    def _tab_dialog(self, parent):
        tab = ttk.Frame(parent, padding=12)
        tab.columnconfigure(0, weight=3, uniform='col')
        tab.columnconfigure(1, weight=2, uniform='col')
        tab.rowconfigure(0, weight=1)

        self.convs = {key: Conversation(key, flags, label, hint)
                      for key, flags, label, hint in CONVERSATIONS}
        for key, conv in self.convs.items():
            conv.load(TEMPLATES[key])
        self.cur_conv = 'offer'
        self.item2node = {}

        left = ttk.Frame(tab)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 10))

        picker = ttk.Frame(left)
        picker.pack(fill='x')
        ttk.Label(picker, text='Conversation').pack(side='left', padx=(0, 8))
        self.var_conv = tk.StringVar(value='Offer')
        for key, _f, label, _h in CONVERSATIONS:
            ttk.Radiobutton(picker, text=label, value=label,
                            variable=self.var_conv,
                            command=lambda k=key: self._conv_switch(k)).pack(
                side='left', padx=(0, 10))
        ttk.Button(picker, text='Load dialog…',
                   command=self.load_dialog).pack(side='right')

        # Shown only while editing an existing dialog (vs building a new
        # quest): Build then ships just the dialog, no new quest.
        self.loaded_dialog = None
        self.edit_bar = ttk.Frame(left)
        self.lbl_edit = ttk.Label(self.edit_bar, foreground=GOLD,
                                  font=('Segoe UI', 9, 'bold'))
        self.lbl_edit.pack(side='left')
        ttk.Button(self.edit_bar, text='New quest instead',
                   command=self._exit_edit_mode).pack(side='right')

        self.lbl_conv_hint = ttk.Label(left, foreground=MUT, wraplength=560,
                                       justify='left')
        self.lbl_conv_hint.pack(anchor='w', pady=(6, 8))

        wrap = ttk.Frame(left)
        wrap.pack(fill='both', expand=True)
        self.tree_lines = ttk.Treeview(wrap, columns=('who', 'text'),
                                       show='tree headings', height=14)
        self.tree_lines.heading('#0', text='Flow')
        self.tree_lines.heading('who', text='Speaker')
        self.tree_lines.heading('text', text='Line')
        self.tree_lines.column('#0', width=190, minwidth=150, stretch=False)
        self.tree_lines.column('who', width=64, anchor='center', stretch=False)
        self.tree_lines.column('text', width=330)
        sc = ttk.Scrollbar(wrap, command=self.tree_lines.yview)
        self.tree_lines.configure(yscrollcommand=sc.set)
        sc.pack(side='right', fill='y')
        self.tree_lines.pack(side='left', fill='both', expand=True)
        self.tree_lines.tag_configure('jump', foreground=GOLD)
        self.tree_lines.tag_configure('orphan', foreground=ERR)
        # One colour per branch; a choice and its whole follow-up strand
        # share it, so you can see at a glance where each option leads.
        for i, col in enumerate(BRANCH_COLORS):
            self.tree_lines.tag_configure(f'branch{i}', foreground=col)
        self.tree_lines.bind('<Double-1>', lambda ev: self.line_edit())
        self._tip = _TreeTip(self.tree_lines, lambda i: self.item_tips.get(i))
        self.item_tips = {}

        btns = ttk.Frame(left)
        btns.pack(fill='x', pady=(8, 0))
        for label, cmd in (('Add reply', self.line_add_reply),
                           ('Add choice', self.line_add_choice),
                           ('Edit', self.line_edit),
                           ('Remove', self.line_remove),
                           ('Link…', self.line_link),
                           ('Preview', self.show_preview)):
            ttk.Button(btns, text=label, command=cmd).pack(side='left',
                                                           padx=(0, 6))
        ttk.Button(btns, text='Reset', command=self.conv_reset).pack(
            side='right')
        ttk.Label(left, foreground=MUT, wraplength=560, justify='left',
                  text='"Add reply" continues after the selected line. '
                       '"Add choice" gives the selected line a second (third, '
                       '…) follow-up — the player then picks from them. '
                       '"Link…" points a line at an existing one, so branches '
                       'can rejoin.').pack(anchor='w', pady=(8, 0))

        right = ttk.Frame(tab)
        right.grid(row=0, column=1, sticky='nsew')
        jour = ttk.LabelFrame(right, text='Journal texts', padding=10)
        jour.pack(fill='both', expand=True)
        ttk.Label(jour, text='On taking the quest (QTD)').pack(anchor='w')
        self.txt_qtd = text_box(jour, 4)
        self.txt_qtd.pack(fill='x', pady=(2, 10))
        ttk.Label(jour, text='After solving, before turn-in (QSD)').pack(
            anchor='w')
        self.txt_qsd = text_box(jour, 4)
        self.txt_qsd.pack(fill='x', pady=(2, 10))
        ttk.Label(jour, text='After completion (QCD)').pack(anchor='w')
        self.txt_qcd = text_box(jour, 4)
        self.txt_qcd.pack(fill='x', pady=(2, 0))
        ttk.Label(jour, foreground=MUT, wraplength=340, justify='left',
                  text='All three are required — a missing one shows its raw '
                       'key in the journal.').pack(anchor='w', pady=(10, 0))

        self._conv_switch('offer')
        return tab

    # -- conversation editing -------------------------------------------

    @property
    def conv(self):
        return self.convs[self.cur_conv]

    def _conv_switch(self, key):
        self.cur_conv = key
        conv = self.conv
        self.var_conv.set(conv.label)
        self.lbl_conv_hint.configure(text=conv.hint)
        self._lines_fill()

    def _lines_fill(self, select=None):
        self.tree_lines.delete(*self.tree_lines.get_children())
        self.item2node = {}
        self.item_tips = {}
        conv = self.conv
        shown = set()

        def render(parent, nid, label, tag, path):
            node = conv.nodes.get(nid)
            if node is None:
                return
            who = 'Giver' if node['who'] == 'npc' else 'Hero'
            if nid in shown:            # branch rejoining an earlier line
                item = self.tree_lines.insert(
                    parent, 'end', text=f'{label} ↩',
                    values=(who, f'back to: {node["text"][:60]}'),
                    tags=('jump',))
                self.item2node[item] = nid
                self.item_tips[item] = (f'{conv.label} · {path} · rejoins an '
                                        'earlier line')
                return
            shown.add(nid)
            tags = (tag,) if tag else ()
            item = self.tree_lines.insert(parent, 'end', text=label,
                                          values=(who, node['text']), tags=tags)
            self.item2node[item] = nid
            self.item_tips[item] = f'{conv.label} · {path}'
            self.tree_lines.item(item, open=True)
            kids = node['next']
            for i, (tid, hide) in enumerate(kids):
                if len(kids) > 1:
                    # a new branch: give it its own colour, carried down
                    sub = f'choice {i + 1}' + (' ·hide' if hide else '')
                    ctag = f'branch{self._branch_ct % len(BRANCH_COLORS)}'
                    self._branch_ct += 1
                    render(item, tid, sub, ctag, f'{path} › choice {i + 1}')
                else:
                    render(item, tid, 'then', tag, path)

        self._branch_ct = 0
        if conv.root:
            render('', conv.root, 'start', '', 'start')
        for nid in conv.nodes:
            if nid not in shown:
                node = conv.nodes[nid]
                item = self.tree_lines.insert(
                    '', 'end', text='unreachable',
                    values=('Giver' if node['who'] == 'npc' else 'Hero',
                            node['text']), tags=('orphan',))
                self.item2node[item] = nid
                self.item_tips[item] = (f'{conv.label} · not reachable from '
                                        'the first line')
        if select is not None:
            for item, nid in self.item2node.items():
                if nid == select:
                    self.tree_lines.selection_set(item)
                    self.tree_lines.see(item)
                    break

    def _selected_node(self):
        sel = self.tree_lines.selection()
        return self.item2node.get(sel[0]) if sel else None

    def conv_reset(self):
        if messagebox.askokcancel(
                APP, f'Reset the "{self.conv.label}" conversation to the '
                     'template? All its lines are lost.'):
            self.conv.load(TEMPLATES[self.cur_conv])
            self._lines_fill()

    def line_add_reply(self):
        src = self._selected_node()
        conv = self.conv
        if src is None and conv.nodes:
            messagebox.showinfo(APP, 'Select the line this one follows.')
            return
        who = 'npc'
        if src is not None:
            who = 'hero' if conv.nodes[src]['who'] == 'npc' else 'npc'
        def done(w, t):
            nid = conv.add(w, t)
            if src is not None:
                conv.link(src, nid)
            self._lines_fill(select=nid)
        self._line_dialog('Add reply', who, '', done)

    def line_add_choice(self):
        src = self._selected_node()
        if src is None:
            messagebox.showinfo(APP, 'Select the line the player answers to.')
            return
        conv = self.conv
        def done(w, t, hide):
            nid = conv.add(w, t)
            conv.link(src, nid, hide)
            self._lines_fill(select=nid)
        self._line_dialog('Add choice', 'hero', '', done, with_hide=True)

    def line_edit(self):
        nid = self._selected_node()
        if nid is None:
            return
        node = self.conv.nodes[nid]
        def done(w, t):
            node['who'], node['text'] = w, t
            self._lines_fill(select=nid)
        self._line_dialog('Edit line', node['who'], node['text'], done)

    # -- loading an existing dialog -------------------------------------

    def _all_dialogs(self):
        """Every dialog tree the game and the installed mods carry, as
        [{'dq','qid','title','entries','tr'}], newest wins per quest id.
        Cached after the first call."""
        if getattr(self, '_dialog_cache', None) is not None:
            return self._dialog_cache
        by_id = {}                      # qid -> record (mod overrides base)

        def ingest(data):
            tr, _al, rest = tw1_lan.read(data)
            for t in tw1_lan.parse_trees(rest):
                m = re.match(r'translateDQ_(\d+)$', t.id)
                if not m:
                    continue
                qid = int(m.group(1))
                title = (tr.get(f'translateQ_{qid}', '').strip()
                         or self.hub.quests.get(qid, ('',))[0])
                by_id[qid] = {'dq': t.id, 'qid': qid, 'title': title,
                              'entries': t.entries, 'tr': tr}

        ingest(open(questforge.BASE_LAN, 'rb').read())          # base first
        for name in self.hub.mods():                            # mods override
            path = os.path.join(self.hub.game_dir, 'Mods', name)
            try:
                for inner in tw1_wd.read(path):
                    if inner.path.lower().endswith('.lan'):
                        ingest(inner.data)
            except Exception:
                pass
        self._dialog_cache = sorted(by_id.values(), key=lambda r: r['qid'])
        return self._dialog_cache

    def load_dialog(self):
        dialogs = self._all_dialogs()
        win = tk.Toplevel(self.root)
        win.title('Load an existing dialog')
        win.geometry('640x560')
        win.transient(self.root); win.grab_set()
        fr = ttk.Frame(win, padding=12); fr.pack(fill='both', expand=True)
        ttk.Label(fr, text='Type a quest name (like in the Two Worlds guide) '
                           'or a Q-number:').pack(anchor='w')
        var_q = tk.StringVar()
        ent = ttk.Entry(fr, textvariable=var_q)
        ent.pack(fill='x', pady=(2, 10), ipady=3)
        ent.focus_set()
        wrap = ttk.Frame(fr); wrap.pack(fill='both', expand=True, pady=(0, 8))
        lb = tk.Listbox(wrap, exportselection=False, font=('Segoe UI', 9))
        sb = ttk.Scrollbar(wrap, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y'); lb.pack(side='left', fill='both',
                                                 expand=True)
        shown = []

        def refill(*_):
            needle = var_q.get().strip().lower()
            lb.delete(0, 'end'); shown.clear()
            for rec in dialogs:
                label = f'Q_{rec["qid"]}  {rec["title"]}'
                if (not needle or needle in label.lower()
                        or needle in f'q_{rec["qid"]}'):
                    shown.append(rec)
                    lb.insert('end', f'{label}   ({len(rec["entries"])} lines)')
            if shown:
                lb.selection_set(0)
        var_q.trace_add('write', refill)
        refill()
        ttk.Label(fr, foreground=MUT, text=f'{len(dialogs)} dialogs from the '
                  'game and your mods.').pack(anchor='w')

        def do_load(*_):
            sel = lb.curselection()
            if not sel:
                return
            rec = shown[sel[0]]
            n = self._convert_tree(rec['entries'], rec['tr'])
            self._enter_edit_mode(rec)
            win.destroy()
            self._conv_switch('offer')
            messagebox.showinfo(APP, f'Loaded {rec["dq"]} "{rec["title"]}" — '
                                f'{n} lines. Edit the conversations and press '
                                '"Save dialog" on the Build tab to ship just '
                                'this dialog as a mod.\n\nNote: cameras reset '
                                'to standard. Use "New quest instead" to '
                                'switch back to building a fresh quest.')
        lb.bind('<Double-1>', do_load)
        ent.bind('<Return>', do_load)
        bar = ttk.Frame(fr); bar.pack(fill='x')
        ttk.Button(bar, text='Load', style='Accent.TButton',
                   command=do_load).pack(side='left')
        ttk.Button(bar, text='Cancel', command=win.destroy).pack(side='left',
                                                                 padx=6)

    def _convert_tree(self, entries, translations):
        """Turn a parsed dialog tree into the four conversation graphs,
        preserving each line's flag, camera and lector. Lines shared by two
        states are duplicated so every state stays a self-contained graph."""
        STATE_FLAG = {'offer': F_FTAS, 'open': F_QNSAE,
                      'solved': F_QSAE, 'closed': F_QC}
        for conv in self.convs.values():
            conv.nodes.clear(); conv.root = None; conv._seq = 0
        reached = set()
        for e in entries:
            for nx in e.next:
                reached.add(abs(nx))
        total = 0
        for state_key, state_flag in STATE_FLAG.items():
            conv = self.convs[state_key]
            roots = [i for i, e in enumerate(entries)
                     if e.flags == state_flag and i not in reached]
            if not roots:
                roots = [i for i, e in enumerate(entries)
                         if e.flags == state_flag][:1]
            if not roots:
                continue
            idx2node = {}

            def build(idx):
                if idx in idx2node:
                    return idx2node[idx]
                e = entries[idx]
                who = 'hero' if e.lector == 1 else 'npc'
                nid = conv.add(who, translations.get(e.tid, e.tid))
                node = conv.nodes[nid]
                node['flags'] = e.flags
                node['cams'] = list(e.cams)
                node['lector'] = e.lector
                idx2node[idx] = nid
                for nx in e.next:
                    child = build(abs(nx))
                    conv.link(nid, child, hide=(nx < 0))
                return nid

            conv.root = build(roots[0])
            for r in roots[1:]:
                build(r)
            total += len(conv.nodes)
        return total

    def _enter_edit_mode(self, rec):
        self.loaded_dialog = {'qid': rec['qid'], 'dq': rec['dq'],
                              'title': rec['title']}
        self.lbl_edit.configure(
            text=f'Editing dialog of Q_{rec["qid"]} "{rec["title"]}"')
        self.edit_bar.pack(fill='x', pady=(6, 0), before=self.lbl_conv_hint)
        if hasattr(self, 'btn_build'):
            self.btn_build.configure(text='Save dialog')
        # Pull in the quest's journal texts + title so they can be edited too;
        # "Save dialog" ships whichever of these are non-empty.
        qid, tr = rec['qid'], rec['tr']
        self.var_title.set(rec['title'])
        for widget, suffix in ((self.txt_qtd, '_QTD'), (self.txt_qsd, '_QSD'),
                               (self.txt_qcd, '_QCD')):
            widget.delete('1.0', 'end')
            widget.insert('1.0', tr.get(f'translateQ_{qid}{suffix}', ''))

    def _exit_edit_mode(self):
        self.loaded_dialog = None
        self.edit_bar.pack_forget()
        if hasattr(self, 'btn_build'):
            self.btn_build.configure(text='Build & install')
        for key, conv in self.convs.items():
            conv.load(TEMPLATES[key])
        self.var_title.set('')
        for widget in (self.txt_qtd, self.txt_qsd, self.txt_qcd):
            widget.delete('1.0', 'end')
        self._conv_switch('offer')

    def line_remove(self):
        nid = self._selected_node()
        if nid is None:
            return
        self.conv.remove(nid)
        self._lines_fill()

    def line_link(self):
        src = self._selected_node()
        conv = self.conv
        if src is None:
            messagebox.showinfo(APP, 'Select the line the link starts from.')
            return
        others = [n for n in conv.order() if n != src]
        if not others:
            messagebox.showinfo(APP, 'There is no other line to link to.')
            return
        win = tk.Toplevel(self.root)
        win.title('Link to an existing line')
        win.geometry('560x420')
        win.transient(self.root); win.grab_set()
        frame = ttk.Frame(win, padding=12); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Continue at:').pack(anchor='w')
        lb = tk.Listbox(frame, height=12, exportselection=False)
        for nid in others:
            node = conv.nodes[nid]
            who = 'Giver' if node['who'] == 'npc' else 'Hero'
            lb.insert('end', f'{who}: {node["text"][:70]}')
        lb.pack(fill='both', expand=True, pady=(4, 8))
        var_hide = tk.BooleanVar()
        ttk.Checkbutton(frame, text='Hide this option once it has been used',
                        variable=var_hide).pack(anchor='w')
        def ok():
            sel = lb.curselection()
            if sel:
                conv.link(src, others[sel[0]], var_hide.get())
                self._lines_fill(select=src)
            win.destroy()
        bar = ttk.Frame(frame); bar.pack(fill='x', pady=(10, 0))
        ttk.Button(bar, text='Link', style='Accent.TButton',
                   command=ok).pack(side='left')
        ttk.Button(bar, text='Cancel', command=win.destroy).pack(side='left',
                                                                 padx=6)

    def _line_dialog(self, title, who, text, on_ok, with_hide=False):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry('560x260')
        win.transient(self.root)
        win.grab_set()
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill='both', expand=True)
        var_who = tk.StringVar(value='Giver' if who == 'npc' else 'Hero')
        row = ttk.Frame(frame); row.pack(anchor='w')
        ttk.Label(row, text='Speaker').pack(side='left')
        ttk.Combobox(row, textvariable=var_who, state='readonly', width=8,
                     values=['Giver', 'Hero']).pack(side='left', padx=8)
        var_hide = tk.BooleanVar()
        if with_hide:
            ttk.Checkbutton(row, text='hide once used',
                            variable=var_hide).pack(side='left', padx=8)
        box = text_box(frame, 6, text)
        box.pack(fill='both', expand=True, pady=8)
        box.focus_set()
        def ok():
            val = get_text(box)
            if val:
                w = 'npc' if var_who.get() == 'Giver' else 'hero'
                if with_hide:
                    on_ok(w, val, var_hide.get())
                else:
                    on_ok(w, val)
            win.destroy()
        bar = ttk.Frame(frame); bar.pack(fill='x')
        ttk.Button(bar, text='OK', style='Accent.TButton',
                   command=ok).pack(side='left')
        ttk.Button(bar, text='Cancel', command=win.destroy).pack(
            side='left', padx=6)
        win.bind('<Escape>', lambda ev: win.destroy())

    def show_preview(self):
        """Render the conversation the way the player will walk through it."""
        conv = self.conv
        win = tk.Toplevel(self.root)
        win.title(f'Preview — {conv.label}')
        win.geometry('620x520')
        win.transient(self.root)
        dark_titlebar(win)
        box = tk.Text(win, wrap='word', font=('Segoe UI', 10),
                      padx=14, pady=12)
        box.pack(fill='both', expand=True)
        box.tag_configure('npc', foreground=INK)
        box.tag_configure('hero', foreground=GOLD)
        box.tag_configure('meta', foreground=MUT, font=('Segoe UI', 9))

        giver = self.pick_giver.get()
        name = self.hub.npcs[giver][0] if giver in self.hub.npcs else 'Giver'
        seen = set()

        def walk(nid, depth):
            if nid is None or nid not in conv.nodes:
                return
            node = conv.nodes[nid]
            pad = '    ' * depth
            if nid in seen:
                box.insert('end', f'{pad}↩ (continues at an earlier line)\n',
                           'meta')
                return
            seen.add(nid)
            who = name if node['who'] == 'npc' else 'Hero'
            tag = 'npc' if node['who'] == 'npc' else 'hero'
            box.insert('end', f'{pad}{who}: ', 'meta')
            box.insert('end', f'{node["text"]}\n', tag)
            kids = node['next']
            if len(kids) > 1:
                box.insert('end', f'{pad}    — the player picks one —\n',
                           'meta')
            for tid, hide in kids:
                if hide:
                    box.insert('end', f'{pad}    (disappears once used)\n',
                               'meta')
                walk(tid, depth + 1 if len(kids) > 1 else depth)

        if conv.root:
            walk(conv.root, 0)
        else:
            box.insert('end', 'This conversation is empty.', 'meta')
        box.configure(state='disabled')

    # -- tab 3: build ----------------------------------------------------

    def _tab_build(self, parent):
        tab = ttk.Frame(parent, padding=12)

        target = ttk.LabelFrame(tab, text='Install into', padding=10)
        target.pack(fill='x')
        mods = self.hub.mods()
        self.var_target = tk.StringVar(
            value=mods[0] if mods else 'MyQuests.wd')
        row = ttk.Frame(target); row.pack(fill='x')
        ttk.Label(row, text='Mod archive (Mods\\)').pack(side='left')
        ttk.Combobox(row, textvariable=self.var_target, width=32,
                     values=mods).pack(side='left', padx=8)
        ttk.Label(target, foreground=MUT, wraplength=860, justify='left',
                  text='Merging into an existing archive that already loads '
                       'is the safe route - brand-new archives are sometimes '
                       'ignored by the game (see the guide). A backup of the '
                       'archive is created next to it. The registry entry is '
                       'set to enabled.').pack(anchor='w', pady=(6, 0))

        actions = ttk.Frame(tab)
        actions.pack(fill='x', pady=(12, 8))
        self.btn_build = ttk.Button(actions, text='Build & install',
                                    style='Accent.TButton',
                                    command=self.build)
        self.btn_build.pack(side='left')
        ttk.Label(actions, foreground=MUT,
                  text='Then start a NEW game to test.').pack(
            side='left', padx=12)

        logf = ttk.LabelFrame(tab, text='Build log', padding=8)
        logf.pack(fill='both', expand=True)
        self.txt_log = tk.Text(logf, height=12, wrap='word',
                               font=('Consolas', 9), state='disabled')
        self.txt_log.pack(fill='both', expand=True)
        self.txt_log.tag_configure('ok', foreground=OK)
        self.txt_log.tag_configure('err', foreground=ERR)
        self.txt_log.tag_configure('gold', foreground=GOLD)
        return tab

    def log(self, msg, tag=None):
        def do():
            self.txt_log.configure(state='normal')
            self.txt_log.insert('end', msg + '\n', tag or ())
            self.txt_log.see('end')
            self.txt_log.configure(state='disabled')
        self.root.after(0, do)

    # -- draft save/load -------------------------------------------------

    def _collect(self):
        return {
            'qid': self.var_qid.get(), 'title': self.var_title.get(),
            'group': self.var_group.get(), 'chain': self.var_chain.get(),
            'chain2': self.var_chain2.get(),
            'giver': self.pick_giver.get(), 'fc': self.var_fc.get(),
            'target_npc': getattr(self, 'pick_target', None) and self.pick_target.get(),
            'obj': getattr(self, 'var_obj', None) and self.var_obj.get(),
            'obj_n': getattr(self, 'var_obj_n', None) and self.var_obj_n.get(),
            'gold_n': getattr(self, 'var_gold_n', None) and self.var_gold_n.get(),
            'gold': self.var_gold.get(), 'exp': self.var_exp.get(),
            'convs': {k: c.to_json() for k, c in self.convs.items()},
            'qtd': get_text(self.txt_qtd), 'qsd': get_text(self.txt_qsd),
            'qcd': get_text(self.txt_qcd),
            'archive': self.var_target.get(),
        }

    def save_draft(self):
        path = filedialog.asksaveasfilename(
            defaultextension='.json', initialdir=HERE,
            filetypes=[('Quest draft', '*.json')])
        if path:
            json.dump(self._collect(), open(path, 'w', encoding='utf-8'),
                      indent=2, ensure_ascii=False)

    def load_draft(self):
        path = filedialog.askopenfilename(
            initialdir=HERE, filetypes=[('Quest draft', '*.json')])
        if not path:
            return
        d = json.load(open(path, encoding='utf-8'))
        self.var_qid.set(d.get('qid', ''))
        self.var_title.set(d.get('title', ''))
        self.var_group.set(d.get('group', ''))
        self.var_chain.set(d.get('chain', ''))
        self.var_chain2.set(d.get('chain2', '(none)'))
        self.var_fc.set(d.get('fc', 'KILL'))
        self._fc_changed()
        if d.get('giver'):
            self.pick_giver.select(d['giver'])
        if d.get('target_npc') and hasattr(self, 'pick_target'):
            self.pick_target.select(d['target_npc'])
        for key, blob in d.get('convs', {}).items():
            if key in self.convs:
                self.convs[key].from_json(blob)
        self._conv_switch(self.cur_conv)
        for widget, key in ((self.txt_qtd, 'qtd'), (self.txt_qsd, 'qsd'),
                            (self.txt_qcd, 'qcd')):
            widget.delete('1.0', 'end')
            widget.insert('1.0', d.get(key, ''))
        if d.get('archive'):
            self.var_target.set(d['archive'])

    # -- the build -------------------------------------------------------

    def _validate(self):
        errs = []
        try:
            qid = int(self.var_qid.get())
            if qid in self.hub.quests or not 0 < qid < 700:
                errs.append(f'Quest ID {qid} is taken or out of range '
                            '(free range is 381-699).')
        except ValueError:
            qid = None
            errs.append('Quest ID must be a number (381-699).')
        if not self.var_title.get().strip():
            errs.append('Title is empty.')
        giver = self.pick_giver.get()
        if giver is None:
            errs.append('No quest giver selected.')
        fc = self.var_fc.get()
        target = None
        if fc in ('KILL', 'TALK'):
            target = self.pick_target.get()
            if target is None:
                errs.append('No target NPC selected.')
            elif target == giver:
                errs.append('Target and giver are the same NPC.')
        for name, widget in (('QTD', self.txt_qtd), ('QSD', self.txt_qsd),
                             ('QCD', self.txt_qcd)):
            if not get_text(widget):
                errs.append(f'Journal text {name} is empty (would show the '
                            'raw key in-game).')
        for conv in self.convs.values():
            if not conv.nodes or conv.root is None:
                errs.append(f'The "{conv.label}" conversation is empty.')
                continue
            seen, stack = set(), [conv.root]
            while stack:
                nid = stack.pop()
                if nid in seen or nid not in conv.nodes:
                    continue
                seen.add(nid)
                stack.extend(e[0] for e in conv.nodes[nid]['next'])
            lost = len(conv.nodes) - len(seen)
            if lost:
                errs.append(f'"{conv.label}": {lost} line(s) cannot be '
                            'reached from the first line.')
            if any(not n['text'].strip() for n in conv.nodes.values()):
                errs.append(f'"{conv.label}" has an empty line.')
        if len(self.convs['offer'].nodes) < 2:
            errs.append('The offer conversation needs at least two lines.')
        for var, label in ((self.var_gold, 'Gold'), (self.var_exp, 'XP')):
            if not var.get().isdigit():
                errs.append(f'{label} reward must be a number.')
        return errs, qid, giver, fc, target

    def build(self):
        if self.loaded_dialog:
            errs = self._validate_dialog()
            args = None
        else:
            errs, qid, giver, fc, target = self._validate()
            args = (qid, giver, fc, target)
        if errs:
            messagebox.showerror('Not yet', '\n'.join(errs))
            return
        exe_running = any(p in subprocess.run(
            ['tasklist'], capture_output=True, text=True).stdout
            for p in ('TwoWorlds.exe', 'TwoWorlds_RADEON.exe'))
        if exe_running:
            messagebox.showerror(APP, 'Two Worlds is running - close the '
                                      'game first (it locks the archives).')
            return
        self.btn_build.state(['disabled'])
        self.notebook.select(2)
        if args is None:
            threading.Thread(target=self._build_dialog_thread,
                             daemon=True).start()
        else:
            threading.Thread(target=self._build_thread, args=args,
                             daemon=True).start()

    def _validate_dialog(self):
        """Editing an existing dialog: only the conversations matter, no
        quest fields. Empty states are fine (a dialog may not use all four)."""
        errs = []
        if not any(c.nodes and c.root for c in self.convs.values()):
            errs.append('All conversations are empty - nothing to save.')
        for conv in self.convs.values():
            if not conv.nodes:
                continue
            seen, stack = set(), [conv.root]
            while stack:
                nid = stack.pop()
                if nid in seen or nid not in conv.nodes:
                    continue
                seen.add(nid)
                stack.extend(e[0] for e in conv.nodes[nid]['next'])
            lost = len(conv.nodes) - len(seen)
            if lost:
                errs.append(f'"{conv.label}": {lost} line(s) cannot be '
                            'reached from the first line.')
            if any(not n['text'].strip() for n in conv.nodes.values()):
                errs.append(f'"{conv.label}" has an empty line.')
        return errs

    def _build_dialog_thread(self):
        try:
            self._do_build_dialog()
            self.log('DONE - start a NEW game (or one from before this quest) '
                     'to see the changed dialog.', 'ok')
        except Exception as exc:
            self.log(f'FAILED: {exc}', 'err')
        finally:
            self.root.after(0, lambda: self.btn_build.state(['!disabled']))

    def _do_build_dialog(self):
        """Ship only the edited dialog tree (+ its texts) as a .lan mod -
        no quest, no qtx. Replaces the tree at its original DQ key."""
        hub = self.hub
        ld = self.loaded_dialog
        dq = ld['dq']
        archive = self.var_target.get()
        self.log(f'Saving dialog {dq} "{ld["title"]}" into {archive}', 'gold')

        suffix_of = {'offer': '0.FT.AS', 'open': '0.QNS.AE',
                     'solved': '0.QS.AE', 'closed': '0.QC'}
        new_text = {}
        entries = []
        for key, _flags, _label, _hint in CONVERSATIONS:
            conv = self.convs[key]
            if not conv.nodes:
                continue
            order = conv.order()
            index = {nid: len(entries) + i for i, nid in enumerate(order)}
            for i, nid in enumerate(order):
                node = conv.nodes[nid]
                tid = f'{dq}_{suffix_of[key]}_{i}'
                new_text[tid] = node['text']
                nxt = [-index[t] if (hide and index[t]) else index[t]
                       for t, hide in node['next'] if t in index]
                is_hero = node['who'] == 'hero'
                flags = node['flags'] if 'flags' in node else conv.flags
                cams = node.get('cams') or [7 if is_hero else 2]
                lec = node['lector'] if 'lector' in node else (
                    1 if is_hero else 0)
                entries.append(tw1_lan.DialogEntry(
                    lector=lec, tid=tid, cue='', next=nxt, flags=flags,
                    cams=cams, anim1=0, anim2=0))
            self.log(f'  {conv.label}: {len(order)} lines')
        tree = tw1_lan.DialogTree(dq, entries)

        # journal texts + title, if the user filled them in
        qid = ld['qid']
        title = self.var_title.get().strip()
        if title:
            new_text[f'translateQ_{qid}'] = title
        jn = 0
        for suffix, widget in (('_QTD', self.txt_qtd), ('_QSD', self.txt_qsd),
                               ('_QCD', self.txt_qcd)):
            txt = get_text(widget)
            if txt:
                new_text[f'translateQ_{qid}{suffix}'] = txt
                jn += 1
        if title or jn:
            self.log(f'journal: title{" +" if jn else ""} {jn} text(s) updated')

        # start from the target archive's master .lan if it has one, else base
        base = hub.mod_lan.get(archive) or open(questforge.BASE_LAN, 'rb').read()
        translations, aliases, rest = tw1_lan.read(base)
        translations.update(new_text)
        trees = [t for t in tw1_lan.parse_trees(rest) if t.id != dq] + [tree]
        full_lan = tw1_lan.build(translations, aliases,
                                 tw1_lan.build_trees(trees))
        overlay = tw1_lan.build(new_text, [], tw1_lan.build_trees([tree]))
        short = dq.replace('translate', '')
        files = {
            'Language\\TwoWorldsQuests.lan': full_lan,
            f'Language\\ZZ_{short}.lan': overlay,
        }
        self.log(f'lan: dialog tree {dq} replaced, {len(new_text)} texts')
        self._pack_into_archive(archive, files)

    def _build_thread(self, qid, giver, fc, target):
        try:
            self._do_build(qid, giver, fc, target)
            self.log('DONE - start a NEW game and take the "offered after" '
                     'quest, then talk to the giver again.', 'ok')
        except Exception as exc:
            self.log(f'FAILED: {exc}', 'err')
        finally:
            self.root.after(0, lambda: self.btn_build.state(['!disabled']))

    def _do_build(self, qid, giver, fc, target):
        hub = self.hub
        d = self._collect()
        group_id = int(re.search(r'\((\d+)\)$', d['group']).group(1))
        chain_qids = [int(re.match(r'Q_(\d+)', d['chain']).group(1))]
        m2 = re.match(r'Q_(\d+)', d.get('chain2', '') or '')
        if m2 and int(m2.group(1)) not in chain_qids:
            chain_qids.append(int(m2.group(1)))
        lector = int(hub.npcs[giver][2])
        self.log(f'Building Q_{qid} "{d["title"]}" - giver '
                 f'{hub.npcs[giver][0]}, unlocked by '
                 + ', '.join(f'Q_{q}' for q in chain_qids), 'gold')

        # --- qtx ---------------------------------------------------------
        if fc == 'KILL' or fc == 'TALK':
            sub_fc = tw1_qtx.sub_fc(fc, f'NPC_{target}')
        elif fc == 'BRING_OBJECT':
            sub_fc = tw1_qtx.sub_fc('BRING_OBJECT', d['obj'], d['obj_n'])
        else:
            sub_fc = tw1_qtx.sub_fc('BRING_GOLD', d['gold_n'])
        quest = tw1_qtx.make_quest(qid, [
            tw1_qtx.sub_giver(giver, 'ACTIVE', 'BACK_TO_GIVER_MAP_SIGN',
                              'NONE'),
            sub_fc,
            tw1_qtx.sub_reward('GLD', 'CLOSE', d['gold']),
            tw1_qtx.sub_reward('EXP', 'CLOSE', d['exp']),
        ], enable_level=1, group=group_id)
        # Start from the target archive's qtx/lan if it ships one - it is a
        # full replacement and already contains earlier custom quests.
        base_qtx = hub.mod_qtx.get(d['archive']) \
            or open(questforge.BASE_QTX, 'rb').read()
        if d['archive'] in hub.mod_qtx:
            self.log(f'base: continuing from the qtx inside {d["archive"]} '
                     '(keeps its existing quests)')
        qtx = tw1_qtx.append_quest(base_qtx, quest).decode('latin-1')
        aoq = f'AOQ PROMOTE TAKE Q_{qid}'
        for chain_qid in chain_qids:
            marker = f'QUEST Q_{chain_qid} '
            start = qtx.index(marker)
            end = qtx.index('END', start)
            block = qtx[start:end]
            if aoq not in block:
                assert '\n  REWARD' in block or '\n  FC' in block
                anchor = '\n  REWARD' if '\n  REWARD' in block else '\n  FC'
                block = block.replace(anchor, f'\n  {aoq}{anchor}', 1)
                qtx = qtx[:start] + block + qtx[end:]
        qtx = qtx.encode('latin-1')
        assert b'\r' not in qtx
        self.log('qtx: quest block appended, ' + aoq + ' added to '
                 + ', '.join(f'Q_{q}' for q in chain_qids))

        # --- lan: texts + dialog tree ------------------------------------
        dq = f'translateDQ_{qid}'
        new_text = {
            f'translateQ_{qid}': d['title'],
            f'translateQ_{qid}_QTD': d['qtd'],
            f'translateQ_{qid}_QSD': d['qsd'],
            f'translateQ_{qid}_QCD': d['qcd'],
        }
        # Flatten every conversation graph into one entry list. Indices are
        # global across the tree, so each conversation gets an offset; a
        # "hide once used" option is written as a negative index, exactly
        # like the 1000 such references in the shipped trees.
        entries = []
        suffix_of = {'offer': '0.FT.AS', 'open': '0.QNS.AE',
                     'solved': '0.QS.AE', 'closed': '0.QC'}
        for key, _flags, _label, _hint in CONVERSATIONS:
            conv = self.convs[key]
            order = conv.order()
            index = {nid: len(entries) + i for i, nid in enumerate(order)}
            for i, nid in enumerate(order):
                node = conv.nodes[nid]
                tid = f'{dq}_{suffix_of[key]}_{i}'
                new_text[tid] = node['text']
                # -0 is indistinguishable from 0, so the very first entry
                # can never carry the "hide" marker.
                nxt = [-index[t] if (hide and index[t]) else index[t]
                       for t, hide in node['next'] if t in index]
                is_hero = node['who'] == 'hero'
                # A loaded line keeps its original flag/cams/lector; a new
                # one uses the state's default flag, a standard camera, and
                # the chosen giver's lector.
                flags = node['flags'] if 'flags' in node else conv.flags
                cams = node.get('cams') or [7 if is_hero else 2]
                lec = node['lector'] if 'lector' in node else (
                    1 if is_hero else lector)
                entries.append(tw1_lan.DialogEntry(
                    lector=lec, tid=tid, cue='',
                    next=nxt, flags=flags, cams=cams, anim1=0, anim2=0))
            branches = sum(1 for nid in order
                           if len(conv.nodes[nid]['next']) > 1)
            self.log(f'  {conv.label}: {len(order)} lines'
                     + (f', {branches} reply menu(s)' if branches else ''))
        tree = tw1_lan.DialogTree(dq, entries)

        master = hub.mod_lan.get(d['archive']) \
            or open(questforge.BASE_LAN, 'rb').read()
        translations, aliases, rest = tw1_lan.read(master)
        translations.update(new_text)
        trees = [t for t in tw1_lan.parse_trees(rest) if t.id != dq] + [tree]
        full_lan = tw1_lan.build(translations, aliases,
                                 tw1_lan.build_trees(trees))
        overlay = tw1_lan.build(new_text, [], tw1_lan.build_trees([tree]))
        self.log(f'lan: {len(new_text)} texts, dialog tree with '
                 f'{len(entries)} lines')

        files = {
            'Scripts\\Quests\\TwoWorldsQuests.qtx': qtx,
            'Language\\TwoWorldsQuests.lan': full_lan,
            f'Language\\ZZ_Q{qid}.lan': overlay,
        }
        self._pack_into_archive(d['archive'], files)

    def _pack_into_archive(self, archive_name, files):
        """Merge `files` (inner path -> bytes) into a Mods\\*.wd, back it up,
        verify byte-for-byte and enable it in the registry."""
        mods_dir = os.path.join(self.hub.game_dir, 'Mods')
        os.makedirs(mods_dir, exist_ok=True)
        archive = os.path.join(mods_dir, archive_name)
        tmp = tempfile.mkdtemp(prefix='questforge_')
        try:
            if os.path.exists(archive):
                backup = archive + '.backup'
                if not os.path.exists(backup):
                    shutil.copy2(archive, backup)
                    self.log(f'backup: {os.path.basename(backup)}')
                wdio.unpack_single(archive, tmp)
                self.log(f'merging into existing {archive_name}')
            else:
                self.log(f'creating new archive {archive_name} - if it does '
                         'not show up, merge into an archive that already '
                         'loads (see guide).', 'gold')
            for inner, data in files.items():
                dest = os.path.join(tmp, inner.replace('\\', os.sep))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                open(dest, 'wb').write(data)
            out = archive + '.new'
            wdio.pack_single(tmp, out, 1, None)
            os.replace(out, archive)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.log(f'packed: {os.path.getsize(archive):,} B')

        got = {e.path: e.data for e in tw1_wd.read(archive)}
        for inner, data in files.items():
            assert got.get(inner) == data, f'verify failed: {inner}'
        self.log('verified: archive re-read, all files byte-identical', 'ok')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_MODS) as k:
            winreg.SetValueEx(k, archive_name, 0, winreg.REG_DWORD, 1)
        self.log(f'registry: "{archive_name}" = 1 (enabled)')

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    App().run()
