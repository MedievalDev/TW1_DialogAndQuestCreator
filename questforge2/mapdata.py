"""Data behind the map window (update 5c): minimap tiles, world -> pixel,
marker groups. No image library needed: DXT1 is decoded here and written
as PNG, which Tk shows directly.

What is proven and where it comes from:

- Minimap tiles: ``Levels\\MipMaps\\Map_E01@0.dds`` .. ``@3.dds`` in
  ``Levels.wd`` (later ``Update11-15.wd``/``Update16.wd`` win), DXT1,
  512/256/128/64 px. The surface grid A..I x 1..12 is complete, 52 interiors
  (``Map_F01_1``) have their own.
- Tile size: every map header (``.lnd``, 20 bytes after the name) says
  128 x 128 cells; the SDK divides world coordinates by 256 per cell
  (``TwoWorldsHeroControl16.ec``: ``nX/=256``). One tile is 32768 units, so
  64 units per pixel at 512 px.
- Orientation: world y grows upwards in the minimap, rows grow downwards.
  Checked by eye on 2026-09-16: gates of D8 lie in both city gates, guard
  routes on the streets, chests of F8 in the ring structure, the static
  teleport of E1 at the end of its path, roads run on across tile borders.
  In the game itself the positions are not measured.
- LOCATION x/y of the quest file are cells (``AddLocation(.., A2G(nX),
  A2G(nY), ..)`` in ``PLocations.ech``).
- Marker groups: sections of ``PEnums.ech`` (quest, unit, town, guards,
  workers, other markers), ``TwoWorldsEnemies16.ec`` (``MARKER_ENEMY_*``,
  ``MARKER_TRAP*``), ``TwoWorldsTeleports.ec`` (``MARKER_TELEPORT_STATIC``).
"""

import hashlib
import json
import os
import re
import struct
import zlib

from . import data, mods

BS = chr(92)
TILE_CELLS = 128                 # map header
CELL_UNITS = 256                 # SDK nX/=256
TILE_UNITS = TILE_CELLS * CELL_UNITS
COLS = 'ABCDEFGHI'
ROWS = 12
LEVEL_PX = {0: 512, 1: 256, 2: 128, 3: 64}
CACHE_FORMAT = 1
POSITIONS_CHECKED = True         # by eye against the minimaps, see above

_DDS = re.compile(r'^levels[\\/]mipmaps[\\/]map_([a-z])(\d{2})(_\d+)?@(\d)\.dds$',
                  re.I)

# marker groups: (key, SDK source, exact names, name prefixes)
MARKER_GROUPS = (
    ('quest_enemy', 'PEnums.ech', ('MARKER_QUEST_CREATE_ENEMY',), ()),
    ('quest_object', 'PEnums.ech', ('MARKER_QUEST_CREATE_OBJECT',), ()),
    ('quest_other', 'PEnums.ech', ('MARKER_QUEST_POINT', 'MARKER_QUEST_WALK',
                                   'MARKER_QUEST_TELEPORT',
                                   'MARKER_QUEST_CLEAR_AREA',
                                   'MARKER_QUEST_KILL_AREA'), ()),
    ('npc_start', 'PEnums.ech', ('MARKER_QUEST_START',), ()),
    ('chest', 'PEnums.ech', ('MARKER_CHEST',), ()),
    ('gate', 'PEnums.ech', ('MARKER_GATE',), ()),
    ('teleport', 'PEnums.ech, TwoWorldsTeleports.ec',
     ('MARKER_TELEPORT', 'MARKER_TELEPORT_STATIC'), ('MARKER_TELEPORT_DEST',)),
    ('enemy', 'TwoWorldsEnemies16.ec', (), ('MARKER_ENEMY_', 'MARKER_TRAP')),
    ('town', 'PEnums.ech, PCommon.ech',
     ('MARKER_NPC', 'MARKER_SLEEP', 'MARKER_PUBLIC_PLACE', 'MARKER_CHAIR',
      'MARKER_TAVERN', 'MARKER_VILLAGE_04', 'MARKER_VILLAGE_02', 'MARKER_SHOP',
      'MARKER_PLAY', 'MARKER_PRAY', 'MARKER_WOODCUT', 'MARKER_BROOM',
      'MARKER_KNEEL', 'MARKER_PICHFORK', 'MARKER_SCYTHE', 'MARKER_PINAXE',
      'MARKER_WALKER', 'MARKER_SITING', 'MARKER_LAY_DOWN', 'MARKER_DESK',
      'MARKER_LOOK_AT'),
     ('MARKER_GUARD', 'MARKER_SHOP_', 'MARKER_COACH_', 'MARKER_CHANGER_',
      'MARKER_F_', 'MARKER_B_', 'MARKER_Q_')),
    ('other', 'PEnums.ech', ('MARKER_RESSURECT', 'MARKER_MANA_REG'), ()),
)
GROUP_KEYS = [g[0] for g in MARKER_GROUPS] + ['unknown']
# layers that are not map markers
EXTRA_LAYERS = ('locations', 'containers')


