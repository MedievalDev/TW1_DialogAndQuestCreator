"""Data model: Project, Quest, graph operations, JSON load/save, undo.

One graph per quest (plan 12.18): every dialog node carries its level
(``state``), the fixed entry node of each level is ``entry:<state>``.
Edges may connect nodes of different levels, as retail trees do.

File: ``*.tw1proj``, UTF-8 JSON, LF line endings, git friendly.
"""

import copy
import json
import os
import re

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
LINE_H = 22          # height of a dialog line with one row of text
ROW_H = 15           # every further wrapped row of the same line
NODE_PAD = 8
TEXT_INSET = 30      # text starts 12 in, 18 kept free for the out port
GLYPH_W = 14         # event glyph (take/close/fight) at the right
DEL_W = 22           # delete cross of question lines
ENTRY_W, ENTRY_H = 150, 34
COMMENT_MIN_W, COMMENT_MIN_H = 80, 40
ACTION_H = 24
TASK_W, TASK_H = 230, 50
TASK_ID = 'task'
CAM_NPC = 2
CAM_HERO = 7

# ---------------------------------------------------------------------------
# quest opcodes (column order from the SDK loader PQuestLoader.ech, arity
# checked by tw1_qtx). Field spec: (key, kind[, default]).
# kinds: npc, object, location, tile, int, amount, party, guild, enemy,
#        text, marker:<editor marker kind>
MARKER_KINDS = ('Q_Solve', 'Q_Action_Teleport', 'Q_Action_Walk',
                'Q_Action_Create_Enemy', 'Q_Action_Create_Object',
                'Q_Action_Clear_Area', 'Q_Action_Kill_Area', 'Gate')
_GO = [('marker', 'marker:Q_Solve'), ('tile', 'tile'), ('range', 'int', 8)]
FC_SPECS = {
    'KILL': [('npc', 'npc')],
    'TALK': [('npc', 'npc')],
    'BRING_OBJECT': [('object', 'object'), ('count', 'int', 1)],
    'BRING_GOLD': [('gold', 'int', 100)],
    'GO': _GO,
    'CLEAR_AREA': [('marker', 'marker:Q_Solve'), ('tile', 'tile'),
                   ('range', 'int', 50), ('party', 'party', 20)],
    'FIND_LOCATION': [('location', 'location')],
    'FIND_OBJECT': [('object', 'object')],
    'DELIVER_OBJECT': [('object', 'object'), ('count', 'int', 1),
                       ('marker', 'marker:Q_Solve'), ('tile', 'tile'),
                       ('range', 'int', 8)],
    'FIND_KILL': [('npc', 'npc')],
    'FIND_TALK': [('npc', 'npc')],
    'GO_AWAY': _GO,
    'FIND_PLACE': _GO,
}
FC_MAIN = ('KILL', 'TALK', 'BRING_OBJECT', 'BRING_GOLD', 'GO', 'CLEAR_AREA',
           'FIND_LOCATION', 'FIND_OBJECT', 'DELIVER_OBJECT')
FC_MORE = ('FIND_KILL', 'FIND_TALK', 'GO_AWAY', 'FIND_PLACE')
_AREA = lambda kind: [('marker', 'marker:' + kind), ('tile', 'tile'),  # noqa
                      ('range', 'int', 50), ('party', 'party', 20)]
