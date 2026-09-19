"""Markers placed on the map inside the tool, and missing game markers put
back into a mod's map (3.9.0).

Both end up as map tiles in ``<project>_levels`` - the project's own folder
mod that also takes tiles saved by the Two Worlds editor (editormaps.py).
From there the rest of the tool already does the right thing: the mod scan
reads the markers (validation sees them), the export packs the tiles the
quests need, and after the export the tool reminds of the level header
cache (LevelHeadersCacheGen.bat; without it the game does not know new
markers).

A tile is always rebuilt from its BASE, never patched twice:
- the tile of a foreign mod the project uses for that tile (its choice in
  ``project.mod_tiles``, else the only mod that brings it),
- else a tile the user imported from the editor (kept as
  ``<project>_levels_base`` once we write over it),
- else the game's tile from Levels.wd.
Then the game markers the base lacks are added (a mod map made from an old
copy of the tile would break original quests), then the placed markers.

The file is written like the editor writes it (measured in editormaps.py):
zlib(FF A1 D0, flags 0x33, class id 20044, GUID) + zlib(map body). The
GUID is made once per tile and kept in the project.

Project data (``project.extra``, saved with the project):
- ``placed_markers``: [{'name', 'num', 'tile', 'x', 'y', 'z', 'angle',
  'quest'}] - name is the engine name (MARKER_QUEST_START ...)
- ``fill_tiles``: tiles whose base only gets the game markers put back
- ``generated_tiles``: tiles this module wrote into the levels folder
- ``tile_guids``: {tile: GUID hex}
"""

import os
import shutil
import struct
import uuid
import zlib

import tw1_lnd

from . import editormaps, lndmap, mods

BS = chr(92)
# the game's own flags for a map (Levels.wd: 0x33); the editor writes 0x31,
# which loads too (Kira campaign), but the export's metadata check expects
# what the game has
FLAGS = 0x33
CLASS_ID = 20044


def placements(project):
    return project.extra.setdefault('placed_markers', [])


def fill_tiles(project):
    return set(project.extra.get('fill_tiles') or [])


def base_dir(project):
    d = editormaps.levels_dir(project)
    return d + '_base' if d else None


def levels_name(project):
    d = editormaps.levels_dir(project)
    return mods.mod_name(d) if d else None


def _generated(project):
    return set(project.extra.get('generated_tiles') or [])


def _ours(project, path):
    """True when ``path`` is a tile this module wrote for the project: the
    editor header carries the GUID kept in ``tile_guids``. Survives a
    project that was not saved after placing (4.0.1)."""
    try:
        with open(path, 'rb') as f:
            head = f.read(4096)
        info = mods.file_entry(head + b'')
        guid = info[3]
    except Exception:
        return False
    if not guid:
        return False
    return guid.hex() in _known_guids(project)


SIDECAR = 'qf2_generated.json'


def _sidecar(project):
    lv = editormaps.levels_dir(project)
    return os.path.join(lv, SIDECAR) if lv else None


def _known_guids(project):
    out = set((project.extra.get('tile_guids') or {}).values())
    path = _sidecar(project)
    if path and os.path.isfile(path):
        try:
            import json
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            out |= {str(v) for v in (data.get('guids') or {}).values()}
        except (OSError, ValueError, AttributeError):
            pass
    return out


def _write_sidecar(project, written):
    """The GUIDs of the tiles in the levels folder that this module wrote,
    next to them: generate() knows its own tiles again after the project
    was closed without saving."""
    import json
    path = _sidecar(project)
    if not path:
        return
    guids = {t: g for t, g in (project.extra.get('tile_guids') or {}).items()
             if t in written}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'format': 1, 'guids': guids}, f, indent=1)
    os.replace(tmp, path)


def _unwrap_file(blob):
    """Uncompressed map body of a file: editor form (two streams, metadata
    first) or a plain one stream .lnd as the SDK writes it."""
    flags, _res, _cid, _guid, body = mods.file_entry(blob)
    if flags is None:
        body = tw1_lnd.unwrap(blob)
    return body


# -- where a tile comes from --------------------------------------------------

