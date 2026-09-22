"""Community tests, bug reports and known issues (4.0.0, Marco 2026-09-19).

- ``Feedback`` hangs at the app: the session log, the random client id, the
  list of untested things (untested.json, shipped with the tool) and the
  summary of the server (foxfeedback.fetch_summary, read in a thread at the
  start). A test the server calls "confirmed" is no longer untested - the
  tool takes that over by itself, without a new release.
- ``TestWindow``: the untested things, exact steps to tick off, "Start game"
  (gamesession.py writes down what can be seen from outside), at the end
  "works" / "does not work". The user sees what is sent before it goes.
- ``BugWindow``: "Report a bug" of the error windows. The public title is
  made from the error, the user's words stay private.
- ``IssuesWindow``: what has been reported for this tool.
- ``WhatsNewWindow``: first start of a new version: what it brings (NEWS),
  each with "Start tour" (guide.TOURS) and "Read in the guide", then the
  untested things with "I will test this" (4.5.0, Marco 2026-09-22: "im
  Fenster, wo steht, was neu ist, verlinkst du die Guides als Tour im Tool
  selbst"). Help > What's new opens it again.
"""

import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import foxfeedback

from . import VERSION, data, theme
from .i18n import get_lang, t

TOOL = 'questcreator'
CONFIRM_NEEDED = 2          # the server confirms a test after 2 passes from different PCs
NL = chr(10)


def _vkey(version):
    out = []
    for part in str(version).split('.'):
        digits = ''
        for ch in part:                  # leading digits: "0-m1" is 0
            if not ch.isdigit():
                break
            digits += ch
        out.append(int(digits or 0))
    return tuple(out)