def group_of(name):
    for key, _src, names, prefixes in MARKER_GROUPS:
        if name in names or any(name.startswith(p) for p in prefixes):
            return key
    return 'unknown'


# ---------------------------------------------------------------------------
# coordinates

def split_tile(tile):
    """``F1_1`` -> (col index, row, interior suffix) or None."""
    m = mods._TILE.match(tile or '')
    if not m or m.group(1) not in COLS:
        return None
    return COLS.index(m.group(1)), int(m.group(2)), m.group(3) or ''


def world_to_map(tile, x, y, px=512):
    """Pixel of a world position in the whole map at ``px`` per tile."""
    s = split_tile(tile)
    if s is None:
        return None
    ci, row, _sfx = s
    f = px / TILE_UNITS
    return ci * px + x * f, (row - 1) * px + px - y * f


def map_to_world(mx, my, px=512):
    """(tile, x, y) of a map pixel (surface tiles)."""
    ci = int(mx // px)
    row = int(my // px) + 1
    if not (0 <= ci < len(COLS) and 1 <= row <= ROWS):
        return None
    f = TILE_UNITS / px
    return (f'{COLS[ci]}{row}', int((mx - ci * px) * f),
            int((px - (my - (row - 1) * px)) * f))


def cells_to_world(cx, cy):
    return cx * CELL_UNITS, cy * CELL_UNITS


# ---------------------------------------------------------------------------
# minimap tiles

def minimap_entries(game_dir):
    """{(tile, level): (archive, DirEntry)} of the game, later wins."""
    out = {}
    for a in mods.RETAIL_MAP_ARCHIVES:
        p = os.path.join(game_dir, 'WDFiles', a)
        if not os.path.isfile(p):
            continue
        for e in mods.wd_directory(p):
            m = _DDS.match(e.path)
            if m:
                tile = f'{m.group(1).upper()}{int(m.group(2))}{m.group(3) or ""}'
                out[(tile, int(m.group(4)))] = (p, e)
    return out


def _rgb565(v):
    r = (v >> 11) & 0x1F
    g = (v >> 5) & 0x3F
    b = v & 0x1F
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def decode_dxt1(blob):
    """(width, height, RGB bytes) of a DXT1 .dds."""
    if blob[:4] != b'DDS ' or blob[84:88] != b'DXT1':
        raise ValueError('not a DXT1 dds')
    h, w = struct.unpack_from('<II', blob, 12)
    out = bytearray(w * h * 3)
    pos = 128
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    for by in range(bh):
        for bx in range(bw):
            c0, c1, bits = struct.unpack_from('<HHI', blob, pos)
            pos += 8
            a, b = _rgb565(c0), _rgb565(c1)
            if c0 > c1:
                pal = (a, b,
                       tuple((2 * x + y) // 3 for x, y in zip(a, b)),
                       tuple((x + 2 * y) // 3 for x, y in zip(a, b)))
            else:
                pal = (a, b, tuple((x + y) // 2 for x, y in zip(a, b)),
                       (0, 0, 0))
            for py in range(4):
                yy = by * 4 + py
                if yy >= h:
                    break
                row = yy * w
                for px in range(4):
                    xx = bx * 4 + px
                    if xx >= w:
                        continue
                    c = pal[(bits >> (2 * (py * 4 + px))) & 3]
                    i = (row + xx) * 3
                    out[i] = c[0]
                    out[i + 1] = c[1]
                    out[i + 2] = c[2]
    return w, h, bytes(out)


def encode_png(w, h, rgb):
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(tag, body):
        return (struct.pack('>I', len(body)) + tag + body
                + struct.pack('>I', zlib.crc32(tag + body) & 0xFFFFFFFF))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(raw), 6))
            + chunk(b'IEND', b''))


def tile_cache_dir(project=None):
    """Next to the project file (``<project>_map``) once it is saved, else
    ``cache/maptiles``."""
    if project is not None and project.path:
        stem = os.path.splitext(project.path)[0]
        return stem + '_map'
    return os.path.join(data.ROOT, 'cache', 'maptiles')


class TileStore:
    """PNG files of the minimap tiles, made once from the archives."""

    def __init__(self, game_dir, cache_dir):
        self.game_dir = game_dir
        self.dir = cache_dir
        self.entries = minimap_entries(game_dir)
        h = hashlib.sha1()
        for (tile, lvl), (p, e) in sorted(self.entries.items()):
            h.update(f'{tile}{lvl}{os.path.basename(p)}{e.offset}{e.clen};'
                     .encode('latin-1'))
        self.stamp = h.hexdigest()[:12]

    def tiles(self, interior=False):
        return sorted({t for t, _l in self.entries
                       if bool(split_tile(t) and split_tile(t)[2]) == interior},
                      key=data._tile_key)

    def has(self, tile, level):
        return (tile, level) in self.entries

    def png_path(self, tile, level):
        return os.path.join(self.dir, f'{tile}@{level}.png')

    def png(self, tile, level):
        """Path of the PNG, decoded and written on first use."""
        path = self.png_path(tile, level)
        if os.path.isfile(path):
            return path
        src = self.entries.get((tile, level))
        if src is None:
            return None
        w, h, rgb = decode_dxt1(mods.wd_data(*src))
        os.makedirs(self.dir, exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(encode_png(w, h, rgb))
        os.replace(tmp, path)
        return path

    def prepare(self, level, progress=None):
        """Decode every surface tile of one level (first open)."""
        tiles = [t for t in self.tiles() if self.has(t, level)]
        stamp_file = os.path.join(self.dir, 'stamp.json')
        try:
            with open(stamp_file, encoding='utf-8') as f:
                if json.load(f).get('stamp') != self.stamp:
                    for n in os.listdir(self.dir):
                        if n.endswith('.png'):
                            os.remove(os.path.join(self.dir, n))
        except (OSError, ValueError):
            pass
        for i, t in enumerate(tiles):
            self.png(t, level)
            if progress:
                progress((i + 1) / len(tiles))
        os.makedirs(self.dir, exist_ok=True)
        with open(stamp_file, 'w', encoding='utf-8') as f:
            json.dump({'format': CACHE_FORMAT, 'stamp': self.stamp}, f)


# ---------------------------------------------------------------------------
# what goes on the map

def collect(retail_tiles, modset=None, index=None, project=None):
    """Every point of the map: [{'name', 'id', 'tile', 'x', 'y', 'group',
    'mod', 'used', 'own'}]. Markers of a mod that exist in the game map are
    not repeated; locations and chests of the quest file come as the layers
    ``locations`` and ``containers``."""
    used = set()
    own = set()
    if index is not None:
        for key in index.d.get('marker_use', {}):
            kind, tile, num = key.split('|')
            name = mods.MARKER_NAMES.get(kind)
            if name and tile:
                used.add((name, tile, int(num)))
        for nid, n in index.npcs.items():
            if n.get('marker') is not None:
                used.add((mods.NPC_MARKER, n.get('tile'), n['marker']))
    if project is not None:
        for q in project.quests:
            try:
                refs = mods.marker_refs(mods.quest_block(q))
            except Exception:
                continue
            for kind, tile, num in refs:
                key = (mods.MARKER_NAMES.get(kind), tile, num)
                used.add(key)
                own.add(key)
            for s in q.speakers:
                if s.get('new') and s.get('tile'):
                    key = (mods.NPC_MARKER, s['tile'].upper(),
                           s.get('marker') or s['id'])
                    used.add(key)
                    own.add(key)
    points = []

    def add(name, ident, tile, x, y, mod=None):
        key = (name, tile, ident)
        points.append({'name': name, 'id': ident, 'tile': tile, 'x': x,
                       'y': y, 'group': group_of(name), 'mod': mod,
                       'used': key in used, 'own': key in own})
    for tile, info in retail_tiles.items():
        for name, lst in info.get('markers', {}).items():
            for ident, x, y, _z, _a in lst:
                add(name, ident, tile, x, y)
    for info in (modset.enabled() if modset else []):
        for tile, rec in info['tiles'].items():
            base = retail_tiles.get(tile, {}).get('markers', {})
            for name, lst in rec.get('markers', {}).items():
                have = {m[0] for m in base.get(name, [])}
                for ident, x, y, _z, _a in lst:
                    if ident not in have:
                        add(name, ident, tile, x, y, info)
    if index is not None:
        for key, loc in index.locations.items():
            if loc.get('tile') in (None, '', '(null)'):
                continue
            x, y = cells_to_world(loc['x'], loc['y'])
            points.append({'name': key, 'id': loc.get('type'),
                           'tile': loc['tile'], 'x': x, 'y': y,
                           'group': 'locations', 'mod': None, 'used': True,
                           'own': False, 'label': loc.get('name') or key,
                           'radius': loc.get('radius')})
    for info in (modset.enabled() if modset else []):
        for key, loc in info['locations'].items():
            p = loc['record'].split()
            try:
                x, y = cells_to_world(int(p[2]), int(p[3]))
            except (IndexError, ValueError):
                continue
            points.append({'name': key, 'id': None, 'tile': loc['tile'],
                           'x': x, 'y': y, 'group': 'locations', 'mod': info,
                           'used': True, 'own': False, 'label': key})
        for key, box in info['containers'].items():
            p = box['record'].split()
            try:
                num = int(p[2])
            except (IndexError, ValueError):
                continue
            tile = box['tile']
            for pt in points:
                if pt['name'] == mods.CHEST_MARKER and pt['tile'] == tile \
                        and pt['id'] == num:
                    points.append(dict(pt, group='containers', mod=info,
                                       label=key))
                    break
    return points
