"""Game data layer: config, game path, base extraction, index cache.

Performance rule (plan 2.2): the 500 quests, ~700 NPCs, 7578 voice cues
and the dialog trees of the 3 MB .lan are parsed ONCE into an index that is
written to ``cache/index.json`` together with mtime/size of every source
archive. Later starts only read the cache. Dialog trees themselves are not
cached; they are loaded when a quest is opened (milestone 4).

Storage location (``app_dir()``): running from source -> the repository
root next to the package (so the existing ``base/`` and
``questforge_config.json`` are reused); frozen exe ->
``%LOCALAPPDATA%\\TW1QuestCreator``.
"""

import glob
import json
import os
import re
import sys
import time

import tw1_lan
import tw1_qtx  # noqa: F401  (index_ids used by later milestones)
import tw1_wd

INDEX_FORMAT = 3      # bump whenever the index content changes
MIN_QUEST_ID = 381
MAX_QUEST_ID = 399          # hard engine cap in single-player, see SKILL.md
RETAIL_LIMIT = 400          # eQuestsNum of the retail PQuests.eco


def max_quest_id(limit=RETAIL_LIMIT):
    """Highest usable quest id for the quest limit the game runs with
    (400 retail, 600 with QuestLimit600.wd, see questlimit.py)."""
    return max(MAX_QUEST_ID, int(limit or RETAIL_LIMIT) - 1)
REG_GAME = r'SOFTWARE\Reality Pump\TwoWorlds'
REG_MODS = REG_GAME + r'\Mods'
INNER_QTX = 'Scripts\\Quests\\TwoWorldsQuests.qtx'
INNER_LAN = 'Language\\TwoWorldsQuests.lan'
STEAM_SUBDIR = r'steamapps\common\Two Worlds - Epic Edition'

# Which marker kind each opcode reads and where marker/tile sit in its
# argument list, verified against the SDK loader (PQuestLoader.ech). For FC
# the index counts after the subtype, for ACTION after subtype and time.
#   kind, marker arg index, tile arg index (None = no tile in the line)
_FC_MARKERS = {
    'GO': ('Q_Solve', 0, 1), 'GO_AWAY': ('Q_Solve', 0, 1),
    'FIND_PLACE': ('Q_Solve', 0, 1), 'CLEAR_AREA': ('Q_Solve', 0, 1),
    'DELIVER_OBJECT': ('Q_Solve', 2, 3),
}
_ACTION_MARKERS = {
    'NPC_TELEPORT': ('Q_Action_Teleport', 1, 2),
    'HERO_TELEPORT_DELAYED': ('Q_Action_Teleport', 1, 2),
    'NPC_GO': ('Q_Action_Walk', 1, None),
    'ENEMY_CREATE': ('Q_Action_Create_Enemy', 3, 4),
    'OBJECT_CREATE': ('Q_Action_Create_Object', 1, 2),
    'CLEAR_AREA': ('Q_Action_Clear_Area', 0, 1),
    'KILL_AREA': ('Q_Action_Kill_Area', 0, 1),
    'OPEN': ('Gate', 0, 1), 'CLOSE': ('Gate', 0, 1),
}


# ---------------------------------------------------------------------------
# paths and config

def app_dir():
    if getattr(sys, 'frozen', False):
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
        return os.path.join(base, 'TW1QuestCreator')
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


ROOT = app_dir()


def resource_path(*parts):
    """Read-only files shipped with the program (README, icons): inside the
    PyInstaller bundle when frozen, else the repository root."""
    base = getattr(sys, '_MEIPASS', None) or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def config_path():
    return os.path.join(ROOT, 'questforge_config.json')


def base_dir():
    return os.path.join(ROOT, 'base')


def cache_path():
    return os.path.join(ROOT, 'cache', 'index.json')


