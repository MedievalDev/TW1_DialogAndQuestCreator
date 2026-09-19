"""The game's level header cache ``Levels/Map_LevelHeaders.lhc``, written by
the tool itself (3.9.2) - for everybody who does not have the SDK.
EXPERIMENTAL until users have confirmed it in the game (Marco 2026-09-19);
the texts say so, and the SDK program is used whenever it is found.

The game reads the markers of all maps from this one file; a marker that is
only in a map and not in the cache does not exist for the quest script. The
SDK rebuilds it with ``MeshParamsGen.exe -levelheaderscache`` (editormaps.
build_lhc). Everything here is measured against that program (2026-09-19,
a copy of the game folder built in the scratchpad, archives named like
mods that are switched on in the registry, each with its own test marker):

File: ``LC`` 00 00, u32 number of maps, u32 0, then per map u32 length +
path (``Levels`` backslash ``Map_A01.lnd``) and the head of the uncompressed
map body up to the end of the marker block, byte for byte. Maps sorted by
path.

Which map counts when several sources have the tile:
1. a loose file in ``<game>/Levels`` (two zlib streams like the editor
   writes them, or plain),
2. else the mods that are ON in the registry (``HKCU/SOFTWARE/Reality
   Pump/TwoWorlds/Mods``, value 1), the alphabetically FIRST archive wins
   (Minimap.wd beat ShaderFix.wd and Yamalin.wd, QuestLimit600.wd beat
   ShaderFix.wd; file times do not matter),
3. else the archives in ``WDFiles``, again the alphabetically first
   (Graphics.wd beat Levels.wd, Levels.wd beat Update16.wd).
A mod with value 0 or without a registry entry is not read. Only
``Levels/Map_*.lnd`` directly in that folder counts.

Proof: ``build`` reproduces the cache of the real game folder (160 maps,
Kira campaign installed) byte for byte; test_lhcache checks the rules.
"""

import os
import struct
import zlib

import tw1_lnd

from . import mods

BS = chr(92)
LHC_FILE = os.path.join('Levels', 'Map_LevelHeaders.lhc')
REG_MODS = 'SOFTWARE' + BS + 'Reality Pump' + BS + 'TwoWorlds' + BS + 'Mods'
PREFIX = 'levels' + BS + 'map_'


def active_mods():
    """Lower case file names of the mods switched on in the registry."""
    try:
        import winreg
    except ImportError:                  # not on Windows
        return set()
    out = set()
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_MODS)
    except OSError:
        return out
    with key:
        i = 0
        while True:
            try:
                name, value, _kind = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            if str(value).strip() == '1':
                out.add(name.lower())
    return out


def _is_map(inner):
    p = inner.lower()
    return p.startswith(PREFIX) and p.endswith('.lnd') and p.count(BS) == 1


def _head(read):
    """Body head up to the end of the marker block; ``read(n)`` gives the
    next uncompressed bytes (b'' at the end)."""
    buf = b''
    while True:
        try:
            _start, end = tw1_lnd._marker_section(buf)
            if end <= len(buf):
                return buf[:end]
        except (struct.error, IndexError):
            pass
        chunk = read(16384)
        if not chunk:
            raise ValueError('marker block not found')
        buf += chunk


def _archive_head(fh, entry):
    fh.seek(entry.offset)
    left = [entry.clen]
    d = zlib.decompressobj() if entry.flags & 0x01 else None

    def read(n):
        out = b''
        while not out and left[0] > 0:
            raw = fh.read(min(n, left[0]))
            if not raw:
                break
            left[0] -= len(raw)
            out = d.decompress(raw) if d else raw
        return out
    return _head(read)


def _loose_head(path):
    with open(path, 'rb') as f:
        body = mods.file_entry(f.read())[4]
    pos = [0]

    def read(n):
        pos[0] += n
        return body[pos[0] - n:pos[0]]
    return _head(read)


