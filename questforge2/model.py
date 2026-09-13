"""Data model: Project, Quest, graph operations, JSON load/save, undo.

One graph per quest (plan 12.18): every dialog node carries its level
(``state``), the fixed entry node of each level is ``entry:<state>``.
Edges may connect nodes of different levels, as retail trees do.

File: ``*.tw1proj``, UTF-8 JSON, LF line endings, git friendly.
"""

import copy
import json
import os

from . import VERSION

FORMAT = 1
PROJECT_EXT = '.tw1proj'

# Conversation levels. The bits are the engine's dialog input flags
# (plan 6.3 result, PQuestsCommon.ech): a line plays when all its state bits
# are part of the current quest state. 'neutral' (0x0) plays always.
STATES = ('first', 'known', 'running', 'taken', 'solved', 'closed',
          'failed', 'lowrep', 'neutral')
DEFAULT_STATES = ('first', 'running', 'solved', 'closed')
STATE_BITS = {'first': 0x1, 'known': 0x2, 'taken': 0x4, 'closed': 0x8,
              'failed': 0x10, 'lowrep': 0x21, 'running': 0x100,
              'solved': 0x200, 'neutral': 0x0}
# Event bits: reported to the script when the conversation ends after
# passing such a line (TakeQuest / CloseQuest / giver turns hostile).
EVENT_BITS = {'take': 0x20000, 'close': 0x40000, 'fight': 0x10000}
STATE_MASK = 0x33f
PLAYER = 'player'            # speaker id of the hero (lector 1)
LEGACY_TABS = {'0.FT.AS': 'first', '0.FT': 'first', '0.QNT': 'known',
               '0.QNS.AE': 'running', '0.QS.AE': 'solved', '0.QC': 'closed',
               '0x0': 'neutral'}

# Node schema (one dict per node in graph['nodes']):
#   type      'entry' | 'npc' | 'player' | 'comment'
#   state     level name (all but comments)
#   x, y      position in world units
#   speaker   NPC id (int) for 'npc', PLAYER for 'player'
#   kind      'answer' | 'question'  ('player' only)
#   lines     [{'text','cue','cam','anim','take','close','fight'}]
#             one out port per line; 'npc' nodes have exactly one line
#   color, w, h, text, attached_to   ('comment' only)
# Edges: [from_id, out_port, to_id]; one edge per out port, any number in.
NODE_W = 200
HEADER_H = 26
LINE_H = 22
NODE_PAD = 8
ENTRY_W, ENTRY_H = 150, 34
COMMENT_MIN_W, COMMENT_MIN_H = 80, 40
CAM_NPC = 2
CAM_HERO = 7


class ModelError(Exception):
    pass


# ---------------------------------------------------------------------------
# quest and project

class Quest:
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
        self.speakers = []               # [{'id','name','lector','tile','new'}]
        self.graph = new_graph()
        self.task = None                 # FC block, dict or None
        self.actions = []                # actions without dialog (6.2)
        self.conditions = []             # entry conditions (6.3)
        self.retail = False              # True = edited retail quest
        self.extra = {}                  # unknown keys, preserved

    _FIELDS = ('title', 'group', 'journal', 'giver', 'giver_type',
               'map_sign', 'offered', 'enable_level', 'speakers', 'graph',
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
                   if k != 'id' and k not in cls._FIELDS and k != 'tabs'}
        if 'tabs' in d and 'graph' not in d:
            q.graph = _graph_from_tabs(d['tabs'])
        q.graph.setdefault('nodes', {})
        q.graph.setdefault('edges', [])
        for st in DEFAULT_STATES:
            ensure_entry(q.graph, st)
        for n in q.graph['nodes'].values():
            if n.get('type') in ('npc', 'player'):
                n.setdefault('lines', [new_line(n.get('state'))])
                for ln in n['lines']:
                    for k, v in new_line(n.get('state')).items():
                        ln.setdefault(k, v)
        return q

    # -- helpers ------------------------------------------------------------

    def node_count(self):
        """Nodes placed by the user (entries do not count)."""
        return sum(1 for n in self.graph['nodes'].values()
                   if n.get('type') != 'entry')

    def states_present(self):
        """Default levels first, then extra levels that have nodes."""
        used = {n.get('state') for n in self.graph['nodes'].values()
                if n.get('type') != 'comment'}
        return [s for s in STATES if s in DEFAULT_STATES or s in used]

    def speaker(self, sid):
        for s in self.speakers:
            if s['id'] == sid:
                return s
        return None

    def add_speaker(self, spk):
        if self.speaker(spk['id']) is None:
            self.speakers.append(spk)
        return spk

    def speaker_used(self, sid):
        return any(n.get('speaker') == sid for n in self.graph['nodes'].values())

    def remove_speaker(self, sid):
        if self.speaker_used(sid):
            return False
        self.speakers = [s for s in self.speakers if s['id'] != sid]
        return True

    def snapshot(self):
        """Everything the undo stack restores (graph, speakers, fields)."""
        return self.to_dict()

    def restore(self, snap):
        self.id = snap.get('id', self.id)
        for f in self._FIELDS:
            if f in snap:
                setattr(self, f, copy.deepcopy(snap[f]))


