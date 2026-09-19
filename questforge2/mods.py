"""Mods as a third source next to the game and the project (update 5b).

A mod is a ``.wd`` archive or an unpacked folder. It is read with the
existing modules (``tw1_wd`` directory layout, ``tw1_qtx`` block syntax via
``data``, ``tw1_lan``, ``tw1_lnd``); every piece of content keeps its origin:
mod name, archive path, inner file and, for map data, the tile.

What is proven and where it comes from:

- Marker name per quest line: SDK ``Campaigns/Missions/PInc/PEnums.ech``
  (``MARKER_ACTION_CREATE_ENEMY "MARKER_QUEST_CREATE_ENEMY"`` and so on),
  table ``MARKER_NAMES``. Measured 2026-09-16 against the game maps: all
  287 marker references of the retail quests and all 216 NPC start markers
  (``MARKER_QUEST_START``) exist on their tile under these names.
- Tile names: ``Levels\\Map_E01.lnd`` in ``Levels.wd`` is the tile ``E1``
  of the quest file, interiors ``Map_B08_1.lnd`` are ``B8_1``.
- Retail maps: ``Levels.wd``, overridden by ``Update11-15.wd`` and
  ``Update16.wd`` (load order of ``wd_metadaten.REIHENFOLGE``, later wins).
- Two archives with the same inner file: the later one wins (README 3.1).
  UNVERIFIED: which of two mods the game loads later. The tool uses the order
  of the project's mod list.

The directory metadata (flags, resource name, class id, GUID) of an entry
lives only in the archive directory; writing into a mod goes through
``export.pack_archive`` (buglord's ``wdio``) which verifies every untouched
entry, and ``metadata_problems`` compares the result with the game archives
like ``wd_metadaten.pruefen``.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import struct
import uuid
import zlib

import tw1_lan
import tw1_lnd
import tw1_wd

from . import data, model

BS = chr(92)
MOD_FORMAT = 2            # 3.9.3: maps with a marker text were "unreadable"
MARKER_CACHE_FORMAT = 1
INNER_QTX = data.INNER_QTX
INNER_LAN = data.INNER_LAN

# index marker kind (data._FC_MARKERS/_ACTION_MARKERS) -> marker name in the
# .lnd, SDK PEnums.ech
MARKER_NAMES = {
    'Q_Solve': 'MARKER_QUEST_POINT',
    'Gate': 'MARKER_GATE',
    'Q_Action_Walk': 'MARKER_QUEST_WALK',
    'Q_Action_Teleport': 'MARKER_QUEST_TELEPORT',
    'Q_Action_Create_Object': 'MARKER_QUEST_CREATE_OBJECT',
    'Q_Action_Create_Enemy': 'MARKER_QUEST_CREATE_ENEMY',
    'Q_Action_Clear_Area': 'MARKER_QUEST_CLEAR_AREA',
    'Q_Action_Kill_Area': 'MARKER_QUEST_KILL_AREA',
}
NPC_MARKER = 'MARKER_QUEST_START'       # PEnums.ech MARKER_QUEST_START


def editor_name(marker):
    """Name of a marker in the Two Worlds Editor's object tree (Special
    Objects > Quests), e.g. MARKER_QUEST_START -> Q_Giver."""
    if marker == NPC_MARKER:
        return 'Q_Giver'
    for kind, name in MARKER_NAMES.items():
        if name == marker and kind.startswith('Q_'):
            return kind
    return marker
CHEST_MARKER = 'MARKER_CHEST'           # PEnums.ech MARKER_CONTAINER

# game archives with maps, later wins
RETAIL_MAP_ARCHIVES = ('Levels.wd', 'Update11-15.wd', 'Update16.wd')
# game archives whose directory entries are the metadata template
TEMPLATE_ARCHIVES = ('Scripts.wd', 'Levels.wd', 'Parameters.wd',
                     'Graphics.wd', 'Update11-15.wd', 'Update16.wd')

_LND = re.compile(r'^levels[\\/]map_([a-z])(\d{2})(_\d+)?\.lnd$', re.I)
_TILE = re.compile(r'^([A-Z])(\d{1,2})(_\d+)?$')


def tile_of_lnd(inner):
    """``Levels\\Map_E01.lnd`` -> ``E1``; None for other files."""
    m = _LND.match(inner or '')
    if not m:
        return None
    return f'{m.group(1).upper()}{int(m.group(2))}{m.group(3) or ""}'


def lnd_of_tile(tile):
    m = _TILE.match(tile or '')
    if not m:
        return None
    return f'Levels{BS}Map_{m.group(1)}{int(m.group(2)):02d}{m.group(3) or ""}.lnd'


def mod_name(path):
    return os.path.basename(os.path.normpath(path))


def cache_dir():
    return os.path.join(data.ROOT, 'cache', 'mods')


# ---------------------------------------------------------------------------
# archive directory

class DirEntry:
    __slots__ = ('path', 'flags', 'offset', 'clen', 'rlen', 'res',
                 'class_id', 'guid')

    def __init__(self, path, flags, offset, clen, rlen, res, class_id, guid):
        self.path = path
        self.flags = flags
        self.offset = offset
        self.clen = clen
        self.rlen = rlen
        self.res = res
        self.class_id = class_id
        self.guid = guid

    def meta(self):
        return (self.flags, self.res, self.class_id, self.guid)


def wd_directory(path):
    """Every directory entry of a WD 0x200 archive, file data untouched."""
    with open(path, 'rb') as f:
        f.seek(-4, 2)
        dir_off = struct.unpack('<I', f.read(4))[0]
        f.seek(-dir_off, 2)
        raw = f.read()
    t = zlib.decompressobj().decompress(raw)
    off = 8
    count = struct.unpack_from('<H', t, off)[0]
    off += 2
    out = []
    for _ in range(count):
        n = t[off]
        off += 1
        name = t[off:off + n].decode('latin-1')
        off += n
        flags, foff, clen, rlen = struct.unpack_from('<BIII', t, off)
        off += 13
        res = class_id = guid = None
        if flags & 0x08:
            xl = t[off]
            off += 1
            res = t[off:off + xl]
            off += xl
        if flags & 0x10:
            class_id = struct.unpack_from('<I', t, off)[0]
            off += 4
        if flags & 0x20:
            guid = t[off:off + 16]
            off += 16
        out.append(DirEntry(name, flags, foff, clen, rlen, res, class_id,
                            guid))
    if off != len(t):
        raise ValueError(f'{path}: {len(t) - off} bytes left in directory')
    return out


def wd_data(path, entry):
    """Uncompressed bytes of one entry."""
    with open(path, 'rb') as f:
        f.seek(entry.offset)
        raw = f.read(entry.clen)
    if entry.flags & 0x01:
        return zlib.decompressobj().decompress(raw)
    return raw


def _markers_prefix(fh, offset, clen, compressed):
    """Marker section of an archived .lnd, decompressing only as much as
    needed (the markers sit in the first kilobytes of a 4 MB map)."""
    fh.seek(offset)
    d = zlib.decompressobj() if compressed else None
    buf = b''
    left = clen
    while True:
        try:
            return tw1_lnd.markers_full(buf)
        except (struct.error, IndexError):
            if left <= 0:
                raise ValueError('marker section not found')
        chunk = fh.read(min(32768 if buf else 16384, left))
        left -= len(chunk)
        buf += d.decompress(chunk) if d else chunk


def _plain_markers(markers):
    return {name: [[i, x, y, z, a] for i, (x, y, z, a) in lst]
            for name, lst in markers.items()}


def file_entry(blob):
    """(flags, res, class_id, guid, data) of a staged file. Files unpacked
    by wdio and editor exports carry the directory metadata as a first zlib
    stream ``FF A1 D0 <flags> ...``; a plain file has none (flags None)."""
    if blob[:2] == b'\x78\x9c':
        d = zlib.decompressobj()
        head = d.decompress(blob)
        rest = d.unused_data
        if head[:3] == b'\xff\xa1\xd0' and len(head) >= 4:
            flags = head[3]
            off = 4
            res = class_id = guid = None
            if flags & 0x08:
                n = head[off]
                res = head[off + 1:off + 1 + n]
                off += 1 + n
            if flags & 0x10:
                class_id = struct.unpack_from('<I', head, off)[0]
                off += 4
            if flags & 0x20:
                guid = head[off:off + 16]
            body = zlib.decompressobj().decompress(rest) if flags & 0x01 \
                else rest
            return flags, res, class_id, guid, body
    return None, None, None, None, blob


# ---------------------------------------------------------------------------
# retail maps

def marker_cache_path():
    return os.path.join(data.ROOT, 'cache', 'lnd_markers.json')


def _stamps(paths):
    out = {}
    for p in paths:
        if os.path.isfile(p):
            st = os.stat(p)
            out[os.path.normcase(p)] = [int(st.st_mtime), st.st_size]
    return out


def retail_markers(game_dir, progress=None, force=False):
    """{tile: {'archive', 'inner', 'markers': {name: [[id, x, y, z, angle]]}}}
    of the game maps, cached in ``cache/lnd_markers.json``."""
    paths = [os.path.join(game_dir, 'WDFiles', a) for a in RETAIL_MAP_ARCHIVES]
    stamps = _stamps(paths)
    path = marker_cache_path()
    if not force:
        try:
            with open(path, encoding='utf-8') as f:
                cached = json.load(f)
            if cached.get('format') == MARKER_CACHE_FORMAT and \
                    cached.get('sources') == stamps:
                return cached['tiles']
        except (OSError, ValueError):
            pass
    found = {}
    for p in paths:
        if not os.path.isfile(p):
            continue
        for e in wd_directory(p):
            tile = tile_of_lnd(e.path)
            if tile:
                found[tile] = (p, e)
    tiles = {}
    by_archive = {}
    for tile, (p, e) in found.items():
        by_archive.setdefault(p, []).append((tile, e))
    done, total = 0, max(len(found), 1)
    for p, lst in by_archive.items():
        with open(p, 'rb') as fh:
            for tile, e in sorted(lst, key=lambda te: te[1].offset):
                try:
                    m = _markers_prefix(fh, e.offset, e.clen, e.flags & 0x01)
                    tiles[tile] = {'archive': os.path.basename(p),
                                   'inner': e.path,
                                   'markers': _plain_markers(m)}
                except ValueError:
                    tiles[tile] = {'archive': os.path.basename(p),
                                   'inner': e.path, 'markers': {},
                                   'error': 'unreadable'}
                done += 1
                if progress and done % 10 == 0:
                    progress(done / total)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'format': MARKER_CACHE_FORMAT, 'sources': stamps,
                   'tiles': tiles}, f, separators=(',', ':'))
    os.replace(tmp, path)
    return tiles


def marker_ids(tile_info, name):
    """Instance ids of one marker name in a tile record."""
    return {m[0] for m in (tile_info or {}).get('markers', {}).get(name, [])}


def missing_markers(retail_tile, mod_tile):
    """Retail markers ``[name, id]`` the mod tile no longer has."""
    out = []
    mod = mod_tile.get('markers', {})
    for name, lst in sorted((retail_tile or {}).get('markers', {}).items()):
        have = {m[0] for m in mod.get(name, [])}
        out += [[name, m[0]] for m in lst if m[0] not in have]
    return out


# ---------------------------------------------------------------------------
# retail quest file parts (comparison base for "new" and "changed")

def qtx_parts(text):
    """{'quests': {qid: block}, 'npcs': {nid: line}, 'locations': {name:
    line}, 'containers': {name: line}} of a full .qtx text."""
    text = text.replace(chr(13) + chr(10), chr(10))
    out = {'quests': {}, 'npcs': {}, 'locations': {}, 'containers': {}}
    for qid, _h, _s, block in data._split_quests(text):
        out['quests'][qid] = block
    for ln in text.split(chr(10)):
        p = ln.split()
        if len(p) < 2:
            continue
        if p[0] == 'NPC' and p[1].startswith('NPC_'):
            nid = data._npc_id(p[1])
            if nid is not None:
                out['npcs'][nid] = ln.rstrip()
        elif p[0] == 'LOCATION':
            out['locations'][p[1]] = ln.rstrip()
        elif p[0] == 'CONTAINER':
            out['containers'][p[1]] = ln.rstrip()
    return out


def _state(key, value, base):
    if key not in base:
        return 'new'
    return 'same' if base[key] == value else 'changed'


# ---------------------------------------------------------------------------
# reading one mod

def _folder_files(path):
    out = {}
    for dirpath, _dirs, files in os.walk(path):
        for fn in files:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, path).replace('/', BS)
            if rel in ('GUID', 'FILETIME'):
                continue
            out[rel] = full
    return out


def _relevant(inner):
    low = inner.lower()
    return (low == INNER_QTX.lower() or low.endswith('.lan')
            or tile_of_lnd(inner) is not None)


def mod_stamp(path):
    if os.path.isfile(path):
        st = os.stat(path)
        return [int(st.st_mtime), st.st_size]
    h = hashlib.sha1()
    for rel, full in sorted(_folder_files(path).items()):
        if _relevant(rel):
            st = os.stat(full)
            h.update(f'{rel}|{int(st.st_mtime)}|{st.st_size};'.encode(
                'latin-1', 'replace'))
    return [h.hexdigest()]


def read_files(path, wanted=None):
    """{inner: bytes} of the relevant files of a mod (or of ``wanted``).
    Archive entries come uncompressed; folder files are unwrapped from the
    wdio header form."""
    out = {}
    if os.path.isfile(path):
        for e in wd_directory(path):
            if (wanted is None and _relevant(e.path)) or (
                    wanted is not None and e.path in wanted):
                out[e.path] = wd_data(path, e)
        return out
    for rel, full in _folder_files(path).items():
        if (wanted is None and _relevant(rel)) or (
                wanted is not None and rel in wanted):
            with open(full, 'rb') as f:
                out[rel] = file_entry(f.read())[4]
    return out


def scan_mod(path, base_parts, retail_tiles, translations=None):
    """Content of one mod with its origin (see module doc)."""
    name = mod_name(path)
    kind = 'wd' if os.path.isfile(path) else 'folder'
    info = {'format': MOD_FORMAT, 'path': path, 'name': name, 'kind': kind,
            'stamp': mod_stamp(path), 'qtx': None, 'quests': {}, 'npcs': {},
            'locations': {}, 'containers': {}, 'lans': [], 'trees': {},
            'texts': 0, 'tiles': {}, 'error': None}
    if not os.path.exists(path):
        info['error'] = 'missing'
        return info
    try:
        files = read_files(path)
    except (OSError, ValueError, zlib.error, struct.error) as e:
        info['error'] = str(e)
        return info
    tr = dict(translations or {})
    for inner in sorted((k for k in files if k.lower().endswith('.lan')),
                        key=str.lower):
        info['lans'].append(inner)
        try:
            mtr, _aliases, rest = tw1_lan.read(files[inner])
            trees = tw1_lan.parse_trees(rest)
        except Exception:                  # unreadable .lan: listed only
            continue
        tr.update(mtr)
        info['texts'] += len(mtr)
        for tree in trees:
            info['trees'][tree.id] = inner
    qtx_inner = next((k for k in files if k.lower() == INNER_QTX.lower()),
                     None)
    if qtx_inner:
        info['qtx'] = qtx_inner
        text = files[qtx_inner].decode('latin-1')
        parts = qtx_parts(text)
        for qid, block in parts['quests'].items():
            st = _state(qid, block, base_parts['quests'])
            if st == 'same':
                continue
            header = block.split(chr(10), 1)[0].split()[2:]
            q = {'state': st, 'title': tr.get(f'translateQ_{qid}', ''),
                 'group': data._int(header[1]) if len(header) > 1 else 0,
                 'giver': None, 'fc': None, 'aoq': [],
                 'block_sha': hashlib.sha1(block.encode('latin-1')
                                           ).hexdigest()}
            for ln in block.split(chr(10))[1:]:
                toks = ln.split()
                if len(toks) >= 3 and toks[0] == 'GIVER':
                    q['giver'] = data._npc_id(toks[2])
                elif toks and toks[0] == 'FC':
                    q['fc'] = toks[1:]
                elif len(toks) >= 4 and toks[0] == 'AOQ':
                    q['aoq'].append([toks[1], toks[2],
                                     data._quest_id(toks[3])])
            info['quests'][str(qid)] = q
        for nid, ln in parts['npcs'].items():
            st = _state(nid, ln, base_parts['npcs'])
            if st != 'same':
                p = ln.split()
                info['npcs'][str(nid)] = {
                    'state': st, 'record': ln,
                    'name': tr.get(f'translateNPC_{nid}', f'NPC_{nid}'),
                    'tile': p[4] if len(p) > 4 else '',
                    'marker': data._int(p[3], None) if len(p) > 3 else None}
        for key in ('locations', 'containers'):
            for lname, ln in parts[key].items():
                st = _state(lname, ln, base_parts[key])
                if st != 'same':
                    p = ln.split()
                    tile = p[4] if key == 'locations' and len(p) > 4 else (
                        p[3] if len(p) > 3 else '')
                    info[key][lname] = {'state': st, 'record': ln,
                                        'tile': tile}
    for inner, blob in files.items():
        tile = tile_of_lnd(inner)
        if not tile:
            continue
        rec = {'inner': inner, 'markers': {}, 'missing': [], 'error': None}
        try:
            rec['markers'] = _plain_markers(tw1_lnd.markers_full(blob))
        except (struct.error, IndexError, zlib.error, ValueError):
            rec['error'] = 'unreadable'
        if tile in retail_tiles and not rec['error']:
            rec['missing'] = missing_markers(retail_tiles[tile], rec)
        rec['state'] = 'changed' if tile in retail_tiles else 'new'
        info['tiles'][tile] = rec
    return info


def _cache_file(path):
    key = hashlib.sha1(os.path.normcase(os.path.abspath(path)).encode(
        'utf-8')).hexdigest()[:16]
    return os.path.join(cache_dir(), key + '.json')


def load_mod(path, base_parts, retail_tiles, translations=None, force=False,
             base_stamp=None):
    """scan_mod with a cache per mod (mtime/size of the archive or of the
    relevant folder files, plus the stamp of the comparison base)."""
    cf = _cache_file(path)
    stamp = mod_stamp(path) if os.path.exists(path) else None
    if not force and stamp is not None:
        try:
            with open(cf, encoding='utf-8') as f:
                cached = json.load(f)
            if (cached.get('format') == MOD_FORMAT
                    and cached.get('stamp') == stamp
                    and cached.get('base') == base_stamp
                    and os.path.normcase(cached.get('path', ''))
                    == os.path.normcase(path)):
                return cached
        except (OSError, ValueError):
            pass
    info = scan_mod(path, base_parts, retail_tiles, translations)
    info['base'] = base_stamp
    if not info['error']:
        os.makedirs(cache_dir(), exist_ok=True)
        tmp = cf + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, separators=(',', ':'))
        os.replace(tmp, cf)
    return info


# ---------------------------------------------------------------------------
# the mods of a project

class ModSet:
    """Mods of the project in load order (``project.mods``)."""

    def __init__(self, entries, infos, retail_tiles, tile_choice=None):
        self.entries = entries          # [{'path', 'enabled'}]
        self.infos = infos              # [scan dict], same order
        self.retail_tiles = retail_tiles or {}
        self.tile_choice = tile_choice or {}

    def enabled(self):
        return [i for e, i in zip(self.entries, self.infos)
                if e.get('enabled', True) and not i.get('error')]

    def by_path(self, path):
        key = os.path.normcase(os.path.abspath(path))
        for i in self.infos:
            if os.path.normcase(os.path.abspath(i['path'])) == key:
                return i
        return None

    def by_name(self, name):
        for i in self.infos:
            if i['name'] == name:
                return i
        return None

    def quest_ids(self, states=('new',)):
        """Quest ids the enabled mods add (for free id computation)."""
        return {int(k) for i in self.enabled()
                for k, q in i['quests'].items() if q['state'] in states}

    def quests(self):
        """[(mod info, qid, quest info)] of the enabled mods."""
        return [(i, int(k), q) for i in self.enabled()
                for k, q in sorted(i['quests'].items(),
                                   key=lambda kv: int(kv[0]))]

    def tile_providers(self, tile):
        return [i for i in self.enabled() if tile in i['tiles']]

    def tile_conflicts(self):
        """{tile: [mod names]} for tiles that several enabled mods bring."""
        out = {}
        for i in self.enabled():
            for tile in i['tiles']:
                out.setdefault(tile, []).append(i['name'])
        return {k: v for k, v in out.items() if len(v) > 1}

    def id_clashes(self, project=None):
        """[(qid, [names])]: new quest ids two mods use, or a mod and an own
        quest of the project."""
        seen = {}
        for i, qid, q in self.quests():
            if q['state'] == 'new':
                seen.setdefault(qid, []).append(i['name'])
        if project is not None:
            for q in project.quests:
                if q.id in seen and not q.retail:
                    seen[q.id].append('project')
        return sorted((k, v) for k, v in seen.items() if len(v) > 1)

    def marker_rows(self, kind, tile=None):
        """[(num, tile, mod info or None, blocked)] of one marker kind: all
        markers of the game maps, plus the ones the enabled mods add.
        ``blocked`` lists missing retail markers of the mod tile."""
        name = MARKER_NAMES.get(kind)
        if not name:
            return []
        rows = []
        tiles = [tile] if tile else sorted(
            set(self.retail_tiles) | {t for i in self.enabled()
                                      for t in i['tiles']},
            key=data._tile_key)
        for tl in tiles:
            base = marker_ids(self.retail_tiles.get(tl), name)
            rows += [(n, tl, None, []) for n in sorted(base)]
            for i in self.enabled():
                rec = i['tiles'].get(tl)
                if not rec:
                    continue
                for n in sorted(marker_ids(rec, name) - base):
                    rows.append((n, tl, i, rec.get('missing') or []))
        return rows


def open_modset(project, game_dir, base_parts, retail_tiles, translations,
                base_stamp=None, force=False):
    infos = [load_mod(e['path'], base_parts, retail_tiles, translations,
                      force, base_stamp) for e in project.mods]
    return ModSet(project.mods, infos, retail_tiles, project.mod_tiles)


def game_mods(game_dir):
    """``<game>\\Mods\\*.wd`` paths, sorted."""
    d = os.path.join(game_dir or '', 'Mods')
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, n) for n in os.listdir(d)
                  if n.lower().endswith('.wd'))


# ---------------------------------------------------------------------------
# marker dependencies of the project

def marker_refs(block_text):
    """[(kind, tile, number)] of the marker references in a QUEST block,
    with the same tables as the index."""
    out = []
    for _qid, _h, subs, _b in data._split_quests(block_text):
        for toks in subs:
            kw, args = toks[0], toks[1:]
            if kw == 'FC' and args:
                spec, rest = data._FC_MARKERS.get(args[0]), args[1:]
            elif kw == 'ACTION' and len(args) >= 2:
                spec, rest = data._ACTION_MARKERS.get(args[0]), args[2:]
            else:
                continue
            if not spec:
                continue
            kind, mi, ti = spec
            if mi >= len(rest):
                continue
            num = data._int(rest[mi], None)
            tile = rest[ti] if ti is not None and ti < len(rest) else ''
            if num is not None and tile and tile != '(null)':
                out.append((kind, tile.upper(), num))
    return out


def quest_block(quest):
    from . import export, retail
    if quest.retail:
        return retail.block_text(quest)
    return export.build_quest_block(quest).emit()


def dependencies(project, modset):
    """Map tiles of mods the project's quests need because they use a marker
    only that mod has. [{'tile', 'mod', 'path', 'inner', 'uses', 'missing',
    'providers', 'status'}], status 'ok' | 'missing' | 'conflict'."""
    need = {}
    for q in project.quests:
        if q.id is None:
            continue
        try:
            refs = marker_refs(quest_block(q))
        except Exception:            # an invalid quest: validation says why
            continue
        for kind, tile, num in refs:
            name = MARKER_NAMES.get(kind)
            if not name or num in marker_ids(modset.retail_tiles.get(tile),
                                             name):
                continue
            providers = [i for i in modset.tile_providers(tile)
                         if num in marker_ids(i['tiles'][tile], name)]
            if not providers:
                continue
            d = need.setdefault(tile, {'uses': [], 'providers': set()})
            d['uses'].append((q.id, kind, num))
            d['providers'].update(i['name'] for i in providers)
    out = []
    for tile in sorted(need, key=data._tile_key):
        d = need[tile]
        all_names = [i['name'] for i in modset.tile_providers(tile)]
        choice = modset.tile_choice.get(tile)
        if choice in all_names:
            mod = choice
        elif len(d['providers']) == 1:
            mod = next(iter(d['providers']))
        else:
            mod = None
        info = modset.by_name(mod) if mod else None
        rec = info['tiles'].get(tile) if info else None
        status = 'ok'
        if mod is None or (len(all_names) > 1 and choice not in all_names
                           and len(d['providers']) > 1):
            status = 'conflict'
        elif rec and rec.get('missing'):
            status = 'missing'
        out.append({'tile': tile, 'mod': mod,
                    'path': info['path'] if info else None,
                    'inner': rec['inner'] if rec else lnd_of_tile(tile),
                    'uses': d['uses'], 'missing': (rec or {}).get('missing',
                                                                  []),
                    'providers': sorted(all_names), 'status': status})
    return out


def dependency_entries(deps, log=print):
    """{inner: tw1_wd.Entry} of the map files to pack into the project's
    archive, with the directory metadata of the mod."""
    out = {}
    for d in deps:
        if d['status'] != 'ok' or not d['path']:
            continue
        path, inner = d['path'], d['inner']
        if os.path.isfile(path):
            ent = next((e for e in wd_directory(path) if e.path == inner),
                       None)
            if ent is None:
                raise model.ModelError(f'{inner} not in {path}')
            out[inner] = tw1_wd.Entry(inner, wd_data(path, ent), ent.flags,
                                      ent.res or b'', ent.class_id or 0,
                                      ent.guid or b'')
        else:
            full = os.path.join(path, *inner.split(BS))
            with open(full, 'rb') as f:
                flags, res, class_id, guid, body = file_entry(f.read())
            if flags is None:
                # a bare map body: flags and class id of the game's own
                # entry, a fresh GUID (official updates never reuse one)
                flags, res, class_id = 0x33, None, 20044
                guid = uuid.uuid4().bytes
                log(('lnd_meta', inner))
            out[inner] = tw1_wd.Entry(inner, body, flags, res or b'',
                                      class_id or 0, guid or b'')
        log(('lnd', inner, d['mod']))
        # the physics of the same tile (Levels\physic\Map_<cell>.phx): a tile
        # changed in the editor comes with its own collision; the retail one
        # would not match the new ground. Stored uncompressed like retail.
        phx = _phx_inner(inner)
        if os.path.isfile(path):
            ent = next((e for e in wd_directory(path) if e.path.lower()
                        == phx.lower()), None)
            if ent is not None:
                out[ent.path] = tw1_wd.Entry(ent.path, wd_data(path, ent),
                                             ent.flags, ent.res or b'',
                                             ent.class_id or 0,
                                             ent.guid or b'')
                log(('lnd', ent.path, d['mod']))
        else:
            full = os.path.join(path, *phx.split(BS))
            if os.path.isfile(full):
                with open(full, 'rb') as f:
                    flags, res, class_id, guid, body = file_entry(f.read())
                out[phx] = tw1_wd.Entry(phx, body, flags or 0x00, res or b'',
                                        class_id or 0, guid or b'')
                log(('lnd', phx, d['mod']))
    return out


def _phx_inner(lnd_inner):
    """Levels\\Map_E01.lnd -> Levels\\physic\\Map_E01.phx"""
    head, name = lnd_inner.rsplit(BS, 1)
    return f'{head}{BS}physic{BS}{os.path.splitext(name)[0]}.phx'


# ---------------------------------------------------------------------------
# metadata check (wd_metadaten.pruefen)

def metadata_template(game_dir):
    """{inner lower: (flags, res, class_id, has guid)} of the game archives,
    later archive wins."""
    wdf = os.path.join(game_dir, 'WDFiles')
    out = {}
    names = [a for a in TEMPLATE_ARCHIVES
             if os.path.isfile(os.path.join(wdf, a))]
    for a in names:
        for e in wd_directory(os.path.join(wdf, a)):
            out[e.path.lower()] = (e.flags, e.res, e.class_id,
                                   e.guid is not None)
    return out


def metadata_problems(archive, template):
    """Entries whose flags, resource name or class id differ from the game
    archives, or that lost their GUID. The qtx and lan are left out: the
    game loads a qtx packed with 0x01 as well (SKILL, community mods)."""
    out = []
    for e in wd_directory(archive):
        low = e.path.lower()
        want = template.get(low)
        if want is None or low.endswith(('.qtx', '.lan', 'editordef.txt')):
            continue
        flags, res, class_id, has_guid = want
        if (e.flags, e.res, e.class_id) != (flags, res, class_id):
            out.append(f'{e.path}: flags={e.flags:#04x} id={e.class_id} '
                       f'-> game flags={flags:#04x} id={class_id}')
        elif has_guid and e.guid is None:
            out.append(f'{e.path}: GUID missing')
    return out


# ---------------------------------------------------------------------------
# backups

def backup_stem(path):
    return os.path.normpath(path) + '.bak-'


def list_backups(path):
    stem = os.path.basename(backup_stem(path))
    d = os.path.dirname(os.path.normpath(path))
    if not os.path.isdir(d):
        return []
    return sorted((os.path.join(d, n) for n in os.listdir(d)
                   if n.startswith(stem)), reverse=True)


def make_backup(path, today=None, files=None):
    """``<mod>.wd.bak-<date>`` next to the archive, or for a folder
    ``<folder>.bak-<date>`` with the files about to change. Made once per
    day, so it holds the state before the first write. Returns the path or
    None when it already existed."""
    date = (today or datetime.date.today()).isoformat()
    dest = backup_stem(path) + date
    if os.path.exists(dest):
        if os.path.isdir(dest) and files:
            for rel in files:
                src = os.path.join(path, *rel.split(BS))
                tgt = os.path.join(dest, *rel.split(BS))
                if os.path.isfile(src) and not os.path.exists(tgt):
                    os.makedirs(os.path.dirname(tgt), exist_ok=True)
                    shutil.copy2(src, tgt)
        return None
    if os.path.isfile(path):
        shutil.copy2(path, dest)
    else:
        for rel in files or ():
            src = os.path.join(path, *rel.split(BS))
            tgt = os.path.join(dest, *rel.split(BS))
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(tgt), exist_ok=True)
                shutil.copy2(src, tgt)
        os.makedirs(dest, exist_ok=True)
    return dest


def restore_backup(path, backup):
    """Put a backup back. The current state is kept as
    ``<mod>.bak-<date>-before-restore`` first."""
    stamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
    keep = backup_stem(path) + stamp + '-before-restore'
    if os.path.isfile(path):
        shutil.copy2(path, keep)
        shutil.copy2(backup, path)
        return keep
    os.makedirs(keep, exist_ok=True)
    for rel, full in _folder_files(backup).items():
        cur = os.path.join(path, *rel.split(BS))
        if os.path.isfile(cur):
            tgt = os.path.join(keep, *rel.split(BS))
            os.makedirs(os.path.dirname(tgt), exist_ok=True)
            shutil.copy2(cur, tgt)
        os.makedirs(os.path.dirname(cur), exist_ok=True)
        shutil.copy2(full, cur)
    return keep


# ---------------------------------------------------------------------------
# change log (tooltip "changed on <date>")

def changes_path():
    return os.path.join(cache_dir(), 'changes.json')


def load_changes():
    try:
        with open(changes_path(), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def note_change(path, qid, when=None):
    d = load_changes()
    key = os.path.normcase(os.path.abspath(path))
    d.setdefault(key, {})[str(qid)] = (when or datetime.datetime.now()
                                       ).strftime('%Y-%m-%d %H:%M')
    os.makedirs(cache_dir(), exist_ok=True)
    with open(changes_path(), 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=1)


def changed_on(path, qid, changes=None):
    d = changes if changes is not None else load_changes()
    return d.get(os.path.normcase(os.path.abspath(path)), {}).get(str(qid))


# ---------------------------------------------------------------------------
# reading and writing a mod quest

def quest_sources(path):
    """(qtx text, [(inner, lan bytes)]) of a mod."""
    files = read_files(path)
    qtx = next((v for k, v in files.items()
                if k.lower() == INNER_QTX.lower()), None)
    lans = sorted(((k, v) for k, v in files.items()
                   if k.lower().endswith('.lan')), key=lambda kv: kv[0].lower())
    return (qtx.decode('latin-1') if qtx is not None else None), lans


def lan_target(lans, qid):
    """The .lan of the mod that carries the quest's dialog or texts (the
    last one in name order, as the overlays load after the base), else the
    full quest .lan, else None."""
    tid = f'translateDQ_{qid}'
    key = f'translateQ_{qid}'
    hit = None
    for inner, blob in lans:
        try:
            tr, _a, rest = tw1_lan.read(blob)
            ids = {t.id for t in tw1_lan.parse_trees(rest)}
        except Exception:
            continue
        if tid in ids or key in tr:
            hit = inner
    if hit:
        return hit
    return next((k for k, _v in lans if k.lower() == INNER_LAN.lower()), None)


def overlay_inner(path):
    stem = re.sub(r'[^A-Za-z0-9_-]+', '', os.path.splitext(mod_name(path))[0])
    return f'Language{BS}ZZ_QF_Mod_{stem or "Mod"}.lan'


def write_quest(path, quest, index, master_lan, game_dir=None, log=print,
                today=None):
    """Write one quest back into its mod: qtx block and dialog/texts. Makes
    the dated backup first, packs with wdio (archive) or writes the files
    (folder), checks the metadata. Returns {'backup', 'files', 'problems'}."""
    from . import export
    text, lans = quest_sources(path)
    if text is None:
        raise model.ModelError(f'{mod_name(path)} has no {INNER_QTX}')
    new_text, _ = export.patch_qtx(text, [quest], index)
    files = {INNER_QTX: new_text.encode('latin-1')}
    target = lan_target(lans, quest.id)
    lan_map = dict(lans)
    if target is None and overlay_inner(path) in lan_map:
        # our overlay from an earlier save: rebuild it with this quest,
        # otherwise the texts of the quest saved before are gone
        target = overlay_inner(path)
    if target:
        files[target] = export.build_lan(lan_map[target], [quest])[0]
    else:
        files[overlay_inner(path)] = export.build_lan(master_lan, [quest])[1]
    template = metadata_template(game_dir) if game_dir else None
    before = metadata_problems(path, template) if (
        template is not None and os.path.isfile(path)) else []
    if os.path.isfile(path):
        backup = make_backup(path, today)
        if backup:
            log(('backup', backup))
        export.pack_archive(path, files, log, backup=False)
        after = metadata_problems(path, template) if template is not None \
            else []
        new = [p for p in after if p not in before]
        if new:
            raise model.ModelError('metadata check failed: '
                                   + '; '.join(new[:5]))
    else:
        existing = _folder_files(path)
        qtx_rel = next((k for k in existing
                        if k.lower() == INNER_QTX.lower()), INNER_QTX)
        rel_files = {}
        for inner, blob in files.items():
            rel = next((k for k in existing if k.lower() == inner.lower()),
                       inner)
            rel_files[qtx_rel if inner == INNER_QTX else rel] = blob
        backup = make_backup(path, today, list(rel_files))
        if backup:
            log(('backup', backup))
        for rel, blob in rel_files.items():
            dest = os.path.join(path, *rel.split(BS))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(blob)
        files = rel_files
    note_change(path, quest.id)
    return {'backup': backup, 'files': sorted(files), 'problems': before}
