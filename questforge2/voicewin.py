"""Voice line finder, recording library panel and the trim editor (3.6.0).

- VoiceFinder: type what a line should say, get the closest original lines
  (hero by default, any original speaker by filter), listen, take the cue
  and its exact wording.
- LibraryPanel: every own take of the project with length, quest, node and
  line; play, jump to the line, trim, delete unused files.
- TrimWindow: waveform with a start and an end handle, play the selection,
  detect the silence, apply (the untrimmed take stays in ``_original``).
- PlaceholderWindow (4.5.0): placeholder voices for the silent lines from
  the speech synthesis of Windows (tts.py), marked as placeholders.
"""

import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import recorder, theme, voicebank
from .i18n import get_lang, t


def original_voices(app):
    """One OriginalVoices per game folder, kept on the app."""
    game = app.cfg.get('game_dir')
    ov = getattr(app, '_orig_voices', None)
    if ov is None or ov.game_dir != game:
        ov = app._orig_voices = voicebank.OriginalVoices(game)
    return ov


def play_cue(app, cue, parent=None):
    try:
        original_voices(app).play(cue)
        return True
    except (voicebank.VoiceError, OSError) as e:
        messagebox.showwarning(t('finder.title'), t('finder.noplay', err=e),
                               parent=parent or app.root)
        return False


# -- finder -------------------------------------------------------------------

class VoiceFinder:
    """Modal. ``result``: None or (cue, text or None)."""

    def __init__(self, app, text='', current=''):
        self.app = app
        self.result = None
        self.index = app.index
        self._job = None
        self.win = tk.Toplevel(app.root)
        self.win.title(t('finder.title'))
        self.win.transient(app.root)
        self.win.geometry('980x620')
        self.win.minsize(720, 420)
        theme.dark_titlebar(self.win)
        f = ttk.Frame(self.win, padding=12)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=t('finder.head'), style='Brand.TLabel'
                  ).pack(anchor='w')
        ttk.Label(f, text=t('finder.sub'), style='Muted.TLabel',
                  wraplength=940, justify='left').pack(anchor='w',
                                                       pady=(2, 8))
        top = ttk.Frame(f)
        top.pack(fill='x')
        ttk.Label(top, text=t('finder.say')).pack(side='left')
        self.q = tk.StringVar(value=text)
        ent = ttk.Entry(top, textvariable=self.q)
        ent.pack(side='left', fill='x', expand=True, padx=6)
        ent.bind('<KeyRelease>', lambda e: self._schedule())
        ent.bind('<Return>', lambda e: self._run())
        ttk.Label(top, text=t('finder.speaker')).pack(side='left',
                                                      padx=(8, 4))
        self.speakers = voicebank.speakers(self.index)
        self.labels = [t('finder.all')] + [self._speaker_label(s)
                                           for s in self.speakers]
        self.spk = tk.StringVar(value=self.labels[1] if len(self.labels) > 1
                                else self.labels[0])
        cb = ttk.Combobox(top, textvariable=self.spk, values=self.labels,
                          state='readonly', width=30)
        cb.pack(side='left')
        cb.bind('<<ComboboxSelected>>', lambda e: self._run())

        box = ttk.Frame(f)
        box.pack(fill='both', expand=True, pady=8)
        cols = ('score', 'text', 'speaker', 'quest', 'cue')
        self.tree = ttk.Treeview(box, columns=cols, show='headings',
                                 selectmode='browse')
        for col, w, st in (('score', 60, False), ('text', 470, True),
                           ('speaker', 150, False), ('quest', 150, False),
                           ('cue', 120, False)):
            self.tree.heading(col, text=t('finder.col.' + col))
            self.tree.column(col, width=w, stretch=st,
                             anchor='e' if col == 'score' else 'w')
        self.tree.tag_configure('current', foreground=theme.GOLD_HI)
        sb = ttk.Scrollbar(box, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.tree.pack(side='left', fill='both', expand=True)
        self.tree.bind('<Double-Button-1>', lambda e: self._ok())
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._selected())
        self.tree.bind('<space>', lambda e: (self._play(), 'break')[1])

        self.full = ttk.Label(f, text='', wraplength=940, justify='left')
        self.full.pack(anchor='w')
        self.count = ttk.Label(f, text='', style='Muted.TLabel')
        self.count.pack(anchor='w')
        bottom = ttk.Frame(f)
        bottom.pack(fill='x', pady=(8, 0))
        self.play_btn = ttk.Button(bottom, text='▶ ' + t('finder.play'),
                                   command=self._play)
        self.play_btn.pack(side='left')
        theme.Tooltip(self.play_btn, t('finder.play.tip'))
        self.take_text = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom, text=t('finder.taketext'),
                        variable=self.take_text).pack(side='left', padx=12)
        ttk.Button(bottom, text=t('cancel'), command=self.win.destroy
                   ).pack(side='right')
        ttk.Button(bottom, text=t('finder.take'), style='Accent.TButton',
                   command=self._ok).pack(side='right', padx=(0, 6))
        if not original_voices(app).available():
            self.play_btn.state(['disabled'])
            theme.Tooltip(self.play_btn, t('finder.nobank'))
        self.win.bind('<Escape>', lambda e: self.win.destroy())
        self.current = current
        self.rows = {}
        self._run()
        ent.focus_set()
        ent.icursor('end')
        self.win.grab_set()

    def _speaker_label(self, s):
        lec, names, n = s
        if lec == voicebank.HERO_LECTOR:
            name = t('finder.hero')
        else:
            name = names or t('finder.lector', n=lec)
        return f'{name}  ({n})'

    def _lector(self):
        v = self.spk.get()
        if v in self.labels[1:]:
            return self.speakers[self.labels.index(v) - 1][0]
        return None

    def _speaker_name(self, lec):
        for s in self.speakers:
            if s[0] == lec:
                return self._speaker_label(s).rsplit('  (', 1)[0]
        return str(lec)

    def _schedule(self):
        if self._job:
            self.win.after_cancel(self._job)
        self._job = self.win.after(250, self._run)

    def _run(self):
        self._job = None
        res = voicebank.search(self.index.cues, self.q.get(), self._lector())
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for i, (score, cue, lec, text, tree) in enumerate(res):
            qid = voicebank.tree_quest(tree)
            quest = self.index.quest_label(qid) if qid is not None else ''
            iid = str(i)
            self.rows[iid] = (cue, text)
            self.tree.insert('', 'end', iid=iid, values=(
                f'{score * 100:.0f} %' if self.q.get().strip() else '',
                text, self._speaker_name(lec), quest, cue),
                tags=('current',) if cue == self.current else ())
        self.count.configure(text=t('finder.count', n=len(res)))
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids[0])
            self.tree.see(kids[0])
        else:
            self.full.configure(text='')

    def _selected(self):
        sel = self.tree.selection()
        if sel:
            cue, text = self.rows[sel[0]]
            self.full.configure(text=f'{cue}:  {text}')

    def _play(self):
        sel = self.tree.selection()
        if sel:
            play_cue(self.app, self.rows[sel[0]][0], self.win)

    def _ok(self):
        sel = self.tree.selection()
        if not sel:
            return
        recorder.stop_playing()
        cue, text = self.rows[sel[0]]
        self.result = (cue, text if self.take_text.get() else None)
        self.win.destroy()