ACTION_SPECS = {
    ('REWARD', 'GLD'): [('amount', 'amount', '500')],
    ('REWARD', 'EXP'): [('amount', 'amount', '250')],
    ('REWARD', 'ITM'): [('count', 'int', 1), ('object', 'object')],
    ('REWARD', 'REP'): [('count', 'int', 1), ('guild', 'guild', '202')],
    ('ACTION', 'NPC_CREATE'): [('npc', 'npc')],
    ('ACTION', 'NPC_REMOVE'): [('npc', 'npc')],
    ('ACTION', 'NPC_KILL'): [('npc', 'npc')],
    ('ACTION', 'NPC_TELEPORT'): [('npc', 'npc'),
                                 ('marker', 'marker:Q_Action_Teleport'),
                                 ('tile', 'tile'), ('angle', 'int', 0)],
    ('ACTION', 'NPC_GO'): [('npc', 'npc'), ('marker', 'marker:Q_Action_Walk')],
    ('ACTION', 'HERO_TELEPORT_DELAYED'): [
        ('delay', 'int', 1), ('marker', 'marker:Q_Action_Teleport'),
        ('tile', 'tile'), ('angle', 'int', 0)],
    ('ACTION', 'ENEMY_CREATE'): [
        ('enemy', 'enemy', 'ENEMY_GOBLIN'), ('count', 'int', 3),
        ('level', 'int', 1), ('marker', 'marker:Q_Action_Create_Enemy'),
        ('tile', 'tile'), ('party', 'party', 20)],
    ('ACTION', 'OBJECT_CREATE'): [('object', 'object'),
                                  ('marker', 'marker:Q_Action_Create_Object'),
                                  ('tile', 'tile')],
    ('ACTION', 'OPEN'): [('marker', 'marker:Gate'), ('tile', 'tile')],
    ('ACTION', 'CLOSE'): [('marker', 'marker:Gate'), ('tile', 'tile')],
    ('ACTION', 'SHOW_LOCATION'): [('location', 'location')],
    ('ACTION', 'CREATE_EFFECT'): [('effect', 'text', 'EFFECT_17'),
                                  ('x', 'int', 0), ('y', 'int', 0),
                                  ('tile', 'tile')],
    ('REWARD', 'SKL'): [('count', 'int', 1)],
    ('ACTION', 'NPC_CHANGE_PARTY'): [('npc', 'npc'), ('party', 'party', 20)],
    ('ACTION', 'CLEAR_AREA'): _AREA('Q_Action_Clear_Area'),
    ('ACTION', 'KILL_AREA'): _AREA('Q_Action_Kill_Area'),
    ('ACTION', 'PLAY_CUTSCENE'): [('number', 'int', 1)],
    ('ACTION', 'SET_WORLD_STATE'): [('number', 'int', 1)],
}
ACTION_MAIN = [('REWARD', 'GLD'), ('REWARD', 'EXP'), ('REWARD', 'ITM'),
               ('REWARD', 'REP'), ('ACTION', 'NPC_CREATE'),
               ('ACTION', 'NPC_REMOVE'), ('ACTION', 'NPC_KILL'),
               ('ACTION', 'NPC_TELEPORT'), ('ACTION', 'NPC_GO'),
               ('ACTION', 'HERO_TELEPORT_DELAYED'), ('ACTION', 'ENEMY_CREATE'),
               ('ACTION', 'OBJECT_CREATE'), ('ACTION', 'OPEN'),
               ('ACTION', 'CLOSE'), ('ACTION', 'SHOW_LOCATION'),
               ('ACTION', 'CREATE_EFFECT')]
ACTION_MORE = [k for k in ACTION_SPECS if k not in ACTION_MAIN]
REWARD_WHEN = ('TAKE', 'SOLVE', 'CLOSE', 'HEAR')
ACTION_WHEN = ('TAKE', 'SOLVE', 'CLOSE', 'ENABLE', 'HEAR', 'FAIL', 'FIGHT')
# Party numbers from the SDK (Scripts\Common\Enums.ech). 0 to 17 are the
# players and their enemies and never appear in quests; retail quests use
# 18 to 23 (and once 25). 26 to 42 are the town factions, which are neutral
# to the player, so enemies created in them do not attack on their own.
PARTIES = (18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33,
           34, 35, 36, 37, 38, 39, 40, 41, 42, 43)
PARTY_FIGHT = (18, 19, 20, 21, 22, 23)      # the hostile ones
# guild numbers, same source: 200 is "no guild", 206 is unused
GUILDS = (200, 201, 202, 203, 204, 205, 207, 208)


def guild_label(value, t):
    """'202  Warriors' for the picker; '(null)' and unknown values stay."""
    text = str(value).strip()
    if not text or text == '(null)':
        return text or '(null)'
    if not text.split()[0].isdigit():
        return text
    num = int(text.split()[0])
    name = t(f'guild.{num}')
    return f'{num}  {name}' if name != f'guild.{num}' else str(num)


def parse_guild(text):
    """Number out of '202  Warriors'; '(null)' and free text stay."""
    head = str(text).strip().split()
    if head and head[0].isdigit():
        return head[0]
    return str(text).strip()


