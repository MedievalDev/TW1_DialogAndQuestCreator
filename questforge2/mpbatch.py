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
"""

import math
import random
from collections import deque

import tkinter as tk
from tkinter import messagebox, ttk

from . import lndmap, mapdata, mods, mpmerge, placed, theme
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

    def anywhere(self):
        tile = self.rng.choices(self.tiles, self.weights)[0]
        return (tile,) + self.grids[tile].random_point(self.rng)

    def giver(self, blocked=lambda tile: False):
        """GIVER_GAP_M from every giver so far (else the widest gap of the
        tries); ``blocked(tile)``: the giver's number is taken there."""
        best, best_gap = None, -1.0
        for _ in range(TRIES):
            tile, x, y = self.anywhere()
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

    def around(self, spot, lo, hi, tries=TRIES):
        """A spot lo to hi metres from ``spot`` on a chosen tile, None when
        the tries find none."""
        centre = to_map(spot['tile'], spot['x'], spot['y'])
        for _ in range(tries):
            ang = self.rng.uniform(0.0, 2 * math.pi)
            r = math.sqrt(self.rng.uniform(lo * lo, hi * hi))
            got = mapdata.map_to_world(centre[0] + r * math.cos(ang),
                                       centre[1] + r * math.sin(ang), px=M)
            if got is None:
                continue
            tile, x, y = got
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


