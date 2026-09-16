"""Windows for mods as a source (update 5b): the mod list with load order,
the marker dependencies of the project and the one-time save hint."""

import os
import tkinter as tk
from tkinter import messagebox, ttk

from . import mods, theme
from .i18n import t

NL = chr(10)


def origin_text(info, inner, tile=None, state=None, extra=None):
    """``From mod: <name> - Tile F1 - File x.lnd`` (+ overrides original)."""
    parts = [t('mod.origin', mod=info['name'])]
    if tile:
        parts.append(t('mod.origin.tile', tile=tile))
    if inner:
        parts.append(t('mod.origin.file', file=inner))
    text = ' - '.join(parts)
    if state == 'changed':
        text += NL + t('mod.overrides')
    for line in extra or ():
        text += NL + line
    return text


def missing_text(missing, limit=8):
    lines = [f'{name} {num}' for name, num in missing[:limit]]
    if len(missing) > limit:
        lines.append(t('mod.more', n=len(missing) - limit))
    return t('mod.redtile', n=len(missing)) + NL + NL.join(lines)


class ModsWindow:
    """The mods of the project: add, order, switch on and off, remove,
    restore a backup; details of the selected mod."""
    _open = None

    @classmethod
    def show(cls, app):
        win = cls._open
        if win is not None:
            try:
                win.win.lift()
                win.refresh()
                return win
            except tk.TclError:
                cls._open = None
        cls._open = cls(app)
        return cls._open

    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title(t('mods.title'))
        self.win.geometry('980x680')
        self.win.minsize(760, 460)
        theme.dark_titlebar(self.win)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.win.bind('<Escape>', lambda e: self.close())
        f = ttk.Frame(self.win, padding=14)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=t('mods.head'), style='Brand.TLabel'
                  ).pack(anchor='w')
        ttk.Label(f, text=t('mods.sub'), style='Muted.TLabel',
                  wraplength=940, justify='left').pack(anchor='w',
                                                        pady=(2, 8))
        bar = ttk.Frame(f)
        bar.pack(fill='x')
        for key, cmd in (('mods.add.wd', app.add_mod_archive),
                         ('mods.add.folder', app.add_mod_folder),
                         ('mods.add.game', app.add_game_mods)):
            ttk.Button(bar, text=t(key), command=cmd).pack(side='left',
                                                           padx=(0, 4))
        ttk.Button(bar, text=t('mods.deps'),
                   command=app.show_dependencies).pack(side='right')
        ttk.Button(bar, text=t('mods.rescan'),
                   command=lambda: app.load_modset(force=True)
                   ).pack(side='right', padx=4)
        body = ttk.Frame(f)
        body.pack(fill='both', expand=True, pady=(8, 0))
        cols = ('on', 'name', 'kind', 'quests', 'tiles', 'lans', 'path')
        self.tree = ttk.Treeview(body, columns=cols, show='headings',
                                 selectmode='browse', height=8)
        widths = {'on': 44, 'name': 170, 'kind': 60, 'quests': 110,
                  'tiles': 130, 'lans': 50, 'path': 380}
        for c in cols:
            self.tree.heading(c, text=t('mods.col.' + c))
            self.tree.column(c, width=widths[c], stretch=c == 'path',
                             anchor='w')
        self.tree.tag_configure('off', foreground=theme.DIM)
        self.tree.tag_configure('err', foreground=theme.ERR)
        self.tree.tag_configure('mod', foreground=theme.MOD)
        sb = ttk.Scrollbar(body, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._details())
        self.tree.bind('<Double-Button-1>', lambda e: self.toggle())
        self.tree.bind('<Motion>', self._hover)
        self.tree.bind('<Leave>', lambda e: self.tip.hide())
        self.tip = theme.FloatTip(self.win)
        row = ttk.Frame(f)
        row.pack(fill='x', pady=(6, 0))
        for key, cmd in (('mods.up', lambda: self.move(-1)),
                         ('mods.down', lambda: self.move(1)),
                         ('mods.toggle', self.toggle),
                         ('mods.remove', self.remove),
                         ('mods.restore', self.restore)):
            ttk.Button(row, text=t(key), command=cmd).pack(side='left',
                                                           padx=(0, 4))
        ttk.Label(f, text=t('mods.order'), style='Muted.TLabel',
                  wraplength=940, justify='left').pack(anchor='w',
                                                        pady=(6, 4))
        self.txt = tk.Text(f, wrap='word', font=theme.FONT_MONO, height=10)
        self.txt.pack(fill='both', expand=True)
        for tag, colour in (('mod', theme.MOD), ('err', theme.ERR),
                            ('warn', '#e0a050'), ('mut', theme.MUT)):
            self.txt.tag_configure(tag, foreground=colour)
        self.txt.configure(state='disabled')
        ttk.Button(f, text=t('close'), command=self.close
                   ).pack(anchor='e', pady=(8, 0))
        self.refresh()

    def close(self):
        ModsWindow._open = None
        self.tip.hide()
        self.win.destroy()

    # -- list -----------------------------------------------------------------

    def refresh(self):
        app = self.app
        sel = self._selected()
        self.tree.delete(*self.tree.get_children())
        p = app.project
        ms = app.modset
        conflicts = ms.tile_conflicts() if ms else {}
        for i, entry in enumerate(p.mods if p else []):
            info = ms.infos[i] if ms and i < len(ms.infos) else None
            on = entry.get('enabled', True)
            if info is None or info.get('error'):
                vals = ('x' if on else '', mods.mod_name(entry['path']), '-',
                        '-', '-', '-', entry['path'])
                tag = 'err'
            else:
                new = sum(1 for q in info['quests'].values()
                          if q['state'] == 'new')
                chg = len(info['quests']) - new
                red = sum(1 for r in info['tiles'].values() if r['missing'])
                tiles = t('mods.tiles', n=len(info['tiles']), red=red) \
                    if info['tiles'] else '-'
                vals = ('x' if on else '', info['name'],
                        t('mods.kind.' + info['kind']),
                        t('mods.quests', new=new, chg=chg), tiles,
                        len(info['lans']), entry['path'])
                tag = 'mod' if on else 'off'
                if on and any(tl in conflicts for tl in info['tiles']):
                    vals = vals[:4] + (vals[4] + '  !',) + vals[5:]
            self.tree.insert('', 'end', iid=str(i), values=vals, tags=(tag,))
        if sel is not None and self.tree.exists(str(sel)):
            self.tree.selection_set(str(sel))
        elif self.tree.get_children():
            self.tree.selection_set('0')
        self._details()

    def _selected(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _hover(self, ev):
        iid = self.tree.identify_row(ev.y)
        ms = self.app.modset
        if not iid or not ms or int(iid) >= len(ms.infos):
            self.tip.hide()
            return
        info = ms.infos[int(iid)]
        text = info['path']
        if info.get('error'):
            text += NL + t('mods.error', err=info['error'])
        self.tip.show(text, ev.x_root, ev.y_root)

    def _put(self, text, tag=None):
        self.txt.insert('end', text + NL, tag)

    def _details(self):
        self.txt.configure(state='normal')
        self.txt.delete('1.0', 'end')
        i = self._selected()
        ms = self.app.modset
        if i is None or not ms or i >= len(ms.infos):
            self._put(t('mods.empty'), 'mut')
            self.txt.configure(state='disabled')
            return
        info = ms.infos[i]
        self._put(f"{info['name']}   {info['path']}", 'mod')
        if info.get('error'):
            self._put(t('mods.error', err=info['error']), 'err')
            self.txt.configure(state='disabled')
            return
        if info['qtx']:
            self._put(t('mods.d.qtx', file=info['qtx']))
        for qid, q in sorted(info['quests'].items(), key=lambda kv: int(kv[0])):
            state = t('mods.state.' + q['state'])
            self._put(f"  Q_{qid}  {q['title'] or '-'}   ({state})",
                      'mod' if q['state'] == 'new' else None)
        clashes = ms.id_clashes(self.app.project)
        for qid, names in clashes:
            if info['name'] in names:
                self._put(t('mods.d.clash', id=qid, names=', '.join(names)),
                          'warn')
        if info['npcs'] or info['locations'] or info['containers']:
            self._put(t('mods.d.records', npcs=len(info['npcs']),
                        locs=len(info['locations']),
                        chests=len(info['containers'])))
        if info['lans']:
            self._put(t('mods.d.lans', n=len(info['lans']),
                        trees=len(info['trees']), texts=info['texts']))
        conflicts = ms.tile_conflicts()
        for tile in sorted(info['tiles'], key=mods.data._tile_key):
            rec = info['tiles'][tile]
            line = f"  {tile:7} {rec['inner']}"
            if rec.get('error'):
                self._put(line + '  ' + t('mods.error', err=rec['error']),
                          'err')
                continue
            if rec['missing']:
                self._put(line + '  ' + t('mods.d.red',
                                          n=len(rec['missing'])), 'err')
                self._put('      ' + ', '.join(
                    f'{n} {k}' for n, k in rec['missing'][:12]), 'err')
            else:
                self._put(line + '  ' + t('mods.d.tileok'))
            if tile in conflicts:
                self._put('      ' + t('mods.d.conflict',
                                       names=', '.join(conflicts[tile])),
                          'warn')
        backups = mods.list_backups(info['path'])
        if backups:
            self._put(t('mods.d.backups', n=len(backups)), 'mut')
            for b in backups[:5]:
                self._put('  ' + os.path.basename(b), 'mut')
        self.txt.configure(state='disabled')

    # -- actions ----------------------------------------------------------------

    def move(self, step):
        i = self._selected()
        p = self.app.project
        if i is None or not p:
            return
        j = i + step
        if not 0 <= j < len(p.mods):
            return
        p.mods[i], p.mods[j] = p.mods[j], p.mods[i]
        self.app.mods_changed()
        self.tree.selection_set(str(j))
        self.refresh()
        self.tree.selection_set(str(j))

    def toggle(self):
        i = self._selected()
        p = self.app.project
        if i is None or not p:
            return
        p.mods[i]['enabled'] = not p.mods[i].get('enabled', True)
        self.app.mods_changed()
        self.refresh()

    def remove(self):
        i = self._selected()
        p = self.app.project
        if i is None or not p:
            return
        name = mods.mod_name(p.mods[i]['path'])
        if not messagebox.askyesno(t('mods.title'),
                                   t('mods.remove.q', name=name),
                                   parent=self.win):
            return
        del p.mods[i]
        self.app.mods_changed()
        self.refresh()

    def restore(self):
        i = self._selected()
        p = self.app.project
        if i is None or not p:
            return
        path = p.mods[i]['path']
        backups = mods.list_backups(path)
        if not backups:
            messagebox.showinfo(t('mods.title'), t('mods.restore.none'),
                                parent=self.win)
            return
        dlg = tk.Toplevel(self.win)
        dlg.title(t('mods.restore'))
        dlg.transient(self.win)
        theme.dark_titlebar(dlg)
        box = ttk.Frame(dlg, padding=12)
        box.pack(fill='both', expand=True)
        ttk.Label(box, text=t('mods.restore.pick', name=mods.mod_name(path)),
                  wraplength=420, justify='left').pack(anchor='w')
        lst = tk.Listbox(box, height=min(10, len(backups)), width=60,
                         activestyle='none', exportselection=False)
        lst.pack(fill='both', expand=True, pady=8)
        for b in backups:
            lst.insert('end', os.path.basename(b))
        lst.selection_set(0)

        def go():
            sel = lst.curselection()
            if not sel:
                return
            dlg.destroy()
            self.app.restore_mod_backup(path, backups[sel[0]])
            self.refresh()
        btns = ttk.Frame(box)
        btns.pack(fill='x')
        ttk.Button(btns, text=t('cancel'), command=dlg.destroy
                   ).pack(side='right')
        ttk.Button(btns, text=t('mods.restore.go'), style='Accent.TButton',
                   command=go).pack(side='right', padx=6)
        lst.bind('<Double-Button-1>', lambda e: go())
        dlg.bind('<Escape>', lambda e: dlg.destroy())
        dlg.grab_set()


class DependencyWindow:
    """Map tiles of mods that go into the project's build, with the reason
    and the result of the marker check; a mod per tile on conflicts."""
    _open = None

    @classmethod
    def show(cls, app):
        win = cls._open
        if win is not None:
            try:
                win.win.lift()
                win.refresh()
                return win
            except tk.TclError:
                cls._open = None
        cls._open = cls(app)
        return cls._open

    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title(t('deps.title'))
        self.win.geometry('900x480')
        theme.dark_titlebar(self.win)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.win.bind('<Escape>', lambda e: self.close())
        f = ttk.Frame(self.win, padding=14)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=t('deps.head'), style='Brand.TLabel'
                  ).pack(anchor='w')
        ttk.Label(f, text=t('deps.sub'), style='Muted.TLabel',
                  wraplength=860, justify='left').pack(anchor='w',
                                                        pady=(2, 8))
        cols = ('tile', 'mod', 'file', 'uses', 'status')
        self.tree = ttk.Treeview(f, columns=cols, show='headings',
                                 selectmode='browse', height=10)
        widths = {'tile': 60, 'mod': 160, 'file': 200, 'uses': 260,
                  'status': 180}
        for c in cols:
            self.tree.heading(c, text=t('deps.col.' + c))
            self.tree.column(c, width=widths[c], anchor='w',
                             stretch=c == 'uses')
        self.tree.tag_configure('ok', foreground=theme.MOD)
        self.tree.tag_configure('missing', foreground=theme.ERR)
        self.tree.tag_configure('conflict', foreground='#e0a050')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._choice())
        self.tree.bind('<Motion>', self._hover)
        self.tree.bind('<Leave>', lambda e: self.tip.hide())
        self.tree.bind('<Button-3>', self._menu)
        self.tip = theme.FloatTip(self.win)
        self.close_btn = ttk.Button(f, text=t('close'), command=self.close)
        self.close_btn.pack(side='bottom', anchor='e', pady=(8, 0))
        self.pick_row = ttk.Frame(f)
        self.pick_lbl = ttk.Label(self.pick_row, text='')
        self.pick_lbl.pack(side='left')
        self.pick_var = tk.StringVar()
        self.pick = ttk.Combobox(self.pick_row, textvariable=self.pick_var,
                                 state='readonly', width=30)
        self.pick.pack(side='left', padx=6)
        self.pick.bind('<<ComboboxSelected>>', lambda e: self._set_choice())
        self.deps = []
        self.refresh()

    def close(self):
        DependencyWindow._open = None
        self.tip.hide()
        self.win.destroy()

    def refresh(self):
        app = self.app
        self.deps = mods.dependencies(app.project, app.modset) \
            if app.project and app.modset else []
        self.tree.delete(*self.tree.get_children())
        for i, d in enumerate(self.deps):
            uses = ', '.join(f'Q_{q} {mods.MARKER_NAMES.get(k, k)} {n}'
                             for q, k, n in d['uses'][:4])
            if len(d['uses']) > 4:
                uses += ' ...'
            status = t('deps.status.' + d['status'])
            if d['status'] == 'missing':
                status += f" ({len(d['missing'])})"
            self.tree.insert('', 'end', iid=str(i), values=(
                d['tile'], d['mod'] or '?', d['inner'], uses, status),
                tags=(d['status'],))
        if not self.deps:
            self.tree.insert('', 'end', values=('', t('deps.none'), '', '',
                                                ''))
        self._choice()

    def _menu(self, ev):
        iid = self.tree.identify_row(ev.y)
        if not iid.isdigit() or int(iid) >= len(self.deps):
            return
        self.tree.selection_set(iid)
        d = self.deps[int(iid)]
        q, kind, num = d['uses'][0]
        menu = theme.Menu(self.win, tearoff=0)
        menu.add_command(label=t('map.showin'), command=lambda: (
            self.app.show_map(), self._show(d, kind, num)))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _show(self, d, kind, num):
        from .mapwin import MapWindow
        if MapWindow._open:
            MapWindow._open.show_point(mods.MARKER_NAMES.get(kind), d['tile'],
                                       num)

    def _dep(self):
        sel = self.tree.selection()
        if not sel or not sel[0].isdigit() or int(sel[0]) >= len(self.deps):
            return None
        return self.deps[int(sel[0])]

    def _hover(self, ev):
        iid = self.tree.identify_row(ev.y)
        if not iid.isdigit() or int(iid) >= len(self.deps):
            self.tip.hide()
            return
        d = self.deps[int(iid)]
        lines = [f'Q_{q}  {mods.MARKER_NAMES.get(k, k)}  {n}'
                 for q, k, n in d['uses']]
        if d['missing']:
            lines.append(missing_text(d['missing']))
        if len(d['providers']) > 1:
            lines.append(t('deps.providers', names=', '.join(d['providers'])))
        self.tip.show(NL.join(lines), ev.x_root, ev.y_root)

    def _choice(self):
        d = self._dep()
        if not d or len(d['providers']) < 2:
            self.pick_row.pack_forget()
            return
        self.pick_row.pack(fill='x', pady=(8, 0), before=self.close_btn)
        self.pick.state(['!disabled'])
        self.pick_lbl.configure(text=t('deps.choose', tile=d['tile']))
        self.pick.configure(values=d['providers'])
        self.pick_var.set(d['mod'] or '')

    def _set_choice(self):
        d = self._dep()
        if not d:
            return
        self.app.project.mod_tiles[d['tile']] = self.pick_var.get()
        self.app.mods_changed(rescan=False)
        self.refresh()


