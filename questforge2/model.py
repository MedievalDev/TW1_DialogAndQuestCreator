"""Data model: Project, Quest, JSON load/save.

Milestone 1 only defines the containers and the file format. Node types,
edges and the undo stack are filled in by milestones 2 and 3; the schema
already reserves the fields so later versions read M1 files unchanged.

File: ``*.tw1proj``, UTF-8 JSON, LF line endings, git friendly.
"""

import json
import os

from . import VERSION

FORMAT = 1
PROJECT_EXT = '.tw1proj'

# Conversation levels (tabs) keyed by their state flag name, see plan 5.1.
DEFAULT_TABS = ('0.FT.AS', '0.QNS.AE', '0.QS.AE', '0.QC')


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
        self.tabs = {k: {'nodes': {}, 'edges': []} for k in DEFAULT_TABS}
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
            q.tabs.setdefault(k, {'nodes': {}, 'edges': []})
        return q

    def node_count(self):
        return sum(len(t.get('nodes', {})) for t in self.tabs.values())


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
