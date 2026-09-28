"""All multiplayer quests into the single player at once, with random
markers (4.6.0, Marco 2026-09-25: "automatisches Uebertragen aller MP-Quests
in SP moeglich mit Random-Markern ueber den begehbaren Bereich der Map,
schliesse die Rand- und Wassertiles direkt aus"; his choices: the target
300 to 800 m from the giver, about 12 tiles, names from a list, givers that
do not talk to the hero on their own).

Measured 2026-09-25 on the 108 surface tiles:
- the sea (water pools at height 870) fills the west: A1-A6, A12, B1, B2
  and B5 are all water, A11 97 %, B3 and B4 85 %; the passable field
  blocks open sea but lets up to 7 % shallow water of a coast tile
  through, so "dry" is checked against the pools (lndmap.Terrain.wet);
- columns A and I and rows 1 and 12 are the edge of the world (sea in the
  west, mountains elsewhere): left out, like tiles with half water or
  more - 66 tiles remain;
- the 120 multiplayer quests (Q_700 to Q_959): 90 clear an area (FC
  CLEAR_AREA, its range in metres: PQuestLoader M2A), 30 bring an object;
  each has its own giver (half of them women, CITIZEN_F_*), none has a
  name, none links to another (AOQ);
- ids: with the quest limit 600 there are 197 free quest ids (without it
  one), and 191 NPC ids (507 to 697).

Where the markers of a quest go: the giver anywhere on the chosen tiles,
30 m from every other giver; the target of the task (the area to clear,
the object to bring) 300 to 800 m from him; every further line (the
enemies, a second object) around the target within the range of the task,
at most 20 m. A marker only lands on a cell (2 m) that is walkable and
dry, 16 m or more from the border of its tile, with walkable cells on all
four sides and in the largest connected walkable area of the tile (no
pocket closed in by rocks). The tiles are picked as groups of 3 or 4
neighbours, so the ring of 300 to 800 m reaches other chosen tiles; every
tile with a marker goes into the mod as a whole map (about 1.4 MB).

Own maps (Marco 2026-09-28, for Smoothness, who wants his own maps to get
the markers): the tiles can be typed in ("f01-f04, g01-g04") instead of
rolled, every tile of the list can get an own .lnd (empty: the original
level), and every quest can get its own tiles ("f01, f02"; empty: any tile
of the list). Tiles typed in count even on the edge of the world; water
stays out everywhere. The walkable cells come from the own map, and at
"Take all over" the own maps go into the project like maps from the
editor (the markers are written into them, the file itself is kept in
<project>_levels_base). A quest whose tiles leave no room for 300 to 800 m
gets its target on them anyway, nearer or farther ("relaxed").
"""

import math
import random
from collections import deque

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import os
import re

from . import editormaps, lndmap, mapdata, mods, mpmerge, placed, theme
from .i18n import t

M = 512                          # metres (and map pixels) per tile side
UNITS = lndmap.TILE_UNITS        # world units per tile side
GRID = 256                       # cells per tile side: 2 m each
CELL = UNITS // GRID
EDGE_M = 16                      # keep off the border of a tile
WATER_OUT = 0.5                  # a tile half under water or more is out
WATER_SAMPLES = 32               # per side, for the water share of a tile
TARGET_M = (300, 800)
NEAR_M = 20                      # further lines around the target
GIVER_GAP_M = 30                 # givers not closer to each other
TILES = 12
CLUSTER = (3, 4)
TRIES = 400
GIVER = mpmerge.GIVER_MARKER

# Names for the givers (Marco: "Namensliste"); the tool skips any name a
# character of the game or the project has already.
NAMES_M = (
    'Alrik', 'Berend', 'Cedrik', 'Dorian', 'Egbert', 'Falko', 'Gerold',
    'Hagen', 'Ingram', 'Jorin', 'Konrad', 'Lambert', 'Merten', 'Norbert',
    'Osric', 'Piet', 'Quirin', 'Roderich', 'Sigmar', 'Tankred', 'Ulrich',
    'Volker', 'Wendel', 'Anselm', 'Bertram', 'Claas', 'Detlef', 'Eckhard',
    'Florian', 'Gunther', 'Hartwig', 'Ivo', 'Jost', 'Kilian', 'Leopold',
    'Magnus', 'Nikolas', 'Oswin', 'Pankraz', 'Rainald', 'Severin',
    'Theobald', 'Utz', 'Veit', 'Wolfram', 'Adalbert', 'Balduin', 'Clemens',
    'Dietmar', 'Emmerich', 'Friedhelm', 'Gisbert', 'Heribert', 'Isidor',
    'Jobst', 'Kuno', 'Leonhard', 'Meinhard', 'Notker', 'Ortwin', 'Pius',
    'Ruprecht', 'Sebald', 'Thiemo', 'Ulf', 'Valentin', 'Wigand', 'Arnold',
    'Burkhard', 'Diether', 'Ewald', 'Frowin', 'Gerwin', 'Helmar', 'Irwin',
    'Jaromir', 'Kasimir', 'Ludger', 'Marbod', 'Odo', 'Radulf', 'Siegbert',
    'Tassilo', 'Walram', 'Wernher', 'Benno', 'Gottfried', 'Hubert', 'Otmar',
    'Reinhold')
