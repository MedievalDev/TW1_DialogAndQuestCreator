"""All multiplayer quests at once with random markers (mpbatch.py, 4.6.0)."""

import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import data, mapdata, mods, mpbatch, mpmerge, placed  # noqa: E402
from questforge2.tests.test_mpmerge import mp_quest  # noqa: E402

U = mpbatch.UNITS


class FakeTerrain:
    """A tile: the western quarter is sea, a wall of rocks at x = 0.6
    splits the land into a big and a small part."""

    pools = [(870, 0, 0, 0, 127, 127)]

    def wet(self, x, y):
        return x < U // 4

    def passable(self, x, y):
        return not (0.6 * U <= x < 0.62 * U) and not self.wet(x, y)

    def height(self, x, y):
        return 1000


class Tiles(unittest.TestCase):
    def test_edge(self):
        for tile in ('A5', 'I3', 'E1', 'E12', 'A1', 'I12'):
            self.assertTrue(mpbatch.is_edge(tile), tile)
        for tile in ('B2', 'E5', 'H11'):
            self.assertFalse(mpbatch.is_edge(tile), tile)

    def test_water_share(self):
        self.assertAlmostEqual(mpbatch.water_share(FakeTerrain()), 0.25)

    def test_usable(self):
        tiles = [f'{c}{r}' for c in mapdata.COLS
                 for r in range(1, mapdata.ROWS + 1)] + ['E1_1']
        wet = {'B3'}

        class Dry(FakeTerrain):
            def wet(self, x, y):
                return False

        class Sea(FakeTerrain):
            def wet(self, x, y):
                return x < U * 0.6        # 60 % water: out

        got = mpbatch.usable_tiles(
            tiles, lambda k: Sea() if k in wet else Dry())
        self.assertEqual(len(got), 7 * 10 - 1)
        self.assertNotIn('B3', got)
        self.assertNotIn('E1_1', got)
        self.assertFalse(any(mpbatch.is_edge(k) for k in got))

    def test_groups_of_neighbours(self):
        usable = {f'{c}{r}' for c in mapdata.COLS[1:-1]
                  for r in range(2, mapdata.ROWS)}
        for seed in range(20):
            got = mpbatch.pick_tiles(usable, 12, random.Random(seed))
            self.assertEqual(len(got), 12)
            self.assertEqual(len(set(got)), 12)
            for k in got:
                self.assertTrue(any(nb in got
                                    for nb in mpbatch.neighbours(k)), k)