# -- placeholder voices (4.5.0) -------------------------------------------------

class PlaceholderWindow:
    """Placeholder voices for the silent lines: voice, pitch and speed per
    speaker (kept in the project as ``tts_voices``), then one run of the
    speech synthesis for all lines of the scope. Modal."""

    def __init__(self, app):
        from . import tts
        self.app = app
        self.tts = tts
        self.voices = []
        self.conf = {}                   # speaker key -> settings shown
        self.rows = []
        self.running = False
        self.cancel = None
        self.progress = (0, 1)
        p = app.project
        self.settings = p.extra.setdefault('tts_voices', {})
        in_project = app.quest is not None and app.quest in p.quests
        self.win = tk.Toplevel(app.root)
        self.win.title(t('tts.title'))
        self.win.transient(app.root)
        self.win.geometry('840x580')
        self.win.minsize(720, 440)
        theme.dark_titlebar(self.win)
        f = ttk.Frame(self.win, padding=12)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=t('tts.head'), style='Brand.TLabel').pack(anchor='w')
        ttk.Label(f, text=t('tts.sub'), style='Muted.TLabel', wraplength=800,
                  justify='left').pack(anchor='w', pady=(2, 8))
        top = ttk.Frame(f)
        top.pack(fill='x')
        ttk.Label(top, text=t('tts.scope')).pack(side='left')
        self.scope = tk.StringVar(value='quest' if in_project else 'all')
        rq = ttk.Radiobutton(top, text=t('tts.scope.quest',
                                         id=app.quest.id if in_project else '-'),
                             value='quest', variable=self.scope,
                             command=self._fill)
        rq.pack(side='left', padx=(6, 0))
        if not in_project:
            rq.state(['disabled'])
        ttk.Radiobutton(top, text=t('tts.scope.all'), value='all',
                        variable=self.scope, command=self._fill
                        ).pack(side='left', padx=(12, 0))
        outer = ttk.Frame(f)
        outer.pack(fill='both', expand=True, pady=(10, 6))
        canvas = tk.Canvas(outer, bg=theme.BG, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        self.table = ttk.Frame(canvas)
        canvas.create_window(0, 0, window=self.table, anchor='nw')
        self.table.bind('<Configure>', lambda e: canvas.configure(
            scrollregion=canvas.bbox('all')))
        self.renew_old = tk.BooleanVar(value=True)
        self.renew_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text=t('tts.renew.outdated'),
                        variable=self.renew_old, command=self._count
                        ).pack(anchor='w')
        ttk.Checkbutton(f, text=t('tts.renew.all'), variable=self.renew_all,
                        command=self._count).pack(anchor='w')
        self.info = ttk.Label(f, text=t('tts.loading'), wraplength=800,
                              justify='left')
        self.info.pack(anchor='w', pady=(8, 0))
        self.bar = ttk.Progressbar(f, maximum=100)
        self.bar.pack(fill='x', pady=(6, 0))
        bottom = ttk.Frame(f)
        bottom.pack(fill='x', pady=(10, 0))
        self.close_btn = ttk.Button(bottom, text=t('close'),
                                    command=self.close)
        self.close_btn.pack(side='right')
        self.start_btn = ttk.Button(bottom, text=t('tts.start'),
                                    style='Accent.TButton',
                                    command=self.start)
        self.start_btn.pack(side='right', padx=(0, 6))
        self.start_btn.state(['disabled'])
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.win.bind('<Escape>', lambda e: self.close())
        self._load()
        self.win.grab_set()

    # -- data -----------------------------------------------------------------

    def _alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def _later(self, ms, fn):
        if self._alive():
            self.win.after(ms, fn)

    def _load(self):
        box = {}

        def work():
            try:
                box['v'] = self.tts.voices()
            except Exception as e:           # shown in the window
                box['err'] = e
        th = threading.Thread(target=work, daemon=True)
        th.start()

        def poll():
            if th.is_alive():
                self._later(100, poll)
                return
            if not self._alive():
                return
            self.voices = box.get('v') or []
            if not self.voices:
                self.info.configure(text=t('tts.novoices',
                                           err=box.get('err') or '-'),
                                    foreground=theme.ERR)
                return
            self._fill()
        self._later(100, poll)

    def _quests(self):
        p = self.app.project
        if self.scope.get() == 'quest' and self.app.quest in p.quests:
            return [self.app.quest]
        return list(p.quests)

    def _all_quests(self):
        app = self.app
        qs = list(app.project.quests)
        qs += [q for q in getattr(app, 'mod_quests', {}).values()
               if q not in qs]
        return qs

    def _speakers(self, quests):
        """[(key, label)]: the hero first, then the NPCs as they come."""
        tts = self.tts
        seen = {}
        for q in quests:
            for node in q.graph.get('nodes', {}).values():
                if not tts.voiced_node(node) or not any(
                        tts.clean(ln.get('text'))
                        for ln in node.get('lines') or []):
                    continue
                key = tts.speaker_key(node)
                if key in seen:
                    continue
                if key == tts.HERO:
                    seen[key] = t('finder.hero')
                else:
                    spk = q.speaker(node.get('speaker')) or {}
                    name = spk.get('name') or ''
                    seen[key] = f'{name}  (NPC_{key})' if name \
                        else f'NPC_{key}'
        pos = {k: i for i, k in enumerate(seen)}
        order = sorted(seen, key=lambda k: (k != tts.HERO, pos[k]))
        return [(k, seen[k]) for k in order]

    def _voice_label(self, v):
        g = v.get('gender')
        extra = v['lang'] + (', ' + t('tts.' + g) if g in ('male', 'female')
                             else '')
        return f"{self.tts.short_name(v)}  ({extra})"

    def _exists(self, line):
        path = recorder.voice_path(self.app.project, line)
        return bool(path and os.path.isfile(path))

    def _todo(self):
        return self.tts.todo(self._quests(), self._exists,
                             self.renew_old.get(), self.renew_all.get())

    # -- table ----------------------------------------------------------------

    def _fill(self):
        if not self.voices:
            return
        tts = self.tts
        for w in self.table.winfo_children():
            w.destroy()
        self.rows = []
        speakers = self._speakers(self._quests())
        keys = [k for k, _ in speakers]
        have = {k: v for k, v in self.settings.items()}
        have.update(self.conf)
        new = tts.defaults(self.voices, get_lang(), keys, have)
        for k in keys:
            if k not in self.conf:
                self.conf[k] = dict(self.settings.get(k) or new[k])
        labels = [self._voice_label(v) for v in self.voices]
        for c, key in enumerate(('speaker', 'voice', 'pitch', 'rate', '',
                                 'lines')):
            ttk.Label(self.table, text=t('tts.col.' + key) if key else '',
                      style='Muted.TLabel').grid(row=0, column=c, sticky='w',
                                                 padx=(0, 10), pady=(0, 4))
        for r, (key, name) in enumerate(speakers, start=1):
            conf = self.conf[key]
            v = tts.find(self.voices, conf.get('voice')) or tts.pick(
                self.voices, get_lang())
            conf['voice'] = v['id']
            ttk.Label(self.table, text=name).grid(row=r, column=0,
                                                  sticky='w', padx=(0, 10))
            var = tk.StringVar(value=self._voice_label(v))
            cb = ttk.Combobox(self.table, textvariable=var, values=labels,
                              state='readonly', width=34)
            cb.grid(row=r, column=1, sticky='w', padx=(0, 10), pady=1)
            pitch = tk.StringVar(value=str(conf.get('pitch', 0)))
            rate = tk.StringVar(value=str(conf.get('rate', 0)))
            for c, sv in ((2, pitch), (3, rate)):
                ttk.Spinbox(self.table, from_=-tts.LIMIT, to=tts.LIMIT,
                            increment=5, width=6, textvariable=sv
                            ).grid(row=r, column=c, sticky='w', padx=(0, 10))
            pb = ttk.Button(self.table, text='▶ ' + t('tts.probe'),
                            command=lambda k=key: self._probe(k))
            pb.grid(row=r, column=4, sticky='w', padx=(0, 10))
            theme.Tooltip(pb, t('tts.probe.tip'))
            cnt = ttk.Label(self.table, text='', style='Muted.TLabel')
            cnt.grid(row=r, column=5, sticky='w')

            def changed(*_a, k=key, var=var, pitch=pitch, rate=rate):
                self._take(k, var, pitch, rate)
            var.trace_add('write', changed)
            pitch.trace_add('write', changed)
            rate.trace_add('write', changed)
            self.rows.append((key, cnt, pb))
        self._count()

    def _take(self, key, var, pitch, rate):
        conf = self.conf[key]
        labels = [self._voice_label(v) for v in self.voices]
        if var.get() in labels:
            conf['voice'] = self.voices[labels.index(var.get())]['id']
        for name, sv in (('pitch', pitch), ('rate', rate)):
            try:
                val = int(float(sv.get()))
            except ValueError:
                continue
            conf[name] = max(-self.tts.LIMIT, min(self.tts.LIMIT, val))
        if self.settings.get(key) != conf:
            self.settings[key] = dict(conf)
            self.app.mark_dirty()

    def _count(self):
        if not self.voices:
            return
        items = self._todo()
        per = {}
        kinds = {'new': 0, 'outdated': 0, 'renew': 0}
        for it in items:
            per[it[4]] = per.get(it[4], 0) + 1
            kinds[it[5]] += 1
        for key, cnt, _pb in self.rows:
            cnt.configure(text=str(per.get(key, 0)))
        if items:
            self.info.configure(text=t('tts.count', n=len(items),
                                       new=kinds['new'],
                                       old=kinds['outdated'],
                                       again=kinds['renew']),
                                foreground=theme.INK)
        else:
            self.info.configure(text=t('tts.count.none'),
                                foreground=theme.INK)
        if not self.running:
            self.start_btn.state(['!disabled'] if items else ['disabled'])

    # -- speaking -------------------------------------------------------------

    def _job(self, key, text):
        conf = self.conf[key]
        v = self.tts.find(self.voices, conf.get('voice')) or self.tts.pick(
            self.voices, get_lang())
        return {'voice': v, 'pitch': conf.get('pitch', 0),
                'rate': conf.get('rate', 0), 'text': text}

    def _probe(self, key):
        if self.running:
            return
        text = None
        for q in self._quests():
            for node in q.graph.get('nodes', {}).values():
                if self.tts.voiced_node(node) and \
                        self.tts.speaker_key(node) == key:
                    for ln in node.get('lines') or []:
                        if self.tts.clean(ln.get('text')):
                            text = ln['text']
                            break
                if text:
                    break
            if text:
                break
        job = self._job(key, text or t('tts.sample'))
        box = {}

        def work():
            try:
                box['res'] = self.tts.synthesize([job])[0]
            except Exception as e:           # shown in the window
                box['res'] = (None, str(e))
        th = threading.Thread(target=work, daemon=True)
        th.start()
        self.win.configure(cursor='watch')

        def poll():
            if th.is_alive():
                self._later(100, poll)
                return
            if not self._alive():
                return
            self.win.configure(cursor='')
            pcm, err = box['res']
            if err:
                self.info.configure(text=t('tts.error', err=err),
                                    foreground=theme.ERR)
                return
            import tempfile
            p = os.path.join(tempfile.gettempdir(), 'qf2_tts_probe.wav')
            recorder.stop_playing()
            recorder.write_wav(p, pcm)
            recorder.play(p)
        self._later(100, poll)

    def start(self):
        if self.running:
            if self.cancel is not None:
                self.cancel.set()
            return
        app, tts = self.app, self.tts
        items = self._todo()
        if not items:
            return
        for key, conf in self.conf.items():
            if self.settings.get(key) != conf:
                self.settings[key] = dict(conf)
                app.mark_dirty()
        project = app.project
        quests = self._all_quests()
        jobs = [self._job(it[4], it[3]['text']) for it in items]
        names = [recorder.take_name(project, quests, q, nid, i, ln)
                 for q, nid, i, ln, _k, _r in items]
        folder = recorder.voice_dir(project)
        self.cancel = threading.Event()
        self.running = True
        app.tts_busy = True
        self.progress = (0, 2 * len(jobs))
        self.start_btn.configure(text=t('tts.cancel'))
        self.close_btn.state(['disabled'])
        recorder.stop_playing()
        box = {}

        def progress(done, total):
            self.progress = (done, 2 * total)

        def work():
            out = []
            try:
                res = tts.synthesize(jobs, progress, self.cancel)
                for k, ((pcm, err), name) in enumerate(zip(res, names)):
                    self.progress = (len(jobs) + k + 1, 2 * len(jobs))
                    if pcm is None:
                        out.append((False, err))
                        continue
                    p = os.path.join(folder, name)
                    try:
                        recorder.write_wav(p, pcm)
                        recorder.drop_original(p)
                        out.append((True, None))
                    except OSError as e:
                        out.append((False, str(e)))
            except Exception as e:           # shown in the window
                box['err'] = e
            box['out'] = out
        th = threading.Thread(target=work, daemon=True)
        th.start()

        def poll():
            done, total = self.progress
            try:
                self.bar.configure(value=100 * done / max(total, 1))
                self.info.configure(text=t('tts.running',
                                           done=min(done, len(jobs)),
                                           total=len(jobs)),
                                    foreground=theme.INK)
            except tk.TclError:
                pass
            if th.is_alive():
                self._later(150, poll)
                return
            self._finish(items, names, jobs, box)
        self._later(150, poll)

    def _finish(self, items, names, jobs, box):
        app, tts = self.app, self.tts
        self.running = False
        app.tts_busy = False
        out = box.get('out') or []
        ok = [(it, name, job) for it, name, job, res in
              zip(items, names, jobs, out) if res[0]]
        errs = [res[1] for res in out if not res[0]]
        if 'err' in box:
            errs.insert(0, str(box['err']))
        cur = app.quest
        if any(it[0] is cur for it, _n, _j in ok):
            app.push_undo('voice')
        for (q, nid, i, ln, key, reason), name, job in ok:
            ln['voice'] = name
            tts.mark(ln, job['voice']['id'], job['pitch'], job['rate'])
        if ok:
            if any(it[0] is cur for it, _n, _j in ok):
                app.changed(from_inspector=True)
            else:
                app.mark_dirty()
            app.inspector.refresh()
            app.voice_library_changed()
        if not self._alive():
            return
        self.start_btn.configure(text=t('tts.start'))
        self.close_btn.state(['!disabled'])
        self.bar.configure(value=100 if ok else 0)
        self._count()
        text = t('tts.done', n=len(ok))
        app.set_info(text, 'StatusOk.TLabel')
        failed = len(items) - len(ok)
        if failed:
            text += '  ' + t('tts.failed', n=failed,
                             err=errs[0] if errs else '-')
        self.info.configure(text=text, foreground=theme.ERR if failed
                            else theme.OK)

    def close(self):
        if self.running:
            if self.cancel is not None:
                self.cancel.set()
            return
        recorder.stop_playing()
        self.win.destroy()


