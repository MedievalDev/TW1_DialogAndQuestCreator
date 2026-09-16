"""Timeline of all quests (plan section 10).

A horizontal strip of cards. Order: topological sort over the AOQ
PROMOTE/TAKE chain, quests without any chain after that by id; journal
groups form labelled sections. Own quests have a gold frame, quests of the
game a grey one, game quests changed in the project a dashed gold one.
"""

import heapq
import tkinter as tk
from tkinter import ttk

from . import model, theme
from .i18n import t

SIZES = {'small': (150, 42), 'large': (200, 96)}
TAB_H = 22
GAP = 8
SECTION_GAP = 26
LABEL_H = 18


def chain_order(entries, edges):
    """Quest ids in chain order: Kahn's algorithm (smallest id first) over
    the chained quests, cycles broken by id, unchained quests at the end."""
    ids = {e['qid'] for e in entries}
    succ, indeg, chained = {}, {i: 0 for i in ids}, set()
    for a, b in edges:
        if a in ids and b in ids and a != b and b not in succ.setdefault(a, set()):
            succ[a].add(b)
            indeg[b] += 1
            chained.update((a, b))
    heap = [i for i in chained if indeg[i] == 0]
    heapq.heapify(heap)
    out, seen = [], set()
    while len(seen) < len(chained):
        if not heap:
            rest = sorted(i for i in chained if i not in seen)
            heapq.heappush(heap, rest[0])
            indeg[rest[0]] = 0
        i = heapq.heappop(heap)
        if i in seen:
            continue
        seen.add(i)
        out.append(i)
        for j in sorted(succ.get(i, ())):
            indeg[j] -= 1
            if indeg[j] <= 0 and j not in seen:
                heapq.heappush(heap, j)
    out += sorted(i for i in ids if i not in chained)
    return out