class Feedback:
    def __init__(self, app):
        self.app = app
        self.log = foxfeedback.SessionLog()
        self.summary = None              # None: server not reached (yet)
        self.tests = self._load_tests()
        self.log.add(f'{TOOL} {VERSION} started, lang {get_lang()}')

    @staticmethod
    def _load_tests():
        try:
            with open(data.resource_path('questforge2', 'untested.json'),
                      encoding='utf-8') as f:
                return json.load(f).get('tests') or []
        except (OSError, ValueError):
            return []

    def client_id(self):
        import re
        cid = self.app.cfg.get('client_id')
        if not isinstance(cid, str) or not re.fullmatch('[0-9a-f]{32}', cid):
            cid = foxfeedback.new_client_id()
            self.app.cfg.set('client_id', cid)
            self.app.cfg.save()
        return cid

    # -- server state ------------------------------------------------------

    def _bg(self, work, done):
        """Run ``work()`` in a thread, then ``done(result)`` in the UI
        thread. The UI polls: Tk must not be called from the worker."""
        box = []

        def run():
            try:
                box.append((work(), None))
            except Exception as e:           # handed to done()
                box.append((None, e))

        def poll():
            if not box:
                try:
                    self.app.root.after(80, poll)
                except (tk.TclError, RuntimeError):
                    pass
                return
            try:
                done(*box[0])
            except tk.TclError:              # the window is gone
                pass
        threading.Thread(target=run, daemon=True).start()
        self.app.root.after(80, poll)

    def refresh(self, then=None):
        """Read the summary in a thread; ``then()`` runs in the UI after."""
        def done(s, _err):
            if s is not None:
                self.summary = s
            if then:
                then()
        self._bg(lambda: foxfeedback.fetch_summary(TOOL, VERSION), done)

    def state(self, test_id):
        """'open', 'confirmed', 'failed', 'closed' or 'unknown' (the server
        does not list the test, or was not reached)."""
        tests = (self.summary or {}).get('tests') or {}
        return (tests.get(test_id) or {}).get('status') or 'unknown'

    def counts(self, test_id):
        rec = ((self.summary or {}).get('tests') or {}).get(test_id) or {}
        return int(rec.get('pass') or 0), int(rec.get('fail') or 0)

    def untested(self):
        """Tests of this version or older that nobody has confirmed and
        that the server takes (offline: all of them)."""
        return [x for x in self.tests
                if _vkey(x.get('since', '0')) <= _vkey(VERSION)
                and self.state(x['id']) not in ('confirmed', 'closed')
                and self.can_report(x['id'])]

    def experimental(self, label):
        """True while the test behind an "experimental" label is not
        confirmed or closed (no server: still experimental)."""
        for x in self.tests:
            if x.get('experimental') == label:
                return self.state(x['id']) not in ('confirmed', 'closed')
        return False

    def can_report(self, test_id):
        """False when the server was reached and does not take this test
        (not created there yet, or closed) - it would answer 400."""
        if self.summary is None:
            return True                      # offline: offer the text file
        return self.state(test_id) in ('open', 'failed', 'confirmed')

    def mine(self, test_id):
        """What this PC reported for the test: 'pass', 'fail' or ''."""
        sent = self.app.cfg.get('test_sent') or {}
        return sent.get(test_id, '') if isinstance(sent, dict) else ''

    def remember(self, test_id, passed):
        sent = self.app.cfg.get('test_sent') or {}
        if not isinstance(sent, dict):
            sent = {}
        sent[test_id] = 'pass' if passed else 'fail'
        self.app.cfg.set('test_sent', sent)
        self.app.cfg.save()

    def issues(self):
        return (self.summary or {}).get('issues') or []

    # -- sending -------------------------------------------------------------

    def send(self, payload, parent, on_ok=None):
        """Send in a thread, tell the user how it went."""
        def done(rid, err):
            # the window the report came from may be closed by now
            try:
                par = parent if parent.winfo_exists() else self.app.root
            except tk.TclError:
                par = self.app.root
            if err is None:
                self.log.add(f'report sent: {rid}')
                messagebox.showinfo(t('fb.title'), t('fb.sent', id=rid),
                                    parent=par)
                self.refresh(on_ok)
                return
            code = getattr(err, 'code', 'offline')
            detail = getattr(err, 'detail', str(err))
            self.log.add(f'report not sent: {code} {detail}')
            key = 'fb.err.' + (code if code in ('rate', 'closed', 'too_large',
                                                'offline') else 'invalid')
            if messagebox.askyesno(t('fb.title'), t(key, detail=detail) + NL
                                   + NL + t('fb.savefile'), parent=par):
                self.save_file(payload, par)
        self._bg(lambda: foxfeedback.submit(payload), done)

    @staticmethod
    def save_file(payload, parent):
        path = filedialog.asksaveasfilename(
            parent=parent, defaultextension='.txt',
            initialfile=f"{payload.get('kind')}_report.txt",
            filetypes=[('Text', '*.txt')])
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(foxfeedback.preview(payload))
            except OSError as e:
                messagebox.showerror(t('fb.title'), str(e), parent=parent)


def _loc(d):
    return (d or {}).get(get_lang()) or (d or {}).get('en') or ''