# -- trim editor ----------------------------------------------------------------

class TrimWindow:
    W, H = 760, 170

    def __init__(self, app, path, on_done=None):
        self.app = app
        self.path = path
        self.on_done = on_done
        self.pcm, self.rate = recorder.read_wav(path)
        self.total = len(self.pcm) / (2.0 * self.rate)
        self.start, self.end = 0.0, self.total
        self._drag = None
        self.win = tk.Toplevel(app.root)
        self.win.title(t('trim.title', name=os.path.basename(path)))
        self.win.transient(app.root)
        self.win.resizable(False, False)
        theme.dark_titlebar(self.win)
        f = ttk.Frame(self.win, padding=12)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=t('trim.head'), style='Brand.TLabel').pack(anchor='w')
        ttk.Label(f, text=t('trim.sub'), style='Muted.TLabel',
                  wraplength=self.W, justify='left').pack(anchor='w',
                                                          pady=(2, 8))
        self.c = tk.Canvas(f, width=self.W, height=self.H, bg=theme.CANVAS_BG,
                           highlightthickness=1,
                           highlightbackground=theme.LINE, cursor='sb_h_double_arrow')
        self.c.pack()
        self.c.bind('<ButtonPress-1>', self._press)
        self.c.bind('<B1-Motion>', self._motion)
        self.c.bind('<ButtonRelease-1>', lambda e: setattr(self, '_drag', None))
        self.info = ttk.Label(f, text='')
        self.info.pack(anchor='w', pady=(6, 0))
        row = ttk.Frame(f)
        row.pack(fill='x', pady=(10, 0))
        ttk.Button(row, text='▶ ' + t('trim.play'),
                   command=self._play_sel).pack(side='left')
        ttk.Button(row, text='▶ ' + t('trim.playall'),
                   command=lambda: recorder.play(self.path)
                   ).pack(side='left', padx=(6, 0))
        ttk.Button(row, text=t('trim.auto'), command=self._auto
                   ).pack(side='left', padx=(6, 0))
        self.restore_btn = ttk.Button(row, text=t('trim.restore'),
                                      command=self._restore)
        self.restore_btn.pack(side='left', padx=(6, 0))
        if not os.path.isfile(recorder.original_path(path)):
            self.restore_btn.state(['disabled'])
        ttk.Button(row, text=t('cancel'), command=self.close
                   ).pack(side='right')
        ttk.Button(row, text=t('trim.apply'), style='Accent.TButton',
                   command=self._apply).pack(side='right', padx=(0, 6))
        self.win.bind('<Escape>', lambda e: self.close())
        self.win.bind('<space>', lambda e: self._play_sel())
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.wave = recorder.peaks(self.pcm, self.W)
        self._draw()
        self.win.grab_set()

    def _x(self, sec):
        return sec / self.total * self.W if self.total else 0

    def _sec(self, x):
        return max(0.0, min(self.total, x / self.W * self.total))

    def _draw(self):
        c = self.c
        c.delete('all')
        mid = self.H / 2
        x0, x1 = self._x(self.start), self._x(self.end)
        c.create_rectangle(0, 0, x0, self.H, fill='#000000', outline='',
                           stipple='gray50')
        c.create_rectangle(x1, 0, self.W, self.H, fill='#000000', outline='',
                           stipple='gray50')
        for x, v in enumerate(self.wave):
            inside = x0 <= x <= x1
            h = max(1, v * (self.H / 2 - 6))
            c.create_line(x, mid - h, x, mid + h,
                          fill=theme.GOLD if inside else theme.MUT)
        for x, tag in ((x0, 'start'), (x1, 'end')):
            c.create_line(x, 0, x, self.H, fill=theme.MOD, width=2)
            c.create_rectangle(x - 6, 0, x + 6, 14, fill=theme.MOD,
                               outline='')
        self.info.configure(text=t('trim.info', start=self.start, end=self.end,
                                   len=self.end - self.start,
                                   total=self.total))

    def _press(self, ev):
        x0, x1 = self._x(self.start), self._x(self.end)
        self._drag = 'start' if abs(ev.x - x0) <= abs(ev.x - x1) else 'end'
        self._motion(ev)

    def _motion(self, ev):
        if not self._drag:
            return
        s = self._sec(ev.x)
        gap = 0.1
        if self._drag == 'start':
            self.start = min(s, self.end - gap)
        else:
            self.end = max(s, self.start + gap)
        self.start = max(0.0, self.start)
        self.end = min(self.total, self.end)
        self._draw()

    def _auto(self):
        self.start, self.end = recorder.detect_trim(self.pcm, self.rate)
        self._draw()

    def _play_sel(self):
        import tempfile
        part = recorder.cut(self.pcm, self.rate, self.start, self.end)
        p = os.path.join(tempfile.gettempdir(), 'qf2_trim_preview.wav')
        recorder.stop_playing()
        recorder.write_wav(p, part, self.rate)
        recorder.play(p)

    def _apply(self):
        recorder.stop_playing()
        if self.start <= 0.0005 and self.end >= self.total - 0.0005:
            self.close()
            return
        try:
            n = recorder.trim_file(self.path, self.start, self.end)
        except (OSError, ValueError) as e:
            messagebox.showerror(t('trim.head'), str(e), parent=self.win)
            return
        self.app.set_info(t('trim.done', name=os.path.basename(self.path),
                            s=n), 'StatusOk.TLabel')
        self.close(done=True)

    def _restore(self):
        recorder.stop_playing()
        if not messagebox.askyesno(t('trim.head'), t('trim.restore.q'),
                                   parent=self.win):
            return
        if recorder.restore_original(self.path):
            self.app.set_info(t('trim.restored',
                                name=os.path.basename(self.path)),
                              'StatusOk.TLabel')
        self.close(done=True)

    def close(self, done=False):
        recorder.stop_playing()
        self.win.destroy()
        if done and self.on_done:
            self.on_done()


