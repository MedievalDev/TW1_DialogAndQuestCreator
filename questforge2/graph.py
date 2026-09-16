"""The node graph canvas (plan sections 5, 12.12 and 12.18).

Tag based drawing: every node is a group of items tagged ``n:<id>``, every
edge is one line tagged ``e:<from>:<port>``. Dragging moves one 'sel' tag
per frame; edges are updated through an item table. Zoom is in fixed steps
(mouse wheel) with fonts precomputed per step. Dialog lines wrap; a node
grows downwards with its text. The scroll region always covers every node. World coordinates (the model) map to
canvas coordinates by multiplying with the zoom factor; panning is the
canvas' own scan/scroll.

One graph per quest: nodes carry a level (``state``); ``set_filter`` dims
the nodes of other levels (neutral ones stay visible).
"""

import time
import tkinter as tk
import tkinter.font as tkfont

from . import model, theme
from .i18n import t

ZOOM_STEPS = (0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0)
DEFAULT_ZOOM = ZOOM_STEPS.index(1.0)
GRID = 40
WORLD = (-1000, -1000, 6000, 4000)
REGION_MARGIN = 800            # free space around the outermost nodes
PORT_R = 5
CORNER = 18
END_CAP_W = 30
EVENT_GLYPHS = (('take', '✔', theme.GOLD), ('close', '◆', theme.OK),
                ('fight', '⚔', theme.ERR))


