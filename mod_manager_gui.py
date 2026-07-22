"""TW1 Mod Manager - install, enable and disable Two Worlds mods.

Standard mod-manager fare for a 2007 game that never had one:

* every archive in Mods\\ with its registry switch, toggled per mod
* external .wd files are copied into the game and enabled in one step
* a curated "My Mods" list fetched from the community server, with
  on-demand download and checksum verification
* nothing is ever deleted - disabling flips the registry DWORD, and
  "remove" moves the archive into Mods\\_removed\\

The registry model and its pitfalls (root archives load unconditionally,
`= 0` is a deliberate off switch) are documented in README.md.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
import webbrowser
import winreg
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

from quest_creator_gui import (BG, ERR, FIELD, GOLD, GOLD_HI, INK, LINE, MUT,
                               OK, PANEL, SEL, apply_dark_theme,
                               ask_game_dir, dark_titlebar, find_game_dir)

APP = 'TW1 Mod Manager'
GUIDE_URL = 'https://alchemy-fox.de/game/TW1_DialogAndQuestCreator/'
GITHUB_URL = 'https://github.com/MedievalDev/TW1_DialogAndQuestCreator'
MODS_URL = ('https://alchemy-fox.de/game/TW1_DialogAndQuestCreator/'
            'mods/mods.json')
REG_MODS = r'SOFTWARE\Reality Pump\TwoWorlds\Mods'


def game_running():
    out = subprocess.run(['tasklist'], capture_output=True, text=True).stdout
    return any(p in out for p in ('TwoWorlds.exe', 'TwoWorlds_RADEON.exe'))


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def registry_mods():
    """{archive name: 0/1} for every DWORD under the Mods key."""
    out = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_MODS) as k:
            i = 0
            while True:
                try:
                    name, value, _typ = winreg.EnumValue(k, i)
                except OSError:
                    break
                out[name] = value
                i += 1
    except OSError:
        pass
    return out


def registry_set(name, value):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_MODS) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, int(value))


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP)
        self.root.geometry('900x640')
        self.root.minsize(760, 520)
        apply_dark_theme(self.root)
        dark_titlebar(self.root)

        self.game_dir = find_game_dir()
        if not self.game_dir:
            messagebox.showinfo(
                APP, 'Two Worlds install not found automatically.\n'
                'Please pick your Two Worlds folder (the one with WDFiles).')
            self.game_dir = ask_game_dir(self.root)
        if not self.game_dir:
            messagebox.showerror(APP, 'No Two Worlds folder selected.')
            raise SystemExit(1)
        self.mods_dir = os.path.join(self.game_dir, 'Mods')
        os.makedirs(self.mods_dir, exist_ok=True)
        self.catalog = None           # server mods.json, once fetched

        self._build_menu()
        head = ttk.Frame(self.root, padding=(12, 10))
        head.pack(fill='x')
        ttk.Label(head, text='MOD MANAGER', style='Brand.TLabel').pack(
            side='left')
        self.lbl_game = ttk.Label(head, text=self.game_dir, foreground=MUT)
        self.lbl_game.pack(side='left', padx=14)

        nb = ttk.Notebook(self.root)
        nb.pack(fill='both', expand=True, padx=12, pady=(0, 4))
        nb.add(self._tab_installed(nb), text=' Installed mods ')
        nb.add(self._tab_server(nb), text=' My Mods (server) ')
        self.notebook = nb

        self.lbl_status = ttk.Label(self.root, text='', foreground=MUT,
                                    padding=(14, 4))
        self.lbl_status.pack(fill='x')

        self.refresh()
        threading.Thread(target=self._fetch_catalog, daemon=True).start()

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
        menu.add_command(label='Add external mod…', command=self.add_mod)
        menu.add_command(label='Open Mods folder',
                         command=lambda: os.startfile(self.mods_dir))
        menu.add_command(label='Refresh', command=self.refresh)
        menu.add_separator()
        menu.add_command(label='Change game path…', command=self.change_game_path)
        menu.add_command(label='Exit', command=self.root.destroy)

    def change_game_path(self):
        new = ask_game_dir(self.root, current=self.game_dir)
        if not new:
            return
        self.game_dir = new
        self.mods_dir = os.path.join(new, 'Mods')
        os.makedirs(self.mods_dir, exist_ok=True)
        if hasattr(self, 'lbl_game'):
            self.lbl_game.configure(text=new)
        self.refresh()
        messagebox.showinfo(APP, f'Game path set:\n{new}')

    def _fill_links_menu(self, menu):
        menu.add_command(label='Guide (alchemy-fox.de)',
                         command=lambda: webbrowser.open(GUIDE_URL))
        menu.add_command(label='GitHub',
                         command=lambda: webbrowser.open(GITHUB_URL))

    def status(self, text, error=False):
        def do():
            self.lbl_status.configure(text=text,
                                      foreground=ERR if error else MUT)
        self.root.after(0, do)

    # -- installed tab ---------------------------------------------------

    def _tab_installed(self, parent):
        tab = ttk.Frame(parent, padding=12)
        self.tree = ttk.Treeview(
            tab, columns=('state', 'size', 'date'), show='tree headings')
        self.tree.heading('#0', text='Mod archive')
        self.tree.heading('state', text='State')
        self.tree.heading('size', text='Size')
        self.tree.heading('date', text='Changed')
        self.tree.column('#0', width=280)
        self.tree.column('state', width=110, anchor='center')
        self.tree.column('size', width=90, anchor='e')
        self.tree.column('date', width=130, anchor='center')
        self.tree.pack(fill='both', expand=True)
        self.tree.tag_configure('on', foreground=OK)
        self.tree.tag_configure('off', foreground=MUT)
        self.tree.tag_configure('warn', foreground=ERR)
        self.tree.bind('<Double-1>', lambda ev: self.toggle())

        btns = ttk.Frame(tab)
        btns.pack(fill='x', pady=(10, 0))
        ttk.Button(btns, text='Enable / disable', style='Accent.TButton',
                   command=self.toggle).pack(side='left')
        ttk.Button(btns, text='Add external mod…',
                   command=self.add_mod).pack(side='left', padx=6)
        ttk.Button(btns, text='Remove (keeps a copy)',
                   command=self.remove_mod).pack(side='left')
        ttk.Button(btns, text='Refresh',
                   command=self.refresh).pack(side='right')
        ttk.Label(tab, foreground=MUT, wraplength=820, justify='left',
                  text='Double-click toggles a mod. Disabling keeps the file '
                       'and sets its registry switch to 0 — exactly what the '
                       'in-game Mod Selector does. Changes apply on the next '
                       'game start.').pack(anchor='w', pady=(8, 0))
        return tab

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        reg = registry_mods()
        files = {f for f in os.listdir(self.mods_dir)
                 if f.lower().endswith('.wd')}
        for name in sorted(files | set(reg), key=str.lower):
            path = os.path.join(self.mods_dir, name)
            exists = name in files
            enabled = reg.get(name, 0)
            if not exists:
                state, tag = 'file missing', 'off'
                size = date = '—'
            else:
                st = os.stat(path)
                size = f'{st.st_size / 1048576:.1f} MB'
                import datetime
                date = datetime.datetime.fromtimestamp(
                    st.st_mtime).strftime('%d.%m.%Y %H:%M')
                state, tag = (('enabled', 'on') if enabled
                              else ('disabled', 'off'))
            self.tree.insert('', 'end', iid=name, text=name,
                             values=(state, size, date), tags=(tag,))
        # Archives in the game ROOT load unconditionally - surface them.
        rogues = [f for f in os.listdir(self.game_dir)
                  if f.lower().endswith('.wd')]
        for name in rogues:
            self.tree.insert('', 'end', iid='ROOT::' + name,
                             text=f'{name}  (in the game folder!)',
                             values=('ALWAYS loads', '', ''), tags=('warn',))
        self._refresh_server_states()

    def _selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def toggle(self):
        name = self._selected()
        if not name:
            return
        if name.startswith('ROOT::'):
            messagebox.showwarning(
                APP, 'Archives in the game folder ignore the registry - the '
                     'game loads them no matter what. Move the file out of '
                     'the game folder to disable it.')
            return
        new = 0 if registry_mods().get(name, 0) else 1
        registry_set(name, new)
        self.status(f'{name} {"enabled" if new else "disabled"} - takes '
                    'effect on the next game start.')
        self.refresh()

    def add_mod(self):
        path = filedialog.askopenfilename(
            title='Choose a mod archive',
            filetypes=[('Two Worlds mod', '*.wd')])
        if not path:
            return
        if game_running():
            messagebox.showerror(APP, 'Close Two Worlds first.')
            return
        dest = os.path.join(self.mods_dir, os.path.basename(path))
        if os.path.abspath(path) != os.path.abspath(dest):
            if os.path.exists(dest) and not messagebox.askokcancel(
                    APP, f'{os.path.basename(dest)} already exists - '
                         'replace it? (A .backup copy is kept.)'):
                return
            if os.path.exists(dest):
                backup = dest + '.backup'
                if not os.path.exists(backup):
                    shutil.copy2(dest, backup)
            shutil.copy2(path, dest)
        registry_set(os.path.basename(dest), 1)
        self.status(f'{os.path.basename(dest)} installed and enabled.')
        self.refresh()

    def remove_mod(self):
        name = self._selected()
        if not name or name.startswith('ROOT::'):
            return
        if game_running():
            messagebox.showerror(APP, 'Close Two Worlds first.')
            return
        path = os.path.join(self.mods_dir, name)
        if os.path.exists(path):
            keep = os.path.join(self.mods_dir, '_removed')
            os.makedirs(keep, exist_ok=True)
            target = os.path.join(keep, name)
            if os.path.exists(target):
                base, ext = os.path.splitext(name)
                i = 2
                while os.path.exists(os.path.join(keep, f'{base}_{i}{ext}')):
                    i += 1
                target = os.path.join(keep, f'{base}_{i}{ext}')
            shutil.move(path, target)
        registry_set(name, 0)
        self.status(f'{name} moved to Mods\\_removed and disabled - '
                    'nothing was deleted.')
        self.refresh()

    # -- server tab ------------------------------------------------------

    def _tab_server(self, parent):
        tab = ttk.Frame(parent, padding=12)
        self.stree = ttk.Treeview(
            tab, columns=('ver', 'size', 'status'), show='tree headings')
        self.stree.heading('#0', text='Mod')
        self.stree.heading('ver', text='Version')
        self.stree.heading('size', text='Size')
        self.stree.heading('status', text='On this PC')
        self.stree.column('#0', width=280)
        self.stree.column('ver', width=70, anchor='center')
        self.stree.column('size', width=90, anchor='e')
        self.stree.column('status', width=150, anchor='center')
        self.stree.pack(fill='both', expand=True)
        self.stree.tag_configure('on', foreground=OK)
        self.stree.tag_configure('get', foreground=GOLD)
        self.stree.tag_configure('off', foreground=MUT)

        self.lbl_desc = ttk.Label(tab, foreground=MUT, wraplength=820,
                                  justify='left')
        self.lbl_desc.pack(anchor='w', pady=(8, 0))
        self.stree.bind('<<TreeviewSelect>>', lambda ev: self._show_desc())

        btns = ttk.Frame(tab)
        btns.pack(fill='x', pady=(10, 0))
        self.btn_install = ttk.Button(btns, text='Install / update',
                                      style='Accent.TButton',
                                      command=self.install_server_mod)
        self.btn_install.pack(side='left')
        ttk.Button(btns, text='Reload list',
                   command=lambda: threading.Thread(
                       target=self._fetch_catalog, daemon=True).start()
                   ).pack(side='left', padx=6)
        ttk.Label(tab, foreground=MUT, wraplength=820, justify='left',
                  text='Curated mods from the community server. Downloads '
                       'are checksum-verified; existing archives get a '
                       '.backup copy before an update.').pack(
            anchor='w', pady=(8, 0))
        return tab

    def _fetch_catalog(self):
        self.status('Loading mod list from the server…')
        try:
            with urllib.request.urlopen(MODS_URL, timeout=15) as r:
                self.catalog = json.load(r)
        except Exception as exc:
            self.status(f'Server list not available: {exc}', error=True)
            return
        self.status(f'Mod list loaded - '
                    f'{len(self.catalog.get("mods", []))} mod(s).')
        self.root.after(0, self._refresh_server_states)

    def _refresh_server_states(self):
        if self.catalog is None or not hasattr(self, 'stree'):
            return
        self.stree.delete(*self.stree.get_children())
        reg = registry_mods()
        for mod in self.catalog.get('mods', []):
            local = os.path.join(self.mods_dir, mod['file'])
            if not os.path.exists(local):
                state, tag = 'not installed', 'get'
            elif mod.get('sha256') and sha256_of(local) != mod['sha256']:
                state, tag = 'update available', 'get'
            elif reg.get(mod['file'], 0):
                state, tag = 'installed · enabled', 'on'
            else:
                state, tag = 'installed · disabled', 'off'
            self.stree.insert(
                '', 'end', iid=mod['id'], text=mod['name'],
                values=(mod.get('version', ''),
                        f'{mod.get("size", 0) / 1048576:.1f} MB', state),
                tags=(tag,))

    def _show_desc(self):
        sel = self.stree.selection()
        if not sel or self.catalog is None:
            return
        mod = next((m for m in self.catalog['mods'] if m['id'] == sel[0]),
                   None)
        if mod:
            author = f'  —  {mod["author"]}' if mod.get('author') else ''
            self.lbl_desc.configure(
                text=mod.get('description', '') + author)

    def install_server_mod(self):
        sel = self.stree.selection()
        if not sel or self.catalog is None:
            return
        mod = next((m for m in self.catalog['mods'] if m['id'] == sel[0]),
                   None)
        if mod is None:
            return
        if game_running():
            messagebox.showerror(APP, 'Close Two Worlds first.')
            return
        self.btn_install.state(['disabled'])
        threading.Thread(target=self._download, args=(mod,),
                         daemon=True).start()

    def _download(self, mod):
        try:
            dest = os.path.join(self.mods_dir, mod['file'])
            tmp = dest + '.download'
            self.status(f'Downloading {mod["name"]}…')
            with urllib.request.urlopen(mod['url'], timeout=60) as r, \
                    open(tmp, 'wb') as f:
                total = mod.get('size') or 0
                done = 0
                while True:
                    chunk = r.read(1 << 18)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        self.status(f'Downloading {mod["name"]}… '
                                    f'{done * 100 // total}%')
            if mod.get('sha256'):
                got = sha256_of(tmp)
                if got != mod['sha256']:
                    os.remove(tmp)
                    raise ValueError('checksum mismatch - download discarded')
            if os.path.exists(dest):
                backup = dest + '.backup'
                if not os.path.exists(backup):
                    shutil.copy2(dest, backup)
            os.replace(tmp, dest)
            registry_set(mod['file'], 1)
            self.status(f'{mod["name"]} installed and enabled.')
        except Exception as exc:
            self.status(f'Install failed: {exc}', error=True)
        finally:
            self.root.after(0, lambda: (
                self.btn_install.state(['!disabled']), self.refresh()))

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    App().run()