def _read_mod_tile(info, tile):
    """(body, phx bytes or None) of a tile in a mod (archive or folder)."""
    rec = info['tiles'].get(tile) or {}
    inner = rec.get('inner') or mods.lnd_of_tile(tile)
    path = info['path']
    phx_inner = mods._phx_inner(inner)
    if os.path.isfile(path):
        ents = mods.wd_directory(path)
        ent = next((e for e in ents if e.path.lower() == inner.lower()), None)
        if ent is None:
            return None, None
        body = mods.wd_data(path, ent)
        pe = next((e for e in ents if e.path.lower() == phx_inner.lower()),
                  None)
        return body, (mods.wd_data(path, pe) if pe else None)
    full = os.path.join(path, *inner.split(BS))
    if not os.path.isfile(full):
        return None, None
    with open(full, 'rb') as f:
        body = _unwrap_file(f.read())
    pfull = os.path.join(path, *phx_inner.split(BS))
    phx = None
    if os.path.isfile(pfull):
        with open(pfull, 'rb') as f:
            phx = mods.file_entry(f.read())[4]
    return body, phx


def retail_body(game_dir, modset, tile):
    info = (modset.retail_tiles if modset else {}).get(tile) or {}
    arch, inner = info.get('archive'), info.get('inner')
    if not arch or not inner:
        return None
    path = os.path.join(game_dir, 'WDFiles', arch)
    ent = next((e for e in mods.wd_directory(path) if e.path == inner), None)
    return mods.wd_data(path, ent) if ent else None


def base_of(project, modset, game_dir, tile):
    """(body, phx or None, label) the tile is rebuilt from."""
    own = levels_name(project)
    keep = base_dir(project)
    inner = mods.lnd_of_tile(tile)
    lv = editormaps.levels_dir(project)
    target = os.path.join(lv, *inner.split(BS)) if lv else None
    # the file in the levels folder is the user's when we did not write it
    # (a new import from the editor replaces the kept copy)
    theirs = bool(target and os.path.isfile(target)
                  and not _ours(project, target))
    # 1. a tile the user imported from the editor and we wrote over
    if keep and not theirs:
        full = os.path.join(keep, *inner.split(BS))
        if os.path.isfile(full):
            with open(full, 'rb') as f:
                body = _unwrap_file(f.read())
            pfull = os.path.join(keep, *mods._phx_inner(inner).split(BS))
            phx = None
            if os.path.isfile(pfull):
                with open(pfull, 'rb') as f:
                    phx = mods.file_entry(f.read())[4]
            return body, phx, 'editor'
    # 2. a tile in the levels folder that is not ours: the user's import
    if theirs:
        with open(target, 'rb') as f:
            body = _unwrap_file(f.read())
        pt = os.path.join(lv, *mods._phx_inner(inner).split(BS))
        phx = None
        if os.path.isfile(pt):
            with open(pt, 'rb') as f:
                phx = mods.file_entry(f.read())[4]
        return body, phx, 'editor'
    # 3. a foreign mod the project uses for this tile
    if modset is not None:
        provs = [i for i in modset.tile_providers(tile) if i['name'] != own
                 and not _is_levels_folder(i.get('path'))]
        choice = (project.extra.get('base_choice') or {}).get(tile) or \
            project.mod_tiles.get(tile)
        info = next((i for i in provs if i['name'] == choice), None) or (
            provs[0] if provs else None)
        if info is not None:
            body, phx = _read_mod_tile(info, tile)
            if body is not None:
                return body, phx, info['name']
    # 4. the game
    body = retail_body(game_dir, modset, tile)
    return body, None, 'game'


def _is_levels_folder(path):
    """A ``<project>_levels`` folder of this tool (after "Save as" the old
    one is still in the mod list; its tiles carry our old markers)."""
    return bool(path) and os.path.isdir(path) and \
        os.path.basename(os.path.normpath(path)).endswith('_levels')


def terrain(project, modset, game_dir, tile):
    body, _phx, _src = base_of(project, modset, game_dir, tile)
    return lndmap.Terrain(body) if body else None


# -- building ------------------------------------------------------------------

def missing_game_markers(body, retail):
    """[(name, id, x, y, z, angle)] of the game tile that ``body`` lacks."""
    have = {(n, i) for n, lst in tw1_lnd.markers_full(body).items()
            for i, _p in lst}
    out = []
    for name, lst in tw1_lnd.markers_full(retail).items():
        for ident, (x, y, z, angle) in lst:
            if (name, ident) not in have:
                out.append((name, ident, x, y, z, angle))
    return out