NAMES_F = (
    'Adelheid', 'Berta', 'Cordula', 'Dietlinde', 'Edith', 'Frieda',
    'Gertrud', 'Hedwig', 'Ilse', 'Jutta', 'Kunigunde', 'Liesel',
    'Mechthild', 'Notburga', 'Oda', 'Petronella', 'Richza', 'Sieglinde',
    'Thekla', 'Ursel', 'Walburga', 'Agnes', 'Brunhild', 'Clara', 'Dorothea',
    'Elsbeth', 'Felicitas', 'Gisela', 'Hildegard', 'Irmgard', 'Johanna',
    'Katharina', 'Luitgard', 'Margarete', 'Ottilie', 'Philippa', 'Radegund',
    'Sophia', 'Theresia', 'Uta', 'Veronika', 'Wilhelmine', 'Alruna',
    'Benedikta', 'Caecilia', 'Dagmar', 'Emma', 'Fenja', 'Gunda', 'Helga',
    'Imma', 'Jolanda', 'Klara', 'Lioba', 'Mathilde', 'Nele', 'Odila',
    'Paulina', 'Regina', 'Swanhild', 'Tilda', 'Uda', 'Viola', 'Wendelgard',
    'Ada', 'Bertrada', 'Christa', 'Edda', 'Frauke', 'Gerlinde', 'Hilde',
    'Irma', 'Jorinde', 'Kriemhild', 'Minna', 'Nanna', 'Rotraut', 'Sigrun',
    'Trude', 'Ulla', 'Walda', 'Wiebke', 'Ermengard', 'Gerhild', 'Hiltrud')


# ---------------------------------------------------------------------------
# tiles

_TILE_TOKEN = re.compile(r'^([a-i])(\d{1,2})(?:-([a-i])?(\d{1,2}))?$', re.I)


def parse_tiles(text):
    """Tiles typed in: "f01, f02", "F1 G4", "f01-f04" (a column), "f01-g04"
    (a block). Returns (tiles in map order, bad tokens)."""
    tiles, bad = [], []
    for tok in re.split(r'[,;\s]+', (text or '').strip()):
        if not tok:
            continue
        m = _TILE_TOKEN.match(tok)
        if not m:
            bad.append(tok)
            continue
        c0 = mapdata.COLS.index(m.group(1).upper())
        r0 = int(m.group(2))
        c1 = mapdata.COLS.index(m.group(3).upper()) if m.group(3) else c0
        r1 = int(m.group(4)) if m.group(4) else r0
        if not (1 <= r0 <= mapdata.ROWS and 1 <= r1 <= mapdata.ROWS):
            bad.append(tok)
            continue
        for c in range(min(c0, c1), max(c0, c1) + 1):
            for r in range(min(r0, r1), max(r0, r1) + 1):
                tile = f'{mapdata.COLS[c]}{r}'
                if tile not in tiles:
                    tiles.append(tile)
    return sort_tiles(tiles), bad


def sort_tiles(tiles):
    def key(tile):
        s = mapdata.split_tile(tile)
        return (s[0], s[1]) if s else (99, 99)
    return sorted(set(tiles), key=key)


tile_label = mapdata.tile_label


def is_edge(tile):
    """Column A or I, row 1 or 12: the edge of the world."""
    s = mapdata.split_tile(tile)
    return s is None or s[0] in (0, len(mapdata.COLS) - 1) or \
        s[1] in (1, mapdata.ROWS)