def _preview_window(parent, payload, on_send):
    """What goes out, to read; nothing is sent before "Send"."""
    win = tk.Toplevel(parent)
    win.title(t('fb.preview.title'))
    win.geometry('760x560')
    win.transient(parent)
    theme.dark_titlebar(win)
    f = ttk.Frame(win, padding=12)
    f.pack(fill='both', expand=True)
    ttk.Label(f, text=t('fb.preview.head'), style='Brand.TLabel'
              ).pack(anchor='w')
    ttk.Label(f, text=t('fb.preview.hint'), style='Muted.TLabel',
              wraplength=720, justify='left').pack(anchor='w', pady=(2, 8))
    btns = ttk.Frame(f)
    btns.pack(side='bottom', fill='x', pady=(8, 0))
    box = ttk.Frame(f)
    box.pack(fill='both', expand=True)
    txt = tk.Text(box, wrap='none', font=theme.FONT_MONO)
    sb = ttk.Scrollbar(box, orient='vertical', command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    sb.pack(side='right', fill='y')
    txt.pack(fill='both', expand=True)
    txt.insert('1.0', foxfeedback.preview(payload))
    txt.configure(state='disabled')

    def go():
        win.destroy()
        on_send()
    ttk.Button(btns, text=t('cancel'), command=win.destroy).pack(side='right')
    ttk.Button(btns, text=t('fb.send'), style='Accent.TButton', command=go
               ).pack(side='right', padx=6)
    win.grab_set()
    return win


class TestWindow:
    _open = None

    @classmethod
    def show(cls, app, test_id=None):
        win = cls._open
        if win is not None:
            try:
                win.win.lift()
                if test_id:
                    win.select(test_id)
                return win
            except tk.TclError:
                cls._open = None
        cls._open = cls(app, test_id)
        return cls._open

    def __init__(self, app, test_id=None):
        self.app = app
        self.fb = app.feedback
        self.test = None
        self.session = None
        self.checks = []
        self.win = tk.Toplevel(app.root)
        self.win.title(t('test.title'))
        self.win.geometry('1140x720')
        self.win.minsize(900, 560)
        theme.dark_titlebar(self.win)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        outer = ttk.Frame(self.win, padding=12)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text=t('test.head'), style='Brand.TLabel'
                  ).pack(anchor='w')
        ttk.Label(outer, text=t('test.sub'), style='Muted.TLabel',
                  wraplength=1000, justify='left').pack(anchor='w',
                                                        pady=(2, 8))
        body = ttk.Frame(outer)
        body.pack(fill='both', expand=True)
        left = ttk.Frame(body, width=420)
        left.pack(side='left', fill='y')
        left.pack_propagate(False)
        self.lst = tk.Listbox(left, font=theme.FONT, activestyle='none',
                              exportselection=False)
        self.lst.pack(fill='both', expand=True)
        self.lst.bind('<<ListboxSelect>>', lambda e: self._pick())
        self.server_lbl = ttk.Label(left, text='', style='Muted.TLabel',
                                    wraplength=320, justify='left')
        self.server_lbl.pack(anchor='w', pady=(6, 0))
        self.right = ttk.Frame(body, padding=(14, 0, 0, 0))
        self.right.pack(side='left', fill='both', expand=True)
        self._fill_list()
        self.fb.refresh(self._fill_list)
        if test_id:
            self.select(test_id)
        elif self.items:
            self.lst.selection_set(0)
            self._pick()

    def close(self):
        if self.session is not None and self.session.state in ('waiting',
                                                               'running'):
            if not messagebox.askyesno(t('test.title'), t('test.close.q'),
                                       parent=self.win):
                return
        TestWindow._open = None
        self.win.destroy()

    # -- list ---------------------------------------------------------------

    def _fill_list(self):
        try:
            keep = self.test['id'] if self.test else None
            self.lst.delete(0, 'end')
        except tk.TclError:
            return
        self.items = [x for x in self.fb.tests
                      if _vkey(x.get('since', '0')) <= _vkey(VERSION)
                      and (self.fb.can_report(x['id'])
                           or self.fb.state(x['id']) == 'closed')]
        order = {'failed': 0, 'open': 1, 'unknown': 1, 'confirmed': 2,
                 'closed': 3}
        self.items.sort(key=lambda x: (order.get(self.fb.state(x['id']), 1),
                                       tuple(-v for v in _vkey(x['since']))))
        for i, x in enumerate(self.items):
            st = self.fb.state(x['id'])
            ok, bad = self.fb.counts(x['id'])
            mark = {'confirmed': '✓', 'failed': '!', 'closed': '-'
                    }.get(st, '○')
            need = max(CONFIRM_NEEDED, ok)
            tail = f'  ({ok}/{need})' if st in ('open', 'confirmed') and ok \
                else (f'  ({bad} x !)' if bad else '')
            self.lst.insert('end', f' {mark}  {_loc(x["title"])}{tail}')
            self.lst.itemconfigure(i, foreground={
                'confirmed': theme.OK, 'failed': theme.ERR,
                'closed': theme.MUT}.get(st, theme.INK))
        self.server_lbl.configure(text=t(
            'test.server.ok' if self.fb.summary is not None
            else 'test.server.off'))
        if keep:
            self.select(keep, rebuild=False)

    def select(self, test_id, rebuild=True):
        for i, x in enumerate(self.items):
            if x['id'] == test_id:
                self.lst.selection_clear(0, 'end')
                self.lst.selection_set(i)
                self.lst.see(i)
                if rebuild:
                    self._pick()
                return

    def _pick(self):
        sel = self.lst.curselection()
        if not sel:
            return
        x = self.items[sel[0]]
        if self.test is x:
            return
        if self.session is not None and self.session.state in ('waiting',
                                                               'running'):
            messagebox.showinfo(t('test.title'), t('test.busy'),
                                parent=self.win)
            self.select(self.test['id'], rebuild=False)
            return
        self.test = x
        self.session = None
        self._build(x)

    # -- one test ----------------------------------------------------------------

    def _build(self, x):
        for w in self.right.winfo_children():
            w.destroy()
        r = self.right
        st = self.fb.state(x['id'])
        ok, bad = self.fb.counts(x['id'])
        ttk.Label(r, text=_loc(x['title']), style='Brand.TLabel',
                  wraplength=640, justify='left').pack(anchor='w')
        ttk.Label(r, text=t('test.state.' + st, since=x['since'], ok=ok,
                            bad=bad), style='Muted.TLabel'
                  ).pack(anchor='w', pady=(2, 6))
        self._bar(r, x, st, ok, bad)
        ttk.Label(r, text=_loc(x.get('why')), wraplength=640, justify='left'
                  ).pack(anchor='w', pady=(0, 8))
        bottom = ttk.Frame(r)
        bottom.pack(side='bottom', fill='x')
        ttk.Label(r, text=t('test.steps'), style='Brand.TLabel'
                  ).pack(anchor='w')
        self.checks = []
        for i, step in enumerate(_loc_list(x.get('steps'))):
            v = tk.BooleanVar(value=False)
            row = ttk.Frame(r)
            row.pack(fill='x', pady=1)
            ttk.Checkbutton(row, variable=v, command=lambda i=i, v=v:
                            self.fb.log.add(f'test {x["id"]} step {i + 1} '
                                            f'{"done" if v.get() else "undone"}')
                            ).pack(side='left', anchor='n')
            ttk.Label(row, text=f'{i + 1}. {step}', wraplength=600,
                      justify='left').pack(side='left', anchor='w')
            self.checks.append(v)
        ttk.Label(r, text=t('test.expect'), style='Brand.TLabel'
                  ).pack(anchor='w', pady=(10, 0))
        tk.Label(r, text=_loc(x.get('expect')), wraplength=640,
                 justify='left', anchor='w', bg=theme.BG, fg=theme.GOLD
                 ).pack(anchor='w')
        # -- game -------------------------------------------------------------
        if x.get('needs_game'):
            from . import gamesession
            g = ttk.Frame(r)
            g.pack(fill='x', pady=(12, 0))
            exes = gamesession.game_exes(self.app.cfg.get('game_dir') or '')
            self.exe = tk.StringVar(value=self.app.cfg.get('game_exe')
                                    if self.app.cfg.get('game_exe') in exes
                                    else (exes[0] if exes else ''))
            self.game_btn = ttk.Button(g, text=t('test.game.start'),
                                       style='Accent.TButton',
                                       command=self.start_game)
            self.game_btn.pack(side='left')
            if len(exes) > 1:
                ttk.Combobox(g, textvariable=self.exe, values=exes, width=26,
                             state='readonly').pack(side='left', padx=6)
            if not exes:
                self.game_btn.state(['disabled'])
            self.game_lbl = ttk.Label(g, text=t('test.game.hint'),
                                      style='Muted.TLabel', wraplength=380,
                                      justify='left')
            self.game_lbl.pack(side='left', padx=8)
        # -- result -------------------------------------------------------------
        ttk.Label(bottom, text=t('test.note'), style='Muted.TLabel'
                  ).pack(anchor='w', pady=(8, 0))
        self.note = tk.Text(bottom, height=3, wrap='word', font=theme.FONT)
        self.note.pack(fill='x')
        btns = ttk.Frame(bottom)
        btns.pack(fill='x', pady=(8, 0))
        style = ttk.Style(self.win)
        style.configure('Pass.TButton', background=theme.OK,
                        foreground='#0b1a0f', font=theme.FONT_BOLD)
        style.configure('Fail.TButton', background=theme.ERR,
                        foreground='#1a0b0b', font=theme.FONT_BOLD)
        ttk.Button(btns, text='✓ ' + t('test.pass'),
                   style='Pass.TButton', command=lambda: self.result(True)
                   ).pack(side='left')
        ttk.Button(btns, text='✗ ' + t('test.fail'),
                   style='Fail.TButton', command=lambda: self.result(False)
                   ).pack(side='left', padx=8)
        ttk.Button(btns, text=t('close'), command=self.close
                   ).pack(side='right')

    def start_game(self):
        from . import export, gamesession
        app = self.app
        if export.game_running():
            messagebox.showwarning(t('test.title'), t('test.game.running.q'),
                                   parent=self.win)
            return
        exe = self.exe.get()
        app.cfg.set('game_exe', exe)
        app.cfg.save()
        name = export.archive_name(app.project) if app.project else None
        earlier = self.session.text() if self.session is not None else ''
        self.session = gamesession.GameSession(app.cfg.get('game_dir'),
                                               app.project, name)
        if earlier:
            self.session.add(earlier)
            self.session.add('== started again')
        self.fb.log.add(f'test {self.test["id"]}: game started ({exe})')

        if not self.session.start(exe):
            self._game_state('failed')
            return
        self.game_btn.state(['disabled'])
        self._game_state('waiting')
        self._watch_game(self.session, 'waiting')

    def _watch_game(self, session, shown):
        """Poll the session from the UI thread (Tk is not called from the
        watcher thread)."""
        if session is not self.session:
            return                         # another test was picked
        state = session.state
        if state != shown:
            self._game_state(state)
        if state in ('waiting', 'running'):
            try:
                self.win.after(500, lambda: self._watch_game(session, state))
            except tk.TclError:
                pass

    def _game_state(self, state):
        try:
            self.game_lbl.configure(text=t('test.game.' + state))
            if state in ('ended', 'failed'):
                self.game_btn.state(['!disabled'])
                self.win.lift()
        except tk.TclError:
            pass
        self.fb.log.add(f'game session: {state}')

    def _bar(self, parent, x, st, ok, bad):
        """How far the test is: one tick per confirmation (design 11a)."""
        need = max(CONFIRM_NEEDED, ok)
        if st == 'failed':
            key, colour, filled = 'test.bar.failed', theme.ERR, need
        elif st in ('confirmed', 'closed'):
            key, colour, filled = 'test.bar.confirmed', theme.OK, need
        elif ok:
            key, colour, filled = 'test.bar.some', theme.GOLD, ok
        else:
            key, colour, filled = 'test.bar.none', theme.MUT, 0
        box = ttk.Frame(parent)
        box.pack(anchor='w', fill='x', pady=(2, 6))
        w, h, gap = 150, 12, 4
        c = tk.Canvas(box, width=w, height=h, highlightthickness=0,
                      background=theme.BG, bd=0)
        c.pack(side='left')
        step = (w - gap * (need - 1)) / need if need else w
        for i in range(need):
            x0 = i * (step + gap)
            c.create_rectangle(x0, 0, x0 + step, h, width=0,
                               fill=colour if i < filled else theme.FIELD)
        ttk.Label(box, text=t(key, ok=ok, bad=bad, need=need),
                  style='Muted.TLabel', wraplength=470, justify='left'
                  ).pack(side='left', padx=8)
        mine = self.fb.mine(x['id'])
        if mine:
            ttk.Label(parent, text=t('test.mine.' + mine),
                      foreground=theme.OK if mine == 'pass' else theme.ERR
                      ).pack(anchor='w', pady=(0, 4))

    def result(self, passed):
        x = self.test
        if x is None:
            return
        open_steps = sum(1 for v in self.checks if not v.get())
        if passed and open_steps and not messagebox.askyesno(
                t('test.title'), t('test.steps.open', n=open_steps),
                parent=self.win):
            return
        if not self.fb.can_report(x['id']):
            messagebox.showinfo(t('test.title'), t('test.notopen'),
                                parent=self.win)
            return
        if self.session is not None and self.session.state in ('waiting',
                                                               'running'):
            if not messagebox.askyesno(t('test.title'), t('test.stillrun.q'),
                                       parent=self.win):
                return
        if x.get('needs_game') and self.session is None and \
                not messagebox.askyesno(t('test.title'), t('test.nogame.q'),
                                        parent=self.win):
            return
        note = self.note.get('1.0', 'end').strip()
        if not passed and not note:
            messagebox.showinfo(t('test.title'), t('test.fail.note'),
                                parent=self.win)
            self.note.focus_set()
            return
        self.fb.log.add(f'test {x["id"]}: result '
                        f'{"pass" if passed else "fail"}, '
                        f'{len(self.checks) - open_steps}/{len(self.checks)} '
                        'steps ticked')
        payload = foxfeedback.test_payload(
            TOOL, VERSION, self.fb.client_id(), get_lang(), x['id'], passed,
            message=note, log=self.fb.log.text(),
            game_log=self.session.text() if self.session else '')
        def sent():
            self.fb.remember(x['id'], passed)

            def shown():
                self._fill_list()
                self.test = None      # rebuild the panel with the new count
                self.select(x['id'])
            self.fb.refresh(shown)
        _preview_window(self.win, payload, lambda: self.fb.send(
            payload, self.win, on_ok=sent))


