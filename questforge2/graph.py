"""The node graph canvas (plan section 5.3 and 2.2).

Tag based drawing: every node is a group of items tagged ``n:<id>``, every
edge is one line tagged ``e:<from>:<port>``. Dragging moves only the node
group and its edges; nothing is deleted and redrawn per frame. Zoom is in
fixed steps with fonts precomputed per step. World coordinates (the model)
map to canvas coordinates by multiplying with the zoom factor; panning is
the canvas' own scan/scroll.
"""

import time
import tkinter as tk
import tkinter.font as tkfont

from . import model, theme
from .i18n import t

ZOOM_STEPS = (0.5, 0.75, 1.0, 1.25, 1.5)
DEFAULT_ZOOM = 2
GRID = 40
WORLD = (-1000, -1000, 6000, 4000)
PORT_R = 5
CORNER = 18
END_CAP_W = 30


class GraphView(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, bg=theme.CANVAS_BG, highlightthickness=0,
                         **kw)
        self.tab = None
        self.zoom_i = DEFAULT_ZOOM
        self.show_grid = True
        self.edge_style = 'curve'
        self.selected = set()
        self.selected_edge = None          # (from, port)
        # callbacks set by the app
        self.before_change = lambda label: None
        self.after_change = lambda: None
        self.on_select = lambda: None
        self.on_edge_drop_empty = lambda frm, port, wx, wy: None
        self.on_open_node = lambda nid: None
        self.on_context = None             # (menu, kind, nid) -> None
        self.last_frame_ms = 0.0
        self._drag = None
        self._space = False
        self._fonts = {}
        self._body = {}
        self._edge_items = {}          # (from, port) -> canvas item
        self.configure(scrollregion=self._scrollregion())
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<B1-Motion>', self._motion)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Double-Button-1>', self._double)
        self.bind('<ButtonPress-2>', self._pan_start)
        self.bind('<B2-Motion>', self._pan_move)
        self.bind('<ButtonPress-3>', self._context)
        self.bind('<MouseWheel>', self._wheel)
        self.bind('<Shift-MouseWheel>', self._wheel_h)
        self.bind('<Control-MouseWheel>', self._wheel_zoom)
        self.bind('<KeyPress-space>', lambda e: self._set_space(True))
        self.bind('<KeyRelease-space>', lambda e: self._set_space(False))
        self.bind('<Delete>', lambda e: self.delete_selection())
        self.bind('<Control-a>', lambda e: self.select_all())
        self.bind('<KeyPress-f>', lambda e: self.fit())
        self.bind('<Configure>', lambda e: self._draw_grid())

    # -- coordinates --------------------------------------------------------

    @property
    def zoom(self):
        return ZOOM_STEPS[self.zoom_i]

    def w2c(self, x, y):
        z = self.zoom
        return x * z, y * z

    def c2w(self, cx, cy):
        z = self.zoom
        return cx / z, cy / z

    def event_world(self, ev):
        return self.c2w(self.canvasx(ev.x), self.canvasy(ev.y))

    def _scrollregion(self):
        z = self.zoom
        return tuple(v * z for v in WORLD)

    def _font(self, kind):
        key = (kind, self.zoom_i)
        f = self._fonts.get(key)
        if f is None:
            base = {'title': theme.FONT_BOLD, 'line': theme.FONT,
                    'small': theme.FONT_SMALL}[kind]
            size = max(6, int(round(base[1] * self.zoom)))
            f = tkfont.Font(family=base[0], size=size,
                            weight='bold' if len(base) > 2 else 'normal')
            self._fonts[key] = f
        return f

    def _fit_text(self, text, font, width):
        text = (text or '').replace('\n', ' ')
        if font.measure(text) <= width:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.measure(text[:mid] + '…') <= width:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo] + '…'

    # -- public API ---------------------------------------------------------

    def set_graph(self, tab):
        self.tab = tab
        self.selected = {i for i in self.selected if tab and i in tab['nodes']}
        self.selected_edge = None
        self._drag = None
        self.redraw()

    def redraw(self):
        self.delete('all')
        self._body.clear()
        self._edge_items.clear()
        self.configure(scrollregion=self._scrollregion())
        self._draw_grid()
        if not self.tab:
            return
        for nid in self.tab['nodes']:
            self.draw_node(nid)
        for frm, port, to in self.tab['edges']:
            self.draw_edge(frm, port, to)
        self._apply_selection()

    def set_zoom(self, i, anchor=None):
        i = max(0, min(len(ZOOM_STEPS) - 1, i))
        if i == self.zoom_i:
            return
        if anchor is None:
            anchor = (self.winfo_width() / 2, self.winfo_height() / 2)
        wx, wy = self.c2w(self.canvasx(anchor[0]), self.canvasy(anchor[1]))
        self.zoom_i = i
        self.redraw()
        self._scroll_world_to(wx, wy, anchor)

    def zoom_in(self):
        self.set_zoom(self.zoom_i + 1)

    def zoom_out(self):
        self.set_zoom(self.zoom_i - 1)

    def zoom_reset(self):
        self.set_zoom(DEFAULT_ZOOM)

    def _scroll_world_to(self, wx, wy, screen):
        """Scroll so world point (wx, wy) sits at screen offset (sx, sy)."""
        sr = self._scrollregion()
        cx, cy = self.w2c(wx, wy)
        w, h = sr[2] - sr[0], sr[3] - sr[1]
        self.xview_moveto((cx - screen[0] - sr[0]) / w)
        self.yview_moveto((cy - screen[1] - sr[1]) / h)

    def fit(self):
        if not self.tab or not self.tab['nodes']:
            return
        x1, y1, x2, y2 = self.content_bbox()
        vw, vh = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
        best = 0
        for i, z in enumerate(ZOOM_STEPS):
            if (x2 - x1 + 80) * z <= vw and (y2 - y1 + 80) * z <= vh:
                best = i
        if best != self.zoom_i:
            self.zoom_i = best
            self.redraw()
        self._scroll_world_to((x1 + x2) / 2, (y1 + y2) / 2, (vw / 2, vh / 2))

    def content_bbox(self):
        xs, ys, xe, ye = [], [], [], []
        for n in self.tab['nodes'].values():
            w, h = model.node_size(n)
            xs.append(n['x']); ys.append(n['y'])
            xe.append(n['x'] + w); ye.append(n['y'] + h)
        return min(xs), min(ys), max(xe), max(ye)

    def set_grid(self, on):
        self.show_grid = on
        self._draw_grid()

    def set_edge_style(self, style):
        self.edge_style = style
        if self.tab:
            for frm, port, to in self.tab['edges']:
                self.draw_edge(frm, port, to)

    def select(self, ids, edge=None):
        self.selected = set(ids)
        self.selected_edge = edge
        self._apply_selection()
        self.on_select()

    def select_all(self):
        if self.tab:
            self.select([i for i in self.tab['nodes'] if i != model.ENTRY_ID])

    def delete_selection(self):
        if not self.tab:
            return
        if self.selected_edge and not self.selected:
            frm, port = self.selected_edge
            self.before_change('disconnect')
            model.disconnect(self.tab, frm, port)
            self._delete_edge(frm, port)
            self.draw_node(frm)
            self.selected_edge = None
            self.after_change()
            return
        ids = {i for i in self.selected if i != model.ENTRY_ID}
        if not ids:
            return
        self.before_change('delete')
        touched = {e[0] for e in self.tab['edges'] if e[2] in ids}
        gone = [e for e in self.tab['edges'] if e[0] in ids or e[2] in ids]
        model.remove_nodes(self.tab, ids)
        for i in ids:
            self.delete(f'n:{i}')
            self._body.pop(i, None)
        for frm, port, to in gone:
            self._delete_edge(frm, port)
        for i in touched - ids:
            self.draw_node(i)
        self.selected = set()
        self.after_change()
        self.on_select()

    def add_node_at(self, ntype, wx, wy, title=''):
        self.before_change('add')
        node = model.make_node(ntype, int(wx), int(wy), title)
        nid = model.add_node(self.tab, node)
        self.draw_node(nid)
        self.after_change()
        self.select([nid])
        return nid

    def redraw_node(self, nid):
        """Public: node data changed (text, colour, size, lines)."""
        self.draw_node(nid)
        for e in self.tab['edges']:
            if e[0] == nid or e[2] == nid:
                self.draw_edge(*e)
        self._apply_selection()

    # -- drawing ------------------------------------------------------------

    def _draw_grid(self):
        self.delete('grid')
        if not self.show_grid:
            return
        z = self.zoom
        step = GRID * z
        x0, y0, x1, y1 = self._scrollregion()
        x = x0
        while x <= x1:
            self.create_line(x, y0, x, y1, fill=theme.GRID, tags='grid')
            x += step
        y = y0
        while y <= y1:
            self.create_line(x0, y, x1, y, fill=theme.GRID, tags='grid')
            y += step
        self.create_line(x0, 0, x1, 0, fill=theme.LINE, tags='grid')
        self.create_line(0, y0, 0, y1, fill=theme.LINE, tags='grid')
        self.tag_lower('grid')

    @staticmethod
    def _rr(x1, y1, x2, y2, r, corners=(True, True, True, True)):
        """Points for a smooth polygon with optionally rounded corners."""
        tl, tr, br, bl = corners
        pts = []

        def corner(cx, cy, ax, ay, bx, by, rounded):
            if rounded:
                pts.extend([ax, ay, cx, cy, bx, by])
            else:
                pts.extend([cx, cy, cx, cy, cx, cy])
        corner(x1, y1, x1, y1 + r, x1 + r, y1, tl)
        corner(x2, y1, x2 - r, y1, x2, y1 + r, tr)
        corner(x2, y2, x2, y2 - r, x2 - r, y2, br)
        corner(x1, y2, x1 + r, y2, x1, y2 - r, bl)
        return pts

    def draw_node(self, nid):
        self.delete(f'n:{nid}')
        node = self.tab['nodes'].get(nid)
        if not node:
            return
        z = self.zoom
        w, h = model.node_size(node)
        x1, y1 = self.w2c(node['x'], node['y'])
        x2, y2 = self.w2c(node['x'] + w, node['y'] + h)
        tags = ('node', f'n:{nid}')
        kind = node['type']
        if kind == 'comment':
            color = node.get('color') or theme.COMMENT_COLOR
            body = self.create_rectangle(
                x1, y1, x2, y2, fill=color, stipple='gray50',
                outline=theme.LINE, tags=tags + ('body',))
            text = node.get('text') or t('node.comment')
            self.create_text(x1 + 6 * z, y1 + 4 * z, text=text, anchor='nw',
                             fill=theme.INK, font=self._font('line'),
                             width=(w - 12) * z, tags=tags + ('body',))
            g = 10 * z
            self.create_polygon(x2, y2 - g, x2, y2, x2 - g, y2,
                                fill=theme.MUT, outline='',
                                tags=tags + ('grip',))
        elif kind == 'entry':
            body = self.create_polygon(
                self._rr(x1, y1, x2, y2, h * z / 2), smooth=True,
                fill='#1d3a26', outline=theme.ENTRY_COLOR, width=1.5,
                tags=tags + ('body',))
            self.create_text((x1 + x2) / 2, (y1 + y2) / 2,
                             text=t('node.entry'), fill=theme.ENTRY_COLOR,
                             font=self._font('title'), tags=tags + ('body',))
            self._draw_out_port(nid, 0, tags)
            self._draw_port(x1 + (x2 - x1) / 2, y2, 'cond', nid, tags)
        else:
            color = node.get('color') or theme.SPEAKER_COLORS[0]
            body = self.create_polygon(
                self._rr(x1, y1, x2, y2, CORNER * z), smooth=True,
                fill=theme.FIELD, outline=theme.LINE, width=1,
                tags=tags + ('body',))
            hy = y1 + model.HEADER_H * z
            self.create_polygon(
                self._rr(x1, y1, x2, hy, CORNER * z,
                         (True, True, False, False)), smooth=True,
                fill=color, outline='', tags=tags + ('body',))
            title = self._fit_text(node.get('title') or t('node.dialog'),
                                   self._font('title'), (w - 30) * z)
            self.create_text(x1 + 12 * z, (y1 + hy) / 2, text=title,
                             anchor='w', fill='#17130b',
                             font=self._font('title'), tags=tags + ('body',))
            self._draw_port(x1, (y1 + hy) / 2, 'in', nid, tags)
            self._draw_port((x1 + x2) / 2, y1, 'act', nid, tags)
            self._draw_port((x1 + x2) / 2, y2, 'cond', nid, tags)
            lines = node.get('lines') or [{'text': ''}]
            font = self._font('line')
            for i, line in enumerate(lines):
                ly = hy + (model.NODE_PAD / 2 + i * model.LINE_H
                           + model.LINE_H / 2) * z
                text = self._fit_text(line.get('text') or '…', font,
                                      (w - 30) * z)
                self.create_text(x1 + 12 * z, ly, text=text, anchor='w',
                                 fill=theme.INK if line.get('text')
                                 else theme.MUT, font=font,
                                 tags=tags + ('body',))
                self._draw_out_port(nid, i, tags)
        self._body[nid] = body
        if nid in self.selected:
            self._outline(nid, True)

    def _draw_port(self, cx, cy, role, nid, tags):
        r = PORT_R * self.zoom
        fill = {'in': theme.INK, 'act': theme.GOLD, 'cond': '#9a8fe0'}[role]
        if role == 'in':
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill,
                             outline=theme.BG, tags=tags + (f'port:{role}',))
        else:
            self.create_rectangle(cx - r, cy - r, cx + r, cy + r, fill=fill,
                                  outline=theme.BG,
                                  tags=tags + (f'port:{role}',))

    def _draw_out_port(self, nid, port, tags):
        z = self.zoom
        wx, wy = self.out_pos(nid, port)
        cx, cy = self.w2c(wx, wy)
        r = PORT_R * z
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=theme.INK,
                         outline=theme.BG, tags=tags + (f'port:out:{port}',))
        if model.edge_from(self.tab, nid, port) is None:
            # open end: small grey "end" cap so the user sees where the
            # conversation runs out (plan 5.2, no end node)
            cw, ch = END_CAP_W * z, 14 * z
            self.create_polygon(
                self._rr(cx + r + 2, cy - ch / 2, cx + r + 2 + cw,
                         cy + ch / 2, ch / 2), smooth=True, fill=theme.LINE,
                outline='', tags=tags + ('cap',))
            self.create_text(cx + r + 2 + cw / 2, cy, text=t('node.end'),
                             fill=theme.MUT, font=self._font('small'),
                             tags=tags + ('cap',))

    def out_pos(self, nid, port):
        node = self.tab['nodes'][nid]
        w, h = model.node_size(node)
        if node['type'] == 'entry':
            return node['x'] + w, node['y'] + h / 2
        return (node['x'] + w, node['y'] + model.HEADER_H + model.NODE_PAD / 2
                + port * model.LINE_H + model.LINE_H / 2)

    def in_pos(self, nid):
        node = self.tab['nodes'][nid]
        return node['x'], node['y'] + model.HEADER_H / 2

    def _edge_points(self, frm, port, to):
        x1, y1 = self.w2c(*self.out_pos(frm, port))
        x2, y2 = self.w2c(*self.in_pos(to))
        if self.edge_style == 'curve':
            d = max(40 * self.zoom, abs(x2 - x1) / 2)
            return [x1, y1, x1 + d, y1, x2 - d, y2, x2, y2]
        return [x1, y1, x2, y2]

    def _delete_edge(self, frm, port):
        item = self._edge_items.pop((frm, port), None)
        if item:
            self.delete(item)

    def draw_edge(self, frm, port, to):
        self._delete_edge(frm, port)
        if frm not in self.tab['nodes'] or to not in self.tab['nodes']:
            return
        pts = self._edge_points(frm, port, to)
        sel = self.selected_edge == (frm, port)
        z = self.zoom
        kw = dict(fill=theme.GOLD if sel else theme.MUT,
                  width=(2.5 if sel else 1.5) * z, arrow='last',
                  arrowshape=(10 * z, 12 * z, 4 * z),
                  tags=('edge', f'e:{frm}:{port}'))
        if self.edge_style == 'curve':
            item = self.create_line(*pts, smooth='raw', splinesteps=24, **kw)
        else:
            item = self.create_line(*pts, **kw)
        self._edge_items[(frm, port)] = item
        self.tag_lower(item, 'node')

    def _update_edges_of(self, nid):
        for frm, port, to in self.tab['edges']:
            if frm == nid or to == nid:
                item = self._edge_items.get((frm, port))
                if item:
                    self.coords(item, *self._edge_points(frm, port, to))

    def _outline(self, nid, on):
        body = self._body.get(nid)
        if body:
            node = self.tab['nodes'].get(nid, {})
            if node.get('type') == 'entry':
                self.itemconfigure(body, outline=theme.GOLD if on
                                   else theme.ENTRY_COLOR, width=2 if on else 1.5)
            else:
                self.itemconfigure(body, outline=theme.GOLD if on else theme.LINE,
                                   width=2 if on else 1)

    def _apply_selection(self):
        if not self.tab:
            return
        for nid in self.tab['nodes']:
            self._outline(nid, nid in self.selected)
        for (frm, port), item in self._edge_items.items():
            sel = self.selected_edge == (frm, port)
            self.itemconfigure(item, fill=theme.GOLD if sel else theme.MUT,
                               width=(2.5 if sel else 1.5) * self.zoom)

    # -- hit testing --------------------------------------------------------

    def _hit(self, ev):
        cx, cy = self.canvasx(ev.x), self.canvasy(ev.y)
        items = self.find_overlapping(cx - 3, cy - 3, cx + 3, cy + 3)
        best = None
        for item in reversed(items):
            tags = self.gettags(item)
            if 'grid' in tags:
                continue
            role = None
            nid = None
            edge = None
            for tg in tags:
                if tg.startswith('n:'):
                    nid = tg[2:]
                elif tg.startswith('port:') or tg in ('grip', 'body', 'cap'):
                    role = tg
                elif tg.startswith('e:'):
                    _, frm, port = tg.split(':')
                    edge = (frm, int(port))
            hit = {'nid': nid, 'role': role, 'edge': edge}
            # ports win over bodies, nodes win over edges
            if role and role.startswith('port:'):
                return hit
            if best is None or (best['nid'] is None and nid):
                best = hit
        return best or {'nid': None, 'role': None, 'edge': None}

    # -- mouse --------------------------------------------------------------

    def _set_space(self, on):
        self._space = on
        self.configure(cursor='fleur' if on else '')

    def _press(self, ev):
        self.focus_set()
        if not self.tab:
            return
        if self._space:
            self.scan_mark(ev.x, ev.y)
            self._drag = {'kind': 'pan'}
            return
        hit = self._hit(ev)
        wx, wy = self.event_world(ev)
        ctrl = bool(ev.state & 0x4)
        nid, role = hit['nid'], hit['role']
        if nid and role and role.startswith('port:out:'):
            port = int(role.split(':')[2])
            self._drag = {'kind': 'edge', 'frm': nid, 'port': port,
                          'line': None}
            return
        if nid and role == 'grip':
            node = self.tab['nodes'][nid]
            self._drag = {'kind': 'resize', 'nid': nid, 'wx': wx, 'wy': wy,
                          'w': node['w'], 'h': node['h'], 'pushed': False}
            return
        if nid:
            if ctrl:
                if nid in self.selected:
                    self.selected.discard(nid)
                else:
                    self.selected.add(nid)
            elif nid not in self.selected:
                self.selected = {nid}
            self.selected_edge = None
            self._apply_selection()
            self.on_select()
            self._drag = self._begin_move(wx, wy)
            return
        if hit['edge']:
            self.selected = set()
            self.selected_edge = hit['edge']
            self._apply_selection()
            self.on_select()
            self._drag = None
            return
        if not ctrl:
            self.selected = set()
            self.selected_edge = None
            self._apply_selection()
            self.on_select()
        self._drag = {'kind': 'band', 'x': self.canvasx(ev.x),
                      'y': self.canvasy(ev.y), 'rect': None, 'add': ctrl}

    def _movable(self, ids):
        """Selected nodes plus comments attached to them, minus the entry."""
        out = {i for i in ids if i != model.ENTRY_ID}
        for nid, n in self.tab['nodes'].items():
            if n.get('attached_to') in out:
                out.add(nid)
        return out

    def _begin_move(self, wx, wy):
        """Tag everything that moves once, so each frame is one ``move``
        call for the nodes, one for the inner edges and a coords update
        only for edges that cross the selection border."""
        ids = self._movable(self.selected)
        self.dtag('all', 'sel')
        self.dtag('all', 'seledge')
        for nid in ids:
            self.addtag_withtag('sel', f'n:{nid}')
        border = []
        for frm, port, to in self.tab['edges']:
            a, b = frm in ids, to in ids
            item = self._edge_items.get((frm, port))
            if not item:
                continue
            if a and b:
                self.addtag_withtag('seledge', item)
            elif a or b:
                border.append((item, frm, port, to))
        return {'kind': 'move', 'wx': wx, 'wy': wy, 'moved': False,
                'ids': ids, 'border': border}

    def _motion(self, ev):
        d = self._drag
        if not d:
            return
        t0 = time.perf_counter()
        if d['kind'] == 'pan':
            self.scan_dragto(ev.x, ev.y, gain=1)
            return
        wx, wy = self.event_world(ev)
        if d['kind'] == 'move':
            if not d['ids']:
                return
            # snap to whole world units: the model keeps ints and nothing
            # has to be redrawn when the drag ends
            dx, dy = int(round(wx - d['wx'])), int(round(wy - d['wy']))
            if not dx and not dy:
                return
            if not d['moved']:
                self.before_change('move')
                d['moved'] = True
            d['wx'] += dx
            d['wy'] += dy
            z = self.zoom
            for nid in d['ids']:
                n = self.tab['nodes'][nid]
                n['x'] += dx
                n['y'] += dy
            self.move('sel', dx * z, dy * z)
            self.move('seledge', dx * z, dy * z)
            for item, frm, port, to in d['border']:
                self.coords(item, *self._edge_points(frm, port, to))
        elif d['kind'] == 'edge':
            x1, y1 = self.w2c(*self.out_pos(d['frm'], d['port']))
            x2, y2 = self.canvasx(ev.x), self.canvasy(ev.y)
            if d['line'] is None:
                d['line'] = self.create_line(x1, y1, x2, y2, fill=theme.GOLD,
                                             width=1.5 * self.zoom, dash=(6, 4),
                                             tags='temp')
            else:
                self.coords(d['line'], x1, y1, x2, y2)
        elif d['kind'] == 'resize':
            if not d['pushed']:
                self.before_change('resize')
                d['pushed'] = True
            n = self.tab['nodes'][d['nid']]
            n['w'] = int(max(model.COMMENT_MIN_W, d['w'] + wx - d['wx']))
            n['h'] = int(max(model.COMMENT_MIN_H, d['h'] + wy - d['wy']))
            self.draw_node(d['nid'])
        elif d['kind'] == 'band':
            cx, cy = self.canvasx(ev.x), self.canvasy(ev.y)
            if d['rect'] is None:
                d['rect'] = self.create_rectangle(d['x'], d['y'], cx, cy,
                                                  outline=theme.GOLD,
                                                  dash=(4, 3), tags='temp')
            else:
                self.coords(d['rect'], d['x'], d['y'], cx, cy)
        self.last_frame_ms = (time.perf_counter() - t0) * 1000

    def _release(self, ev):
        d = self._drag
        self._drag = None
        if not d or not self.tab:
            return
        if d['kind'] == 'move':
            self.dtag('all', 'sel')
            self.dtag('all', 'seledge')
            if d['moved']:
                self.after_change()
        elif d['kind'] == 'edge':
            self.delete('temp')
            hit = self._hit(ev)
            wx, wy = self.event_world(ev)
            to = hit['nid']
            if to and to != d['frm'] and model.can_connect(
                    self.tab, d['frm'], d['port'], to):
                self.before_change('connect')
                model.connect(self.tab, d['frm'], d['port'], to)
                self.draw_node(d['frm'])
                self.draw_edge(d['frm'], d['port'], to)
                self.after_change()
            elif not to and not hit['edge']:
                self.on_edge_drop_empty(d['frm'], d['port'], wx, wy)
        elif d['kind'] == 'resize':
            if d['pushed']:
                self.after_change()
        elif d['kind'] == 'band':
            self.delete('temp')
            if d['rect'] is not None:
                x1, y1 = self.c2w(min(d['x'], self.canvasx(ev.x)),
                                  min(d['y'], self.canvasy(ev.y)))
                x2, y2 = self.c2w(max(d['x'], self.canvasx(ev.x)),
                                  max(d['y'], self.canvasy(ev.y)))
                hits = set()
                for nid, n in self.tab['nodes'].items():
                    w, h = model.node_size(n)
                    if (n['x'] < x2 and n['x'] + w > x1 and n['y'] < y2
                            and n['y'] + h > y1):
                        hits.add(nid)
                self.selected = (self.selected | hits) if d['add'] else hits
                self._apply_selection()
                self.on_select()

    def _double(self, ev):
        hit = self._hit(ev)
        if hit['nid']:
            self.on_open_node(hit['nid'])

    def _pan_start(self, ev):
        self.scan_mark(ev.x, ev.y)

    def _pan_move(self, ev):
        self.scan_dragto(ev.x, ev.y, gain=1)

    def _wheel(self, ev):
        self.yview_scroll(-1 if ev.delta > 0 else 1, 'units')

    def _wheel_h(self, ev):
        self.xview_scroll(-1 if ev.delta > 0 else 1, 'units')

    def _wheel_zoom(self, ev):
        self.set_zoom(self.zoom_i + (1 if ev.delta > 0 else -1), (ev.x, ev.y))

    # -- context menu -------------------------------------------------------

    def _context(self, ev):
        if not self.tab:
            return
        self.focus_set()
        hit = self._hit(ev)
        wx, wy = self.event_world(ev)
        menu = tk.Menu(self, tearoff=0)
        nid = hit['nid']
        if nid:
            if nid not in self.selected:
                self.select([nid])
            node = self.tab['nodes'][nid]
            if node['type'] != 'entry':
                menu.add_command(label=t('edit.duplicate'),
                                 command=self.duplicate_selection)
                menu.add_command(label=t('edit.delete'),
                                 command=self.delete_selection)
            if node['type'] == 'comment':
                if node.get('attached_to'):
                    menu.add_command(label=t('ctx.detach'),
                                     command=lambda: self._attach(nid, None))
                else:
                    sub = tk.Menu(menu, tearoff=0)
                    for oid, o in self.tab['nodes'].items():
                        if o['type'] == 'node':
                            label = o.get('title') or oid
                            sub.add_command(
                                label=f'{label}  ({oid})',
                                command=lambda o=oid: self._attach(nid, o))
                    menu.add_cascade(label=t('ctx.attach'), menu=sub)
                col = tk.Menu(menu, tearoff=0)
                for c in [theme.COMMENT_COLOR] + theme.SPEAKER_COLORS:
                    col.add_command(label='■', foreground=c,
                                    command=lambda c=c: self._set_color(nid, c))
                menu.add_cascade(label=t('ctx.color'), menu=col)
            else:
                menu.add_command(label=t('ctx.disconnect'),
                                 command=lambda: self._disconnect_node(nid))
                if node['type'] == 'node':
                    menu.add_command(label=t('ctx.attach_comment'),
                                     command=lambda: self._new_comment_for(nid))
            if self.on_context:
                self.on_context(menu, 'node', nid)
        elif hit['edge']:
            self.selected_edge = hit['edge']
            self.selected = set()
            self._apply_selection()
            menu.add_command(label=t('ctx.cut_edge'),
                             command=self.delete_selection)
        else:
            add = tk.Menu(menu, tearoff=0)
            add.add_command(label=t('node.dialog'),
                            command=lambda: self.add_node_at('node', wx, wy))
            add.add_command(label=t('node.comment'),
                            command=lambda: self.add_node_at('comment', wx, wy))
            menu.add_cascade(label=t('ctx.add'), menu=add)
            if self.on_context:
                self.on_context(menu, 'empty', None)
            menu.add_separator()
            menu.add_command(label=t('edit.autolayout'),
                             command=self.auto_layout)
            menu.add_command(label=t('view.fit'), command=self.fit)
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _attach(self, cid, target):
        self.before_change('attach')
        self.tab['nodes'][cid]['attached_to'] = target
        self.after_change()

    def _set_color(self, nid, color):
        self.before_change('color')
        self.tab['nodes'][nid]['color'] = color
        self.redraw_node(nid)
        self.after_change()

    def _disconnect_node(self, nid):
        self.before_change('disconnect')
        touched = {e[0] for e in self.tab['edges'] if e[2] == nid} | {nid}
        gone = [e for e in self.tab['edges'] if e[0] == nid or e[2] == nid]
        model.disconnect_node(self.tab, nid)
        for frm, port, to in gone:
            self._delete_edge(frm, port)
        for i in touched:
            self.draw_node(i)
        self.after_change()

    def _new_comment_for(self, nid):
        n = self.tab['nodes'][nid]
        w, h = model.node_size(n)
        cid = self.add_node_at('comment', n['x'], n['y'] + h + 12)
        self.tab['nodes'][cid]['attached_to'] = nid

    def duplicate_selection(self):
        ids = {i for i in self.selected if i != model.ENTRY_ID}
        if not ids:
            return
        self.before_change('duplicate')
        new = model.duplicate_nodes(self.tab, ids)
        for nid in new:
            self.draw_node(nid)
        for e in self.tab['edges']:
            if e[0] in new:
                self.draw_edge(*e)
        self.after_change()
        self.select(new)

    def paste(self, clip):
        if not self.tab or not clip or not clip['nodes']:
            return
        self.before_change('paste')
        new = model.paste_nodes(self.tab, clip)
        for nid in new:
            self.draw_node(nid)
        for e in self.tab['edges']:
            if e[0] in new:
                self.draw_edge(*e)
        self.after_change()
        self.select(new)

    def auto_layout(self):
        if not self.tab:
            return
        self.before_change('layout')
        model.auto_layout(self.tab)
        self.redraw()
        self.after_change()
        self.fit()