class Timeline(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, style='Panel.TFrame')
        self.app = app
        self.size = 'small'
        self.cards = {}             # qid -> (x1, y1, x2, y2)
        self.entries = {}
        self._job = None
        bar = ttk.Frame(self, style='Panel.TFrame')
        bar.pack(fill='x')
        ttk.Label(bar, text=t('panel.timeline'), style='PanelTitle.TLabel'
                  ).pack(side='left')
        self.q = tk.StringVar()
        ent = ttk.Entry(bar, textvariable=self.q, width=22)
        ent.pack(side='left', padx=(4, 6), pady=3)
        ent.bind('<KeyRelease>', lambda e: self.schedule(150))
        self.search = ent
        self.group = tk.StringVar(value=t('tl.allgroups'))
        self.group_cb = ttk.Combobox(bar, textvariable=self.group, width=24,
                                     state='readonly')
        self.group_cb.pack(side='left', padx=(0, 6))
        self.group_cb.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        self.own = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text=t('tl.own'), variable=self.own,
                        style='Panel.TCheckbutton',
                        command=self.refresh).pack(side='left', padx=(0, 6))
        self.links = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text=t('tl.links'), variable=self.links,
                        style='Panel.TCheckbutton',
                        command=self.refresh).pack(side='left', padx=(0, 6))
        self.big = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text=t('tl.large'), variable=self.big,
                        style='Panel.TCheckbutton',
                        command=self._resize).pack(side='left')
        self.new_btn = ttk.Button(bar, text='+ ' + t('quest.new'),
                                  command=app.new_quest)
        self.new_btn.pack(side='right', padx=6, pady=2)
        self.enemy_btn = ttk.Button(bar, text=t('tl.enemylevels'),
                                    command=app.show_enemy_levels)
        self.enemy_btn.pack(side='right', padx=(0, 4), pady=2)
        theme.Tooltip(self.enemy_btn, t('tip.enemylevels'))
        self.limit_btn = ttk.Button(bar, text=t('tl.limit', n=400),
                                    command=app.show_quest_limit)
        self.limit_btn.pack(side='right', padx=(0, 4), pady=2)
        theme.Tooltip(self.limit_btn, t('tip.limit'))
        self.count = ttk.Label(bar, text='', style='PanelMuted.TLabel')
        self.count.pack(side='right', padx=6)
        self.tabs = tk.Canvas(self, bg=theme.PANEL, highlightthickness=0,
                              height=TAB_H)
        self.tabs.pack(fill='x')
        self.tabs.bind('<Button-1>', self._tab_click)
        self.tabs.bind('<MouseWheel>', lambda e: self.tabs.xview_scroll(
            -1 if e.delta > 0 else 1, 'units'))
        self.tab_hits = []          # (x1, x2, group or None)
        self.canvas = tk.Canvas(self, bg=theme.CANVAS_BG, highlightthickness=0,
                                height=SIZES['small'][1] + LABEL_H + 18)
        self.sb = ttk.Scrollbar(self, orient='horizontal',
                                command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self.sb.set)
        self.sb.pack(side='bottom', fill='x')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Button-1>', self._click)
        self.canvas.bind('<Button-3>', self._context)
        self.canvas.bind('<MouseWheel>', lambda e: self.canvas.xview_scroll(
            -3 if e.delta > 0 else 3, 'units'))
        self.canvas.bind('<Motion>', self._hover)
        self.canvas.bind('<Leave>', lambda e: self.app.set_hint(''))

    # -- data -------------------------------------------------------------------

    def collect(self):
        """{qid: entry} and chain edges from the index and the project."""
        app = self.app
        idx = app.index
        entries, edges = {}, []
        if idx:
            for key, q in idx.quests.items():
                qid = int(key)
                giver = idx.npc(q['giver']) if q.get('giver') is not None else None
                entries[qid] = {
                    'qid': qid, 'title': q['title'], 'group': q['group'],
                    'giver': giver['name'] if giver else '',
                    'fc': ' '.join(q['fc'] or [])[:60], 'lines': q['lines'],
                    'source': q['source'], 'modified': q.get('modified_by'),
                    'kind': 'game'}
                for act, ev, target in q.get('aoq') or []:
                    if act in ('PROMOTE', 'TAKE') and target is not None:
                        edges.append((qid, target))
        if app.project:
            for q in app.project.quests:
                if q.id is None:
                    continue
                e = entries.get(q.id, {'qid': q.id, 'source': 'project',
                                       'modified': None, 'lines': 0, 'fc': ''})
                task = q.task()
                e = dict(e, title=q.title or e.get('title', ''),
                         group=q.group, kind='edited' if q.retail else 'own',
                         giver=app.speaker_style(q.giver)[0]
                         if q.giver is not None else '',
                         lines=sum(len(n.get('lines') or [])
                                   for n in q.graph['nodes'].values()
                                   if n.get('type') in ('npc', 'player')),
                         fc=(task.get('fc') or '') + ' ' + ' '.join(
                             str(v) for v in (task.get('args') or {}).values()))
                entries[q.id] = e
                if not q.retail:
                    for c in q.conditions_list():
                        if c.get('cond') == 'after' and isinstance(
                                c.get('quest'), int):
                            edges.append((c['quest'], q.id))
        return entries, edges

    # -- drawing ------------------------------------------------------------------

    def schedule(self, ms=400):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(ms, self.refresh)

    def _resize(self):
        self.size = 'large' if self.big.get() else 'small'
        h = SIZES[self.size][1] + LABEL_H + 18
        self.canvas.configure(height=h)
        self.app.timeline_height(h + 40)
        self.refresh()

    def refresh(self):
        self._job = None
        c = self.canvas
        c.delete('all')
        self.cards = {}
        entries, edges = self.collect()
        self.entries = entries
        idx = self.app.index
        groups = sorted({e['group'] for e in entries.values()})
        names = [t('tl.allgroups')] + [
            f"{g}  {idx.groups.get(str(g), '') if idx else ''}".rstrip()
            for g in groups]
        self.group_cb.configure(values=names)
        sel_group = None
        if self.group.get() != t('tl.allgroups'):
            try:
                sel_group = int(self.group.get().split()[0])
            except (ValueError, IndexError):
                sel_group = None
        q = self.q.get().strip().lower()
        own_only = self.own.get()
        order = chain_order(list(entries.values()), edges)
        pos = {qid: i for i, qid in enumerate(order)}
        pool = []                 # everything but the group filter: the tabs
        for qid in order:
            e = entries[qid]
            if own_only and e['kind'] == 'game':
                continue
            if q and q not in (f"q_{qid} {qid} {e['title']} {e['giver']}"
                               .lower()):
                continue
            pool.append(e)
        shown = [e for e in pool
                 if sel_group is None or e['group'] == sel_group]
        # sections: groups ordered by their first quest in chain order
        first = {}
        for e in shown:
            first.setdefault(e['group'], pos[e['qid']])
        sections = sorted(first, key=lambda g: first[g])
        by_group = {}
        for e in shown:
            by_group.setdefault(e['group'], []).append(e)
        w, h = SIZES[self.size]
        x, y = 8, LABEL_H + 4
        cur = self.app.quest.id if self.app.quest else None
        for gi, g in enumerate(sections):
            label = self.group_name(g)
            c.create_text(x, 3, anchor='nw', fill=theme.group_color(g),
                          font=theme.FONT_BOLD,
                          text=t('tl.groupcount', name=label,
                                 n=len(by_group[g])))
            for e in by_group[g]:
                self._card(e, x, y, w, h, e['qid'] == cur)
                self.cards[e['qid']] = (x, y, x + w, y + h)
                x += w + GAP
            if gi < len(sections) - 1:
                sx = x + SECTION_GAP / 2 - GAP / 2
                c.create_line(sx, 2, sx, y + h + 2, fill=theme.LINE)
                x += SECTION_GAP
        tab_first, tab_counts = {}, {}
        for e in pool:
            tab_first.setdefault(e['group'], pos[e['qid']])
            tab_counts[e['group']] = tab_counts.get(e['group'], 0) + 1
        self._draw_tabs(tab_counts,
                        sorted(tab_first, key=lambda g: tab_first[g]),
                        len(pool))
        bx = x + 4
        c.create_rectangle(bx, y, bx + 120, y + h, outline=theme.GOLD,
                           dash=(4, 3), tags=('newcard',))
        c.create_text(bx + 60, y + h / 2, text='+ ' + t('quest.new'),
                      fill=theme.GOLD, font=theme.FONT, tags=('newcard',))
        if self.links.get():
            for a, b in set(edges):
                if a in self.cards and b in self.cards:
                    x1, y1, x2, y2 = self.cards[a]
                    u1, v1, u2, v2 = self.cards[b]
                    sx, tx = (x1 + x2) / 2, (u1 + u2) / 2
                    top = y1 - 2
                    c.create_line(sx, top, (sx + tx) / 2,
                                  top - min(14, abs(tx - sx) / 20 + 4), tx,
                                  top, smooth=True, fill=theme.GOLD_HI,
                                  width=1, arrow='last', arrowshape=(5, 6, 2))
        c.configure(scrollregion=(0, 0, bx + 140, y + h + 6))
        self.count.configure(text=t('tl.count', n=len(shown), all=len(entries)))

    def _card(self, e, x, y, w, h, current):
        c = self.canvas
        tag = ('card', f'q:{e["qid"]}')
        kind = e['kind']
        colour = theme.group_color(e['group'])
        # own and changed quests keep their gold frame, the rest gets the
        # colour of its quest line (Marco 2026-09-16)
        outline = {'own': theme.GOLD, 'edited': theme.GOLD}.get(kind, colour)
        dash = (5, 3) if kind == 'edited' else ''
        fill = (theme.mix(colour, theme.SEL, 0.35) if current
                else theme.mix(colour, theme.FIELD, 0.12))
        c.create_rectangle(x, y, x + w, y + h, fill=fill, outline=outline,
                           width=2 if current or kind != 'game' else 1,
                           dash=dash, tags=tag)
        c.create_rectangle(x, y, x + 5, y + h, fill=colour, outline='',
                           tags=tag)
        font_b, font_s = theme.FONT_BOLD, theme.FONT_SMALL
        title = e['title'] or '-'
        c.create_text(x + 10, y + 4, anchor='nw', text=f"Q_{e['qid']}",
                      fill=colour, font=font_s, tags=tag)
        if e['source'] not in ('retail', 'project'):
            c.create_text(x + w - 5, y + 4, anchor='ne', text=e['source'][:12],
                          fill=theme.MUT, font=font_s, tags=tag)
        small = self.size == 'small'
        # small cards are 42 px high: one line only, clipped, never wrapped
        c.create_text(x + 10, y + 20, anchor='nw',
                      width=0 if small else w - 16,
                      text=_clip(title, 22 if small else 34),
                      fill=theme.INK,
                      font=theme.FONT if small else font_b, tags=tag)
        if self.size == 'large':
            rows = [e['giver'], e['fc'], t('tl.lines', n=e['lines'])]
            for i, r in enumerate(rows):
                c.create_text(x + 10, y + 42 + i * 16, anchor='nw',
                              text=_clip(r, 34), fill=theme.MUT, font=font_s,
                              tags=tag)

    def group_name(self, g):
        idx = self.app.index
        name = idx.groups.get(str(g), '') if idx else ''
        return name or t('tl.nogroup', g=g)

    def _draw_tabs(self, counts, sections, total):
        """One tab per quest line (journal group) plus "all", left of the
        cards and in the same order as the sections below."""
        c = self.tabs
        c.delete('all')
        self.tab_hits = []
        sel = self.selected_group()
        x = 8
        tabs = [(None, t('tl.alltab'), total)]
        for g in sections:
            tabs.append((g, self.group_name(g), counts.get(g, 0)))
        for g, name, n in tabs:
            text = f'{name}  {n}'
            active = (g == sel)
            gcol = theme.GOLD if g is None else theme.group_color(g)
            colour = gcol if active else theme.mix(gcol, theme.MUT, 0.55)
            item = c.create_text(x + 10, TAB_H / 2, anchor='w', text=text,
                                 fill=colour,
                                 font=theme.FONT_BOLD if active
                                 else theme.FONT_SMALL)
            x1, _y1, x2, _y2 = c.bbox(item)
            if active:
                c.create_line(x, TAB_H - 2, x2 + 10, TAB_H - 2,
                              fill=gcol, width=2)
            self.tab_hits.append((x, x2 + 10, g))
            x = x2 + 22
        c.configure(scrollregion=(0, 0, x, TAB_H))

    def selected_group(self):
        if self.group.get() == t('tl.allgroups'):
            return None
        try:
            return int(self.group.get().split()[0])
        except (ValueError, IndexError):
            return None

    def _tab_click(self, ev):
        x = self.tabs.canvasx(ev.x)
        for x1, x2, g in self.tab_hits:
            if x1 <= x <= x2:
                if g is None:
                    self.group.set(t('tl.allgroups'))
                else:
                    idx = self.app.index
                    name = idx.groups.get(str(g), '') if idx else ''
                    self.group.set(f'{g}  {name}'.rstrip())
                self.refresh()
                return

    # -- interaction ---------------------------------------------------------------

    def _qid_at(self, ev):
        x, y = self.canvas.canvasx(ev.x), self.canvas.canvasy(ev.y)
        for item in reversed(self.canvas.find_overlapping(x, y, x, y)):
            for tg in self.canvas.gettags(item):
                if tg.startswith('q:'):
                    return int(tg[2:])
                if tg == 'newcard':
                    return 'new'
        return None

    def _click(self, ev):
        qid = self._qid_at(ev)
        if qid == 'new':
            self.app.new_quest()
        elif qid is not None:
            self.app.open_any_quest(qid)

    def _hover(self, ev):
        qid = self._qid_at(ev)
        e = self.entries.get(qid) if isinstance(qid, int) else None
        if e:
            src = {'retail': t('tl.src.game'), 'project': t('tl.src.project')
                   }.get(e['source'], e['source'])
            self.app.set_hint(f"Q_{qid}  {e['title']}  |  {e['giver']}  |  "
                              f"{e['fc']}  |  {src}")
        else:
            self.app.set_hint('')

    def _context(self, ev):
        qid = self._qid_at(ev)
        if not isinstance(qid, int):
            return
        e = self.entries[qid]
        app = self.app
        pq = app.project.quest_by_id(qid) if app.project else None
        menu = theme.Menu(self, tearoff=0)
        menu.add_command(label=t('tl.open'),
                         command=lambda: app.open_any_quest(qid))
        menu.add_command(label=t('tl.dup'),
                         command=lambda: app.duplicate_any_quest(qid))
        menu.add_command(label=t('tl.delete'),
                         command=lambda: app.delete_quest(pq),
                         state='normal' if pq else 'disabled')
        menu.add_command(label=t('tl.exportone'),
                         command=lambda: app.export_ui(quests=[pq]),
                         state='normal' if pq else 'disabled')
        menu.add_command(label=t('tl.text'),
                         command=lambda: app.show_preview(app.quest_for(qid)))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def show_current(self):
        cur = self.app.quest.id if self.app.quest else None
        if cur in self.cards:
            x1, _, x2, _ = self.cards[cur]
            region = self.canvas.bbox('all')
            if region and region[2] > 0:
                width = self.canvas.winfo_width()
                self.canvas.xview_moveto(max(0, (x1 - width / 3)) / region[2])


def _clip(text, n):
    text = (text or '').replace('\n', ' ')
    return text if len(text) <= n else text[:n - 1] + '…'