def party_label(num, t):
    """'20  Bandits' for the picker; unknown numbers keep their number."""
    key = f'party.{num}'
    name = t(key)
    return f'{num}  {name}' if name != key else str(num)


def parse_party(text):
    """Number out of '20  Bandits', a bare number or something else."""
    head = str(text).strip().split()
    try:
        return int(head[0])
    except (IndexError, ValueError):
        return text

AOQ_EVENTS = ('TAKE', 'SOLVE', 'CLOSE')
# AOQ <type> <trigger> Q_<n>: when this quest reaches <trigger>, do <type>
# with the other quest. Both lists from the SDK loader (PQuestLoader.ech,
# ParseAOQ); "AOQ ENABLE" does not exist.
AOQ_TYPES = ('PROMOTE', 'TAKE', 'DISABLE', 'SOLVE', 'CLOSE', 'FAIL_CLOSE')
AOQ_TRIGGERS = ('ENABLE', 'TAKE', 'HEAR', 'SOLVE', 'CLOSE', 'FAIL', 'FIGHT',
                'NONE')
# Animation of a dialog line: the .par carries anTalk0 to anTalk17 per unit,
# what each one shows is not documented. Retail uses 0, 10, 11 and 17 most.
ANIMATIONS = tuple(range(18))
ANIM_COMMON = (0, 10, 11, 17, 7, 8, 16, 9)
# map cells: A to L plus the row, interiors with _1, _2 ...
TILE_RE = re.compile(r'^[A-Z]\d{1,2}(_\d+)?$')


def anim_label(num, t):
    """'10  Talk 10 (often used)' for the picker."""
    try:
        num = int(str(num).split()[0])
    except (ValueError, IndexError):
        return str(num)
    text = f'{num}  ' + t('anim.name', n=num)
    if num in ANIM_COMMON:
        text += ' ' + t('anim.common')
    return text


def parse_anim(text):
    head = str(text).strip().split()
    try:
        return int(head[0])
    except (IndexError, ValueError):
        return 0

# Every list of numbers with a fixed meaning in one place: the pickers and
# the reference tables of the guide read from here.
# name -> (values, where it is proven, 'proven' or 'unverified')
NUMBER_LISTS = {
    'party': (PARTIES, 'SDK Enums.ech (ePartyX)', 'proven'),
    'guild': (GUILDS, 'SDK Enums.ech (eGuildX)', 'proven'),
    'aoq_type': (AOQ_TYPES, 'SDK PQuestLoader.ech (ParseAOQ)', 'proven'),
    'aoq_trigger': (AOQ_TRIGGERS, 'SDK PQuestLoader.ech (ParseAOQ)',
                    'proven'),
    'action_when': (ACTION_WHEN, 'SDK PQuestLoader.ech (ParseACT)', 'proven'),
    'animation': (ANIMATIONS, 'TwoWorlds.par anTalk0 to anTalk17',
                  'unverified'),
}
# fields whose numbers nobody could trace: shown with a warning
UNVERIFIED_FIELDS = {('ACTION', 'SET_WORLD_STATE'): ('number',),
                     ('ACTION', 'PLAY_CUTSCENE'): ('number',)}