def place_quest(src, targets, placer, number_of, blocked, band=TARGET_M):
    """Set 'placed' on every target that the game does not have. Returns
    False when no spot was found (the quest is left out)."""
    refs = mpmerge.marker_refs(src)
    giver = next(tg for tg in targets if tg['key'] == mpmerge.GIVER_KEY)
    anchor = anchor_index(targets, refs)
    near = NEAR_M
    rng = _task_range(src)
    if rng:
        near = max(4, min(NEAR_M, rng // 2))
    for _attempt in range(20):
        g = placer.giver(blocked)
        if g is None:
            return False
        a = None
        if anchor is not None:
            a = placer.around(g, *band)
            if a is None:
                placer.givers.pop()      # this giver has no target: again
                continue
        giver['placed'] = dict(g, num=giver['num'])
        number_of(giver)
        for k, tg in enumerate(targets):
            if tg is giver or tg.get('exists'):
                continue
            if k == anchor:
                spot = a
            else:
                spot = placer.around(a or g, 2, near) or dict(a or g)
            tg['placed'] = dict(spot, num=None)
            number_of(tg)
        return True
    return False


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
        self.tiles = []
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

    def _body(self, tile):
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
             progress=lambda text: None):
        """Choose the tiles and a spot for every marker of every open
        quest. Nothing is written."""
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        rng = random.Random(self.seed)
        self.jobs, self.skipped = [], []
        progress(t('mpb.p.tiles'))
        usable = usable_tiles(self.surface(), self._load)
        self.tiles = pick_tiles(usable, n_tiles, rng)
        grids = {}
        for k, tile in enumerate(self.tiles):
            progress(t('mpb.p.grid', tile=tile, i=k + 1, n=len(self.tiles)))
            grids[tile] = TileGrid(tile, self._load(tile))
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
            if not place_quest(src, targets, placer, number_of, blocked,
                               band):
                self.skipped.append((qid, 'mpb.skip.spot'))
                continue
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
        report = placewin.commit_many(app, pairs)
        app.project.extra['mp_batch'] = {
            'seed': self.seed, 'tiles': list(self.tiles),
            'quests': [q.id for q, _tg in pairs]}
        return [q for q, _tg in pairs], report


# ---------------------------------------------------------------------------
# window

class BatchWindow:
    """Quest > Take over all multiplayer quests: settings, "Roll" (the
    result is shown, nothing written), "Take over"."""

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
        self.win = tk.Toplevel(app.root)
        self.win.title(t('mpb.title'))
        self.win.geometry('760x640')
        self.win.minsize(640, 520)
        self.win.transient(app.root)
        theme.dark_titlebar(self.win)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.win.bind('<Escape>', lambda e: self.close())
        f = ttk.Frame(self.win, padding=14)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=t('mpb.head'), style='Brand.TLabel').pack(anchor='w')
        ttk.Label(f, text=t('mpb.intro'), style='Muted.TLabel',
                  wraplength=720, justify='left').pack(anchor='w', pady=(2, 8))
        self.info = ttk.Label(f, text='', wraplength=720, justify='left')
        self.info.pack(anchor='w')
        self.limit_btn = ttk.Button(f, text=t('mpb.limit.btn'),
                                    command=self._limit)
        opts = ttk.Frame(f)
        opts.pack(fill='x', pady=(10, 4))
        ttk.Label(opts, text=t('mpb.tiles')).grid(row=0, column=0, sticky='w')
        self.n_tiles = tk.StringVar(value=str(TILES))
        ttk.Spinbox(opts, from_=1, to=66, width=5, textvariable=self.n_tiles
                    ).grid(row=0, column=1, sticky='w', padx=8)
        ttk.Label(opts, text=t('mpb.tiles.note'), style='Muted.TLabel',
                  wraplength=560, justify='left'
                  ).grid(row=0, column=2, sticky='w')
        ttk.Label(opts, text=t('mpb.dist')).grid(row=1, column=0, sticky='w',
                                                 pady=(4, 0))
        dist = ttk.Frame(opts)
        dist.grid(row=1, column=1, columnspan=2, sticky='w', padx=8,
                  pady=(4, 0))
        self.d_lo = tk.StringVar(value=str(TARGET_M[0]))
        self.d_hi = tk.StringVar(value=str(TARGET_M[1]))
        ttk.Spinbox(dist, from_=0, to=3000, increment=50, width=6,
                    textvariable=self.d_lo).pack(side='left')
        ttk.Label(dist, text=t('mpb.to')).pack(side='left', padx=6)
        ttk.Spinbox(dist, from_=50, to=5000, increment=50, width=6,
                    textvariable=self.d_hi).pack(side='left')
        ttk.Label(dist, text='m').pack(side='left', padx=(6, 0))
        self.active = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text=t('mpb.active'), variable=self.active
                        ).grid(row=2, column=0, columnspan=3, sticky='w',
                               pady=(6, 0))
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
                                  command=self._map)
        ttk.Button(btns, text=t('close'), command=self.close
                   ).pack(side='right')
        self.status = ttk.Label(f, text='', style='Muted.TLabel',
                                wraplength=720, justify='left')
        self.status.pack(side='bottom', anchor='w', pady=(6, 0))
        self.txt = tk.Text(f, wrap='word', font=theme.FONT_MONO, height=12)
        self.txt.pack(fill='both', expand=True, pady=(8, 0))
        self.txt.configure(state='disabled')
        self._info()

    def close(self):
        BatchWindow._open = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _put(self, lines):
        self.txt.configure(state='normal')
        self.txt.delete('1.0', 'end')
        self.txt.insert('end', '\n'.join(lines))
        self.txt.configure(state='disabled')

    def _progress(self, text):
        self.status.configure(text=text)
        try:
            self.win.update()
        except tk.TclError:
            pass

    def _info(self):
        b = self.batch
        n = len(b.open_quests())
        ids = len(b.free_quest_ids())
        npcs = len(b.free_npc_ids(1000))
        lines = [t('mpb.open', n=n), t('mpb.ids', n=ids,
                                       limit=self.app.index.quest_limit),
                 t('mpb.npcs', n=npcs)]
        self.info.configure(text='\n'.join(lines),
                            foreground=theme.WARN if ids < n else theme.INK)
        if ids < n:
            self.limit_btn.pack(anchor='w', pady=(4, 0), after=self.info)
        else:
            self.limit_btn.pack_forget()
        if not n:
            self.roll_btn.state(['disabled'])
            self.status.configure(text=t('mpb.none'))

    def _limit(self):
        self.app.show_quest_limit()

    def _ints(self):
        try:
            n = max(1, int(self.n_tiles.get()))
            lo, hi = int(self.d_lo.get()), int(self.d_hi.get())
        except ValueError:
            return None
        if hi <= lo:
            return None
        return n, (lo, hi)

    def roll(self):
        vals = self._ints()
        if vals is None:
            self.status.configure(text=t('mpb.bad'), foreground=theme.ERR)
            return
        self.status.configure(foreground=theme.MUT)
        self.roll_btn.state(['disabled'])
        self.take_btn.state(['disabled'])
        self.win.configure(cursor='watch')
        try:
            jobs = self.batch.roll(vals[0], vals[1], progress=self._progress)
        except Exception as e:           # shown, nothing was written
            self.status.configure(text=t('mpb.error', e=e),
                                  foreground=theme.ERR)
            return
        finally:
            self.win.configure(cursor='')
            self.roll_btn.state(['!disabled'])
        self.roll_btn.configure(text=t('mpb.reroll'))
        counts = self.batch.tile_counts()
        lines = [t('mpb.result', n=len(jobs), m=sum(counts.values()),
                   tiles=len(counts)), '']
        for tile in self.batch.tiles:
            lines.append(t('mpb.tile.row', tile=tile, n=counts.get(tile, 0)))
        if self.batch.skipped:
            lines += ['', t('mpb.skipped', n=len(self.batch.skipped))]
            for qid, key in self.batch.skipped:
                lines.append(f'  Q_{qid}: ' + t(key))
        lines += ['', t('mpb.examples')]
        for job in jobs[:8]:
            g = job['targets'][0]['placed']
            lines.append(t('mpb.example', old=job['qid'], new=job['new_id'],
                           title=job['src'].title, name=job['name'],
                           tile=g['tile']))
        self._put(lines)
        self.status.configure(text=t('mpb.rolled', seed=self.batch.seed))
        if jobs:
            self.take_btn.state(['!disabled'])

    def ensure_saved(self):
        from . import data, editormaps
        app = self.app
        if editormaps.levels_dir(app.project):
            return True
        path = data.default_project_path(t('mpb.project'))
        if not app._write_project(path):
            return False
        app.set_info(t('mp.saved', path=path), 'StatusOk.TLabel')
        return True

    def take(self):
        if not self.batch.jobs or not self.ensure_saved():
            return
        if not messagebox.askyesno(t('mpb.title'), t(
                'mpb.take.q', n=len(self.batch.jobs),
                tiles=len(self.batch.tile_counts())), parent=self.win):
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
        if clash:
            lines.append(t('mpb.clash', n=len(clash)))
        lines.append(t('mpb.next'))
        self._put(lines)
        self.status.configure(text='', foreground=theme.MUT)
        self.batch.jobs = []
        self.map_btn.pack(side='left', padx=8)
        self._info()

    def _map(self):
        self.app.show_map()