# -- library panel ------------------------------------------------------------

class LibraryPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, style='Panel.TFrame')
        self.app = app
        self.items = []
        self._job = None
        head = ttk.Frame(self, style='Panel.TFrame')
        head.pack(fill='x')
        ttk.Label(head, text=t('lib.title'), style='PanelTitle.TLabel'
                  ).pack(side='left', fill='x', expand=True)
        ttk.Button(head, text='×', width=2,
                   command=self.hide).pack(side='right', padx=4)
        body = ttk.Frame(self, style='Panel.TFrame', padding=(8, 2))
        body.pack(fill='both', expand=True)
        self.q = tk.StringVar()
        ent = ttk.Entry(body, textvariable=self.q)
        ent.pack(fill='x', pady=(2, 4))
        theme.Tooltip(ent, t('lib.search'))
        ent.bind('<KeyRelease>', lambda e: self.fill())
        row = ttk.Frame(body, style='Panel.TFrame')
        row.pack(fill='x', pady=(0, 4))
        self.btns = {}
        for key, glyph, cmd in (('play', '▶', self.play),
                                ('goto', '→', self.goto),
                                ('trim', '✂', self.trim),
                                ('delete', '×', self.delete)):
            b = ttk.Button(row, text=glyph, width=3, command=cmd)
            b.pack(side='left', padx=(0, 3))
            theme.Tooltip(b, t('lib.' + key))
            self.btns[key] = b
        tb = ttk.Button(row, text=t('tts.short'), width=4,
                        command=self.placeholders)
        tb.pack(side='left', padx=(6, 0))
        theme.Tooltip(tb, t('lib.ttsbtn'))
        self.count = ttk.Label(row, text='', style='PanelMuted.TLabel')
        self.count.pack(side='right')
        box = ttk.Frame(body, style='Panel.TFrame')
        box.pack(fill='both', expand=True)
        cols = ('name', 'len', 'where', 'line')
        self.tree = ttk.Treeview(box, columns=cols, show='headings',
                                 selectmode='browse', height=6)
        for col, w, st in (('name', 110, False), ('len', 44, False),
                           ('where', 90, False), ('line', 160, True)):
            self.tree.heading(col, text=t('lib.col.' + col))
            self.tree.column(col, width=w, stretch=st,
                             anchor='e' if col == 'len' else 'w')
        self.tree.tag_configure('unused', foreground=theme.MUT)
        self.tree.tag_configure('missing', foreground=theme.ERR)
        self.tree.tag_configure('tts', foreground=theme.WARN)
        sb = ttk.Scrollbar(box, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.tree.pack(side='left', fill='both', expand=True)
        self.tree.bind('<Double-Button-1>', lambda e: self.goto())
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._buttons())
        self.tree.bind('<space>', lambda e: (self.play(), 'break')[1])
        self.refresh()

    def hide(self):
        self.app.vars['voices'].set(False)
        self.app._apply_panels()

    def placeholders(self):
        self.app.show_placeholders()

    def schedule(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(400, self.refresh)

    def _quests(self):
        app = self.app
        qs = list(app.project.quests) if app.project else []
        qs += [q for q in getattr(app, 'mod_quests', {}).values()
               if q not in qs]
        return qs

    def refresh(self):
        self._job = None
        app = self.app
        self.items = (recorder.library(app.project, self._quests())
                      if app.project else [])
        self.fill()

    def fill(self):
        sel = self.tree.selection()
        keep = sel[0] if sel else None
        self.tree.delete(*self.tree.get_children())
        q = self.q.get().strip().lower()
        shown = 0
        for i, it in enumerate(self.items):
            uses = it['uses']
            where = ', '.join(f'Q_{u[0].id}' for u in uses[:2]) + (
                ' +' if len(uses) > 2 else '')
            line = uses[0][3] if uses else t('lib.unused')
            if not it['exists']:
                line = t('lib.missing') + (' ' + uses[0][3] if uses else '')
            if it.get('tts'):
                line = t('lib.tts') + ' ' + line
            text = f"{it['name']} {where} {' '.join(u[3] for u in uses)}"
            if it.get('tts'):
                text += ' ' + t('lib.tts')
            if q and q not in text.lower():
                continue
            tag = ('missing',) if not it['exists'] else (
                ('unused',) if not uses else (
                    ('tts',) if it.get('tts') else ()))
            secs = it['seconds']
            self.tree.insert('', 'end', iid=str(i), values=(
                it['name'] + (' ✂' if it['trimmed'] else ''),
                f'{secs:.1f}' if secs is not None else '-', where,
                line.replace('\n', ' ')), tags=tag)
            shown += 1
        if keep and self.tree.exists(keep):
            self.tree.selection_set(keep)
        n_unused = sum(1 for it in self.items if it['exists'] and not it['uses'])
        self.count.configure(text=t('lib.count', n=shown, unused=n_unused))
        if not self.app.project or not self.app.project.path:
            self.count.configure(text=t('lib.unsaved'))
        self._buttons()

    def _item(self):
        sel = self.tree.selection()
        return self.items[int(sel[0])] if sel else None

    def _buttons(self):
        it = self._item()
        for key, b in self.btns.items():
            ok = it is not None and {
                'play': it and it['exists'], 'trim': it and it['exists'],
                'goto': it and bool(it['uses']),
                'delete': it and it['exists'] and not it['uses']}[key]
            b.state(['!disabled'] if ok else ['disabled'])

    def play(self):
        it = self._item()
        if it and it['exists']:
            recorder.stop_playing()
            recorder.play(it['path'])

    def goto(self):
        it = self._item()
        if not it or not it['uses']:
            return
        quest, nid = it['uses'][0][0], it['uses'][0][1]
        self.app.goto_problem(quest, nid)
        self.app.inspector.show({nid})

    def trim(self):
        it = self._item()
        if not it or not it['exists']:
            return
        if getattr(self.app, 'voice_rec', None):
            self.app.set_info(t('voice.busy'), 'StatusErr.TLabel')
            return
        try:
            TrimWindow(self.app, it['path'], on_done=self._trimmed)
        except (OSError, ValueError, EOFError) as e:
            messagebox.showerror(t('trim.head'), str(e), parent=self.app.root)

    def _trimmed(self):
        self.refresh()
        self.app.inspector.refresh()

    def delete(self):
        it = self._item()
        if not it or not it['exists'] or it['uses']:
            return
        if not messagebox.askyesno(t('lib.title'),
                                   t('lib.delete.q', name=it['name']),
                                   parent=self.app.root):
            return
        recorder.stop_playing()
        for p in (it['path'], recorder.original_path(it['path'])):
            try:
                os.remove(p)
            except OSError:
                pass
        self.refresh()