# ParseEnemyType in PQuestLoader.ech (unknown names fall back to goblins)
ENEMY_TYPES = (
    'ENEMY_ANIMAL', 'ENEMY_BANDIT', 'ENEMY_DAEMON', 'ENEMY_GOBLIN',
    'ENEMY_GOBLIN2', 'ENEMY_GOLEM_FLESH', 'ENEMY_GOLEM_WOOD',
    'ENEMY_GOLEM_STEEL', 'ENEMY_GOLEM_STONE', 'ENEMY_INSECT',
    'ENEMY_LIZARDMAN', 'ENEMY_MANTIS', 'ENEMY_ORC', 'ENEMY_ORC_2',
    'ENEMY_REPTILE', 'ENEMY_YETI', 'ENEMY_SPIDER', 'ENEMY_UNDEAD',
    'ENEMY_UNDEAD_ANIMAL', 'ENEMY_ZOMBIE', 'ENEMY_SKELETON', 'ENEMY_MINION',
    'ENEMY_SEA_GUY', 'ENEMY_INSECT_GUY', 'ENEMY_SNOW_ORC', 'ENEMY_JACKAL',
    'ENEMY_DRAGON', 'ENEMY_WHITE_DRAGON', 'ENEMY_STONE_DRAGON',
    'ENEMY_LAVA_DRAGON', 'ENEMY_SNOW_ANIMAL', 'ENEMY_NECRO',
    'ENEMY_HELLMASTER', 'ENEMY_DEAD_KNIGHT', 'ENEMY_DWARF',
    'ENEMY_BRO_WARRIOR', 'ENEMY_SOLDIER_04', 'ENEMY_OGR', 'ENEMY_WOLF',
    'GHOST_DWARF', 'ENEMY_KHAN', 'ENEMY_DRAGONFLY2', 'ENEMY_DEADMEAT',
    'ENEMY_SKULL')


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
        self.actions = []                # actions without dialog (6.2):
        #   [{'kind','verb','args','when'}]; docked ones live in the graph
        self.links = []                  # AOQ lines of this quest:
        #   [{'type','event','quest'}], see AOQ_TYPES / AOQ_TRIGGERS
        self.retail = False              # True = edited retail quest
        self.extra = {}                  # unknown keys, preserved

    _FIELDS = ('title', 'group', 'journal', 'giver', 'giver_type',
               'map_sign', 'offered', 'enable_level', 'speakers', 'graph',
               'actions', 'links', 'retail')

    def to_dict(self):
        d = {'id': self.id}
        for f in self._FIELDS:
            # links came with 2.8.0: left out while empty, so projects of
            # older versions load and save byte-identical
            if f == 'links' and not self.links:
                continue
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
                   if k != 'id' and k not in cls._FIELDS
                   and k not in ('tabs', 'task', 'conditions')}
        if 'tabs' in d and 'graph' not in d:
            q.graph = _graph_from_tabs(d['tabs'])
        q.graph.setdefault('nodes', {})
        q.graph.setdefault('edges', [])
        for st in DEFAULT_STATES:
            ensure_entry(q.graph, st)
        ensure_task(q.graph)
        for n in q.graph['nodes'].values():
            if n.get('type') in ('npc', 'player'):
                n.setdefault('lines', [new_line(n.get('state'))])
                for ln in n['lines']:
                    for k, v in new_line(n.get('state')).items():
                        ln.setdefault(k, v)
        return q

    # -- helpers ------------------------------------------------------------

    def node_count(self):
        """Dialog and comment nodes placed by the user."""
        return sum(1 for n in self.graph['nodes'].values()
                   if n.get('type') in ('npc', 'player', 'comment'))

    def task(self):
        return ensure_task(self.graph)

    def links_list(self):
        """AOQ lines of this quest: [{'type', 'event', 'quest'}]."""
        return [x for x in self.links
                if isinstance(x, dict) and x.get('quest') is not None]

    def conditions_list(self):
        return [n for n in self.graph['nodes'].values()
                if n.get('type') == 'condition']

    def graph_actions(self):
        """[(node id, action node)] of actions docked to dialog nodes."""
        return [(nid, n) for nid, n in self.graph['nodes'].items()
                if n.get('type') == 'action']

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
            elif f == 'links':
                self.links = []


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
        self.mods = []                   # [{'path', 'enabled'}], load order
        self.mod_tiles = {}              # tile -> chosen mod name

    def to_dict(self):
        d = {'format': FORMAT, 'tool_version': VERSION, 'name': self.name,
             'target_archive': self.target_archive,
             'quests': [q.to_dict() for q in self.quests]}
        # only written when used, so older projects save byte-identical
        if self.mods:
            d['mods'] = [dict(m) for m in self.mods]
        if self.mod_tiles:
            d['mod_tiles'] = dict(self.mod_tiles)
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
        p.mods = [{'path': str(m.get('path', '')),
                   'enabled': bool(m.get('enabled', True))}
                  for m in d.get('mods') or [] if isinstance(m, dict)]
        p.mod_tiles = {str(k): str(v)
                       for k, v in (d.get('mod_tiles') or {}).items()}
        p.extra = {k: v for k, v in d.items()
                   if k not in ('format', 'tool_version', 'name',
                                'target_archive', 'quests', 'mods',
                                'mod_tiles')}
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
    """Engine flags of one line (plan 12.19). A line may override the
    node's level (``line['state']``, used by imported reply menus whose
    options belong to different levels)."""
    f = STATE_BITS.get(line.get('state') or state, 0)
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
    ensure_task(g)
    return g


