"""Data model: Project, Quest, JSON load/save.

Milestone 1 only defines the containers and the file format. Node types,
edges and the undo stack are filled in by milestones 2 and 3; the schema
already reserves the fields so later versions read M1 files unchanged.

File: ``*.tw1proj``, UTF-8 JSON, LF line endings, git friendly.
"""

import copy
import json
import os

from . import VERSION

FORMAT = 1
PROJECT_EXT = '.tw1proj'

# Conversation levels (tabs) keyed by their state flag name, see plan 5.1.
DEFAULT_TABS = ('0.FT.AS', '0.QNS.AE', '0.QS.AE', '0.QC')
EXTRA_TABS = ('0.FT', '0.QNT', '0x0')
ENTRY_ID = 'entry'

# Node schema (one dict per node in tab['nodes']):
#   type      'entry' (fixed, one per tab) | 'node' (dialog line(s)) | 'comment'
#   x, y      position in world units
#   lines     [{'text': str, ...}]   ('node' only; one out port per line)
#   title     header text ('node': speaker name, milestone 3 fills it)
#   color     header colour ('node') / box colour ('comment'), None = default
#   w, h      size ('comment' only)
#   text      ('comment' only)
#   attached_to  node id a comment follows, or None
# Edges: [from_id, out_port, to_id]; one edge per out port, any number in.
NODE_W = 200
HEADER_H = 26
LINE_H = 22
NODE_PAD = 8
ENTRY_W, ENTRY_H = 110, 34
COMMENT_MIN_W, COMMENT_MIN_H = 80, 40


class ModelError(Exception):
    pass


class Quest:
    """One quest of the project. ``tabs`` maps a flag name to a graph
    ``{'nodes': {id: {...}}, 'edges': [[from, port, to], ...]}``."""

    def __init__(self, qid=None, title=''):
        self.id = qid                    # int 381..399, None = not chosen
        self.title = title
        self.group = 0
        self.journal = {'take': '', 'solve': '', 'close': ''}
        self.giver = None                # NPC id (int)
        self.giver_type = 'ACTIVE'
        self.map_sign = 'BACK_TO_GIVER_MAP_SIGN'
        self.offered = True              # False = AOQ TAKE TAKE (plan 6.4)
        self.enable_level = 1
        self.speakers = []               # [{'id': int, 'name': str, ...}]
        self.tabs = {k: new_tab() for k in DEFAULT_TABS}
        self.task = None                 # FC block, dict or None
        self.actions = []                # actions without dialog (6.2)
        self.conditions = []             # entry conditions (6.3)
        self.retail = False              # True = edited retail quest
        self.extra = {}                  # unknown keys, preserved

    _FIELDS = ('title', 'group', 'journal', 'giver', 'giver_type',
               'map_sign', 'offered', 'enable_level', 'speakers', 'tabs',
               'task', 'actions', 'conditions', 'retail')

    def to_dict(self):
        d = {'id': self.id}
        for f in self._FIELDS:
            d[f] = getattr(self, f)
        d.update(self.extra)
        return d

    @classmethod
    def from_dict(cls, d):
        q = cls(d.get('id'))
        for f in cls._FIELDS:
            if f in d:
                setattr(q, f, d[f])
        q.extra = {k: v for k, v in d.items()
                   if k != 'id' and k not in cls._FIELDS}
        for k in DEFAULT_TABS:
            q.tabs.setdefault(k, new_tab())
        for tab in q.tabs.values():
            tab.setdefault('nodes', {})
            tab.setdefault('edges', [])
            ensure_entry(tab)
        return q

    def node_count(self):
        """Nodes placed by the user (entries do not count)."""
        return sum(1 for tab in self.tabs.values()
                   for n in tab.get('nodes', {}).values()
                   if n.get('type') != 'entry')

    def tab_keys(self):
        """Default tabs first, then any extra levels present."""
        keys = list(DEFAULT_TABS)
        keys += [k for k in self.tabs if k not in keys]
        return keys


