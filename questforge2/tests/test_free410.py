"""4.1.0: markers placed freely (Quest > Place markers on the map), without
the window: the kinds on offer, the IDs given out and refused, and writing
them into the levels folder next to the markers of a quest."""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import tw1_lnd  # noqa: E402
from questforge2 import i18n, mapdata, placed, placewin  # noqa: E402
from questforge2.tests.test_debug401 import _Levels  # noqa: E402
from questforge2.tests.test_placed import OBJ, START, body  # noqa: E402

ENEMY = 'MARKER_QUEST_CREATE_ENEMY'


class Kinds(unittest.TestCase):
    def test_every_marker_a_quest_line_reads(self):
        names = [n for n, _u in placewin.FREE_KINDS]
        self.assertEqual(len(names), len(set(names)))
        wanted = set(tw1_lnd.ACTION_MARKER.values()) | set(
            tw1_lnd.FC_MARKER.values()) | {START, 'MARKER_CHEST'}
        self.assertEqual(set(names), wanted)
        for name, use in placewin.FREE_KINDS:
            self.assertNotEqual(mapdata.group_of(name), 'unknown', name)
            for d in (i18n._DE, i18n._EN):
                self.assertIn('free.use.' + use, d)


class Ids(unittest.TestCase):
    def setUp(self):
        i18n.set_lang('en')

    def test_ranges(self):
        self.assertEqual(placewin.ranges([501, 1, 2, 3, 4, 500, 7, 3]),
                         '1-4, 7, 500, 501')
        self.assertEqual(placewin.ranges([]), '')
        self.assertEqual(placewin.ranges([5, 6]), '5, 6')
        many = placewin.ranges(range(0, 200, 2), limit=3)
        self.assertEqual(many, '0, 2, 4, ...')

    def test_check_id(self):
        taken = {1, 2, 3, 12}
        self.assertEqual(placewin.check_id(' 13 ', taken, 'E1', 13),
                         (13, None))
        self.assertEqual(placewin.check_id('4', taken, 'E1', 13), (4, None))
        n, err = placewin.check_id('3', taken, 'E1', 13)
        self.assertIsNone(n)
        self.assertEqual(err, 'ID 3 is already taken on E1 '
                              '(taken: 1-3, 12). Next free: 13.')
        for bad in ('', 'abc', '0', '-2', '2.5', '65536', '²', '1e3'):
            n, err = placewin.check_id(bad, taken, 'E1', 13)
            self.assertIsNone(n, bad)
            self.assertIn('65535', err)
        self.assertEqual(placewin.check_id('65535', set(), 'E1', 1),
                         (65535, None))

    def test_taken_per_tile_and_kind(self):
        d = body([(OBJ, 3, 0, 0, 0, 0), (OBJ, 7, 0, 0, 0, 0),
                  (ENEMY, 9, 0, 0, 0, 0)])
        pl = [{'name': OBJ, 'tile': 'E1', 'num': 20},
              {'name': OBJ, 'tile': 'F1', 'num': 30},
              {'name': ENEMY, 'tile': 'E1', 'num': 40}]
        self.assertEqual(placed.taken_numbers(OBJ, 'E1', d, pl), {3, 7, 20})
        self.assertEqual(placed.taken_numbers(OBJ, 'E1', d, pl, skip=pl[0]),
                         {3, 7})
        self.assertEqual(placed.taken_numbers(ENEMY, 'E1', d, pl), {9, 40})
        self.assertEqual(placed.taken_numbers(OBJ, 'F1', None, pl), {30})
        self.assertEqual(placed.free_number(OBJ, 'E1', d, pl), 21)


class Commit(_Levels):
    def app(self):
        return types.SimpleNamespace(
            project=self.p, modset=self.ms, cfg={'game_dir': None},
            mark_dirty=lambda: None, load_modset=lambda force=False: None)

    @staticmethod
    def tg(name, num, tile='E1', x=5):
        return {'key': None, 'name': name, 'orig': None,
                'placed': {'tile': tile, 'x': x, 'y': 5, 'z': 5, 'num': num}}

    def test_free_markers_next_to_a_quest(self):
        self.place(self.p, 508)                  # a quest's giver on E1
        app = self.app()
        placewin.commit_free(app, [self.tg(OBJ, 502),
                                   self.tg(ENEMY, 502)])
        self.assertEqual(self.markers(), {OBJ: {1, 502}, ENEMY: {502},
                                          START: {508}})
        lst = placed.placements(self.p)
        self.assertEqual(sorted((p['name'], p['num'], p['quest'])
                                for p in lst),
                         sorted([(START, 508, 385), (OBJ, 502, None),
                                 (ENEMY, 502, None)]))
        # reopened: the window gets the free ones, never the quest's
        tg = placewin.free_targets(self.p)
        self.assertEqual(sorted((x['name'], x['placed']['num']) for x in tg),
                         [(ENEMY, 502), (OBJ, 502)])
        # one removed, one moved to another ID: the quest's giver stays
        moved = next(x for x in tg if x['name'] == OBJ)
        moved['placed'] = dict(moved['placed'], num=503)
        placewin.commit_free(app, [moved])
        self.assertEqual(self.markers(), {OBJ: {1, 503}, START: {508}})
        self.assertEqual(len(placed.placements(self.p)), 2)
        # deleting the quest does not take the free marker along
        placed.forget_quest(self.p, 385)
        self.assertEqual([(p['name'], p['num'])
                          for p in placed.placements(self.p)], [(OBJ, 503)])

    def test_number_the_map_has_meanwhile(self):
        # marker 1 is in the base map of E1: that free marker is not
        # written and leaves the list, the other one is written
        app = self.app()
        rep = placewin.commit_free(app, [self.tg(OBJ, 1),
                                         self.tg(OBJ, 2)])
        self.assertEqual([c['num'] for c in rep['E1']['clash']], [1])
        self.assertEqual([p['num'] for p in placed.placements(self.p)], [2])
        self.assertEqual(self.markers(), {OBJ: {1, 2}})

    def test_nothing_left(self):
        app = self.app()
        placewin.commit_free(app, [self.tg(OBJ, 4)])
        self.assertTrue(os.path.isfile(self.target()))
        placewin.commit_free(app, [])
        self.assertEqual(placed.placements(self.p), [])
        self.assertFalse(os.path.isfile(self.target()))


if __name__ == '__main__':
    unittest.main()