def ensure_task(graph):
    """The quest's single task block (FC), left of the 'solved' entry."""
    if TASK_ID not in graph['nodes']:
        graph['nodes'][TASK_ID] = {'type': 'task', 'fc': None, 'args': {},
                                   'x': 0, 'y': 0}
    restack(graph)
    return graph['nodes'][TASK_ID]


def restack(graph, parent=None):
    """Place docked nodes relative to their parent: actions stacked above a
    dialog node, conditions below the offer entry, the task block left of
    the 'solved' entry."""
    nodes = graph['nodes']
    groups = {}
    for nid, n in nodes.items():
        if n.get('type') in ('action', 'condition') and n.get('attached_to'):
            if parent is None or n['attached_to'] == parent:
                groups.setdefault(n['attached_to'], []).append(nid)
    for pid, ids in groups.items():
        p = nodes.get(pid)
        if not p:
            continue
        ids.sort(key=lambda i: nodes[i].get('slot', 0))
        pw, ph = node_size(p)
        for k, nid in enumerate(ids):
            n = nodes[nid]
            n['slot'] = k
            if n['type'] == 'action':
                n['x'] = p['x']
                n['y'] = p['y'] - (k + 1) * (ACTION_H + 4) - 4
            else:
                n['x'] = p['x']
                n['y'] = p['y'] + ph + 10 + k * (ACTION_H + 4)
    task = nodes.get(TASK_ID)
    ent = nodes.get(entry_id('solved'))
    if task and ent and parent in (None, entry_id('solved')):
        task['x'] = ent['x'] - TASK_W - 40
        task['y'] = ent['y'] - (TASK_H - ENTRY_H) / 2


def is_docked(node):
    return node.get('type') in ('action', 'condition', 'task')


def make_action(kind, verb, attached_to=None):
    spec = ACTION_SPECS[(kind, verb)]
    return {'type': 'action', 'kind': kind, 'verb': verb,
            'args': {f[0]: (f[2] if len(f) > 2 else '') for f in spec},
            'when': None, 'attached_to': attached_to, 'x': 0, 'y': 0,
            'slot': 999}


def make_condition(cond='after', **values):
    n = {'type': 'condition', 'cond': cond,
         'attached_to': entry_id('first'), 'x': 0, 'y': 0, 'slot': 999,
         'quest': 4, 'event': 'TAKE', 'level': 1, 'guild': '(null)',
         'min_rep': 0}
    n.update(values)
    return n


def copy_references(quest, old_id, new_id):
    """After copying a quest: links that pointed at the quest itself now
    point at the copy. Returns the references to other quests that the user
    has to check: [('link'|'condition', quest id, text)]."""
    foreign = []
    for link in quest.links:
        if not isinstance(link, dict):
            continue
        if link.get('quest') == old_id:
            link['quest'] = new_id
        elif link.get('quest') is not None:
            foreign.append(('link', link['quest'],
                            f"AOQ {link.get('type')} {link.get('event')} "
                            f"Q_{link['quest']}"))
    for n in quest.graph['nodes'].values():
        if n.get('type') == 'condition' and n.get('cond') == 'after':
            if n.get('quest') == old_id:
                n['quest'] = new_id
            else:
                foreign.append(('condition', n.get('quest'),
                                f"after Q_{n.get('quest')} "
                                f"{n.get('event', 'TAKE')}"))
    return foreign


def add_default_conditions(quest):
    """New quests: offered after taking Q_4, level 1 (plan 6.3)."""
    g = quest.graph
    add_node(g, make_condition('after', quest=4, event='TAKE'))
    add_node(g, make_condition('level', level=1))
    restack(g)


def set_task(graph, fc):
    task = ensure_task(graph)
    if task.get('fc') == fc:
        return task
    old = task.get('args') or {}
    task['fc'] = fc
    task['args'] = {}
    if fc:
        for f in FC_SPECS[fc]:
            task['args'][f[0]] = old.get(f[0], f[2] if len(f) > 2 else '')
    return task