class Grid(unittest.TestCase):
    def setUp(self):
        self.grid = mpbatch.TileGrid('E5', FakeTerrain())

    def test_cells(self):
        g, n, c = self.grid, mpbatch.GRID, mpbatch.CELL
        self.assertTrue(g.cells)
        ter = FakeTerrain()
        margin = mpbatch.EDGE_M * 64
        for j in g.cells[::97]:
            x, y = j % n * c + c // 2, j // n * c + c // 2
            self.assertTrue(ter.passable(x, y))
            self.assertFalse(ter.wet(x, y))
            self.assertTrue(margin <= x <= U - margin, x)
            self.assertTrue(margin <= y <= U - margin, y)
        # the bigger part (0.25 to 0.6) wins, the strip behind the rocks
        # is a separate area
        self.assertFalse(g.fits(int(0.8 * U), U // 2))
        self.assertTrue(g.fits(int(0.4 * U), U // 2))

    def test_around(self):
        grids = {'E5': self.grid, 'F5': mpbatch.TileGrid('F5', FakeTerrain())}
        p = mpbatch.Placer(grids, random.Random(3))
        g = p.giver()
        centre = mpbatch.to_map(g['tile'], g['x'], g['y'])
        for _ in range(30):
            s = p.around(g, 50, 200)
            if s is None:
                continue
            d = mpbatch.distance(centre, mpbatch.to_map(s['tile'], s['x'],
                                                        s['y']))
            self.assertTrue(49 <= d <= 201, d)
            self.assertTrue(grids[s['tile']].fits(s['x'], s['y']))


class OneQuest(unittest.TestCase):
    def test_giver_target_and_lines(self):
        src = mp_quest()
        targets = mpmerge.marker_targets(src, 509, {})
        grids = {k: mpbatch.TileGrid(k, FakeTerrain())
                 for k in ('D4', 'E4', 'D5', 'E5')}
        placer = mpbatch.Placer(grids, random.Random(7))
        taken = []

        def number_of(tg):
            p = tg['placed']
            if p.get('num') is None:
                p['num'] = placed.free_number(tg['name'], p['tile'], None,
                                              taken)
            taken.append({'name': tg['name'], 'tile': p['tile'],
                          'num': p['num']})
        ok = mpbatch.place_quest(src, targets, placer, number_of,
                                 lambda tile: False, band=(200, 500))
        self.assertTrue(ok)
        giver = targets[0]
        self.assertEqual(giver['placed']['num'], 509)
        g = mpbatch.to_map(giver['placed']['tile'], giver['placed']['x'],
                           giver['placed']['y'])
        refs = mpmerge.marker_refs(src)
        k = mpbatch.anchor_index(targets, refs)
        a = targets[k]['placed']
        d = mpbatch.distance(g, mpbatch.to_map(a['tile'], a['x'], a['y']))
        self.assertTrue(200 <= d <= 500, d)
        for tg in targets[1:]:
            p = tg['placed']
            self.assertIsNotNone(p)
            self.assertLessEqual(mpbatch.distance(
                mpbatch.to_map(a['tile'], a['x'], a['y']),
                mpbatch.to_map(p['tile'], p['x'], p['y'])),
                mpbatch.NEAR_M + 1)
        # the quest built from it points at the placed markers
        new = mpmerge.take_over(src, 386, 509, 'Theobald', targets, {},
                                active=False)
        self.assertEqual(new.giver_type, 'PASSIVE')
        spk = new.speakers[0]
        self.assertEqual((spk['id'], spk['name'], spk['tile'],
                          spk['marker']),
                         (509, 'Theobald', giver['placed']['tile'], 509))
        for ref in mpmerge.marker_refs(new):
            self.assertIn((ref['name'], ref['tile'], ref['num']),
                          {(tg['name'], tg['placed']['tile'],
                            tg['placed']['num']) for tg in targets[1:]})

    def test_names(self):
        self.assertEqual(len(set(mpbatch.NAMES_M)), len(mpbatch.NAMES_M))
        self.assertEqual(len(set(mpbatch.NAMES_F)), len(mpbatch.NAMES_F))
        self.assertFalse(set(mpbatch.NAMES_M) & set(mpbatch.NAMES_F))
        # half the 131 multiplayer givers are women, each needs a name
        self.assertGreaterEqual(min(len(mpbatch.NAMES_M),
                                    len(mpbatch.NAMES_F)), 70)
        for name in mpbatch.NAMES_M + mpbatch.NAMES_F:
            self.assertTrue(name.isascii() and name.isalpha(), name)


def _game():
    g = data.find_game_dir()
    return g if g and os.path.isfile(os.path.join(g, 'WDFiles',
                                                  'Levels.wd')) else None


@unittest.skipIf(_game() is None, 'needs the game')
class Game(unittest.TestCase):
    def test_the_real_tiles(self):
        """Measured 2026-09-25: A1-A6, B1, B2, B5 all sea, B3/B4 85 %; 66
        tiles left."""
        game = _game()
        ms = mods.ModSet([], [], mods.retail_markers(game))
        from questforge2 import lndmap

        def terrain(tile):
            body = placed.retail_body(game, ms, tile)
            return lndmap.Terrain(body) if body else None
        tiles = [k for k in ms.retail_tiles if mapdata.split_tile(k)
                 and not mapdata.split_tile(k)[2]]
        got = mpbatch.usable_tiles(tiles, terrain)
        for k in ('B2', 'B3', 'B4', 'B5'):
            self.assertNotIn(k, got)
        self.assertIn('E5', got)
        self.assertEqual(len(got), 66)


if __name__ == '__main__':
    unittest.main()