class Config:
    """questforge_config.json - compatible with the old tool (``game_dir``)."""

    DEFAULTS = {
        'game_dir': None, 'lang': None, 'recent_projects': [],
        'guide_seen': False,
        'panels': {'timeline': True, 'palette': True, 'inspector': True,
                   'coach': True},
        'window': None,
        'update_check': True, 'update_skip': None, 'voice_device': None,
    }

    def __init__(self, path=None):
        self.path = path or config_path()
        self.data = json.loads(json.dumps(self.DEFAULTS))
        try:
            with open(self.path, encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def add_recent(self, path, limit=8):
        path = os.path.normpath(path)
        recent = [p for p in self.data.get('recent_projects', [])
                  if os.path.normcase(p) != os.path.normcase(path)]
        self.data['recent_projects'] = [path] + recent[:limit - 1]

    def remove_recent(self, path):
        self.data['recent_projects'] = [
            p for p in self.data.get('recent_projects', [])
            if os.path.normcase(p) != os.path.normcase(path)]


# ---------------------------------------------------------------------------
# game path

def valid_game_dir(path):
    if not path or not os.path.isdir(path):
        return False
    wd = os.path.join(path, 'WDFiles')
    return (os.path.isfile(os.path.join(wd, 'Update16.wd'))
            or os.path.isfile(os.path.join(wd, 'Language.wd')))


def _registry_game_dir():
    try:
        import winreg
    except ImportError:
        return None
    for sub, value in ((REG_GAME, 'DataDir'), (REG_GAME + r'\FileSystem',
                                                 'DataDir')):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as k:
                path = winreg.QueryValueEx(k, value)[0].rstrip('\\')
            if valid_game_dir(path):
                return path
        except OSError:
            continue
    return None


def _steam_libraries():
    """Every Steam library root found via libraryfolders.vdf."""
    roots = []
    for steam in (r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam'):
        vdf = os.path.join(steam, 'steamapps', 'libraryfolders.vdf')
        roots.append(steam)
        try:
            text = open(vdf, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            roots.append(m.group(1).replace('\\\\', '\\'))
    return roots


def find_game_dir(cfg=None):
    """Saved config -> registry -> Steam libraries -> known folders."""
    if cfg is not None and valid_game_dir(cfg.get('game_dir')):
        return cfg.get('game_dir')
    found = _registry_game_dir()
    if found:
        return found
    cands = [os.path.join(r, STEAM_SUBDIR) for r in _steam_libraries()]
    cands += [r'F:\SteamLibrary\steamapps\common\Two Worlds - Epic Edition',
              r'C:\GOG Games\Two Worlds Epic Edition',
              r'C:\Program Files (x86)\GOG Galaxy\Games\Two Worlds Epic Edition']
    for c in cands:
        if valid_game_dir(c):
            return os.path.normpath(c)
    return None


# ---------------------------------------------------------------------------
# base data extraction

def _wd_entry(archive, inner):
    """Uncompressed bytes of one inner file of a .wd (None if absent)."""
    for e in tw1_wd.read(archive):
        if e.path == inner:
            return e.data
    return None


def ensure_base(game_dir, progress=None):
    """Extract base qtx/lan into base/ if missing. Returns (qtx, lan) paths."""
    bd = base_dir()
    qtx = os.path.join(bd, 'TwoWorldsQuests.qtx')
    lan = os.path.join(bd, 'TwoWorldsQuests.lan')
    wanted = ((os.path.join(game_dir, 'WDFiles', 'Update16.wd'), INNER_QTX, qtx),
              (os.path.join(game_dir, 'WDFiles', 'Language.wd'), INNER_LAN, lan))
    if not (os.path.isfile(qtx) and os.path.isfile(lan)):
        if progress:
            progress('base', 0.02)
        os.makedirs(bd, exist_ok=True)
        for archive, inner, dest in wanted:
            data = _wd_entry(archive, inner)
            if data is None:
                raise RuntimeError(f'{inner} not found in {archive}')
            with open(dest, 'wb') as f:
                f.write(data)
    return qtx, lan


# ---------------------------------------------------------------------------
# index

def source_files(game_dir):
    """Archives whose change invalidates the cache."""
    wd = os.path.join(game_dir, 'WDFiles')
    files = [os.path.join(wd, n) for n in
             ('Update16.wd', 'Language.wd', 'Content01_Lan.wd',
              'Content02_Lan.wd')]
    files += sorted(glob.glob(os.path.join(game_dir, 'Mods', '*.wd')))
    return [f for f in files if os.path.isfile(f)]


def source_stamps(files):
    out = {}
    for f in files:
        st = os.stat(f)
        out[os.path.normcase(f)] = [int(st.st_mtime), st.st_size]
    return out


def _split_quests(qtx_text):
    """Yield (qid, header_tokens, [sub_lines], block_text) per QUEST block."""
    for m in re.finditer(r'^QUEST Q_(\d+)([^\n]*)\n(.*?)^END', qtx_text,
                         re.M | re.S):
        header = m.group(2).split()
        subs = [ln.strip().split() for ln in m.group(3).split('\n')
                if ln.strip()]
        yield int(m.group(1)), header, subs, m.group(0)


def _index_qtx(qtx_text, tr, idx, source, retail_blocks):
    """Add quests, NPCs, locations, objects, markers of one qtx.

    A mod ships the FULL qtx (file-level override), so its blocks replace
    the retail ones: unchanged retail blocks keep source 'retail', changed
    ones additionally get 'modified_by' = mod name, new ids get the mod as
    source. retail_blocks: qid -> block text of the retail pass.
    """
    quests = idx['quests']
    for qid, header, subs, block in _split_quests(qtx_text):
        key = str(qid)
        if source == 'retail':
            retail_blocks[key] = block
            qsource, modified = 'retail', None
        elif key in retail_blocks:
            qsource = 'retail'
            modified = None if retail_blocks[key] == block else source
        else:
            qsource, modified = source, None
        q = {'title': tr.get(f'translateQ_{qid}', ''),
             'enable_level': _int(header[0]) if header else 1,
             'group': _int(header[1]) if len(header) > 1 else 0,
             'guild': header[2] if len(header) > 2 else '(null)',
             'min_rep': _int(header[3]) if len(header) > 3 else 0,
             'log': (header[4] == 'True') if len(header) > 4 else True,
             'giver': None, 'giver_type': None, 'fc': None,
             'aoq': [], 'actions': 0, 'rewards': 0,
             'lines': 0, 'flags': [], 'source': qsource,
             'modified_by': modified}
        old = quests.get(key)
        if old:
            q['lines'], q['flags'] = old['lines'], old['flags']
        for toks in subs:
            kw, args = toks[0], toks[1:]
            if kw == 'GIVER' and len(args) >= 2:
                q['giver_type'] = args[0]
                q['giver'] = _npc_id(args[1])
            elif kw == 'FC' and args:
                q['fc'] = args
                _add_marker(idx, _FC_MARKERS.get(args[0]), args[1:], qid)
                if args[0] == 'BRING_OBJECT' and len(args) > 1:
                    idx['objects'].add(args[1])
            elif kw == 'AOQ' and len(args) >= 3:
                q['aoq'].append([args[0], args[1], _quest_id(args[2])])
            elif kw == 'ACTION' and len(args) >= 2:
                q['actions'] += 1
                _add_marker(idx, _ACTION_MARKERS.get(args[0]), args[2:], qid)
                if args[0] == 'OBJECT_CREATE' and len(args) > 2:
                    idx['objects'].add(args[2])
            elif kw == 'REWARD' and args:
                q['rewards'] += 1
                if args[0] == 'ITM' and len(args) > 3:
                    idx['objects'].add(args[3])
        quests[key] = q
    for ln in qtx_text.split('\n'):
        if ln.startswith('NPC NPC_'):
            p = ln.split()
            nid = _npc_id(p[1])
            if nid is None or len(p) < 7:
                continue
            key = str(nid)
            if key in idx['npcs'] and source != 'retail':
                continue
            lector = _int(p[6], None)
            idx['npcs'][key] = {
                'name': tr.get(f'translateNPC_{nid}', f'NPC_{nid}'),
                'tile': p[4], 'lector': lector, 'source': source,
                'marker': _int(p[3], None), 'angle': _int(p[5], 0),
                'record': ln}
            idx['tiles'].add(p[4])
            if lector is not None:
                idx['lectors'].setdefault(str(lector), []).append(nid)
        elif ln.startswith('LOCATION '):
            p = ln.split()
            if len(p) < 7 or p[1] in idx['locations']:
                continue
            idx['locations'][p[1]] = {
                'name': tr.get('translate' + p[1], p[1]),
                'x': _int(p[2]), 'y': _int(p[3]), 'tile': p[4],
                'radius': _int(p[5]), 'type': _int(p[6]), 'source': source}
            idx['tiles'].add(p[4])


def _index_lan(tr, rest, idx, source):
    """Add cues, dialog line counts and flag sets from one .lan."""
    quests = idx['quests']
    cues = idx['cues']
    for tree in tw1_lan.parse_trees(rest):
        m = re.fullmatch(r'translateDQ_(\d+)', tree.id)
        if m and m.group(1) in quests:
            # .lan is key-level merged, later archives win (README 3.2)
            q = quests[m.group(1)]
            q['lines'] = len(tree.entries)
            q['flags'] = sorted({e.flags for e in tree.entries})
        for e in tree.entries:
            if e.cue and e.cue not in cues:
                txt = tr.get(e.tid, '').strip()
                if txt:
                    cues[e.cue] = [e.lector, txt, tree.id]


def _add_marker(idx, spec, args, qid):
    if not spec:
        return
    kind, mi, ti = spec
    if mi >= len(args):
        return
    marker = _int(args[mi], None)
    if marker is None:
        return
    tile = args[ti] if ti is not None and ti < len(args) else ''
    if tile == '(null)':
        tile = ''
    key = f'{kind}|{tile}'
    lst = idx['markers'].setdefault(key, [])
    if marker not in lst:
        lst.append(marker)
    if tile:
        idx['tiles'].add(tile)
    use = idx['marker_use'].setdefault(f'{kind}|{tile}|{marker}', [])
    if qid not in use:
        use.append(qid)


def _int(s, default=0):
    try:
        return int(s)
    except (TypeError, ValueError):
        return default


def _npc_id(tok):
    m = re.fullmatch(r'NPC_(\d+)', tok or '')
    return int(m.group(1)) if m else None


def _quest_id(tok):
    m = re.fullmatch(r'Q_(\d+)', tok or '')
    return int(m.group(1)) if m else None


def index_from_parts(qtx_text, lan_bytes, extra_lans=(), mods=(),
                     progress=None):
    """Build the index dict from in-memory data (testable without a game).

    extra_lans: iterable of (name, bytes) - Content01/02 language archives.
    mods: iterable of (mod_name, qtx_text_or_None, [lan_bytes, ...]).
    """
    idx = {'format': INDEX_FORMAT, 'quests': {}, 'npcs': {}, 'groups': {},
           'locations': {}, 'objects': set(), 'tiles': set(),
           'markers': {}, 'marker_use': {}, 'cues': {}, 'lectors': {}}
    retail_blocks = {}
    if progress:
        progress('lan', 0.35)
    tr, _, rest = tw1_lan.read(lan_bytes)
    for k, v in tr.items():
        m = re.fullmatch(r'translateGROUP_(\d+)', k)
        if m:
            idx['groups'][m.group(1)] = v
    if progress:
        progress('qtx', 0.5)
    _index_qtx(qtx_text, tr, idx, 'retail', retail_blocks)
    if progress:
        progress('lan', 0.6)
    _index_lan(tr, rest, idx, 'retail')
    for name, data in extra_lans:
        try:
            tr2, _, rest2 = tw1_lan.read(data)
        except Exception:
            continue
        _index_lan(tr2, rest2, idx, name)
    n = max(len(mods), 1)
    for i, (name, mqtx, mlans) in enumerate(mods):
        if progress:
            progress(('mods', name), 0.7 + 0.2 * i / n)
        mtr = {}
        parsed = []
        for data in mlans:
            try:
                tr2, _, rest2 = tw1_lan.read(data)
            except Exception:
                continue
            mtr.update(tr2)
            parsed.append((tr2, rest2))
        if mqtx:
            _index_qtx(mqtx, {**tr, **mtr}, idx, name, retail_blocks)
        for tr2, rest2 in parsed:
            _index_lan({**tr, **tr2}, rest2, idx, name)
    idx['object_names'] = {o: tr.get('translate' + o, '')
                           for o in idx['objects']}
    idx['objects'] = sorted(idx['objects'])
    idx['tiles'] = sorted(idx['tiles'], key=_tile_key)
    for lst in idx['markers'].values():
        lst.sort()
    return idx


def _tile_key(name):
    m = re.match(r'([A-Z]+)(\d+)(?:_(\d+))?$', name)
    if not m:
        return (1, name, 0, 0)
    return (0, m.group(1), int(m.group(2)), int(m.group(3) or 0))


def _read_mod(archive):
    """(qtx_text or None, [lan bytes]) of one Mods\\*.wd."""
    qtx, lans = None, []
    for e in tw1_wd.read(archive):
        if e.path == INNER_QTX:
            qtx = e.data.decode('latin-1')
        elif e.path.lower().startswith('language\\') and \
                e.path.lower().endswith('.lan'):
            lans.append(e.data)
    return qtx, lans


def build_index(game_dir, progress=None):
    qtx_path, lan_path = ensure_base(game_dir, progress)
    with open(qtx_path, 'rb') as f:
        qtx_text = f.read().decode('latin-1')
    with open(lan_path, 'rb') as f:
        lan_bytes = f.read()
    extra = []
    for n in ('Content01_Lan.wd', 'Content02_Lan.wd'):
        p = os.path.join(game_dir, 'WDFiles', n)
        if os.path.isfile(p):
            try:
                for e in tw1_wd.read(p):
                    if e.path.lower().endswith('.lan'):
                        extra.append((n, e.data))
            except Exception:
                pass
    mods = []
    paths = sorted(glob.glob(os.path.join(game_dir, 'Mods', '*.wd')))
    for i, p in enumerate(paths):
        name = os.path.basename(p)
        if progress:
            progress(('mods', name), 0.05 + 0.25 * i / len(paths))
        try:
            mqtx, mlans = _read_mod(p)
        except Exception:
            continue
        if mqtx or mlans:
            mods.append((name, mqtx, mlans))
    idx = index_from_parts(qtx_text, lan_bytes, extra, mods, progress)
    idx['game_dir'] = game_dir
    idx['sources'] = source_stamps(source_files(game_dir))
    idx['built'] = time.time()
    return idx


_TREES = {}
_BLOCKS = {}


def load_qtx_blocks(game_dir, force=False):
    """{quest id: (QUEST block text, source)} as the game sees them: base
    qtx, then every Mods\\*.wd that ships the full qtx (later wins). The
    source names the archive that last changed or added the block."""
    key = os.path.normcase(game_dir)
    if key in _BLOCKS and not force:
        return _BLOCKS[key]
    qtx_path, _ = ensure_base(game_dir)
    with open(qtx_path, 'rb') as f:
        sources = [('retail', f.read().decode('latin-1'))]
    for p in sorted(glob.glob(os.path.join(game_dir, 'Mods', '*.wd'))):
        try:
            mqtx, _ = _read_mod(p)
        except Exception:
            continue
        if mqtx:
            sources.append((os.path.basename(p), mqtx))
    out = {}
    for name, text in sources:
        text = text.replace('\r\n', '\n')
        for m in re.finditer(r'^QUEST Q_(\d+) [^\n]*\n.*?^END\n', text,
                             re.M | re.S):
            qid = int(m.group(1))
            if qid not in out or out[qid][0] != m.group(0):
                out[qid] = (m.group(0), name)
    _BLOCKS[key] = out
    return out


def load_trees(game_dir, force=False):
    """{tree id: (DialogTree, translations)} from the base .lan and every
    Mods\\*.wd (later wins, README 3.2). Parsed once per session."""
    key = os.path.normcase(game_dir)
    if key in _TREES and not force:
        return _TREES[key]
    out = {}
    qtx_path, lan_path = ensure_base(game_dir)
    sources = [('retail', open(lan_path, 'rb').read())]
    for n in ('Content01_Lan.wd', 'Content02_Lan.wd'):
        p = os.path.join(game_dir, 'WDFiles', n)
        if os.path.isfile(p):
            try:
                for e in tw1_wd.read(p):
                    if e.path.lower().endswith('.lan'):
                        sources.append((n, e.data))
            except Exception:
                pass
    for p in sorted(glob.glob(os.path.join(game_dir, 'Mods', '*.wd'))):
        try:
            _, lans = _read_mod(p)
        except Exception:
            continue
        for d in lans:
            sources.append((os.path.basename(p), d))
    merged_tr = {}
    for name, data in sources:
        try:
            tr, _, rest = tw1_lan.read(data)
            trees = tw1_lan.parse_trees(rest)
        except Exception:
            continue
        merged_tr.update(tr)
        for tree in trees:
            out[tree.id] = (tree, name)
    result = {tid: (tree, merged_tr, src) for tid, (tree, src) in out.items()}
    _TREES[key] = result
    return result


def cache_valid(idx, game_dir):
    if not isinstance(idx, dict) or idx.get('format') != INDEX_FORMAT:
        return False
    if os.path.normcase(idx.get('game_dir', '')) != os.path.normcase(game_dir):
        return False
    return idx.get('sources') == source_stamps(source_files(game_dir))


def load_index(game_dir, progress=None, force=False):
    """(Index, from_cache, seconds). Reads cache/index.json when the source
    archives are unchanged, otherwise rebuilds and writes it."""
    t0 = time.perf_counter()
    path = cache_path()
    if not force:
        try:
            with open(path, encoding='utf-8') as f:
                idx = json.load(f)
            if cache_valid(idx, game_dir):
                return Index(idx), True, time.perf_counter() - t0
        except (OSError, ValueError):
            pass
    idx = build_index(game_dir, progress)
    if progress:
        progress('save', 0.95)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)
    return Index(idx), False, time.perf_counter() - t0


class Index:
    """Read access to the index dict with a few convenience lookups."""

    def __init__(self, d):
        self.d = d
        self.quests = d['quests']
        self.npcs = d['npcs']
        self.groups = d['groups']
        self.locations = d['locations']
        self.objects = d['objects']
        self.object_names = d.get('object_names', {})
        self.tiles = d['tiles']
        self.markers = d['markers']
        self.cues = d['cues']
        self.lectors = d['lectors']
        self.quest_limit = RETAIL_LIMIT  # set by the app (questlimit.py)

    def quest(self, qid):
        return self.quests.get(str(qid))

    def npc(self, nid):
        return self.npcs.get(str(nid))

    def npc_label(self, nid):
        n = self.npc(nid)
        return f'{n["name"]}  (NPC_{nid})' if n else f'NPC_{nid}'

    def quest_label(self, qid):
        q = self.quest(qid)
        return f'Q_{qid}  {q["title"]}' if q else f'Q_{qid}'

    def free_ids(self, taken=()):
        used = {int(k) for k in self.quests} | set(taken)
        return [i for i in range(MIN_QUEST_ID,
                                 max_quest_id(self.quest_limit) + 1)
                if i not in used]

    def retail_quest_ids(self):
        return sorted(int(k) for k, q in self.quests.items()
                      if q['source'] == 'retail')


def load_translations(game_dir):
    """Merged translations of base .lan, Content*_Lan.wd and mods."""
    trees = load_trees(game_dir)
    for _tree, tr, _src in trees.values():
        return tr
    _, lan_path = ensure_base(game_dir)
    with open(lan_path, 'rb') as f:
        return tw1_lan.read(f.read())[0]


# ---------------------------------------------------------------------------
# quest templates (plan 3.1 "Als Vorlage speichern")

TEMPLATE_EXT = '.tw1quest'


def templates_dir():
    return os.path.join(ROOT, 'templates')


def builtin_templates(kind=None):
    """Templates shipped in questforge2/templates/*.json (point 7 of the
    usability update). Every file is a JSON object with a ``template`` part:
    ``{"kind": "quest"|"enemy", "title": {"de", "en"}, "note": {"de", "en"}}``;
    quest templates carry a full quest (``Quest.to_dict``), enemy templates
    ``args`` for ``ACTION ENEMY_CREATE``. Add a file, it shows up."""
    d = resource_path('questforge2', 'templates')
    out = []
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not name.endswith('.json'):
            continue
        path = os.path.join(d, name)
        try:
            with open(path, encoding='utf-8') as f:
                obj = json.load(f)
        except (OSError, ValueError):
            continue
        info = obj.get('template') if 'template' in obj else obj
        k = info.get('kind')
        if kind and k != kind:
            continue
        out.append({'name': os.path.splitext(name)[0], 'kind': k,
                    'title': info.get('title', {}), 'note': info.get('note', {}),
                    'path': path, 'data': obj})
    return out


def list_templates():
    d = templates_dir()
    if not os.path.isdir(d):
        return []
    return sorted((os.path.splitext(n)[0], os.path.join(d, n))
                  for n in os.listdir(d) if n.endswith(TEMPLATE_EXT))


def save_template(name, quest_dict):
    safe = re.sub(r'[^A-Za-z0-9 _-]+', '', name).strip() or 'Vorlage'
    os.makedirs(templates_dir(), exist_ok=True)
    path = os.path.join(templates_dir(), safe + TEMPLATE_EXT)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(quest_dict, f, indent=2, ensure_ascii=False)
    return path


def load_template(path):
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    if not isinstance(d, dict):
        raise ValueError('template must be a JSON object')
    return d