def water_share(terrain, n=WATER_SAMPLES):
    step = UNITS // n
    wet = sum(1 for j in range(n) for i in range(n)
              if terrain.wet(i * step + step // 2, j * step + step // 2))
    return wet / float(n * n)


def usable_tiles(tiles, terrain_of):
    """{tile: water share} of the surface tiles off the edge with less than
    half of them under water; ``terrain_of(tile)`` gives lndmap.Terrain or
    None."""
    out = {}
    for tile in tiles:
        s = mapdata.split_tile(tile)
        if s is None or s[2] or is_edge(tile):
            continue
        ter = terrain_of(tile)
        if ter is None:
            continue
        w = water_share(ter)
        if w < WATER_OUT:
            out[tile] = w
    return out


def neighbours(tile):
    col, row, _sfx = mapdata.split_tile(tile)
    for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        c, r = col + dc, row + dr
        if 0 <= c < len(mapdata.COLS) and 1 <= r <= mapdata.ROWS:
            yield f'{mapdata.COLS[c]}{r}'


def pick_tiles(usable, n, rng):
    """``n`` of the usable tiles in groups of 3 or 4 neighbours; one or
    two left over join a group (a tile alone has no other tile in the
    ring of 300 to 800 m)."""
    free = sorted(usable)
    chosen = []
    while len(chosen) < n and free:
        if chosen and n - len(chosen) < CLUSTER[0]:
            cand = sorted({nb for g in chosen for nb in neighbours(g)
                           if nb in usable and nb not in chosen})
            if cand:
                chosen.append(rng.choice(cand))
                free = [x for x in free if x not in chosen]
                continue
        group = [rng.choice(free)]
        want = min(rng.randint(*CLUSTER), n - len(chosen))
        while len(group) < want:
            cand = sorted({nb for g in group for nb in neighbours(g)
                           if nb in usable and nb not in group
                           and nb not in chosen})
            if not cand:
                break
            group.append(rng.choice(cand))
        chosen += group
        free = [x for x in free if x not in chosen]
    return chosen


class TileGrid:
    """The cells of a tile a marker may go on (see the module text)."""

    def __init__(self, tile, terrain):
        self.tile, self.terrain = tile, terrain
        n = GRID
        m = EDGE_M * 64 // CELL + 1
        ok = bytearray(n * n)
        for cy in range(m, n - m):
            y = cy * CELL + CELL // 2
            row = cy * n
            for cx in range(m, n - m):
                x = cx * CELL + CELL // 2
                if terrain.passable(x, y) and not terrain.wet(x, y):
                    ok[row + cx] = 1
        good = bytearray(n * n)
        for i in range(n + 1, n * n - n - 1):
            if ok[i] and ok[i - 1] and ok[i + 1] and ok[i - n] and ok[i + n]:
                good[i] = 1
        seen = bytearray(n * n)
        best = []
        for i in range(n * n):
            if not good[i] or seen[i]:
                continue
            comp, queue = [], deque([i])
            seen[i] = 1
            while queue:
                j = queue.popleft()
                comp.append(j)
                for k in (j - 1, j + 1, j - n, j + n):
                    if good[k] and not seen[k]:
                        seen[k] = 1
                        queue.append(k)
            if len(comp) > len(best):
                best = comp
        self.cells = best
        self.ok = bytearray(n * n)
        for j in best:
            self.ok[j] = 1

    def random_point(self, rng):
        j = rng.choice(self.cells)
        return (j % GRID * CELL + rng.randrange(CELL),
                j // GRID * CELL + rng.randrange(CELL))

    def fits(self, x, y):
        cx, cy = int(x) // CELL, int(y) // CELL
        return 0 <= cx < GRID and 0 <= cy < GRID and \
            bool(self.ok[cy * GRID + cx])


def to_map(tile, x, y):
    """Map position in metres (north up)."""
    return mapdata.world_to_map(tile, x, y, px=M)


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class Placer:
    """Random spots on the grids of the chosen tiles."""

    def __init__(self, grids, rng):
        self.grids = {k: g for k, g in grids.items() if g.cells}
        self.rng = rng
        self.tiles = sorted(self.grids)
        self.weights = [len(self.grids[k].cells) for k in self.tiles]
        self.givers = []

    def spot(self, tile, x, y):
        return {'tile': tile, 'x': int(x), 'y': int(y),
                'z': self.grids[tile].terrain.height(x, y)}

    def anywhere(self, allowed=None):
        tiles, weights = self.tiles, self.weights
        if allowed:
            tiles = [k for k in self.tiles if k in allowed]
            weights = [len(self.grids[k].cells) for k in tiles]
        if not tiles:
            return None
        tile = self.rng.choices(tiles, weights)[0]
        return (tile,) + self.grids[tile].random_point(self.rng)

    def giver(self, blocked=lambda tile: False, allowed=None):
        """GIVER_GAP_M from every giver so far (else the widest gap of the
        tries); ``blocked(tile)``: the giver's number is taken there;
        ``allowed``: the tiles of the quest (None: all)."""
        best, best_gap = None, -1.0
        for _ in range(TRIES):
            got = self.anywhere(allowed)
            if got is None:
                return None
            tile, x, y = got
            if blocked(tile):
                continue
            p = to_map(tile, x, y)
            gap = min((distance(p, q) for q in self.givers), default=1e9)
            if gap > best_gap:
                best, best_gap = (tile, x, y), gap
            if gap >= GIVER_GAP_M:
                break
        if best is None:
            return None
        self.givers.append(to_map(*best))
        return self.spot(*best)

    def around(self, spot, lo, hi, tries=TRIES, allowed=None):
        """A spot lo to hi metres from ``spot`` on a chosen tile (of
        ``allowed``), None when the tries find none."""
        centre = to_map(spot['tile'], spot['x'], spot['y'])
        for _ in range(tries):
            ang = self.rng.uniform(0.0, 2 * math.pi)
            r = math.sqrt(self.rng.uniform(lo * lo, hi * hi))
            got = mapdata.map_to_world(centre[0] + r * math.cos(ang),
                                       centre[1] + r * math.sin(ang), px=M)
            if got is None:
                continue
            tile, x, y = got
            if allowed and tile not in allowed:
                continue
            g = self.grids.get(tile)
            if g is not None and g.fits(x, y):
                return self.spot(tile, x, y)
        return None


# ---------------------------------------------------------------------------
# one quest

def _task_range(src):
    task = src.task()
    try:
        return int((task.get('args') or {}).get('range') or 0)
    except (TypeError, ValueError):
        return 0


def anchor_index(targets, refs):
    """The target that is 300 to 800 m from the giver: the one of the task,
    else the first object, else the first line."""
    rest = [k for k, tg in enumerate(targets)
            if tg['key'] != mpmerge.GIVER_KEY and not tg.get('exists')]
    if not rest:
        return None
    for k in rest:
        if any(refs[i]['where'] == 'task' for i in targets[k]['refs']):
            return k
    for k in rest:
        if targets[k]['name'] == 'MARKER_QUEST_CREATE_OBJECT':
            return k
    return rest[0]


def place_quest(src, targets, placer, number_of, blocked, band=TARGET_M,
                allowed=None):
    """Set 'placed' on every target that the game does not have. Returns
    'ok', 'relaxed' (the tiles of the quest had no room for the band: the
    target is as near or far as they allow) or False (no spot at all, the
    quest is left out)."""
    refs = mpmerge.marker_refs(src)
    giver = next(tg for tg in targets if tg['key'] == mpmerge.GIVER_KEY)
    anchor = anchor_index(targets, refs)
    near = NEAR_M
    rng = _task_range(src)
    if rng:
        near = max(4, min(NEAR_M, rng // 2))
    result = 'ok'
    g = a = None
    for attempt in range(24):
        lo, hi = band
        if attempt >= 20:                # relaxed: the tiles are too few
            lo, hi, result = 0, 5000, 'relaxed'
        g = placer.giver(blocked, allowed)
        if g is None:
            return False
        if anchor is None:
            break
        a = placer.around(g, lo, hi, allowed=allowed)
        if a is not None:
            break
        placer.givers.pop()              # this giver has no target: again
        g = None
    if g is None:
        return False
    giver['placed'] = dict(g, num=giver['num'])
    number_of(giver)
    for k, tg in enumerate(targets):
        if tg is giver or tg.get('exists'):
            continue
        if k == anchor:
            spot = a
        else:
            spot = placer.around(a or g, 2, near, allowed=allowed) or \
                dict(a or g)
        tg['placed'] = dict(spot, num=None)
        number_of(tg)
    return result


# ---------------------------------------------------------------------------
# the whole batch

def giver_unit(index, npc):
    rec = ((index.npc(npc) if index else None) or {}).get('record') or ''
    parts = rec.split()
    return parts[11].split('(')[0] if len(parts) > 11 else ''


def taken_names(index, project):
    names = {str(n.get('name') or '').lower()
             for n in (index.npcs.values() if index else [])}
    for q in project.quests:
        for s in q.speakers:
            names.add(str(s.get('name') or '').lower())
    return names


class Batch:
    """Plan (roll) and build (take) every open multiplayer quest."""

    def __init__(self, app):
        self.app = app
        self.game = app.cfg.get('game_dir')
        self.retail_tiles = (app.modset.retail_tiles if app.modset
                             else mods.retail_markers(self.game))
        self.jobs = []
        self.skipped = []           # (quest id, reason key)
        self.relaxed = []           # quest ids with the target off the band
        self.tiles = []
        self.empty = []             # chosen tiles without room for a marker
        self.own_maps = {}          # tile: own .lnd (Smoothness' maps)
        self.seed = None
        self._terrain, self._heads = {}, {}

    # -- what there is ----------------------------------------------------------

    def open_quests(self):
        idx = self.app.index
        done = {q.extra.get('mp_source') for q in self.app.project.quests}
        return [int(k) for k in sorted(idx.quests, key=int)
                if mpmerge.is_mp_quest(int(k)) and int(k) not in done]

    def free_quest_ids(self):
        app = self.app
        taken = {q.id for q in app.project.quests}
        if app.modset:
            taken |= app.modset.quest_ids()
        return app.index.free_ids(taken)

    def free_npc_ids(self, n):
        idx, project = self.app.index, self.app.project
        used = {int(k) for k in idx.npcs}
        for q in project.quests:
            used |= {s['id'] for s in q.speakers if isinstance(s['id'], int)}
        retail_max = max([i for i in used if i <= mpmerge.MAX_NPC_ID] + [0])
        out = [i for i in range(retail_max + 1, mpmerge.MAX_NPC_ID + 1)
               if i not in used]
        return out[:n]

    # -- maps -------------------------------------------------------------------

    def set_own_map(self, tile, path):
        """An own .lnd for a tile (None: the original level again)."""
        if path:
            self.own_maps[tile] = path
        else:
            self.own_maps.pop(tile, None)
        self._terrain.pop(tile, None)
        self._heads.pop(tile, None)

    def _body(self, tile):
        own = self.own_maps.get(tile)
        if own:
            with open(own, 'rb') as f:
                return placed._unwrap_file(f.read())
        app = self.app
        return placed.base_of(app.project, app.modset, self.game, tile)[0]

    def _load(self, tile):
        """Terrain of a tile as the project builds it (own map, mod or
        game), cached; None for a map that cannot be read."""
        if tile not in self._terrain:
            body = self._body(tile)
            ter = None
            if body:
                try:
                    ter = lndmap.Terrain(body)
                except Exception:        # a map we cannot read: left out
                    ter = None
            self._terrain[tile] = ter
        return self._terrain[tile]

    def _head(self, tile):
        """The marker block of a chosen tile as placed.generate will write
        it (the game's markers put back): what marker numbers count."""
        if tile not in self._heads:
            body = self._body(tile)
            head = None
            if body:
                retail = placed.retail_body(self.game, self.app.modset, tile)
                if retail:
                    body = placed.build_body(body, retail, [])[0]
                head = placed.marker_head(body)
            self._heads[tile] = head
        return self._heads[tile]

    def surface(self):
        return sorted(k for k in self.retail_tiles
                      if (mapdata.split_tile(k) or (0, 0, 'x'))[2] == '')

    # -- rolling -----------------------------------------------------------------

    def roll(self, n_tiles=TILES, band=TARGET_M, seed=None,
             progress=lambda text: None, tiles=None, quest_tiles=None,
             with_tiles=()):
        """Choose the tiles and a spot for every marker of every open
        quest. Nothing is written. ``tiles``: the tiles typed in (None:
        ``n_tiles`` rolled, groups of neighbours, edge and water out);
        ``quest_tiles`` {quest id: [tiles]}: where a quest may go (they
        join the tiles); ``with_tiles``: tiles that always join (those with
        an own map)."""
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        rng = random.Random(self.seed)
        self.jobs, self.skipped, self.relaxed, self.empty = [], [], [], []
        quest_tiles = {k: v for k, v in (quest_tiles or {}).items() if v}
        wanted = {x for v in quest_tiles.values() for x in v}
        wanted |= set(with_tiles)
        if tiles:
            chosen = list(tiles)
        else:
            progress(t('mpb.p.tiles'))
            usable = usable_tiles(self.surface(), self._load)
            chosen = pick_tiles({k: v for k, v in usable.items()
                                 if k not in wanted},
                                max(0, n_tiles - len(wanted)), rng)
        self.tiles = sort_tiles(set(chosen) | wanted)
        grids = {}
        for k, tile in enumerate(self.tiles):
            progress(t('mpb.p.grid', tile=tile, i=k + 1, n=len(self.tiles)))
            ter = self._load(tile)
            grid = TileGrid(tile, ter) if ter is not None else None
            if grid is None or not grid.cells:
                self.empty.append(tile)
                continue
            grids[tile] = grid
            self._head(tile)
        placer = Placer(grids, rng)
        qids = self.open_quests()
        new_ids = self.free_quest_ids()
        npc_ids = self.free_npc_ids(len(qids))
        names = taken_names(self.app.index, self.app.project)
        pools = {True: [x for x in NAMES_F if x.lower() not in names],
                 False: [x for x in NAMES_M if x.lower() not in names]}
        for pool in pools.values():
            rng.shuffle(pool)
        others = [dict(p) for p in placed.placements(self.app.project)]

        def number_of(tg):
            p = tg['placed']
            if p.get('num') is None:
                p['num'] = placed.free_number(tg['name'], p['tile'],
                                              self._head(p['tile']), others)
            others.append({'name': tg['name'], 'tile': p['tile'],
                           'num': int(p['num'])})

        for k, qid in enumerate(qids):
            if k % 10 == 0:
                progress(t('mpb.p.quests', i=k + 1, n=len(qids)))
            if not new_ids:
                self.skipped.append((qid, 'mpb.skip.ids'))
                continue
            if not npc_ids:
                self.skipped.append((qid, 'mpb.skip.npcs'))
                continue
            src = self.app.build_game_quest(qid)
            if src is None:
                self.skipped.append((qid, 'mpb.skip.load'))
                continue
            mpmerge.recover_null_lines(src)
            npc = npc_ids[0]
            targets = mpmerge.marker_targets(src, npc, self.retail_tiles)

            def blocked(tile, npc=npc):
                return placed.marker_exists(self._head(tile), GIVER,
                                            npc) or any(
                    o['tile'] == tile and o['name'] == GIVER
                    and int(o['num']) == npc for o in others)
            allowed = set(quest_tiles.get(qid) or ()) or None
            if allowed and not allowed & set(grids):
                self.skipped.append((qid, 'mpb.skip.tiles'))
                continue
            done = place_quest(src, targets, placer, number_of, blocked,
                               band, allowed)
            if not done:
                self.skipped.append((qid, 'mpb.skip.spot'))
                continue
            if done == 'relaxed':
                self.relaxed.append(qid)
            female = '_F_' in giver_unit(self.app.index, src.giver)
            pool = pools[female] or pools[not female]
            name = pool.pop() if pool else f'NPC_{npc}'
            self.jobs.append({'qid': qid, 'src': src, 'new_id': new_ids.pop(0),
                              'npc': npc_ids.pop(0), 'name': name,
                              'targets': targets})
        return self.jobs

    def tile_counts(self):
        out = {}
        for job in self.jobs:
            for tg in job['targets']:
                p = tg.get('placed')
                if p:
                    out[p['tile']] = out.get(p['tile'], 0) + 1
        return out

    # -- taking -------------------------------------------------------------------

    def default_group(self):
        idx = self.app.index
        pred = idx.quest(4) if idx else None
        return pred['group'] if pred else None

    def build(self, active=False, progress=lambda text: None):
        """The single player quests of the rolled jobs, the markers into
        the maps of the project (one rebuild of the tiles for all).
        Returns (quests, report)."""
        from . import placewin
        app = self.app
        group = self.default_group()
        pairs = []
        for k, job in enumerate(self.jobs):
            if k % 10 == 0:
                progress(t('mpb.p.build', i=k + 1, n=len(self.jobs)))
            src = job['src']
            journal = dict(src.journal)
            mpmerge.default_journal(journal)
            new = mpmerge.take_over(
                src, job['new_id'], job['npc'], job['name'], job['targets'],
                self.retail_tiles, group=group, active=active,
                availability=mpmerge.START, title=src.title, journal=journal)
            new.extra['mp_batch'] = self.seed
            app.project.quests.append(new)
            pairs.append((new, mpmerge.commit_targets(job['targets'])))
        progress(t('mpb.p.maps', n=len(self.tile_counts())))
        self.import_own_maps()
        report = placewin.commit_many(app, pairs)
        app.project.extra['mp_batch'] = {
            'seed': self.seed, 'tiles': list(self.tiles),
            'own_maps': {k: os.path.basename(v)
                         for k, v in self.own_maps.items()},
            'quests': [q.id for q, _tg in pairs]}
        return [q for q, _tg in pairs], report

    def import_own_maps(self):
        """The own maps of the tiles that got markers into the project's
        levels folder, like maps from the editor (app.import_editor_maps):
        placed.generate then writes the markers into them and keeps the
        file itself in <project>_levels_base."""
        used = set(self.tile_counts())
        paths = [p for k, p in self.own_maps.items() if k in used]
        if not paths:
            return []
        project = self.app.project
        dest = editormaps.levels_dir(project)
        items, _skipped = editormaps.plan_import(paths)
        done = editormaps.import_maps(items, dest)
        key = os.path.normcase(os.path.abspath(dest))
        if not any(os.path.normcase(os.path.abspath(m['path'])) == key
                   for m in project.mods):
            project.mods.append({'path': dest, 'enabled': True})
        return done


# ---------------------------------------------------------------------------
# window

class BatchWindow:
    """Quest > Take over all multiplayer quests: settings, the tiles with
    their own maps, the quests with their tiles, "Roll" (the result is
    shown, nothing written), "Take all over"."""

    _open = None

    @classmethod
    def show(cls, app):
        w = cls._open
        if w is not None:
            try:
                w.win.lift()
                return w
            except tk.TclError:
                cls._open = None
        cls._open = cls(app)
        return cls._open

    def __init__(self, app):
        self.app = app
        self.batch = Batch(app)
        self.rolled = False
        self.qvars = {}
        self.win = tk.Toplevel(app.root)
        self.win.title(t('mpb.title'))
        self.win.geometry('1180x860')
        self.win.minsize(980, 700)
        self.win.transient(app.root)
        theme.dark_titlebar(self.win)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.win.bind('<Escape>', lambda e: self.close())
        f = ttk.Frame(self.win, padding=14)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=t('mpb.head'), style='Brand.TLabel').pack(anchor='w')
        ttk.Label(f, text=t('mpb.intro'), style='Muted.TLabel',
                  wraplength=1140, justify='left').pack(anchor='w', pady=(2, 8))
        top = ttk.Frame(f)
        top.pack(fill='x')
        self.info = ttk.Label(top, text='', justify='left')
        self.info.pack(side='left', anchor='n')
        self.limit_btn = ttk.Button(top, text=t('mpb.limit.btn'),
                                    command=self.app.show_quest_limit)

        # settings
        opts = ttk.Frame(f)
        opts.pack(fill='x', pady=(10, 4))
        opts.columnconfigure(3, weight=1)
        self.mode = tk.StringVar(value='random')
        ttk.Label(opts, text=t('mpb.tiles')).grid(row=0, column=0, sticky='w')
        ttk.Radiobutton(opts, text=t('mpb.mode.random'), value='random',
                        variable=self.mode, command=self._changed
                        ).grid(row=0, column=1, sticky='w', padx=(8, 4))
        self.n_tiles = tk.StringVar(value=str(TILES))
        ttk.Spinbox(opts, from_=1, to=66, width=5, textvariable=self.n_tiles,
                    command=self._changed).grid(row=0, column=2, sticky='w')
        ttk.Label(opts, text=t('mpb.tiles.note'), style='Muted.TLabel',
                  wraplength=700, justify='left'
                  ).grid(row=0, column=3, sticky='w', padx=(10, 0))
        ttk.Radiobutton(opts, text=t('mpb.mode.list'), value='list',
                        variable=self.mode, command=self._changed
                        ).grid(row=1, column=1, sticky='w', padx=(8, 4),
                               pady=(4, 0))
        self.tiles_text = tk.StringVar()
        ent = ttk.Entry(opts, textvariable=self.tiles_text, width=34)
        ent.grid(row=1, column=2, columnspan=2, sticky='w', pady=(4, 0))
        ent.bind('<FocusIn>', lambda e: self.mode.set('list'))
        self.tiles_text.trace_add('write', lambda *_: self._changed())
        theme.Tooltip(ent, t('mpb.tiles.tip'))
        ttk.Label(opts, text=t('mpb.dist')).grid(row=2, column=0, sticky='w',
                                                 pady=(6, 0))
        dist = ttk.Frame(opts)
        dist.grid(row=2, column=1, columnspan=3, sticky='w', padx=8,
                  pady=(6, 0))
        self.d_lo = tk.StringVar(value=str(TARGET_M[0]))
        self.d_hi = tk.StringVar(value=str(TARGET_M[1]))
        ttk.Spinbox(dist, from_=0, to=3000, increment=50, width=6,
                    textvariable=self.d_lo, command=self._changed
                    ).pack(side='left')
        ttk.Label(dist, text=t('mpb.to')).pack(side='left', padx=6)
        ttk.Spinbox(dist, from_=50, to=5000, increment=50, width=6,
                    textvariable=self.d_hi, command=self._changed
                    ).pack(side='left')
        ttk.Label(dist, text='m').pack(side='left', padx=(6, 0))
        self.active = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text=t('mpb.active'), variable=self.active
                        ).grid(row=3, column=0, columnspan=4, sticky='w',
                               pady=(6, 0))

        # buttons and status at the bottom (packed first: they keep room)
        btns = ttk.Frame(f)
        btns.pack(side='bottom', fill='x', pady=(10, 0))
        style = ttk.Style(self.win)
        style.configure('Confirm.TButton', background=theme.OK,
                        foreground='#0b1a0f', font=theme.FONT_BOLD)
        style.map('Confirm.TButton',
                  background=[('active', theme.mix(theme.OK, '#ffffff', 0.2)),
                              ('disabled', theme.MUT)])
        self.roll_btn = ttk.Button(btns, text=t('mpb.roll'),
                                   style='Accent.TButton', command=self.roll)
        self.roll_btn.pack(side='left')
        self.take_btn = ttk.Button(btns, text='✓ ' + t('mpb.take'),
                                   style='Confirm.TButton', command=self.take)
        self.take_btn.pack(side='left', padx=8)
        self.take_btn.state(['disabled'])
        self.map_btn = ttk.Button(btns, text=t('mpb.map'),
                                  command=self.app.show_map)
        ttk.Button(btns, text=t('close'), command=self.close
                   ).pack(side='right')
        self.status = ttk.Label(f, text='', style='Muted.TLabel',
                                wraplength=1140, justify='left')
        self.status.pack(side='bottom', anchor='w', pady=(6, 0))
        self.txt = tk.Text(f, wrap='word', font=theme.FONT_MONO, height=8)
        self.txt.pack(side='bottom', fill='x', pady=(8, 0))
        self.txt.configure(state='disabled')

        # the two lists
        lists = ttk.Frame(f)
        lists.pack(fill='both', expand=True, pady=(8, 0))
        lists.columnconfigure(0, weight=2, uniform='l')
        lists.columnconfigure(1, weight=3, uniform='l')
        lists.rowconfigure(1, weight=1)
        head = ttk.Frame(lists)
        head.grid(row=0, column=0, sticky='ew', padx=(0, 12))
        ttk.Label(head, text=t('mpb.tilelist'), font=theme.FONT_BOLD
                  ).pack(side='left')
        ttk.Button(head, text=t('mpb.maps.many'), command=self._many_maps
                   ).pack(side='right')
        ttk.Label(lists, text=t('mpb.questlist'), font=theme.FONT_BOLD
                  ).grid(row=0, column=1, sticky='w')
        self.tile_box = self._scroll(lists, 0, (0, 12))
        self.quest_box = self._scroll(lists, 1, (0, 0))
        ttk.Label(lists, text=t('mpb.tilelist.note'), style='Muted.TLabel',
                  wraplength=440, justify='left'
                  ).grid(row=2, column=0, sticky='w', padx=(0, 12),
                         pady=(4, 0))
        ttk.Label(lists, text=t('mpb.questlist.note'), style='Muted.TLabel',
                  wraplength=660, justify='left'
                  ).grid(row=2, column=1, sticky='w', pady=(4, 0))
        self._info()
        self._quest_rows()
        self._tile_rows()

    # -- helpers -----------------------------------------------------------------

    def close(self):
        BatchWindow._open = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _scroll(self, parent, column, padx):
        box = ttk.Frame(parent)
        box.grid(row=1, column=column, sticky='nsew', padx=padx)
        cv = tk.Canvas(box, bg=theme.BG, highlightthickness=0, height=80)
        sb = ttk.Scrollbar(box, orient='vertical', command=cv.yview)
        inner = ttk.Frame(cv)
        item = cv.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: cv.configure(
            scrollregion=cv.bbox('all')))
        cv.bind('<Configure>', lambda e: cv.itemconfigure(item, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        cv.pack(side='left', fill='both', expand=True)
        inner._canvas = cv
        return inner

    def _wheel(self, inner, widgets):
        cv = inner._canvas

        def roll(ev):
            cv.yview_scroll(-3 if ev.delta > 0 else 3, 'units')
            return 'break'
        for w in [cv, inner] + list(widgets):
            w.bind('<MouseWheel>', roll)

    def _put(self, lines):
        self.txt.configure(state='normal')
        self.txt.delete('1.0', 'end')
        self.txt.insert('end', '\n'.join(lines))
        self.txt.configure(state='disabled')

    def _progress(self, text):
        self.status.configure(text=text, foreground=theme.MUT)
        try:
            self.win.update()
        except tk.TclError:
            pass

    def _info(self):
        b = self.batch
        n = len(b.open_quests())
        ids = len(b.free_quest_ids())
        npcs = len(b.free_npc_ids(1000))
        self.info.configure(text='\n'.join([
            t('mpb.open', n=n),
            t('mpb.ids', n=ids, limit=self.app.index.quest_limit),
            t('mpb.npcs', n=npcs)]),
            foreground=theme.WARN if ids < n else theme.INK)
        if ids < n:
            self.limit_btn.pack(side='left', anchor='n', padx=(20, 0))
        else:
            self.limit_btn.pack_forget()
        self.roll_btn.state(['!disabled'] if n else ['disabled'])
        if not n:
            self.status.configure(text=t('mpb.none'))

    def _changed(self):
        """Something the roll depends on changed: roll again first."""
        if self.rolled:
            self.rolled = False
            self.take_btn.state(['disabled'])
            self.status.configure(text=t('mpb.changed'),
                                  foreground=theme.WARN)
        self._tile_rows()

    # -- the tiles ---------------------------------------------------------------

    def _typed_tiles(self):
        tiles, bad = parse_tiles(self.tiles_text.get())
        return tiles, bad

    def _quest_tiles(self):
        """({quest id: [tiles]}, [(quest id, bad token)])."""
        out, bad = {}, []
        for qid, var in self.qvars.items():
            tiles, wrong = parse_tiles(var.get())
            if tiles:
                out[qid] = tiles
            bad += [(qid, w) for w in wrong]
        return out, bad

    def _shown_tiles(self):
        if self.rolled:
            tiles = set(self.batch.tiles) | set(self.batch.empty)
        else:
            tiles = set()
            if self.mode.get() == 'list':
                tiles |= set(self._typed_tiles()[0])
            for v in self._quest_tiles()[0].values():
                tiles |= set(v)
        return sort_tiles(tiles | set(self.batch.own_maps))

    def _tile_rows(self):
        box = self.tile_box
        for w in box.winfo_children():
            w.destroy()
        tiles = self._shown_tiles()
        counts = self.batch.tile_counts() if self.rolled else {}
        widgets = []
        if not tiles:
            lbl = ttk.Label(box, text=t('mpb.tiles.none'),
                            style='Muted.TLabel', wraplength=420,
                            justify='left')
            lbl.pack(anchor='w', pady=4)
            widgets.append(lbl)
        for tile in tiles:
            row = ttk.Frame(box)
            row.pack(fill='x', pady=1)
            own = self.batch.own_maps.get(tile)
            name = ttk.Label(row, text=tile_label(tile), width=5,
                             font=theme.FONT_BOLD)
            name.pack(side='left')
            text = os.path.basename(own) if own else t('mpb.orig')
            notes = []
            if self.rolled:
                notes.append(t('mpb.tile.n', n=counts.get(tile, 0)))
            if tile in self.batch.empty:
                notes.append(t('mpb.tile.empty'))
            if is_edge(tile):
                notes.append(t('mpb.tile.edge'))
            src = ttk.Label(row, text=text + ('   ' + ', '.join(notes)
                                              if notes else ''),
                            foreground=theme.OK if own else theme.MUT)
            src.pack(side='left', padx=(6, 0))
            pick = ttk.Button(row, text=t('mpb.map.pick'), width=8,
                              command=lambda k=tile: self._pick_map(k))
            if own:
                x = ttk.Button(row, text='✕', width=3,
                               command=lambda k=tile: self._set_map(k, None))
                x.pack(side='right')
                theme.Tooltip(x, t('mpb.map.clear'))
                widgets.append(x)
            pick.pack(side='right', padx=(0, 4))
            widgets += [row, name, src, pick]
        self._wheel(box, widgets)

    def _set_map(self, tile, path):
        self.batch.set_own_map(tile, path)
        self._changed()

    def _check_map(self, path):
        """The tile an own map is for (from its name), None after a
        message when the name does not tell."""
        info = editormaps.parse_name(path)
        if not info or info[0] != info[0].split('_')[0]:
            messagebox.showwarning(t('mpb.title'), t(
                'mpb.map.bad', file=os.path.basename(path)), parent=self.win)
            return None
        return info[0]

    def _pick_map(self, tile):
        start = editormaps.EDITOR_LEVELS
        path = filedialog.askopenfilename(
            title=t('mpb.map.title', tile=tile_label(tile)), parent=self.win,
            initialdir=start if os.path.isdir(start) else None,
            filetypes=[(t('em.filter'), '*.lnd'), (t('em.filter.all'), '*.*')])
        if not path:
            return
        got = self._check_map(path)
        if got is None:
            return
        if got != tile:
            messagebox.showwarning(t('mpb.title'), t(
                'mpb.map.other', file=os.path.basename(path),
                tile=tile_label(got), want=tile_label(tile)), parent=self.win)
            return
        self._set_map(tile, path)

    def _many_maps(self):
        """Several own maps at once, each to the tile its name tells."""
        start = editormaps.EDITOR_LEVELS
        paths = filedialog.askopenfilenames(
            title=t('mpb.maps.many'), parent=self.win,
            initialdir=start if os.path.isdir(start) else None,
            filetypes=[(t('em.filter'), '*.lnd'), (t('em.filter.all'), '*.*')])
        for path in paths or ():
            tile = self._check_map(path)
            if tile is not None:
                self.batch.set_own_map(tile, path)
        if paths:
            self._changed()

    # -- the quests --------------------------------------------------------------

    def _quest_rows(self):
        box = self.quest_box
        for w in box.winfo_children():
            w.destroy()
        idx = self.app.index
        widgets = []
        old = {k: v.get() for k, v in self.qvars.items()}
        self.qvars = {}
        for qid in self.batch.open_quests():
            info = idx.quest(qid) or {}
            row = ttk.Frame(box)
            row.pack(fill='x', pady=1)
            var = tk.StringVar(value=old.get(qid, ''))
            var.trace_add('write', lambda *_: self._changed())
            ent = ttk.Entry(row, textvariable=var, width=18)
            ent.pack(side='right', padx=(6, 4))
            lbl = ttk.Label(row, text=f"Q_{qid}  {info.get('title') or ''}")
            lbl.pack(side='left', fill='x', expand=True)
            self.qvars[qid] = var
            widgets += [row, ent, lbl]
        if not self.qvars:
            lbl = ttk.Label(box, text=t('mpb.none'), style='Muted.TLabel')
            lbl.pack(anchor='w', pady=4)
            widgets.append(lbl)
        self._wheel(box, widgets)

    # -- roll and take -----------------------------------------------------------

    def _settings(self):
        """(n tiles, band, typed tiles or None, quest tiles), None after a
        message in the status line."""
        try:
            n = max(1, int(self.n_tiles.get()))
            lo, hi = int(self.d_lo.get()), int(self.d_hi.get())
        except ValueError:
            n = lo = hi = None
        if n is None or hi <= lo:
            self.status.configure(text=t('mpb.bad'), foreground=theme.ERR)
            return None
        tiles = None
        if self.mode.get() == 'list':
            tiles, bad = self._typed_tiles()
            if bad or not tiles:
                self.status.configure(text=t(
                    'mpb.tiles.bad', bad=', '.join(bad) or '-'),
                    foreground=theme.ERR)
                return None
        quest_tiles, qbad = self._quest_tiles()
        if qbad:
            self.status.configure(text=t('mpb.quest.bad', items=', '.join(
                f'Q_{q}: {w}' for q, w in qbad[:6])), foreground=theme.ERR)
            return None
        return n, (lo, hi), tiles, quest_tiles

    def roll(self):
        vals = self._settings()
        if vals is None:
            return
        n, band, tiles, quest_tiles = vals
        self.roll_btn.state(['disabled'])
        self.take_btn.state(['disabled'])
        self.win.configure(cursor='watch')
        try:
            # tiles with an own map always join the tiles
            jobs = self.batch.roll(n, band, progress=self._progress,
                                   tiles=tiles, quest_tiles=quest_tiles,
                                   with_tiles=sorted(self.batch.own_maps))
        except Exception as e:           # shown, nothing was written
            self.status.configure(text=t('mpb.error', e=e),
                                  foreground=theme.ERR)
            return
        finally:
            self.win.configure(cursor='')
            self.roll_btn.state(['!disabled'])
        self.rolled = True
        self.roll_btn.configure(text=t('mpb.reroll'))
        counts = self.batch.tile_counts()
        lines = [t('mpb.result', n=len(jobs), m=sum(counts.values()),
                   tiles=len(counts))]
        if self.batch.empty:
            lines.append(t('mpb.empty', tiles=', '.join(
                tile_label(k) for k in self.batch.empty)))
        if self.batch.relaxed:
            lines.append(t('mpb.relaxed', n=len(self.batch.relaxed),
                           ids=', '.join(f'Q_{q}' for q in
                                         self.batch.relaxed[:10])))
        if self.batch.skipped:
            lines.append(t('mpb.skipped', n=len(self.batch.skipped)))
            for qid, key in self.batch.skipped[:12]:
                lines.append(f'  Q_{qid}: ' + t(key))
        lines += ['', t('mpb.examples')]
        for job in jobs[:6]:
            g = job['targets'][0]['placed']
            lines.append(t('mpb.example', old=job['qid'], new=job['new_id'],
                           title=job['src'].title, name=job['name'],
                           tile=tile_label(g['tile'])))
        self._put(lines)
        self._tile_rows()
        self.status.configure(text=t('mpb.rolled', seed=self.batch.seed),
                              foreground=theme.MUT)
        if jobs:
            self.take_btn.state(['!disabled'])

    def ensure_saved(self):
        from . import data
        app = self.app
        if editormaps.levels_dir(app.project):
            return True
        path = data.default_project_path(t('mpb.project'))
        if not app._write_project(path):
            return False
        app.set_info(t('mp.saved', path=path), 'StatusOk.TLabel')
        return True

    def take(self):
        if not self.rolled or not self.batch.jobs or not self.ensure_saved():
            return
        own = sorted(k for k in self.batch.tile_counts()
                     if k in self.batch.own_maps)
        text = t('mpb.take.q', n=len(self.batch.jobs),
                 tiles=len(self.batch.tile_counts()))
        if own:
            text += '\n\n' + t('mpb.take.own', tiles=', '.join(
                tile_label(k) for k in own))
        if not messagebox.askyesno(t('mpb.title'), text, parent=self.win):
            return
        app = self.app
        self.take_btn.state(['disabled'])
        self.roll_btn.state(['disabled'])
        self.win.configure(cursor='watch')
        try:
            quests, report = self.batch.build(self.active.get(),
                                              progress=self._progress)
        except Exception as e:
            self.win.configure(cursor='')
            self.roll_btn.state(['!disabled'])
            self.status.configure(text=t('mpb.error', e=e),
                                  foreground=theme.ERR)
            return
        self.win.configure(cursor='')
        app.mark_dirty()
        if app.project.path:
            app._write_project(app.project.path)
        try:
            app.timeline.refresh()
        except Exception:
            pass
        clash = [c for r in (report or {}).values() for c in r['clash']]
        lines = [t('mpb.done', n=len(quests),
                   first=quests[0].id if quests else '-',
                   last=quests[-1].id if quests else '-')]
        if own:
            lines.append(t('mpb.done.own', tiles=', '.join(
                tile_label(k) for k in own)))
        if clash:
            lines.append(t('mpb.clash', n=len(clash)))
        lines.append(t('mpb.next'))
        self._put(lines)
        self.status.configure(text='', foreground=theme.MUT)
        self.batch.jobs = []
        self.rolled = False
        self.map_btn.pack(side='left', padx=8)
        self._info()
        self._quest_rows()
        self._tile_rows()
