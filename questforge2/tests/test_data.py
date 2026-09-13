import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tw1_lan  # noqa: E402
from questforge2 import data  # noqa: E402

QTX = """NPC NPC_3 3 3 F5 0 4 25 (null) SMALL True NPC_Q_003(100) 0
NPC NPC_5 5 5 D8 0 (null) 23 (null) SMALL True NPC_Q_005(55) 0
LOCATION LOC_F05_0_01 70 40 F5 50 19
QUEST Q_4 1 3 (null) 0 True
  GIVER ACTIVE NPC_3 AUTO_CLOSE_ON_SOLVE NONE
  FC TALK NPC_5
  AOQ PROMOTE TAKE Q_385
  REWARD GLD TAKE SMALL
END
QUEST Q_385 1 105 (null) 0 True
  GIVER ACTIVE NPC_3 BACK_TO_GIVER_MAP_SIGN NONE
  FC CLEAR_AREA 385 E1 50 20
  ACTION ENEMY_CREATE ENABLE ENEMY_GOBLIN2 3 1 385 E1 20
  ACTION OBJECT_CREATE ENABLE QITEM_040 7 F2
  ACTION NPC_TELEPORT SOLVE NPC_5 7 F2 192
  REWARD GLD CLOSE 500
  REWARD ITM CLOSE 1 QITEM_040
END
"""


def _lan():
    tr = {'translateQ_4': 'Erste Quest', 'translateQ_385': 'Erpresser',
          'translateNPC_3': 'Tago', 'translateGROUP_3': 'Kapitel 1',
          'translateGROUP_105': 'Nebenquests',
          'translateLOC_F05_0_01': 'Komorin',
          'translateDQ_385_0': 'Hallo Held.', 'translateDQ_385_1': 'Hallo.',
          'translateDQ_385_2': 'Bis dann.'}
    e = tw1_lan.DialogEntry
    trees = [tw1_lan.DialogTree('translateDQ_385', [
        e(4, 'translateDQ_385_0', 'CUE_0004_0001', [1], 0x20001, [2]),
        e(1, 'translateDQ_385_1', 'CUE_0001_0099', [], 0x20001, [7]),
        e(4, 'translateDQ_385_2', '', [], 0x8, [2])])]
    return tw1_lan.build(tr, [], tw1_lan.build_trees(trees))