def _loc_list(d):
    return (d or {}).get(get_lang()) or (d or {}).get('en') or []


class BugWindow:
    """``error_text`` is what the tool showed, ``error_key`` its message
    key, ``guide`` the guide chapter the tool pointed to."""

    def __init__(self, app, parent=None, error_text='', error_key='',
                 guide='', title=None, fp_text=None):
        self.app = app
        self.fb = app.feedback
        self.error_text, self.error_key, self.guide = (error_text, error_key,
                                                       guide)
        self.fp_text = fp_text
        self.title = title or (error_key or t('bug.general'))
        parent = parent or app.root
        self.win = tk.Toplevel(parent)
        self.win.title(t('bug.title'))
        self.win.geometry('640x520')
        self.win.transient(parent)
        theme.dark_titlebar(self.win)
        f = ttk.Frame(self.win, padding=14)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=t('bug.head'), style='Brand.TLabel').pack(anchor='w')
        ttk.Label(f, text=t('bug.sub'), style='Muted.TLabel', wraplength=600,
                  justify='left').pack(anchor='w', pady=(2, 8))
        known = [i for i in self.fb.issues()
                 if i.get('status') != 'fixed'][:4]
        if known:
            ttk.Label(f, text=t('bug.known'), style='Brand.TLabel'
                      ).pack(anchor='w')
            for i in known:
                ttk.Label(f, text=f"  {i.get('title')}  ({i.get('version')}, "
                                  f"{i.get('count')}x)", style='Muted.TLabel',
                          wraplength=600, justify='left').pack(anchor='w')
        if error_text:
            ttk.Label(f, text=t('bug.error'), style='Brand.TLabel'
                      ).pack(anchor='w', pady=(8, 0))
            ttk.Label(f, text=error_text[:600], wraplength=600,
                      justify='left').pack(anchor='w')
        if guide:
            ttk.Button(f, text=t('bug.guide'), command=lambda:
                       app.show_guide(guide)).pack(anchor='w', pady=(6, 0))
        btns = ttk.Frame(f)
        btns.pack(side='bottom', fill='x', pady=(8, 0))
        ttk.Label(f, text=t('bug.what'), style='Brand.TLabel'
                  ).pack(anchor='w', pady=(10, 0))
        self.note = tk.Text(f, height=6, wrap='word', font=theme.FONT)
        self.note.pack(fill='both', expand=True)
        ttk.Button(btns, text=t('cancel'), command=self.win.destroy
                   ).pack(side='right')
        ttk.Button(btns, text=t('bug.next'), style='Accent.TButton',
                   command=self.next).pack(side='right', padx=6)
        self.note.focus_set()

    def next(self):
        note = self.note.get('1.0', 'end').strip()
        if not note and not self.error_text:
            messagebox.showinfo(t('bug.title'), t('bug.empty'),
                                parent=self.win)
            return
        payload = foxfeedback.bug_payload(
            TOOL, VERSION, self.fb.client_id(), get_lang(), self.title,
            error_key=self.error_key, error_text=self.error_text,
            guide_ref=self.guide, fp_text=self.fp_text,
            message=(note + NL + NL + self.error_text[:1500]).strip(),
            log=self.fb.log.text())
        _preview_window(self.win, payload, lambda: self.fb.send(
            payload, self.app.root, on_ok=None) or self.win.destroy())