def set_action_verb(node, kind, verb):
    old = node.get('args') or {}
    node['kind'], node['verb'] = kind, verb
    node['args'] = {f[0]: old.get(f[0], f[2] if len(f) > 2 else '')
                    for f in ACTION_SPECS[(kind, verb)]}


def action_when(graph, node):
    """Event of an action: docked ones derive it from the parent's level
    (plan 6.2 table), free ones carry it. None = not allowed there."""
    pid = node.get('attached_to')
    if not pid:
        return node.get('when')
    parent = graph['nodes'].get(pid)
    if not parent:
        return None
    st = parent.get('state')
    if st == 'first':
        return 'TAKE'
    if st == 'solved':
        return 'SOLVE' if node.get('when') == 'SOLVE' else 'CLOSE'
    return None


def op_tokens(spec, values):
    """qtx argument tokens for a field spec; raises ModelError on empties."""
    out = []
    for f in spec:
        key, kind = f[0], f[1]
        v = values.get(key, '')
        v = '' if v is None else str(v).strip()
        if kind == 'tile':
            out.append(v.upper() if v else '(null)')
            continue
        if v == '':
            raise FieldError(key, 'empty', v, f'field {key} is empty')
        if kind == 'npc':
            if v.startswith('NPC_'):
                v = v[4:]
            if not v.isdigit():
                raise FieldError(key, 'number', v,
                                 f'field {key} must be an NPC id: {v!r}')
            out.append(f'NPC_{v}')
        elif kind in ('int', 'party') or kind.startswith('marker:'):
            try:
                out.append(str(int(v)))
            except ValueError:
                raise FieldError(key, 'number', v,
                                 f'field {key} must be a number: {v!r}')
        elif kind == 'amount':
            if v.upper() in ('SMALL', 'MEDIUM', 'HIGH'):
                out.append(v.upper())
            else:
                try:
                    out.append(str(int(v)))
                except ValueError:
                    raise FieldError(key, 'amount', v,
                                     f'field {key}: number or SMALL/MEDIUM/'
                                     f'HIGH, not {v!r}')
        else:
            if ' ' in v:
                raise FieldError(key, 'space', v,
                                 f'field {key} must not contain spaces')
            out.append(v)
    return out


class FieldError(ModelError):
    """A field of an opcode cannot be written (``reason``: empty, number,
    amount, space)."""

    def __init__(self, key, reason, value, text):
        super().__init__(text)
        self.key, self.reason, self.value = key, reason, value


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


# -- wrapped dialog lines: a node grows downwards with its text ----------
# The graph view installs the real font measure (font at 100 % zoom); the
# fallback keeps the model usable without Tk (tests, export).

_measure = None
_wrap_cache = {}


def set_text_measure(fn):
    global _measure
    _measure = fn
    _wrap_cache.clear()


def _text_w(text):
    return _measure(text) if _measure else len(text) * 6.5


def _break_word(word, width):
    """Split a word that is wider than a row into row-sized pieces."""
    parts = []
    while len(word) > 1 and _text_w(word) > width:
        lo, hi = 1, len(word) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _text_w(word[:mid]) <= width:
                lo = mid
            else:
                hi = mid - 1
        parts.append(word[:lo])
        word = word[lo:]
    return parts, word


def wrap_text(text, width):
    """Rows of ``text`` that fit ``width`` world units."""
    key = (text, width)
    rows = _wrap_cache.get(key)
    if rows is not None:
        return rows
    rows = []
    for para in (text or '').splitlines() or ['']:
        if _text_w(para) <= width:
            rows.append(para)
            continue
        cur = ''
        for word in para.split(' '):
            cand = word if not cur else cur + ' ' + word
            if _text_w(cand) <= width:
                cur = cand
                continue
            if cur:
                rows.append(cur)
            parts, cur = _break_word(word, width)
            rows.extend(parts)
        rows.append(cur)
    if len(_wrap_cache) > 20000:
        _wrap_cache.clear()
    _wrap_cache[key] = rows
    return rows