def _graph_from_tabs(tabs):
    """Milestone-2 files kept one graph per tab; merge them."""
    g = {'nodes': {}, 'edges': []}
    for i, (key, tab) in enumerate(tabs.items()):
        state = LEGACY_TABS.get(key, 'neutral')
        ids = {}
        for nid, n in tab.get('nodes', {}).items():
            n = copy.deepcopy(n)
            if n.get('type') == 'entry':
                new = entry_id(state)
                n['state'] = state
            else:
                new = f't{i}_{nid}'
                if n.get('type') == 'node':
                    n['type'] = 'npc'
                    n['speaker'] = None
                    n['lines'] = [dict(new_line(state), text=ln.get('text', ''))
                                  for ln in n.get('lines') or [{}]]
                if n.get('type') != 'comment':
                    n['state'] = state
            ids[nid] = new
            g['nodes'][new] = n
        for frm, port, to in tab.get('edges', []):
            if frm in ids and to in ids:
                g['edges'].append([ids[frm], port, ids[to]])
        for n in g['nodes'].values():
            if n.get('attached_to') in ids:
                n['attached_to'] = ids[n['attached_to']]
    return g


class Project:
    def __init__(self, name=''):
        self.name = name
        self.target_archive = ''         # Mods\<name>.wd
        self.quests = []
        self.path = None                 # file path, None = never saved
        self.dirty = False
        self.extra = {}

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
        if not self.name:
            self.name = os.path.splitext(os.path.basename(path))[0]
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(self.to_json())
        os.replace(tmp, path)
        self.path = path
        self.dirty = False

    @classmethod
    def load(cls, path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            p = cls.from_json(f.read())
        p.path = path
        p.dirty = False
        if not p.name:
            p.name = os.path.splitext(os.path.basename(path))[0]
        return p

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
# levels and flags

def entry_id(state):
    return f'entry:{state}'


def is_entry(nid):
    return isinstance(nid, str) and nid.startswith('entry:')


def line_flags(state, line):
    """Engine flags of one line (plan 12.19)."""
    f = STATE_BITS.get(state, 0)
    for k, bit in EVENT_BITS.items():
        if line.get(k):
            f |= bit
    return f


def flags_to_state(flags):
    """(state, take, close, fight) for a retail flag value; unknown state
    combinations map to 'neutral' (the caller keeps the raw flags)."""
    ev = {k: bool(flags & bit) for k, bit in EVENT_BITS.items()}
    sbits = flags & STATE_MASK
    state = 'neutral'
    for name, bits in STATE_BITS.items():
        if bits == sbits and name != 'neutral':
            state = name
            break
    return state, ev['take'], ev['close'], ev['fight']


# ---------------------------------------------------------------------------
# graph operations (work on the graph dict; the caller handles undo)

def new_graph(states=DEFAULT_STATES):
    g = {'nodes': {}, 'edges': []}
    for st in states:
        ensure_entry(g, st)
    return g


def ensure_entry(graph, state):
    nid = entry_id(state)
    if nid not in graph['nodes']:
        i = STATES.index(state) if state in STATES else len(STATES)
        graph['nodes'][nid] = {'type': 'entry', 'state': state, 'x': 40,
                               'y': 60 + i * 160}
    return graph['nodes'][nid]


def new_node_id(graph):
    n = 1
    while f'n{n}' in graph['nodes']:
        n += 1
    return f'n{n}'


def new_line(state=None):
    return {'text': '', 'cue': '', 'cam': None, 'anim': 0, 'take': False,
            'close': state == 'solved', 'fight': False}


def make_node(ntype, x, y, state='first', speaker=None):
    if ntype == 'comment':
        return {'type': 'comment', 'x': x, 'y': y, 'w': 200, 'h': 80,
                'text': '', 'color': None, 'attached_to': None}
    if ntype == 'player':
        return {'type': 'player', 'state': state, 'x': x, 'y': y,
                'speaker': PLAYER, 'kind': 'answer', 'lines': [new_line(state)]}
    return {'type': 'npc', 'state': state, 'x': x, 'y': y,
            'speaker': speaker, 'lines': [new_line(state)]}


def node_size(node):
    """(w, h) in world units."""
    t = node.get('type')
    if t == 'entry':
        return ENTRY_W, ENTRY_H
    if t == 'comment':
        return (max(COMMENT_MIN_W, node.get('w', 200)),
                max(COMMENT_MIN_H, node.get('h', 80)))
    n = max(1, len(node.get('lines') or []))
    extra = LINE_H if (t == 'player' and node.get('kind') == 'question') else 0
    return NODE_W, HEADER_H + n * LINE_H + NODE_PAD + extra


def out_port_count(node):
    t = node.get('type')
    if t == 'entry':
        return 1
    if t == 'comment':
        return 0
    return max(1, len(node.get('lines') or []))


def add_node(graph, node, nid=None):
    nid = nid or new_node_id(graph)
    graph['nodes'][nid] = node
    return nid


def remove_nodes(graph, ids):
    ids = {i for i in ids if not is_entry(i)}
    for i in ids:
        graph['nodes'].pop(i, None)
    graph['edges'] = [e for e in graph['edges']
                      if e[0] not in ids and e[2] not in ids]
    for n in graph['nodes'].values():
        if n.get('attached_to') in ids:
            n['attached_to'] = None
    return ids


def can_connect(graph, frm, port, to):
    a, b = graph['nodes'].get(frm), graph['nodes'].get(to)
    if not a or not b or frm == to:
        return False
    if a['type'] == 'comment' or b['type'] in ('comment', 'entry'):
        return False
    return 0 <= port < out_port_count(a)


def connect(graph, frm, port, to):
    """One edge per out port: an existing edge from that port is replaced."""
    if not can_connect(graph, frm, port, to):
        return False
    graph['edges'] = [e for e in graph['edges']
                      if not (e[0] == frm and e[1] == port)]
    graph['edges'].append([frm, port, to])
    return True


def disconnect(graph, frm, port=None):
    before = len(graph['edges'])
    graph['edges'] = [e for e in graph['edges']
                      if not (e[0] == frm and (port is None or e[1] == port))]
    return before - len(graph['edges'])


def disconnect_node(graph, nid):
    before = len(graph['edges'])
    graph['edges'] = [e for e in graph['edges'] if e[0] != nid and e[2] != nid]
    return before - len(graph['edges'])


def edge_from(graph, frm, port):
    for e in graph['edges']:
        if e[0] == frm and e[1] == port:
            return e
    return None


def add_line(graph, nid):
    node = graph['nodes'][nid]
    node.setdefault('lines', []).append(new_line(node.get('state')))
    return len(node['lines']) - 1


def remove_line(graph, nid, index):
    """Drop line ``index`` and renumber the out ports above it."""
    node = graph['nodes'][nid]
    lines = node.get('lines') or []
    if len(lines) <= 1 or not 0 <= index < len(lines):
        return False
    del lines[index]
    edges = []
    for frm, port, to in graph['edges']:
        if frm == nid:
            if port == index:
                continue
            if port > index:
                port -= 1
        edges.append([frm, port, to])
    graph['edges'] = edges
    return True


def copy_nodes(graph, ids):
    """Clipboard payload: the nodes (deep copy) and the edges between them."""
    ids = {i for i in ids if not is_entry(i) and i in graph['nodes']}
    nodes = {i: copy.deepcopy(graph['nodes'][i]) for i in ids}
    for n in nodes.values():
        if n.get('attached_to') not in ids:
            n['attached_to'] = None
    edges = [list(e) for e in graph['edges'] if e[0] in ids and e[2] in ids]
    return {'nodes': nodes, 'edges': edges}


def paste_nodes(graph, clip, dx=30, dy=30):
    """Insert a clipboard payload with fresh ids. Returns the new ids."""
    mapping = {}
    for old, node in clip['nodes'].items():
        n = copy.deepcopy(node)
        n['x'] += dx
        n['y'] += dy
        mapping[old] = add_node(graph, n)
    for old, nid in mapping.items():
        n = graph['nodes'][nid]
        if n.get('attached_to') in mapping:
            n['attached_to'] = mapping[n['attached_to']]
    for frm, port, to in clip['edges']:
        connect(graph, mapping[frm], port, mapping[to])
    return list(mapping.values())


def duplicate_nodes(graph, ids):
    return paste_nodes(graph, copy_nodes(graph, ids))


def successors(graph, nid):
    """Targets of nid ordered by out port."""
    return [e[2] for e in sorted((e for e in graph['edges'] if e[0] == nid),
                                 key=lambda e: e[1])]


def reachable_from(graph, start):
    seen, stack = set(), [start]
    while stack:
        nid = stack.pop()
        if nid in seen or nid not in graph['nodes']:
            continue
        seen.add(nid)
        stack.extend(successors(graph, nid))
    return seen


def auto_layout(graph, gap_x=80, gap_y=30, x0=40, y0=40):
    """Left to right by conversation flow (DFS from each entry in level
    order), branches fan out downwards, one band per entry. Unreachable
    nodes go into a row below. Comments stay."""
    nodes = graph['nodes']
    entries = [entry_id(s) for s in STATES if entry_id(s) in nodes]
    level, order, seen = {}, [], set()
    for ent in entries:
        level[ent] = 0
        stack = [ent]
        while stack:
            nid = stack.pop()
            if nid in seen or nid not in nodes:
                continue
            seen.add(nid)
            order.append(nid)
            succ = successors(graph, nid)
            for s in reversed(succ):
                if s not in seen:
                    level[s] = max(level.get(s, 0), level[nid] + 1)
                    stack.append(s)
    widths = {}
    for nid in order:
        w, h = node_size(nodes[nid])
        widths[level[nid]] = max(widths.get(level[nid], 0), w)
    col_x, x = {}, x0
    for lv in sorted(widths):
        col_x[lv] = x
        x += widths[lv] + gap_x
    col_next_y, parent_y, band_y = {}, {}, y0
    for nid in order:
        if is_entry(nid):
            # every level starts below everything placed so far
            band_y = max([band_y] + list(col_next_y.values()))
            col_next_y = {}
        lv = level[nid]
        w, h = node_size(nodes[nid])
        y = max(col_next_y.get(lv, band_y), parent_y.get(nid, band_y))
        nodes[nid]['x'] = col_x[lv]
        nodes[nid]['y'] = y
        col_next_y[lv] = y + h + gap_y
        for s in successors(graph, nid):
            parent_y.setdefault(s, y)
    max_y = max([band_y] + list(col_next_y.values()))
    x = x0
    for nid, n in nodes.items():
        if nid in seen or n.get('type') == 'comment':
            continue
        n['x'], n['y'] = x, max_y + gap_y
        x += node_size(n)[0] + gap_x
    return order


class UndoStack:
    """Snapshots per action (plan 5.3)."""

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