class Project:
    def __init__(self, name=''):
        self.name = name
        self.target_archive = ''         # Mods\<name>.wd
        self.quests = []
        self.path = None                 # file path, None = never saved
        self.dirty = False
        self.extra = {}

    # -- serialisation ----------------------------------------------------

    def to_dict(self):
        d = {'format': FORMAT, 'tool_version': VERSION, 'name': self.name,
             'target_archive': self.target_archive,
             'quests': [q.to_dict() for q in self.quests]}
        d.update(self.extra)
        return d

    @classmethod
    def from_dict(cls, d):
        fmt = d.get('format')
        if not isinstance(fmt, int) or fmt > FORMAT:
            raise ModelError(f'unsupported project format {fmt!r} '
                             f'(this version reads up to {FORMAT})')
        p = cls(d.get('name', ''))
        p.target_archive = d.get('target_archive', '')
        p.quests = [Quest.from_dict(q) for q in d.get('quests', [])]
        p.extra = {k: v for k, v in d.items()
                   if k not in ('format', 'tool_version', 'name',
                                'target_archive', 'quests')}
        return p

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + '\n'

    @classmethod
    def from_json(cls, text):
        try:
            d = json.loads(text)
        except ValueError as e:
            raise ModelError(f'not valid JSON: {e}')
        if not isinstance(d, dict):
            raise ModelError('project file must contain a JSON object')
        return cls.from_dict(d)

    def save(self, path=None):
        path = path or self.path
        if not path:
            raise ModelError('no file path')
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(self.to_json())
        os.replace(tmp, path)
        self.path = path
        self.dirty = False
        if not self.name:
            self.name = os.path.splitext(os.path.basename(path))[0]

    @classmethod
    def load(cls, path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            p = cls.from_json(f.read())
        p.path = path
        p.dirty = False
        if not p.name:
            p.name = os.path.splitext(os.path.basename(path))[0]
        return p

    # -- helpers ------------------------------------------------------------

    def display_name(self):
        if self.path:
            return os.path.splitext(os.path.basename(self.path))[0]
        return self.name

    def quest_by_id(self, qid):
        for q in self.quests:
            if q.id == qid:
                return q
        return None


# ---------------------------------------------------------------------------
# graph operations (work on one tab dict; the caller handles undo)

def new_tab():
    tab = {'nodes': {}, 'edges': []}
    ensure_entry(tab)
    return tab


def ensure_entry(tab):
    if ENTRY_ID not in tab['nodes']:
        tab['nodes'][ENTRY_ID] = {'type': 'entry', 'x': 40, 'y': 200}
    return tab['nodes'][ENTRY_ID]


def new_node_id(tab):
    n = 1
    while f'n{n}' in tab['nodes']:
        n += 1
    return f'n{n}'


def make_node(ntype, x, y, title=''):
    if ntype == 'comment':
        return {'type': 'comment', 'x': x, 'y': y, 'w': 200, 'h': 80,
                'text': '', 'color': None, 'attached_to': None}
    return {'type': 'node', 'x': x, 'y': y, 'title': title,
            'lines': [{'text': ''}], 'color': None}


def node_size(node):
    """(w, h) in world units."""
    t = node.get('type')
    if t == 'entry':
        return ENTRY_W, ENTRY_H
    if t == 'comment':
        return (max(COMMENT_MIN_W, node.get('w', 200)),
                max(COMMENT_MIN_H, node.get('h', 80)))
    n = max(1, len(node.get('lines') or []))
    return NODE_W, HEADER_H + n * LINE_H + NODE_PAD


def out_port_count(node):
    t = node.get('type')
    if t == 'entry':
        return 1
    if t == 'comment':
        return 0
    return max(1, len(node.get('lines') or []))


def add_node(tab, node, nid=None):
    nid = nid or new_node_id(tab)
    tab['nodes'][nid] = node
    return nid


def remove_nodes(tab, ids):
    ids = {i for i in ids if i != ENTRY_ID}
    for i in ids:
        tab['nodes'].pop(i, None)
    tab['edges'] = [e for e in tab['edges']
                    if e[0] not in ids and e[2] not in ids]
    for n in tab['nodes'].values():
        if n.get('attached_to') in ids:
            n['attached_to'] = None
    return ids


def can_connect(tab, frm, port, to):
    a, b = tab['nodes'].get(frm), tab['nodes'].get(to)
    if not a or not b or frm == to:
        return False
    if a['type'] == 'comment' or b['type'] in ('comment', 'entry'):
        return False
    return 0 <= port < out_port_count(a)


def connect(tab, frm, port, to):
    """One edge per out port: an existing edge from that port is replaced."""
    if not can_connect(tab, frm, port, to):
        return False
    tab['edges'] = [e for e in tab['edges'] if not (e[0] == frm and e[1] == port)]
    tab['edges'].append([frm, port, to])
    return True


def disconnect(tab, frm, port=None):
    before = len(tab['edges'])
    tab['edges'] = [e for e in tab['edges']
                    if not (e[0] == frm and (port is None or e[1] == port))]
    return before - len(tab['edges'])


def disconnect_node(tab, nid):
    before = len(tab['edges'])
    tab['edges'] = [e for e in tab['edges'] if e[0] != nid and e[2] != nid]
    return before - len(tab['edges'])


def edge_from(tab, frm, port):
    for e in tab['edges']:
        if e[0] == frm and e[1] == port:
            return e
    return None


def copy_nodes(tab, ids):
    """Clipboard payload: the nodes (deep copy) and the edges between them."""
    ids = {i for i in ids if i != ENTRY_ID and i in tab['nodes']}
    nodes = {i: copy.deepcopy(tab['nodes'][i]) for i in ids}
    for n in nodes.values():
        if n.get('attached_to') not in ids:
            n['attached_to'] = None
    edges = [list(e) for e in tab['edges'] if e[0] in ids and e[2] in ids]
    return {'nodes': nodes, 'edges': edges}


def paste_nodes(tab, clip, dx=30, dy=30):
    """Insert a clipboard payload with fresh ids. Returns the new ids."""
    mapping = {}
    for old, node in clip['nodes'].items():
        n = copy.deepcopy(node)
        n['x'] += dx
        n['y'] += dy
        mapping[old] = add_node(tab, n)
    for old, nid in mapping.items():
        n = tab['nodes'][nid]
        if n.get('attached_to') in mapping:
            n['attached_to'] = mapping[n['attached_to']]
    for frm, port, to in clip['edges']:
        connect(tab, mapping[frm], port, mapping[to])
    return list(mapping.values())


def duplicate_nodes(tab, ids):
    return paste_nodes(tab, copy_nodes(tab, ids))


def successors(tab, nid):
    """Targets of nid ordered by out port."""
    return [e[2] for e in sorted((e for e in tab['edges'] if e[0] == nid),
                                 key=lambda e: e[1])]


def auto_layout(tab, gap_x=80, gap_y=30, x0=40, y0=40):
    """Left to right by conversation flow (DFS from the entry), branches fan
    out downwards. Unreachable nodes go into a row below. Comments stay."""
    nodes = tab['nodes']
    level = {ENTRY_ID: 0}
    order = []
    stack = [ENTRY_ID]
    seen = set()
    while stack:
        nid = stack.pop()
        if nid in seen or nid not in nodes:
            continue
        seen.add(nid)
        order.append(nid)
        succ = successors(tab, nid)
        for s in reversed(succ):
            if s not in seen:
                level[s] = max(level.get(s, 0), level[nid] + 1)
                stack.append(s)
    col_x = {}
    col_next_y = {}
    widths = {}
    for nid in order:
        lv = level[nid]
        w, h = node_size(nodes[nid])
        widths[lv] = max(widths.get(lv, 0), w)
    x = x0
    for lv in sorted(widths):
        col_x[lv] = x
        x += widths[lv] + gap_x
    parent_y = {}
    for nid in order:
        lv = level[nid]
        w, h = node_size(nodes[nid])
        y = max(col_next_y.get(lv, y0), parent_y.get(nid, y0))
        nodes[nid]['x'] = col_x[lv]
        nodes[nid]['y'] = y
        col_next_y[lv] = y + h + gap_y
        for s in successors(tab, nid):
            parent_y.setdefault(s, y)
    max_y = max(col_next_y.values()) if col_next_y else y0
    x = x0
    for nid, n in nodes.items():
        if nid in seen or n.get('type') == 'comment':
            continue
        n['x'], n['y'] = x, max_y + gap_y
        x += node_size(n)[0] + gap_x
    return order


class UndoStack:
    """Snapshots of a quest's tabs (plan 5.3: snapshot per action)."""

    def __init__(self, limit=100):
        self.limit = limit
        self._undo = []
        self._redo = []

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    def push(self, state, label=''):
        self._undo.append((label, copy.deepcopy(state)))
        del self._undo[:-self.limit]
        self._redo.clear()

    def undo(self, current):
        if not self._undo:
            return None
        label, state = self._undo.pop()
        self._redo.append((label, copy.deepcopy(current)))
        return state

    def redo(self, current):
        if not self._redo:
            return None
        label, state = self._redo.pop()
        self._undo.append((label, copy.deepcopy(current)))
        return state

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)
