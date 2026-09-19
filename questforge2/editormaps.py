"""Map tiles saved by the Two Worlds editor, taken into the project.

After the multiplayer take-over (mpmerge.py) the user places the markers of
the checklist in the Two Worlds editor. The editor saves a tile under
``%USERPROFILE%\\Saved Games\\Two Worlds Saves\\Levels`` as
``Map_<cell><suffix>.lnd`` (+ ``.bmp``) and the physics as
``physic\\Map_<cell><suffix>.phx``; the suffix is ``s`` or ``m`` depending on
how it was saved (the editor cannot save under the original name).

Measured 2026-09-18:

- editor ``.lnd``: carries its directory metadata as a first zlib stream
  (flags 0x31, class id 20044, own GUID); the Kira campaign ships them like
  that (build_campaign.py, EDITOR_MAPS) and the game loads them.
- ``.phx``: retail stores them uncompressed, flags 0x00
  (``Levels.wd``, 191 files), the editor writes the plain bytes.
- in the game: ``Levels\\Map_<cell>.lnd`` and ``Levels\\physic\\Map_<cell>.phx``.

The files go into ``<project>_levels`` next to the project file, laid out
like a mod (``Levels\\...``), and that folder is one of the project's mods.
So the tool reads the new markers at once (mods.scan_mod), ticks the
checklist, and the export packs the tiles the quests need
(mods.dependency_entries, now with the .phx).

The game keeps a cache of all level headers with their markers,
``Levels\\Map_LevelHeaders.lhc``. The SDK's ``LevelHeadersCacheGen.bat``
rebuilds it from what is installed; without a fresh one the game does not
know the new markers. It has to run after the export, before the next start.

3.9.1: the tool runs it itself after the export. The batch is one call,
``MeshParamsGen.exe "<game>/>" -levelheaderscache "Levels\\Map_*.lnd"
"Levels\\Map_LevelHeaders.lhc"``, with the paths of the SDK owner's machine
typed in and a ``pause`` at the end, so the tool calls the exe with its own
game path. Measured 2026-09-19: 0.6 s, exit code 0, prints every map and
"Finished: 160 levels added to cache file", writes
``<game>\\Levels\\Map_LevelHeaders.lhc``; the file holds, per map, the path
and the head of the map body up to the end of the marker block, and it has
the maps of the mod archives in it (10 tiles differ from Levels.wd with
the Kira campaign installed), so the exe reads the WD files too.
"""

import os
import re
import shutil
import subprocess

from . import mods

BS = chr(92)
EDITOR_LEVELS = os.path.join(os.path.expanduser('~'), 'Saved Games',
                             'Two Worlds Saves', 'Levels')
LHC_BAT = 'LevelHeadersCacheGen.bat'
LHC_GUESSES = (r'D:\Games\TwoWorldsSDK\Tools',
               r'C:\Games\TwoWorldsSDK\Tools',
               r'C:\Program Files (x86)\Reality Pump\Two Worlds SDK\Tools',
               r'C:\Program Files\Reality Pump\Two Worlds SDK\Tools')

# Map_E01s.lnd, Map_F01_1s.phx, Map_F01m.lnd, Map_E01.lnd, Map_E01sa.lnd
_NAME = re.compile(r'^map_([a-z])(\d{1,2})(_\d+)?([a-z]*)\.(lnd|phx)$', re.I)


def parse_name(filename):
    """(tile 'E1' / 'F1_1', cell 'E01' / 'F01_1', ext, suffix) or None."""
    m = _NAME.match(os.path.basename(filename))
    if not m:
        return None
    letter, num, sub, suffix, ext = m.groups()
    cell = f'{letter.upper()}{int(num):02d}{sub or ""}'
    tile = mods.tile_of_lnd(f'Levels{BS}Map_{cell}.lnd')
    return tile, cell, ext.lower(), suffix.lower()


def inner_path(cell, ext):
    if ext == 'phx':
        return f'Levels{BS}physic{BS}Map_{cell}.phx'
    return f'Levels{BS}Map_{cell}.lnd'


def _partner(path, ext):
    """The editor keeps the .phx in physic\\ below the .lnd (and the .lnd one
    folder up from the .phx); also accept both side by side."""
    folder, name = os.path.split(path)
    stem = os.path.splitext(name)[0]
    if ext == 'phx':
        cands = [os.path.join(folder, 'physic', stem + '.phx'),
                 os.path.join(folder, stem + '.phx')]
    else:
        cands = [os.path.join(os.path.dirname(folder), stem + '.lnd'),
                 os.path.join(folder, stem + '.lnd')]
    return next((c for c in cands if os.path.isfile(c)), None)


def plan_import(paths):
    """What dropping/choosing ``paths`` does.

    Returns (items, skipped): items [{'tile', 'cell', 'lnd', 'phx'}] (source
    paths, None when not there) one per tile, the partner file found
    automatically; skipped [path] of files that are no editor map."""
    by_cell, skipped = {}, []
    for p in paths:
        info = parse_name(p) if os.path.isfile(p) else None
        if not info:
            skipped.append(p)
            continue
        tile, cell, ext, _suffix = info
        rec = by_cell.setdefault(cell, {'tile': tile, 'cell': cell,
                                        'lnd': None, 'phx': None})
        rec[ext] = p
    for rec in by_cell.values():
        for have, want in (('lnd', 'phx'), ('phx', 'lnd')):
            if rec[have] and not rec[want]:
                rec[want] = _partner(rec[have], want)
    items = sorted(by_cell.values(), key=lambda r: mods.data._tile_key(r['tile']))
    return items, skipped