def line_text_width(node, line):
    """Width available for the text of one dialog line."""
    glyphs = sum(1 for k in ('take', 'close', 'fight') if line.get(k))
    many = (node.get('type') == 'player' and node.get('kind') == 'question'
            and len(node.get('lines') or []) > 1)
    return (NODE_W - TEXT_INSET - (glyphs * GLYPH_W + 6 if glyphs else 0)
            - (DEL_W if many else 0) - 4)


def line_rows(node, line):
    return wrap_text(line.get('text') or '…', line_text_width(node, line))


def line_tops(node):
    """(tops, total): offset of every line below the header padding and
    the height of all lines together."""
    tops, y = [], 0
    for line in (node.get('lines') or [new_line()]):
        tops.append(y)
        y += LINE_H + (len(line_rows(node, line)) - 1) * ROW_H
    return tops, y


def node_size(node):
    """(w, h) in world units."""
    t = node.get('type')
    if t == 'entry':
        return ENTRY_W, ENTRY_H
    if t in ('action', 'condition'):
        return NODE_W, ACTION_H
    if t == 'task':
        return TASK_W, TASK_H
    if t == 'comment':
        return (max(COMMENT_MIN_W, node.get('w', 200)),
                max(COMMENT_MIN_H, node.get('h', 80)))
    extra = LINE_H if (t == 'player' and node.get('kind') == 'question') else 0
    return NODE_W, HEADER_H + line_tops(node)[1] + NODE_PAD + extra


def out_port_count(node):
    t = node.get('type')
    if t == 'entry':
        return 1
    if t in ('comment', 'action', 'condition', 'task'):
        return 0
    return max(1, len(node.get('lines') or []))


def add_node(graph, node, nid=None):
    nid = nid or new_node_id(graph)
    graph['nodes'][nid] = node
    return nid


def remove_nodes(graph, ids):
    ids = {i for i in ids if not is_entry(i) and i != TASK_ID}
    # docked actions/conditions go with their parent
    ids |= {nid for nid, n in graph['nodes'].items()
            if n.get('type') in ('action', 'condition')
            and n.get('attached_to') in ids}
    parents = {graph['nodes'][i].get('attached_to') for i in ids
               if i in graph['nodes']}
    for i in ids:
        graph['nodes'].pop(i, None)
    for p in parents:
        if p in graph['nodes']:
            restack(graph, p)
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
    if b['type'] not in ('npc', 'player') or a['type'] not in ('npc',
                                                              'player',
                                                              'entry'):
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
    ids = {i for i in ids if not is_entry(i) and i != TASK_ID
           and i in graph['nodes']}
    # copying a dialog node takes its actions along; a lone action or
    # condition cannot live without its parent and is skipped
    ids |= {nid for nid, n in graph['nodes'].items()
            if n.get('type') == 'action' and n.get('attached_to') in ids}
    ids = {i for i in ids if not (graph['nodes'][i].get('type') in
                                  ('action', 'condition')
                                  and graph['nodes'][i].get('attached_to')
                                  not in ids)}
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
    restack(graph)
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
    # docked nodes need room: actions stack above, conditions below
    above, below = {}, {}
    for n in nodes.values():
        pid = n.get('attached_to')
        if n.get('type') == 'action' and pid:
            above[pid] = above.get(pid, 0) + ACTION_H + 4
        elif n.get('type') == 'condition' and pid:
            below[pid] = below.get(pid, 10) + ACTION_H + 4
    col_next_y, parent_y, band_y = {}, {}, y0
    for nid in order:
        if is_entry(nid):
            # every level starts below everything placed so far
            band_y = max([band_y] + list(col_next_y.values()))
            col_next_y = {}
        lv = level[nid]
        w, h = node_size(nodes[nid])
        y = max(col_next_y.get(lv, band_y), parent_y.get(nid, band_y))
        y += above.get(nid, 0)
        nodes[nid]['x'] = col_x[lv]
        nodes[nid]['y'] = y
        col_next_y[lv] = y + h + below.get(nid, 0) + gap_y
        for s in successors(graph, nid):
            parent_y.setdefault(s, y)
    max_y = max([band_y] + list(col_next_y.values()))
    x = x0
    for nid, n in nodes.items():
        if nid in seen or n.get('type') == 'comment' or is_docked(n):
            continue
        n['x'], n['y'] = x, max_y + gap_y
        x += node_size(n)[0] + gap_x
    restack(graph)
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
