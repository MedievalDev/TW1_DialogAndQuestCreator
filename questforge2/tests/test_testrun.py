"""Test run in the game (4.5.0): starter quest in and out, where to."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import export, model, placed, testrun  # noqa: E402

QTX = """NPC NPC_3 3 3 E1 0 123 25 (null) SMALL True CHAR_05(15) 0
  OBJECTS True
END
QUEST Q_3 0 1 (null) 0 True
  GIVER NPC_3 ACTIVE BACK_TO_GIVER_MAP_SIGN NONE
  FC TALK NPC_3
END
QUEST Q_385 1 1 (null) 0 True
  GIVER NPC_508 ACTIVE BACK_TO_GIVER_MAP_SIGN NONE
  FC TALK NPC_508
END
"""


class Index:
    def __init__(self, ids=(3, 4, 385), npcs=None):
        self.quests = {str(i): {} for i in ids}
        self._npcs = npcs or {}

    def npc(self, nid):
        return self._npcs.get(str(nid))


def project(enable=2):
    p = model.Project('T')
    q = model.Quest(385, 'Hunger')
    q.enable_level = enable
    q.giver = 508
    q.add_speaker({'id': 508, 'name': 'Kunibert', 'lector': None,
                   'tile': 'E1', 'marker': 508, 'new': True})
    p.quests.append(q)
    return p, q


class Starter(unittest.TestCase):
    def spec(self, **kw):
        s = {'starter': 599, 'quest': 385, 'marker': 7, 'tile': 'E1',
             'promote': 2, 'group': 1}
        s.update(kw)
        return s

    def test_block(self):
        block = testrun.starter_block(self.spec())
        lines = block.strip().split('\n')
        # enable level 2: StartQuests must not enable it, only Q_3
        self.assertEqual(lines[0], 'QUEST Q_599 2 1 (null) 0 False')
        # the delay counts game ticks, 30 a second
        self.assertIn('  ACTION HERO_TELEPORT_DELAYED ENABLE 450 7 E1 0', lines)
        # again after the goblins, if the first jump got lost
        self.assertIn('  ACTION HERO_TELEPORT_DELAYED SOLVE 30 7 E1 0', lines)
        # the quest creates its giver itself once it is enabled
        self.assertFalse([ln for ln in lines if 'NPC_CREATE' in ln])
        self.assertEqual(lines.count('  AOQ PROMOTE TAKE Q_385'), 2)
        self.assertEqual(lines[-1], 'END')

    def test_in_and_out_again(self):
        text = testrun.add_starter(QTX, self.spec())
        self.assertIn('QUEST Q_599 ', text)
        q3 = export._find_block(text, 3).group(0)
        self.assertIn('AOQ SOLVE SOLVE Q_599', q3)
        self.assertIn('  AOQ TAKE ENABLE Q_599\n', q3)
        # a second test build replaces the first, no second block
        again = testrun.add_starter(text, self.spec(marker=8))
        self.assertEqual(again.count('QUEST Q_599 '), 1)
        self.assertEqual(again.count('AOQ TAKE ENABLE Q_599'), 1)
        self.assertIn('ENABLE 450 8 E1 0', again)
        self.assertEqual(again.count('AOQ SOLVE SOLVE Q_599'), 1)
        # the normal export: exactly the game's file again
        self.assertEqual(export.strip_quests(again, {599}), QTX)
        # the engine's loader still reads every block, the starter included
        npcs, quests = export.engine_parse(text, 600)
        self.assertEqual(quests, {3, 385, 599})
        self.assertEqual(npcs, {'NPC_3'})

    def test_without_teleport(self):
        block = testrun.starter_block(self.spec(marker=None))
        self.assertNotIn('HERO_TELEPORT', block)

    def test_starter_id(self):
        p, _q = project()
        self.assertEqual(testrun.starter_id(Index(), p, 400), 399)
        self.assertEqual(testrun.starter_id(Index(ids=(3, 399)), p, 400), 398)
        self.assertEqual(testrun.starter_id(Index(), p, 600), 599)
        # our own starter of the last test build is in the index (read from
        # the mod in the game) but free for the next one
        testrun.remember(p, {'starter': 399, 'quest': 385}, 'T.wd')
        self.assertEqual(testrun.starter_id(Index(ids=(3, 399)), p, 400), 399)

    def test_remember_forget(self):
        p, _q = project()
        self.assertFalse(testrun.active(p))
        testrun.remember(p, self.spec(), 'T.wd')
        testrun.remember(p, self.spec(starter=598), 'T.wd')
        self.assertEqual(testrun.starters(p), {598, 599})
        self.assertTrue(testrun.active(p))
        testrun.forget(p)
        self.assertEqual(testrun.starters(p), set())


class Plan(unittest.TestCase):
    """Where the hero lands; the maps are stand-ins."""

    def setUp(self):
        self.markers = {}
        self._tm, self._fs = testrun.tile_markers, testrun.free_spot
        self._fn = placed.free_number
        testrun.tile_markers = lambda p, m, g, tile: (self.markers,
                                                       b'body')
        testrun.free_spot = lambda p, m, g, tile, spot: (
            spot[0] + 180, spot[1], spot[2])
        placed.free_number = lambda name, tile, body, taken: 12

    def tearDown(self):
        testrun.tile_markers, testrun.free_spot = self._tm, self._fs
        placed.free_number = self._fn

    def test_new_marker_next_to_the_giver(self):
        p, q = project()
        self.markers = {'MARKER_QUEST_START': [(508, 17920, 14387, 22473, 0)],
                        'MARKER_QUEST_TELEPORT': [(3, 30000, 30000, 0, 0)]}
        spec = testrun.plan(p, Index(), None, 'game', q, 400)
        self.assertIsNone(spec['problem'])
        self.assertEqual((spec['tile'], spec['marker'], spec['dist']),
                         ('E1', 12, 180))
        self.assertEqual(spec['new']['quest'], testrun.TEST_TAG)
        self.assertEqual((spec['new']['x'], spec['new']['z']),
                         (18100, 22473))
        self.assertEqual(spec['promote'], 2)
        self.assertEqual(spec['starter'], 399)

    def test_existing_marker_close_by(self):
        p, q = project(enable=0)
        self.markers = {'MARKER_QUEST_START': [(508, 17920, 14387, 22473, 0)],
                        'MARKER_QUEST_TELEPORT': [(3, 18920, 14387, 0, 0)]}
        spec = testrun.plan(p, Index(), None, 'game', q, 400)
        self.assertEqual((spec['marker'], spec['dist'], spec['new']),
                         (3, 1000, None))
        self.assertEqual(spec['promote'], 0)

    def test_problems(self):
        p, q = project()
        self.markers = {}
        self.assertEqual(testrun.plan(p, Index(), None, 'g', q, 400)
                         ['problem'], 'testrun.nomarker')
        q.giver = None
        self.assertEqual(testrun.plan(p, Index(), None, 'g', q, 400)
                         ['problem'], 'testrun.nogiver')


class Marker(unittest.TestCase):
    def test_set_and_clear(self):
        p, _q = project()
        own = {'name': 'MARKER_QUEST_START', 'num': 508, 'tile': 'E1',
               'x': 1, 'y': 2, 'z': 3, 'angle': 0, 'quest': 385}
        placed.placements(p).append(own)
        new = {'name': 'MARKER_QUEST_TELEPORT', 'num': 12, 'tile': 'E1',
               'x': 5, 'y': 6, 'z': 7, 'angle': 0, 'quest': testrun.TEST_TAG}
        self.assertTrue(testrun.set_marker(p, {'new': new}))
        self.assertFalse(testrun.set_marker(p, {'new': dict(new)}))
        self.assertEqual(len(placed.placements(p)), 2)
        self.assertTrue(testrun.clear_marker(p))
        self.assertFalse(testrun.clear_marker(p))
        self.assertEqual(placed.placements(p), [own])


if __name__ == '__main__':
    unittest.main()