def build_body(base, retail, placed, fill=True):
    """(body, added game markers, placed markers written, clashes)."""
    add = missing_game_markers(base, retail) if (fill and retail) else []
    have = {(n, i) for n, lst in tw1_lnd.markers_full(base).items()
            for i, _p in lst} | {(m[0], m[1]) for m in add}
    mine, clash = [], []
    for p in placed:
        key = (p['name'], int(p['num']))
        if key in have:
            clash.append(p)
            continue
        have.add(key)
        mine.append((p['name'], int(p['num']), int(p['x']), int(p['y']),
                     int(p['z']), int(p.get('angle') or 0)))
    return lndmap.add_markers(base, add + mine), add, mine, clash


def editor_file(body, guid):
    head = bytes([0xFF, 0xA1, 0xD0, FLAGS]) + struct.pack('<I', CLASS_ID) \
        + guid[:16].ljust(16, b'\0')
    return zlib.compress(head) + zlib.compress(body)


# the first four bytes of the GUID of every tile this module writes: a
# tile is recognised as ours even when the project was closed without
# saving and lost ``tile_guids`` (4.0.1); the other 12 bytes are random
GUID_TAG = b'QF2L'


def _guid(project, tile):
    g = project.extra.setdefault('tile_guids', {})
    if tile not in g:
        g[tile] = (GUID_TAG + uuid.uuid4().bytes[4:]).hex()
    return bytes.fromhex(g[tile])


def _write(path, blob):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(blob)
    os.replace(tmp, path)


def generate(project, modset, game_dir, log=print):
    """Write every tile that needs placed or put back markers into the
    levels folder, remove tiles no longer needed. Returns a report
    {tile: {'source', 'added', 'placed', 'clash'}}."""
    lv = editormaps.levels_dir(project)
    if not lv:
        raise ValueError('project not saved')
    if modset is None and game_dir:
        # without the game's maps every tile would count as "no base" and
        # the tiles of all other quests would be taken away
        raise ValueError('the maps of the game are not loaded')
    keep = base_dir(project)
    by_tile = {}
    for p in placements(project):
        by_tile.setdefault(p['tile'], []).append(p)
    wanted = set(by_tile) | fill_tiles(project)
    written = set(wanted)
    report = {}
    for tile in sorted(wanted):
        inner = mods.lnd_of_tile(tile)
        target = os.path.join(lv, *inner.split(BS))
        # the user's own editor tile is kept aside before we write over it
        if os.path.isfile(target) and not _ours(project, target):
            dst = os.path.join(keep, *inner.split(BS))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(target, dst)
            pt = os.path.join(lv, *mods._phx_inner(inner).split(BS))
            if os.path.isfile(pt):
                pd = os.path.join(keep, *mods._phx_inner(inner).split(BS))
                os.makedirs(os.path.dirname(pd), exist_ok=True)
                shutil.copyfile(pt, pd)
        base, phx, src = base_of(project, modset, game_dir, tile)
        if base is None:
            report[tile] = {'source': None, 'added': [], 'placed': [],
                            'clash': by_tile.get(tile, [])}
            if not (os.path.isfile(target) and _ours(project, target)):
                written.discard(tile)    # keep a tile of ours as it is
            continue
        retail = retail_body(game_dir, modset, tile)
        body, add, mine, clash = build_body(base, retail,
                                            by_tile.get(tile, []))
        _write(target, editor_file(body, _guid(project, tile)))
        pt = os.path.join(lv, *mods._phx_inner(inner).split(BS))
        if phx is not None:
            _write(pt, phx)
        elif os.path.isfile(pt):
            os.remove(pt)                # physics of an earlier base
        report[tile] = {'source': src, 'added': add, 'placed': mine,
                        'clash': clash}
        log(('tile', tile, src, len(add), len(mine)))
    # tiles we wrote earlier that nothing needs any more (found by their
    # GUID too, so a project closed without saving is cleaned as well)
    gone = set(_generated(project)) - written
    for tile in _levels_tiles(lv):
        if tile not in written and _ours(project, os.path.join(
                lv, *mods.lnd_of_tile(tile).split(BS))):
            gone.add(tile)
    for tile in gone:
        inner = mods.lnd_of_tile(tile)
        for sub in (inner, mods._phx_inner(inner)):
            path = os.path.join(lv, *sub.split(BS))
            saved = os.path.join(keep, *sub.split(BS)) if keep else None
            if saved and os.path.isfile(saved):
                lnd = os.path.join(lv, *inner.split(BS))
                # back only over our own tile: a newer import stays
                if not os.path.isfile(lnd) or _ours(project, lnd):
                    shutil.copyfile(saved, path)   # the user's tile again
                os.remove(saved)
            elif os.path.isfile(path) and (sub == inner or not os.path.isfile(
                    os.path.join(lv, *inner.split(BS)))
                    or _ours(project, os.path.join(lv, *inner.split(BS)))):
                os.remove(path)
    project.extra['generated_tiles'] = sorted(written)
    _write_sidecar(project, written)
    # the levels folder is a mod of the project and wins these tiles
    key = os.path.normcase(os.path.abspath(lv))
    if not any(os.path.normcase(os.path.abspath(m['path'])) == key
               for m in project.mods):
        project.mods.append({'path': lv, 'enabled': True})
    name = levels_name(project)
    choice = project.extra.setdefault('base_choice', {})
    for tile in written:
        before = project.mod_tiles.get(tile)
        if before and before != name and not _is_levels_folder_name(before):
            choice[tile] = before        # the user's pick among the mods
        project.mod_tiles[tile] = name
    for tile in gone:
        if project.mod_tiles.get(tile) == name:
            project.mod_tiles.pop(tile, None)
            if tile in choice:
                project.mod_tiles[tile] = choice.pop(tile)
    return report