class IndexBuild(unittest.TestCase):
    def setUp(self):
        self.idx = data.Index(data.index_from_parts(QTX, _lan()))

    def test_quests(self):
        q = self.idx.quest(385)
        self.assertEqual(q['title'], 'Erpresser')
        self.assertEqual(q['group'], 105)
        self.assertEqual(q['giver'], 3)
        self.assertEqual(q['fc'][0], 'CLEAR_AREA')
        self.assertEqual(q['lines'], 3)
        self.assertEqual(q['flags'], [0x8, 0x20001])
        self.assertEqual(q['source'], 'retail')
        self.assertEqual(self.idx.quest(4)['aoq'], [['PROMOTE', 'TAKE', 385]])

    def test_npcs_groups_locations(self):
        self.assertEqual(self.idx.npc(3)['name'], 'Tago')
        self.assertEqual(self.idx.npc(3)['lector'], 4)
        self.assertIsNone(self.idx.npc(5)['lector'])
        self.assertEqual(self.idx.npc(5)['name'], 'NPC_5')
        self.assertEqual(self.idx.groups['105'], 'Nebenquests')
        loc = self.idx.locations['LOC_F05_0_01']
        self.assertEqual((loc['name'], loc['tile'], loc['radius'],
                          loc['type']), ('Komorin', 'F5', 50, 19))
        self.assertEqual(self.idx.lectors['4'], [3])

    def test_objects_tiles_markers(self):
        self.assertEqual(self.idx.objects, ['QITEM_040'])
        self.assertEqual(self.idx.tiles, ['D8', 'E1', 'F2', 'F5'])
        self.assertEqual(self.idx.markers['Q_Solve|E1'], [385])
        self.assertEqual(self.idx.markers['Q_Action_Teleport|F2'], [7])
        self.assertEqual(self.idx.markers['Q_Action_Create_Enemy|E1'], [385])
        self.assertEqual(self.idx.markers['Q_Action_Create_Object|F2'], [7])
        self.assertEqual(self.idx.npc(3)['marker'], 3)
        self.assertTrue(self.idx.npc(3)['record'].startswith('NPC NPC_3 3 3 F5'))

    def test_cues(self):
        self.assertEqual(self.idx.cues['CUE_0004_0001'],
                         [4, 'Hallo Held.', 'translateDQ_385'])
        self.assertEqual(len(self.idx.cues), 2)

    def test_free_ids_and_labels(self):
        free = self.idx.free_ids()
        self.assertNotIn(385, free)
        self.assertIn(381, free)
        self.assertEqual(len(free), 18)
        self.assertEqual(self.idx.npc_label(3), 'Tago  (NPC_3)')
        self.assertEqual(self.idx.quest_label(4), 'Q_4  Erste Quest')

    def test_mod_adds_own_quests_only(self):
        mod_qtx = QTX + ("QUEST Q_390 1 105 (null) 0 True\n"
                         "  GIVER PASSIVE NPC_3 NONE NONE\n"
                         "  FC BRING_GOLD 100\nEND\n")
        mod_lan = tw1_lan.build({'translateQ_390': 'Modquest',
                                 'translateQ_385': 'UMBENANNT'})
        idx = data.Index(data.index_from_parts(
            QTX, _lan(), mods=[('Test.wd', mod_qtx, [mod_lan])]))
        self.assertEqual(idx.quest(390)['source'], 'Test.wd')
        self.assertEqual(idx.quest(390)['title'], 'Modquest')
        self.assertIsNone(idx.quest(390)['modified_by'])
        # unchanged retail block: stays retail, mod .lan renames it (key merge)
        self.assertEqual(idx.quest(385)['title'], 'UMBENANNT')
        self.assertEqual(idx.quest(385)['source'], 'retail')
        self.assertIsNone(idx.quest(385)['modified_by'])
        self.assertEqual(idx.quest(385)['lines'], 3)

    def test_mod_changes_retail_block(self):
        mod_qtx = QTX.replace('  AOQ PROMOTE TAKE Q_385\n',
                              '  AOQ PROMOTE TAKE Q_385\n'
                              '  AOQ PROMOTE TAKE Q_390\n')
        idx = data.Index(data.index_from_parts(
            QTX, _lan(), mods=[('Test.wd', mod_qtx, [])]))
        q4 = idx.quest(4)
        self.assertEqual(q4['source'], 'retail')
        self.assertEqual(q4['modified_by'], 'Test.wd')
        self.assertEqual(q4['aoq'], [['PROMOTE', 'TAKE', 385],
                                     ['PROMOTE', 'TAKE', 390]])
        self.assertEqual(q4['lines'], 0)
        self.assertIsNone(idx.quest(385)['modified_by'])


def _w(path, blob):
    with open(path, 'wb') as f:
        f.write(blob)


class CacheStamps(unittest.TestCase):
    def test_stamps_detect_change(self):
        with tempfile.TemporaryDirectory() as d:
            game = os.path.join(d, 'game')
            os.makedirs(os.path.join(game, 'WDFiles'))
            os.makedirs(os.path.join(game, 'Mods'))
            wd = os.path.join(game, 'WDFiles', 'Update16.wd')
            _w(wd, b'x' * 10)
            files = data.source_files(game)
            self.assertEqual([os.path.basename(f) for f in files],
                             ['Update16.wd'])
            idx = {'format': data.INDEX_FORMAT, 'game_dir': game,
                   'sources': data.source_stamps(files)}
            self.assertTrue(data.cache_valid(idx, game))
            _w(os.path.join(game, 'Mods', 'A.wd'), b'y')
            self.assertFalse(data.cache_valid(idx, game))
            idx['sources'] = data.source_stamps(data.source_files(game))
            self.assertTrue(data.cache_valid(idx, game))
            _w(wd, b'x' * 11)
            self.assertFalse(data.cache_valid(idx, game))
            self.assertFalse(data.cache_valid({'format': 0}, game))


class ConfigTest(unittest.TestCase):
    def test_recent_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'cfg.json')
            cfg = data.Config(path)
            self.assertIsNone(cfg.get('game_dir'))
            cfg.set('game_dir', 'X:\\Game')
            for i in range(10):
                cfg.add_recent(f'C:\\p\\{i}.tw1proj')
            cfg.add_recent('c:\\P\\9.tw1proj')
            cfg.save()
            cfg2 = data.Config(path)
            self.assertEqual(cfg2.get('game_dir'), 'X:\\Game')
            recent = cfg2.get('recent_projects')
            self.assertEqual(len(recent), 8)
            self.assertEqual(recent[0], 'c:\\P\\9.tw1proj')
            self.assertEqual(recent[1], 'C:\\p\\8.tw1proj')
            cfg2.remove_recent('C:\\P\\9.tw1proj')
            self.assertEqual(len(cfg2.get('recent_projects')), 7)
            self.assertEqual(cfg2.get('panels')['timeline'], True)


if __name__ == '__main__':
    unittest.main()