class IssuesWindow:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title(t('issues.title'))
        self.win.geometry('720x460')
        self.win.transient(app.root)
        theme.dark_titlebar(self.win)
        f = ttk.Frame(self.win, padding=14)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=t('issues.head'), style='Brand.TLabel'
                  ).pack(anchor='w')
        self.sub = ttk.Label(f, text=t('issues.loading'),
                             style='Muted.TLabel', wraplength=680,
                             justify='left')
        self.sub.pack(anchor='w', pady=(2, 8))
        btns = ttk.Frame(f)
        btns.pack(side='bottom', fill='x', pady=(8, 0))
        cols = ('status', 'title', 'version', 'count', 'fixed')
        self.tree = ttk.Treeview(f, columns=cols, show='headings')
        for c, w in zip(cols, (90, 360, 70, 60, 80)):
            self.tree.heading(c, text=t('issues.col.' + c))
            self.tree.column(c, width=w, anchor='w', stretch=c == 'title')
        self.tree.pack(fill='both', expand=True)
        ttk.Button(btns, text=t('close'), command=self.win.destroy
                   ).pack(side='right')
        ttk.Button(btns, text=t('bug.button'), command=lambda:
                   BugWindow(app, self.win)).pack(side='left')
        ttk.Button(btns, text=t('test.menu'), command=lambda:
                   TestWindow.show(app)).pack(side='left', padx=6)
        self.fill()
        app.feedback.refresh(self.fill)

    def fill(self):
        fb = self.app.feedback
        try:
            self.tree.delete(*self.tree.get_children())
        except tk.TclError:
            return
        if fb.summary is None:
            self.sub.configure(text=t('issues.offline'))
            return
        rows = fb.issues()
        self.sub.configure(text=t('issues.sub', n=len(rows),
                                  tests=len(fb.untested())))
        for i in rows:
            self.tree.insert('', 'end', values=(
                t('issues.status.' + str(i.get('status'))), i.get('title'),
                i.get('version'), i.get('count'), i.get('fixed_in') or ''))