def _is_levels_folder_name(name):
    return str(name or '').endswith('_levels')


def _levels_tiles(lv):
    """Tiles with a map file in the levels folder."""
    out = []
    folder = os.path.join(lv or '', 'Levels')
    if not os.path.isdir(folder):
        return out
    for fn in os.listdir(folder):
        info = editormaps.parse_name(fn)
        if info and info[2] == 'lnd':
            out.append(info[0])
    return out


def forget_quest(project, qid, new_id=None):
    """Placements of a quest that was deleted (``new_id`` None) or got
    another number. Returns True when something changed."""
    lst = placements(project)
    mine = [p for p in lst if p.get('quest') == qid]
    if not mine:
        return False
    if new_id is None:
        lst[:] = [p for p in lst if p.get('quest') != qid]
    else:
        for p in mine:
            p['quest'] = new_id
    return True


def move_levels(project, old_path):
    """"Save as": the new project file gets its own levels folder - copy
    ``<old>_levels`` and ``<old>_levels_base`` along and point the mod list
    and the tile choices at the copy."""
    if not old_path or not project.path or \
            os.path.normcase(old_path) == os.path.normcase(project.path):
        return False
    old_lv = os.path.splitext(old_path)[0] + '_levels'
    new_lv = editormaps.levels_dir(project)
    if not os.path.isdir(old_lv):
        return False
    # a project saved over an older one: its levels folder is no longer of
    # any project - kept under another name, never used, never deleted
    import time
    stamp = time.strftime('%Y%m%d-%H%M%S')
    for folder in (new_lv, new_lv + '_base'):
        if os.path.exists(folder):
            os.replace(folder, f'{folder}.old-{stamp}')
    shutil.copytree(old_lv, new_lv)
    if os.path.isdir(old_lv + '_base'):
        shutil.copytree(old_lv + '_base', new_lv + '_base')
    old_key = os.path.normcase(os.path.abspath(old_lv))
    for m in project.mods:
        if os.path.normcase(os.path.abspath(m['path'])) == old_key:
            m['path'] = new_lv
    old_name, new_name = mods.mod_name(old_lv), mods.mod_name(new_lv)
    # a folder copied with shutil keeps the old GUIDs: the new project
    # file keeps the same tile_guids, so its tiles are still "ours"
    for tile, name in list(project.mod_tiles.items()):
        if name == old_name:
            project.mod_tiles[tile] = new_name
    return True


def marker_head(body):
    """The map body up to the end of its marker block (what numbering and
    the level header cache need)."""
    _start, end = tw1_lnd._marker_section(body)
    return bytes(body[:end])


def marker_exists(body, name, num):
    """True when the map already has marker ``name`` number ``num``."""
    return bool(body) and any(
        i == int(num) for i, _p in tw1_lnd.markers_full(body).get(name, []))


def free_number(name, tile, body, placed, skip=None):
    """Next marker number for ``name`` on ``tile``: above the highest one
    in the map and in the placements (``skip``: a placement being moved)."""
    nums = [i for i, _p in tw1_lnd.markers_full(body).get(name, [])] \
        if body else []
    nums += [int(p['num']) for p in placed
             if p['tile'] == tile and p['name'] == name and p is not skip]
    return (max(nums) + 1) if nums else 1