def levels_dir(project):
    """``<project>_levels`` next to the project file (None before the first
    save), laid out like a mod."""
    if project is None or not project.path:
        return None
    return os.path.splitext(project.path)[0] + '_levels'


def import_maps(items, dest):
    """Copy the files under their game name into ``dest``. Returns
    [(tile, inner, source)] of what was written."""
    done = []
    for rec in items:
        for ext in ('lnd', 'phx'):
            src = rec.get(ext)
            if not src:
                continue
            inner = inner_path(rec['cell'], ext)
            target = os.path.join(dest, *inner.split(BS))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            tmp = target + '.tmp'
            shutil.copyfile(src, tmp)
            os.replace(tmp, target)
            done.append((rec['tile'], inner, src))
    return done


def present(dest):
    """[(tile, has_lnd, has_phx, mtime)] of the tiles in the project folder."""
    out = {}
    if not dest or not os.path.isdir(dest):
        return []
    lv = os.path.join(dest, 'Levels')
    for folder in (lv, os.path.join(lv, 'physic')):
        if not os.path.isdir(folder):
            continue
        for fn in os.listdir(folder):
            info = parse_name(fn)
            if not info or info[3]:
                continue
            tile, _cell, ext, _ = info
            rec = out.setdefault(tile, {'lnd': False, 'phx': False, 't': 0})
            rec[ext] = True
            rec['t'] = max(rec['t'], os.path.getmtime(os.path.join(folder, fn)))
    return [(k, v['lnd'], v['phx'], v['t'])
            for k, v in sorted(out.items(), key=lambda kv: mods.data._tile_key(kv[0]))]


def tick_found(quests, modset):
    """Tick checklist items whose marker is now on a map the tool knows
    (the game maps or an enabled mod of the project). Returns the number of
    newly ticked items."""
    if modset is None:
        return 0
    n = 0
    for q in quests:
        for item in q.extra.get('markers_todo') or []:
            if not isinstance(item, dict) or item.get('done'):
                continue
            name, tile = item.get('name'), str(item.get('tile') or '').upper()
            try:
                num = int(item.get('num'))
            except (TypeError, ValueError):
                continue
            recs = [modset.retail_tiles.get(tile)] + [
                i['tiles'].get(tile) for i in modset.enabled()]
            if any(num in mods.marker_ids(r, name) for r in recs if r):
                item['done'] = True
                n += 1
    return n


def find_lhc_bat(cfg):
    """Path of the SDK's LevelHeadersCacheGen.bat or None."""
    p = (cfg or {}).get('lhc_bat')
    if p and os.path.isfile(p):
        return p
    sdk = (cfg or {}).get('sdk_dir')
    guesses = ([os.path.join(sdk, 'Tools'), sdk] if sdk else []) + list(LHC_GUESSES)
    for d in guesses:
        c = os.path.join(d, LHC_BAT)
        if os.path.isfile(c):
            return c
    return None


LHC_EXE = 'MeshParamsGen.exe'
LHC_FILE = os.path.join('Levels', 'Map_LevelHeaders.lhc')


def find_lhc_exe(cfg):
    """MeshParamsGen.exe of the SDK (next to the batch) or None."""
    p = (cfg or {}).get('lhc_bat')
    if p and os.path.basename(p).lower() == LHC_EXE.lower() \
            and os.path.isfile(p):
        return p
    bat = find_lhc_bat(cfg)
    folders = [os.path.dirname(bat)] if bat else []
    if p:
        folders.append(os.path.dirname(p))
    sdk = (cfg or {}).get('sdk_dir')
    folders += ([os.path.join(sdk, 'Tools'), sdk] if sdk else [])
    folders += list(LHC_GUESSES)
    for d in folders:
        c = os.path.join(d, LHC_EXE)
        if os.path.isfile(c):
            return c
    return None


def build_lhc(exe, game_dir, timeout=300):
    """Rebuild the level header cache of ``game_dir``. Returns (ok, number
    of maps or None, text): ok means exit code 0, the "Finished" line and a
    cache file written just now."""
    import time
    target = os.path.join(game_dir, LHC_FILE)
    before = time.time() - 2
    try:
        r = subprocess.run(
            [exe, game_dir.rstrip('/' + BS) + '/>', '-levelheaderscache',
             'Levels' + BS + 'Map_*.lnd', 'Levels' + BS + 'Map_LevelHeaders.lhc'],
            cwd=os.path.dirname(exe), capture_output=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError) as e:
        return False, None, str(e)
    out = (r.stdout or b'').decode('mbcs', 'replace') if os.name == 'nt' \
        else (r.stdout or b'').decode('latin-1')
    m = re.search(r'(\d+) levels added', out)
    fresh = os.path.isfile(target) and os.path.getmtime(target) >= before
    ok = r.returncode == 0 and m is not None and fresh
    tail = [ln for ln in out.replace(chr(13), '').split(chr(10))
            if ln.strip() and not ln.startswith('Levels' + BS)]
    return ok, (int(m.group(1)) if m else None), chr(10).join(tail[-4:])


def run_lhc_bat(path):
    """Start the batch in its own console window (it ends with pause)."""
    folder = os.path.dirname(path)
    subprocess.Popen(f'start "LevelHeadersCacheGen" /D "{folder}" "{path}"',
                     shell=True, cwd=folder)