# What every version brings: (id, tour in guide.TOURS or None, chapter of
# the guide); the texts are news.<id>.title / .text.
NEWS = {
    '4.5.0': (('enemystats', 'enemy', 'enemylevels'),
              ('expcurve', 'enemy', 'enemylevels'),
              ('placeholders', None, 'npcs'),
              ('voicepack', None, 'npcs'),
              ('testrun', None, 'build')),
}


def news_since(seen):
    """The news of the versions after ``seen`` up to this one; with no
    version seen (first start) those of this one."""
    now = _vkey(VERSION)
    out = []
    for version, items in NEWS.items():
        v = _vkey(version)
        if v > now or (seen is None and v != now) or \
                (seen is not None and v <= _vkey(seen)):
            continue
        out.extend(items)
    return out


class WhatsNewWindow:
    """First start of a new version: its news with tour and guide, and the
    untested things."""

    @classmethod
    def maybe(cls, app):
        seen = app.cfg.get('news_seen')
        if seen == VERSION:
            return None
        if app.feedback.summary is None:
            return None                  # offline: ask again next start
        first_run = not isinstance(seen, str)
        app.cfg.set('news_seen', VERSION)
        app.cfg.save()
        fresh = [x for x in app.feedback.untested()
                 if first_run or _vkey(x['since']) > _vkey(seen)]
        news = news_since(None if first_run else seen)
        return cls(app, fresh, news) if fresh or news else None

    @classmethod
    def show_current(cls, app):
        """Help > What's new: this version's news and its untested things."""
        tests = [x for x in app.feedback.untested()
                 if _vkey(x['since']) == _vkey(VERSION)]
        return cls(app, tests, news_since(None))

    def __init__(self, app, tests, news=()):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title(t('news.title', version=VERSION))
        self.win.minsize(640, 200)
        self.win.transient(app.root)
        theme.dark_titlebar(self.win)
        f = ttk.Frame(self.win, padding=16)
        f.pack(fill='both', expand=True)
        ttk.Button(f, text=t('close'), command=self.win.destroy
                   ).pack(side='bottom', anchor='e', pady=(10, 0))
        if news:
            ttk.Label(f, text=t('news.new.head', version=VERSION),
                      style='Brand.TLabel').pack(anchor='w')
            ttk.Label(f, text=t('news.new.sub'), style='Muted.TLabel',
                      wraplength=640, justify='left'
                      ).pack(anchor='w', pady=(2, 8))
            for nid, tour, chapter in news:
                row = ttk.Frame(f)
                row.pack(fill='x', pady=4)
                btns = ttk.Frame(row)
                btns.pack(side='right', anchor='n')
                if tour:
                    ttk.Button(btns, text=t('news.tour'),
                               style='Accent.TButton',
                               command=lambda n=tour: self._tour(n)
                               ).pack(side='left', padx=(6, 0))
                if chapter:
                    ttk.Button(btns, text=t('news.guide'),
                               command=lambda c=chapter: app.show_guide(c)
                               ).pack(side='left', padx=(6, 0))
                text = ttk.Frame(row)
                text.pack(side='left', fill='x', expand=True)
                ttk.Label(text, text=t(f'news.{nid}.title'),
                          font=theme.FONT_BOLD, wraplength=420,
                          justify='left').pack(anchor='w')
                ttk.Label(text, text=t(f'news.{nid}.text'),
                          style='Muted.TLabel', wraplength=420,
                          justify='left').pack(anchor='w')
        if not tests:
            return
        ttk.Label(f, text=t('news.head'), style='Brand.TLabel'
                  ).pack(anchor='w', pady=(16 if news else 0, 0))
        ttk.Label(f, text=t('news.sub'), style='Muted.TLabel', wraplength=640,
                  justify='left').pack(anchor='w', pady=(2, 10))
        for x in tests[:6]:
            row = ttk.Frame(f)
            row.pack(fill='x', pady=3)
            ttk.Button(row, text=t('news.test'), style='Accent.TButton',
                       command=lambda i=x['id']: (self.win.destroy(),
                                                  TestWindow.show(app, i))
                       ).pack(side='right')
            ttk.Label(row, text=f"{_loc(x['title'])}  ({x['since']})",
                      wraplength=440, justify='left').pack(side='left')

    def _tour(self, name):
        self.win.destroy()
        self.app.start_tour(name)