def sources(game_dir, active=None):
    """{inner path lower: (shown path, kind, file, entry or None)} - the
    map that counts for every tile, by the rules above."""
    active = active_mods() if active is None else {a.lower() for a in active}
    found = {}

    def archives(folder, only=None):
        if not os.path.isdir(folder):
            return
        names = [n for n in os.listdir(folder) if n.lower().endswith('.wd')
                 and (only is None or n.lower() in only)]
        for name in sorted(names, key=str.lower, reverse=True):
            full = os.path.join(folder, name)
            try:
                entries = mods.wd_directory(full)
            except Exception:            # not an archive we can read
                continue
            for e in entries:
                if _is_map(e.path):
                    found[e.path.lower()] = (e.path, 'archive', full, e)
    # weakest first, so the stronger source overwrites: WDFiles, then the
    # active mods; inside a folder the alphabetically first comes last
    archives(os.path.join(game_dir, 'WDFiles'))
    archives(os.path.join(game_dir, 'Mods'), active)
    levels = os.path.join(game_dir, 'Levels')
    if os.path.isdir(levels):
        for name in os.listdir(levels):
            inner = 'Levels' + BS + name
            if _is_map(inner):
                shown = found.get(inner.lower(), (inner,))[0]
                found[inner.lower()] = (shown, 'loose',
                                        os.path.join(levels, name), None)
    return found


def build(game_dir, active=None):
    """(cache bytes, [(path, source file)]) for the game folder."""
    src = sources(game_dir, active)
    by_file = {}
    for key, (_shown, kind, full, entry) in src.items():
        if kind == 'archive':
            by_file.setdefault(full, []).append((key, entry))
    heads = {}
    for full, lst in by_file.items():
        with open(full, 'rb') as fh:
            for key, entry in sorted(lst, key=lambda ke: ke[1].offset):
                heads[key] = _archive_head(fh, entry)
    for key, (_shown, kind, full, _e) in src.items():
        if kind == 'loose':
            heads[key] = _loose_head(full)
    keys = sorted(heads, key=lambda k: src[k][0])
    out = [b'LC' + bytes(2) + struct.pack('<II', len(keys), 0)]
    for key in keys:
        raw = src[key][0].encode('latin-1')
        out.append(struct.pack('<I', len(raw)) + raw + heads[key])
    return b''.join(out), [(src[k][0], src[k][2]) for k in keys]


def parse(blob):
    """{path: head} of a cache file (for checks)."""
    if blob[:2] != b'LC':
        raise ValueError('not a level header cache')
    count = struct.unpack_from('<I', blob, 4)[0]
    pos, out = 12, {}
    for _ in range(count):
        n = struct.unpack_from('<I', blob, pos)[0]
        path = blob[pos + 4:pos + 4 + n].decode('latin-1')
        pos += 4 + n
        _start, end = tw1_lnd._marker_section(blob[pos:])
        out[path] = blob[pos:pos + end]
        pos += end
    if pos != len(blob):
        raise ValueError(f'{len(blob) - pos} bytes left')
    return out


def write(game_dir, active=None):
    """Rebuild the cache file of the game. Returns (ok, number of maps,
    text); the old file is kept once as ``.qf2backup``."""
    target = os.path.join(game_dir, LHC_FILE)
    try:
        blob, used = build(game_dir, active)
        if not used:
            return False, None, 'no maps found'
        parse(blob)                       # reads back cleanly
        os.makedirs(os.path.dirname(target), exist_ok=True)
        keep = target + '.qf2backup'
        if os.path.isfile(target) and not os.path.isfile(keep):
            with open(target, 'rb') as a, open(keep, 'wb') as b:
                b.write(a.read())
        tmp = target + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(blob)
        os.replace(tmp, target)
    except (OSError, ValueError, struct.error, zlib.error) as e:
        return False, None, str(e)
    return True, len(used), ''


def rebuild(game_dir, exe=None):
    """Rebuild the cache: with the SDK's program when there is one (the
    reference), else with ``write``. Returns {'ok', 'n', 'text', 'how'
    ('sdk' | 'tool'), 'used' [(path, source file)]}."""
    from . import editormaps
    if exe:
        ok, n, text = editormaps.build_lhc(exe, game_dir)
        how = 'sdk'
    else:
        ok, n, text = write(game_dir)
        how = 'tool'
    used = []
    if ok:
        try:
            src = sources(game_dir)
            used = [(v[0], v[2]) for v in src.values()]
        except OSError:
            pass
    return {'ok': ok, 'n': n, 'text': text, 'how': how, 'used': used}


def overruled(used, archive, inners):
    """[(map path, winning file)] of the maps in ``inners`` that the
    project's ``archive`` packs but another source wins (a loose file or a
    mod that comes first in the alphabet)."""
    mine = os.path.normcase(os.path.abspath(archive))
    want = {i.lower() for i in inners}
    return sorted((path, os.path.basename(full)) for path, full in used
                  if path.lower() in want
                  and os.path.normcase(os.path.abspath(full)) != mine)