def ask_save_hint(app):
    """Hint before the first write into a mod in this session: quest
    changes only reach a new game. True = go on."""
    if app.mod_hint_done or not app.cfg.get('mod_save_hint', True):
        return True
    win = tk.Toplevel(app.root)
    win.title(t('modsave.title'))
    win.transient(app.root)
    theme.dark_titlebar(win)
    f = ttk.Frame(win, padding=16)
    f.pack(fill='both', expand=True)
    ttk.Label(f, text=t('modsave.text'), wraplength=460, justify='left'
              ).pack(anchor='w')
    off = tk.BooleanVar(value=False)
    ttk.Checkbutton(f, text=t('modsave.off'), variable=off
                    ).pack(anchor='w', pady=(10, 0))
    result = {'ok': False}

    def done(ok):
        result['ok'] = ok
        win.destroy()
    btns = ttk.Frame(f)
    btns.pack(fill='x', pady=(12, 0))
    ttk.Button(btns, text=t('cancel'), command=lambda: done(False)
               ).pack(side='right')
    ttk.Button(btns, text=t('modsave.go'), style='Accent.TButton',
               command=lambda: done(True)).pack(side='right', padx=6)
    win.bind('<Escape>', lambda e: done(False))
    win.grab_set()
    app.root.wait_window(win)
    if result['ok']:
        app.mod_hint_done = True
        if off.get():
            app.cfg.set('mod_save_hint', False)
            app.cfg.save()
    return result['ok']