class GraphView(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, bg=theme.CANVAS_BG, highlightthickness=0,
                         **kw)
        self.graph = None
        self.zoom_i = DEFAULT_ZOOM
        self.show_grid = True
        self.edge_style = 'curve'
        self.filter_state = None
        self.selected = set()
        self.selected_edge = None          # (from, port)
        # callbacks set by the app
        self.before_change = lambda label: None
        self.after_change = lambda: None
        self.on_select = lambda: None
        self.on_edge_drop_empty = lambda frm, port, wx, wy, ev: None
        self.on_open_node = lambda nid: None
        self.fill_add_menu = None          # (menu, wx, wy) -> None
        self.node_style = lambda node: ('', theme.SPEAKER_COLORS[0])
        # (title, summary, problem) of an action / condition / task node
        self.docked_text = lambda node: ('', '', False)
        self.fill_docked_menu = None       # (menu, kind, nid) -> None
        self.get_clipboard = None          # () -> clipboard payload or None
        self.last_frame_ms = 0.0
        self._drag = None
        self._space = False
        self._fonts = {}
        self._body = {}
        self._edge_items = {}          # (from, port) -> canvas item
        self._wheel_acc = 0
        # wrapping is measured with the line font at 100 % zoom
        self._font100 = tkfont.Font(family=theme.FONT[0], size=theme.FONT[1])
        model.set_text_measure(self._font100.measure)
        self.configure(scrollregion=self._scrollregion())
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<B1-Motion>', self._motion)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Double-Button-1>', self._double)
        self.bind('<ButtonPress-2>', self._pan_start)
        self.bind('<B2-Motion>', self._pan_move)
        self.bind('<ButtonPress-3>', self._context)
        self.bind('<MouseWheel>', self._wheel_zoom)
        self.bind('<Shift-MouseWheel>', self._wheel_h)
        self.bind('<Control-MouseWheel>', self._wheel)
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
        """The world area plus every node with a margin, so no dialog can
        lie outside the scrollable area."""
        x0, y0, x1, y1 = WORLD
        if self.graph:
            m = REGION_MARGIN
            for n in self.graph['nodes'].values():
                w, h = model.node_size(n)
                x0 = min(x0, n['x'] - m)
                y0 = min(y0, n['y'] - m)
                x1 = max(x1, n['x'] + w + m)
                y1 = max(y1, n['y'] + h + m)
        z = self.zoom
        return (x0 * z, y0 * z, x1 * z, y1 * z)

    def _update_region(self):
        region = self._scrollregion()
        current = tuple(float(v) for v in self.cget('scrollregion').split())
        if current != tuple(float(v) for v in region):
            self.configure(scrollregion=region)
            self._draw_grid()

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

    def set_graph(self, graph):
        self.graph = graph
        self.selected = {i for i in self.selected
                         if graph and i in graph['nodes']}
        self.selected_edge = None
        self._drag = None
        self.redraw()

    def set_filter(self, state):
        self.filter_state = state
        self.redraw()

    def redraw(self):
        self.delete('all')
        self._body.clear()
        self._edge_items.clear()
        self.configure(scrollregion=self._scrollregion())
        self._draw_grid()
        if not self.graph:
            return
        for nid in self.graph['nodes']:
            self.draw_node(nid)
        for frm, port, to in self.graph['edges']:
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

    def scroll_to_node(self, nid, margin=60):
        n = self.graph['nodes'].get(nid) if self.graph else None
        if n:
            self._scroll_world_to(n['x'] - margin, n['y'] - margin, (0, 0))

    def fit(self):
        if not self.graph or not self.graph['nodes']:
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
        for n in self.graph['nodes'].values():
            if self._dimmed(n):
                continue
            w, h = model.node_size(n)
            xs.append(n['x']); ys.append(n['y'])
            xe.append(n['x'] + w); ye.append(n['y'] + h)
        if not xs:
            return 0, 0, 100, 100
        return min(xs), min(ys), max(xe), max(ye)

    def set_grid(self, on):
        self.show_grid = on
        self._draw_grid()

    def set_edge_style(self, style):
        self.edge_style = style
        if self.graph:
            for frm, port, to in self.graph['edges']:
                self.draw_edge(frm, port, to)

    def select(self, ids, edge=None):
        self.selected = set(ids)
        self.selected_edge = edge
        self._apply_selection()
        self.on_select()

    def select_all(self):
        if self.graph:
            self.select([i for i, n in self.graph['nodes'].items()
                         if not model.is_entry(i) and not model.is_docked(n)
                         and not self._dimmed(n)])

    def delete_selection(self):
        if not self.graph:
            return
        if self.selected_edge and not self.selected:
            frm, port = self.selected_edge
            self.before_change('disconnect')
            model.disconnect(self.graph, frm, port)
            self._delete_edge(frm, port)
            self.draw_node(frm)
            self.selected_edge = None
            self.after_change()
            return
        ids = {i for i in self.selected if not model.is_entry(i)
               and i != model.TASK_ID}
        if not ids:
            return
        self.before_change('delete')
        if any(model.is_docked(self.graph['nodes'][i]) for i in ids) or any(
                n.get('attached_to') in ids and model.is_docked(n)
                for n in self.graph['nodes'].values()):
            model.remove_nodes(self.graph, ids)
            self.selected = set()
            self.redraw()
            self.after_change()
            self.on_select()
            return
        touched = {e[0] for e in self.graph['edges'] if e[2] in ids}
        gone = [e for e in self.graph['edges'] if e[0] in ids or e[2] in ids]
        model.remove_nodes(self.graph, ids)
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

    def add_node_at(self, ntype, wx, wy, speaker=None, state=None,
                    connect_from=None):
        """Create a node; ``connect_from`` = (from_id, port) links it."""
        self.before_change('add')
        state = state or self.filter_state or 'first'
        node = model.make_node(ntype, int(wx), int(wy), state, speaker)
        nid = model.add_node(self.graph, node)
        if connect_from and model.connect(self.graph, connect_from[0],
                                          connect_from[1], nid):
            self.draw_node(connect_from[0])
            self.draw_edge(connect_from[0], connect_from[1], nid)
        self.draw_node(nid)
        self.after_change()
        self.select([nid])
        return nid

    def add_docked(self, node, select=True):
        """Add an action or condition node and restack its group."""
        self.before_change('add')
        nid = model.add_node(self.graph, node)
        model.restack(self.graph, node.get('attached_to'))
        self.redraw_group(node.get('attached_to'))
        self.after_change()
        if select:
            self.select([nid])
        return nid

    def redraw_group(self, parent):
        """Redraw a parent and everything docked to it."""
        if not self.graph:
            return
        for nid, n in self.graph['nodes'].items():
            if nid == parent or n.get('attached_to') == parent:
                self.draw_node(nid)
        self._apply_selection()

    def node_at(self, x_root, y_root):
        """Node id under a screen position (for drops from the palette)."""
        x, y = x_root - self.winfo_rootx(), y_root - self.winfo_rooty()
        if not (0 <= x < self.winfo_width() and 0 <= y < self.winfo_height()):
            return None, None
        ev = type('E', (), {'x': x, 'y': y})()
        return self._hit(ev)['nid'], self.c2w(self.canvasx(x),
                                               self.canvasy(y))

    def highlight_drop(self, nid):
        """Gold frame around the node a palette item would drop onto."""
        if getattr(self, '_drop_hint', None) == nid:
            return
        self._drop_hint = nid
        self.delete('drophint')
        node = self.graph['nodes'].get(nid) if (self.graph and nid) else None
        if not node:
            return
        w, h = model.node_size(node)
        x1, y1 = self.w2c(node['x'], node['y'])
        x2, y2 = self.w2c(node['x'] + w, node['y'] + h)
        m = 4 * self.zoom
        self.create_rectangle(x1 - m, y1 - m, x2 + m, y2 + m,
                              outline=theme.GOLD, width=2.5, dash=(6, 4),
                              tags='drophint')

    def redraw_node(self, nid):
        """Public: node data changed (text, colour, size, lines)."""
        if not self.graph or nid not in self.graph['nodes']:
            return
        # the node may have grown: docked conditions below it move along
        model.restack(self.graph, nid)
        for other, n in self.graph['nodes'].items():
            if other == nid or n.get('attached_to') == nid:
                self.draw_node(other)
        for e in self.graph['edges']:
            if e[0] == nid or e[2] == nid:
                self.draw_edge(*e)
        self._apply_selection()
        self._update_region()

    # -- drawing ------------------------------------------------------------

    def _dimmed(self, node):
        if not self.filter_state or node.get('type') == 'comment':
            return False
        if node.get('type') == 'task':
            return self.filter_state != 'solved'
        if node.get('type') in ('action', 'condition'):
            parent = self.graph['nodes'].get(node.get('attached_to'))
            return self._dimmed(parent) if parent else False
        return node.get('state') not in (self.filter_state, 'neutral')

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
        node = self.graph['nodes'].get(nid)
        if not node:
            return
        z = self.zoom
        w, h = model.node_size(node)
        x1, y1 = self.w2c(node['x'], node['y'])
        x2, y2 = self.w2c(node['x'] + w, node['y'] + h)
        tags = ('node', f'n:{nid}')
        kind = node['type']
        dim = self._dimmed(node)
        ink = theme.DIM if dim else theme.INK
        stip = 'gray25' if dim else ''
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
        elif kind in ('action', 'condition', 'task'):
            body = self._draw_docked(nid, node, x1, y1, x2, y2, tags, dim)
        elif kind == 'entry':
            col = theme.STATE_COLORS.get(node.get('state'), theme.ENTRY_COLOR)
            body = self.create_polygon(
                self._rr(x1, y1, x2, y2, h * z / 2), smooth=True,
                fill='#1d3a26' if not dim else theme.PANEL,
                outline=theme.DIM if dim else col, width=1.5,
                tags=tags + ('body',))
            label = t('node.entry') + ' ' + t('state.' + node.get('state', ''))
            self.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label,
                             fill=theme.DIM if dim else col,
                             font=self._font('title'), tags=tags + ('body',))
            self._draw_out_port(nid, 0, tags, dim)
            self._draw_port(x1 + (x2 - x1) / 2, y2, 'cond', nid, tags)
        else:
            title, color = self.node_style(node)
            if dim:
                color = theme.PANEL
            body = self.create_polygon(
                self._rr(x1, y1, x2, y2, CORNER * z), smooth=True,
                fill=theme.FIELD, outline=theme.LINE, width=1,
                stipple=stip, tags=tags + ('body',))
            hy = y1 + model.HEADER_H * z
            self.create_polygon(
                self._rr(x1, y1, x2, hy, CORNER * z,
                         (True, True, False, False)), smooth=True,
                fill=color, outline='', stipple=stip, tags=tags + ('body',))
            font_t = self._font('title')
            band = t('state.short.' + node.get('state', ''))
            band_w = font_t.measure(band) + 10 * z
            if kind == 'player':
                title = t('node.player')
                kind_lbl = t('insp.kind.' + node.get('kind', 'answer')) + ' ▾'
                kw_ = font_t.measure(kind_lbl) + 8 * z
                self.create_text(x2 - band_w - 6 * z, (y1 + hy) / 2,
                                 text=kind_lbl, anchor='e',
                                 fill='#17130b' if not dim else theme.DIM,
                                 font=self._font('small'),
                                 tags=tags + ('kind',))
            else:
                kw_ = 0
            title = self._fit_text(title or t('node.dialog'), font_t,
                                   (w - 30) * z - band_w - kw_)
            self.create_text(x1 + 12 * z, (y1 + hy) / 2, text=title,
                             anchor='w', fill='#17130b' if not dim
                             else theme.DIM, font=font_t,
                             tags=tags + ('body',))
            # state band at the right of the header
            bx1, by1 = x2 - band_w - 2 * z, y1 + 4 * z
            self.create_polygon(
                self._rr(bx1, by1, x2 - 3 * z, hy - 4 * z, 8 * z),
                smooth=True, fill=theme.BG, outline='',
                tags=tags + ('body',))
            self.create_text((bx1 + x2 - 3 * z) / 2, (by1 + hy - 4 * z) / 2,
                             text=band, fill=theme.STATE_COLORS.get(
                                 node.get('state'), theme.MUT)
                             if not dim else theme.DIM,
                             font=self._font('small'), tags=tags + ('body',))
            self._draw_port(x1, (y1 + hy) / 2, 'in', nid, tags)
            self._draw_port((x1 + x2) / 2, y1, 'act', nid, tags)
            lines = node.get('lines') or [model.new_line()]
            font = self._font('line')
            many = kind == 'player' and node.get('kind') == 'question'
            tops, total = model.line_tops(node)
            for i, line in enumerate(lines):
                ly = hy + (model.NODE_PAD / 2 + tops[i]
                           + model.LINE_H / 2) * z
                dw = 22 * z if many and len(lines) > 1 else 0
                avail = model.line_text_width(node, line) * z
                # full text, wrapped; rows are re-fitted only where the
                # zoomed font is wider than the scaled row (small zoom)
                for r, row in enumerate(model.line_rows(node, line)):
                    self.create_text(
                        x1 + 12 * z, ly + r * model.ROW_H * z,
                        text=self._fit_text(row, font, avail + 2 * z),
                        anchor='w',
                        fill=ink if line.get('text') else theme.DIM,
                        font=font, tags=tags + ('body',))
                gx = x2 - 12 * z - dw
                for k, g, c in reversed(EVENT_GLYPHS):
                    if line.get(k):
                        self.create_text(gx, ly, text=g, anchor='e',
                                         fill=c if not dim else theme.DIM,
                                         font=font, tags=tags + ('body',))
                        gx -= font.measure(g) + 2 * z
                if dw:
                    self.create_text(x2 - 18 * z, ly, text='×', anchor='e',
                                     fill=theme.MUT, font=font,
                                     tags=tags + (f'delline:{i}',))
                self._draw_out_port(nid, i, tags, dim)
            if many:
                ly = hy + (model.NODE_PAD / 2 + total
                           + model.LINE_H / 2) * z
                self.create_text(x1 + 12 * z, ly, text='+ ' + t('insp.addline'),
                                 anchor='w', fill=theme.GOLD if not dim
                                 else theme.DIM, font=self._font('small'),
                                 tags=tags + ('addline',))
        self._body[nid] = body
        if nid in self.selected:
            self._outline(nid, True)

    def _draw_docked(self, nid, node, x1, y1, x2, y2, tags, dim):
        z = self.zoom
        kind = node['type']
        title, summary, problem = self.docked_text(node)
        col = {'action': theme.GOLD, 'condition': '#9a8fe0',
               'task': theme.STATE_COLORS['solved']}[kind]
        glyph = {'action': '\u26a1', 'condition': '\u25c9',
                 'task': '\u25ce'}[kind]
        outline = theme.ERR if problem else col
        if dim:
            col = outline = theme.DIM
        body = self.create_polygon(
            self._rr(x1, y1, x2, y2, min(10 * z, (y2 - y1) / 2)),
            smooth=True, fill=theme.PANEL, outline=outline,
            width=1.5 if kind != 'task' else 2, tags=tags + ('body',))
        font = self._font('small' if kind != 'task' else 'line')
        w = (x2 - x1) - 26 * z
        if kind == 'task':
            self.create_text(x1 + 10 * z, y1 + 13 * z, anchor='w',
                             text=glyph + ' ' + title, fill=col,
                             font=self._font('title'), tags=tags + ('body',))
            self.create_text(x1 + 10 * z, y1 + 34 * z, anchor='w',
                             text=self._fit_text(summary, font, w + 10 * z),
                             fill=theme.DIM if dim else theme.INK, font=font,
                             tags=tags + ('body',))
        else:
            text = self._fit_text(glyph + ' ' + summary, font, w)
            self.create_text(x1 + 8 * z, (y1 + y2) / 2, anchor='w', text=text,
                             fill=theme.DIM if dim else theme.INK, font=font,
                             tags=tags + ('body',))
        return body

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

    def _draw_out_port(self, nid, port, tags, dim=False):
        z = self.zoom
        wx, wy = self.out_pos(nid, port)
        cx, cy = self.w2c(wx, wy)
        r = PORT_R * z
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                         fill=theme.DIM if dim else theme.INK,
                         outline=theme.BG, tags=tags + (f'port:out:{port}',))
        if model.edge_from(self.graph, nid, port) is None and not dim:
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
        node = self.graph['nodes'][nid]
        w, h = model.node_size(node)
        if node['type'] == 'entry':
            return node['x'] + w, node['y'] + h / 2
        tops, total = model.line_tops(node)
        top = tops[port] if port < len(tops) else total
        return (node['x'] + w, node['y'] + model.HEADER_H + model.NODE_PAD / 2
                + top + model.LINE_H / 2)

    def in_pos(self, nid):
        node = self.graph['nodes'][nid]
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
        nodes = self.graph['nodes']
        if frm not in nodes or to not in nodes:
            return
        pts = self._edge_points(frm, port, to)
        sel = self.selected_edge == (frm, port)
        dim = self._dimmed(nodes[frm]) or self._dimmed(nodes[to])
        z = self.zoom
        kw = dict(fill=theme.GOLD if sel else (theme.DIM if dim else theme.MUT),
                  width=(2.5 if sel else 1.5) * z, arrow='last',
                  arrowshape=(10 * z, 12 * z, 4 * z),
                  tags=('edge', f'e:{frm}:{port}'))
        if dim:
            kw['dash'] = (4, 4)
        if self.edge_style == 'curve':
            item = self.create_line(*pts, smooth='raw', splinesteps=24, **kw)
        else:
            item = self.create_line(*pts, **kw)
        self._edge_items[(frm, port)] = item
        self.tag_lower(item, 'node')

    def _update_edges_of(self, nid):
        for frm, port, to in self.graph['edges']:
            if frm == nid or to == nid:
                item = self._edge_items.get((frm, port))
                if item:
                    self.coords(item, *self._edge_points(frm, port, to))

    def _outline(self, nid, on):
        body = self._body.get(nid)
        if body:
            node = self.graph['nodes'].get(nid, {})
            if node.get('type') == 'entry':
                col = theme.STATE_COLORS.get(node.get('state'),
                                             theme.ENTRY_COLOR)
                self.itemconfigure(body, outline=theme.GOLD if on else col,
                                   width=2.5 if on else 1.5)
            else:
                self.itemconfigure(body, outline=theme.GOLD if on
                                   else theme.LINE, width=2 if on else 1)

    def _apply_selection(self):
        if not self.graph:
            return
        for nid in self.graph['nodes']:
            self._outline(nid, nid in self.selected)
        nodes = self.graph['nodes']
        for frm, port, to in self.graph['edges']:
            item = self._edge_items.get((frm, port))
            if not item:
                continue
            if self.selected_edge == (frm, port):
                self.itemconfigure(item, fill=theme.GOLD, width=2.5 * self.zoom)
            else:
                dim = self._dimmed(nodes[frm]) or self._dimmed(nodes[to])
                self.itemconfigure(item, fill=theme.DIM if dim else theme.MUT,
                                   width=1.5 * self.zoom)

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
                elif (tg.startswith('port:') or tg.startswith('delline:')
                      or tg in ('grip', 'body', 'cap', 'addline', 'kind')):
                    role = tg
                elif tg.startswith('e:'):
                    _, frm, port = tg.split(':')
                    edge = (frm, int(port))
            hit = {'nid': nid, 'role': role, 'edge': edge}
            # ports and buttons win over bodies, nodes win over edges
            if role and (role.startswith('port:') or role in ('addline', 'kind')
                         or role.startswith('delline:') or role == 'grip'):
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
        if not self.graph:
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
            self._mark_targets(nid, port)
            return
        if nid and role == 'grip':
            node = self.graph['nodes'][nid]
            self._drag = {'kind': 'resize', 'nid': nid, 'wx': wx, 'wy': wy,
                          'w': node['w'], 'h': node['h'], 'pushed': False}
            return
        if nid and role == 'addline':
            self._add_line(nid)
            return
        if nid and role and role.startswith('delline:'):
            self._remove_line(nid, int(role.split(':')[1]))
            return
        if nid and role == 'kind':
            self.select([nid])
            self._kind_menu(nid, ev)
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

    def _mark_targets(self, frm, port):
        """Grey out input ports that cannot take the dragged edge (plan
        5.3); ``frm=None`` restores them."""
        for item in self.find_withtag('port:in'):
            nid = next((tg[2:] for tg in self.gettags(item)
                        if tg.startswith('n:')), None)
            ok = frm is None or (nid and model.can_connect(self.graph, frm,
                                                           port, nid))
            self.itemconfigure(item, fill=theme.INK if ok else theme.LINE,
                               outline=theme.BG if ok else theme.LINE)

    def set_as_start(self, nid):
        node = self.graph['nodes'][nid]
        st = node.get('state')
        if st in (None, 'neutral'):
            return
        self.before_change('start')
        ent = model.entry_id(st)
        model.ensure_entry(self.graph, st)
        model.connect(self.graph, ent, 0, nid)
        self.redraw()
        self.after_change()

    def _movable(self, ids):
        """Selected nodes plus whatever is attached to them (comments,
        actions), minus entries and docked nodes selected on their own."""
        nodes = self.graph['nodes']
        out = {i for i in ids if not model.is_entry(i)
               and not model.is_docked(nodes[i])}
        for nid, n in nodes.items():
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
        for frm, port, to in self.graph['edges']:
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
                n = self.graph['nodes'][nid]
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
            n = self.graph['nodes'][d['nid']]
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
        if not d or not self.graph:
            return
        if d['kind'] == 'move':
            self.dtag('all', 'sel')
            self.dtag('all', 'seledge')
            if d['moved']:
                self._update_region()
                self.after_change()
        elif d['kind'] == 'edge':
            self.delete('temp')
            self._mark_targets(None, None)
            hit = self._hit(ev)
            wx, wy = self.event_world(ev)
            to = hit['nid']
            if to and to != d['frm'] and model.can_connect(
                    self.graph, d['frm'], d['port'], to):
                self.before_change('connect')
                model.connect(self.graph, d['frm'], d['port'], to)
                self.draw_node(d['frm'])
                self.draw_edge(d['frm'], d['port'], to)
                self.after_change()
            elif not to and not hit['edge']:
                self.on_edge_drop_empty(d['frm'], d['port'], wx, wy, ev)
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
                for nid, n in self.graph['nodes'].items():
                    if self._dimmed(n):
                        continue
                    w, h = model.node_size(n)
                    if (n['x'] < x2 and n['x'] + w > x1 and n['y'] < y2
                            and n['y'] + h > y1):
                        hits.add(nid)
                self.selected = (self.selected | hits) if d['add'] else hits
                self._apply_selection()
                self.on_select()

    def _double(self, ev):
        hit = self._hit(ev)
        if hit['nid'] and hit['role'] in ('body', 'cap', None):
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
        """Mouse wheel zooms around the cursor; fine touchpad deltas are
        collected until they make one notch."""
        self._wheel_acc += ev.delta
        steps = int(self._wheel_acc / 120)
        if not steps:
            return
        self._wheel_acc -= steps * 120
        self.set_zoom(self.zoom_i + steps, (ev.x, ev.y))

    # -- node buttons -------------------------------------------------------

    def _add_line(self, nid):
        self.before_change('addline')
        model.add_line(self.graph, nid)
        self.redraw_node(nid)
        self.after_change()

    def _remove_line(self, nid, index):
        self.before_change('delline')
        if model.remove_line(self.graph, nid, index):
            self.redraw_node(nid)
            self.after_change()

    def _kind_menu(self, nid, ev):
        menu = theme.Menu(self, tearoff=0)
        for kind in ('answer', 'question'):
            menu.add_command(label=t('insp.kind.' + kind),
                             command=lambda k=kind: self.set_kind(nid, k))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def set_kind(self, nid, kind):
        node = self.graph['nodes'][nid]
        if node.get('kind') == kind:
            return
        self.before_change('kind')
        node['kind'] = kind
        if kind == 'answer':
            while len(node['lines']) > 1:
                model.remove_line(self.graph, nid, len(node['lines']) - 1)
        self.redraw_node(nid)
        self.after_change()

    def set_state(self, nid, state):
        node = self.graph['nodes'][nid]
        if node.get('state') == state or node.get('type') in ('entry',
                                                              'comment'):
            return
        self.before_change('state')
        node['state'] = state
        self.redraw_node(nid)
        self.after_change()

    # -- context menu -------------------------------------------------------

    def _context(self, ev):
        if not self.graph:
            return
        self.focus_set()
        hit = self._hit(ev)
        wx, wy = self.event_world(ev)
        menu = theme.Menu(self, tearoff=0)
        nid = hit['nid']
        if nid:
            if nid not in self.selected:
                self.select([nid])
            node = self.graph['nodes'][nid]
            if model.is_docked(node):
                if self.fill_docked_menu:
                    self.fill_docked_menu(menu, node['type'], nid)
                if node['type'] != 'task':
                    menu.add_command(label=t('edit.delete'),
                                     command=self.delete_selection)
                try:
                    menu.tk_popup(ev.x_root, ev.y_root)
                finally:
                    menu.grab_release()
                return
            if node['type'] != 'entry':
                menu.add_command(label=t('edit.duplicate'),
                                 command=self.duplicate_selection)
                menu.add_command(label=t('edit.delete'),
                                 command=self.delete_selection)
            if self.fill_docked_menu and (
                    node['type'] in ('npc', 'player')
                    or nid == model.entry_id('first')):
                self.fill_docked_menu(menu, node['type'], nid)
            if node['type'] == 'comment':
                if node.get('attached_to'):
                    menu.add_command(label=t('ctx.detach'),
                                     command=lambda: self._attach(nid, None))
                else:
                    sub = theme.Menu(menu, tearoff=0)
                    for oid, o in self.graph['nodes'].items():
                        if o['type'] in ('npc', 'player'):
                            label = self.node_style(o)[0] or oid
                            sub.add_command(
                                label=f'{label}  ({oid})',
                                command=lambda o=oid: self._attach(nid, o))
                    menu.add_cascade(label=t('ctx.attach'), menu=sub)
                col = theme.Menu(menu, tearoff=0)
                for c in [theme.COMMENT_COLOR] + theme.SPEAKER_COLORS:
                    col.add_command(label='■', foreground=c,
                                    command=lambda c=c: self._set_color(nid, c))
                menu.add_cascade(label=t('ctx.color'), menu=col)
            else:
                menu.add_command(label=t('ctx.disconnect'),
                                 command=lambda: self._disconnect_node(nid))
                if node['type'] in ('npc', 'player'):
                    st = theme.Menu(menu, tearoff=0)
                    for s in model.STATES:
                        st.add_radiobutton(
                            label=t('state.' + s), value=s,
                            variable=tk.StringVar(value=node.get('state')),
                            command=lambda s=s: self.set_state(nid, s))
                    menu.add_cascade(label=t('insp.state'), menu=st)
                    menu.add_command(label=t('ctx.attach_comment'),
                                     command=lambda: self._new_comment_for(nid))
                    menu.add_command(
                        label=t('ctx.setstart'),
                        command=lambda: self.set_as_start(nid),
                        state='normal' if node.get('state') != 'neutral'
                        else 'disabled')
        elif hit['edge']:
            self.selected_edge = hit['edge']
            self.selected = set()
            self._apply_selection()
            menu.add_command(label=t('ctx.cut_edge'),
                             command=self.delete_selection)
        else:
            add = theme.Menu(menu, tearoff=0)
            if self.fill_add_menu:
                self.fill_add_menu(add, wx, wy)
            else:
                add.add_command(label=t('node.player'), command=lambda:
                                self.add_node_at('player', wx, wy))
            add.add_separator()
            add.add_command(label=t('node.comment'),
                            command=lambda: self.add_node_at('comment', wx, wy))
            menu.add_cascade(label=t('ctx.add'), menu=add)
            clip = self.get_clipboard() if self.get_clipboard else None
            menu.add_command(label=t('edit.paste'),
                             command=lambda: self.paste(clip),
                             state='normal' if clip else 'disabled')
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
        self.graph['nodes'][cid]['attached_to'] = target
        self.after_change()

    def _set_color(self, nid, color):
        self.before_change('color')
        self.graph['nodes'][nid]['color'] = color
        self.redraw_node(nid)
        self.after_change()

    def _disconnect_node(self, nid):
        self.before_change('disconnect')
        touched = {e[0] for e in self.graph['edges'] if e[2] == nid} | {nid}
        gone = [e for e in self.graph['edges'] if e[0] == nid or e[2] == nid]
        model.disconnect_node(self.graph, nid)
        for frm, port, to in gone:
            self._delete_edge(frm, port)
        for i in touched:
            self.draw_node(i)
        self.after_change()

    def _new_comment_for(self, nid):
        n = self.graph['nodes'][nid]
        w, h = model.node_size(n)
        cid = self.add_node_at('comment', n['x'], n['y'] + h + 12)
        self.graph['nodes'][cid]['attached_to'] = nid

    def duplicate_selection(self):
        ids = {i for i in self.selected if not model.is_entry(i)}
        if not ids:
            return
        self.before_change('duplicate')
        new = model.duplicate_nodes(self.graph, ids)
        for nid in new:
            self.draw_node(nid)
        for e in self.graph['edges']:
            if e[0] in new:
                self.draw_edge(*e)
        self.after_change()
        self.select(new)

    def paste(self, clip):
        if not self.graph or not clip or not clip['nodes']:
            return
        self.before_change('paste')
        new = model.paste_nodes(self.graph, clip)
        for nid in new:
            self.draw_node(nid)
        for e in self.graph['edges']:
            if e[0] in new:
                self.draw_edge(*e)
        self.after_change()
        self.select(new)

    def auto_layout(self):
        if not self.graph:
            return
        self.before_change('layout')
        model.auto_layout(self.graph)
        self.redraw()
        self.after_change()
        self.fit()
