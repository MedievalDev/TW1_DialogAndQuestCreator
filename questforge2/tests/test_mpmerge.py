"""Multiplayer quest into single player (mpmerge.py)."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import export, mods, model, mpmerge, retail, validate  # noqa: E402
from questforge2.model import Project, Quest  # noqa: E402
from questforge2.tests.test_quest_export import _Index  # noqa: E402

MP_BLOCK = """QUEST Q_700 0 (null) (null) 0 True
  GIVER PASSIVE NPC_700 BACK_TO_GIVER_MAP_SIGN NONE
  FC BRING_OBJECT QITEM_040 2
  ACTION OBJECT_CREATE ENABLE QITEM_040 1 (null)
  ACTION OBJECT_CREATE ENABLE QITEM_040 1 (null)
  ACTION ENEMY_CREATE TAKE ENEMY_ANIMAL 2 5 3 (null) 20
  REWARD GLD CLOSE SMALL
END
"""


def mp_quest():
    q = Quest(700, 'Grosser Hunger')
    q.journal = {'take': 'a', 'solve': 'b', 'close': 'c'}
    retail.import_block(q, MP_BLOCK)
    q.add_speaker({'id': 700, 'name': 'NPC_700', 'lector': None,
                   'tile': '(null)', 'new': False})
    # MP dialog lines have no lector: the import makes "Lector -1"
    q.add_speaker({'id': 'L-1', 'name': 'Lector -1', 'lector': -1,
                   'tile': '', 'new': False})
    n = model.add_node(q.graph, model.make_node('npc', 0, 0, 'first', 'L-1'))
    q.graph['nodes'][n]['lines'][0]['text'] = 'Hallo'
    return q


class _Idx(_Index):
    def __init__(self):
        super().__init__()
        self.npcs['506'] = {'name': 'Last', 'tile': 'H6', 'lector': 5,
                            'record': 'NPC NPC_506 506 506 H6 0 5 26 (null) '
                                      'SMALL True CHAR_01(15) 0',
                            'source': 'retail'}
        self.npcs['700'] = {'name': 'NPC_700', 'tile': '(null)',
                            'lector': None,
                            'record': 'NPC NPC_700 700 (null) (null) 0 '
                                      '(null) (null) (null) SMALL True '
                                      'CITIZEN_01_01(20)#WP_MACE_0(5,0) 0',
                            'source': 'retail'}
        self.groups = {'3': 'Kapitel'}


RETAIL_TILES = {'E1': {'markers': mods._plain_markers({
    'MARKER_QUEST_CREATE_OBJECT': [(1, (0, 0, 0, 0)), (3, (0, 0, 0, 0))],
    'MARKER_QUEST_START': [(3, (0, 0, 0, 0))]})}}


class Merge(unittest.TestCase):
    def test_limits(self):
        self.assertTrue(mpmerge.is_mp_quest(700))
        self.assertFalse(mpmerge.is_mp_quest(399))
        self.assertEqual(mpmerge.free_npc_id(_Idx()), 507)
        p = Project('P')
        q = Quest(390, 'x')
        q.add_speaker({'id': 507, 'name': 'n', 'lector': None, 'tile': 'E1',
                       'new': True})
        p.quests.append(q)
        self.assertEqual(mpmerge.free_npc_id(_Idx(), p), 508)

    def test_refs_and_plan(self):
        q = mp_quest()
        refs = mpmerge.marker_refs(q)
        self.assertEqual([r['name'] for r in refs],
                         ['MARKER_QUEST_CREATE_OBJECT'] * 2
                         + ['MARKER_QUEST_CREATE_ENEMY'])
        self.assertEqual([r['tile'] for r in refs], ['', '', ''])
        items, mapping = mpmerge.plan(q, 507, 'E1', RETAIL_TILES)
        # the giver first; object marker 1 exists on E1 -> next free is 4,
        # both OBJECT_CREATE lines share it; enemy marker 3 is free -> kept
        self.assertEqual(items[0]['name'], 'MARKER_QUEST_START')
        self.assertEqual((items[0]['num'], items[0]['tile'],
                          items[0]['exists']), (507, 'E1', False))
        self.assertEqual(mapping[('MARKER_QUEST_CREATE_OBJECT', 'E1', 1)], 4)
        self.assertEqual(mapping[('MARKER_QUEST_CREATE_ENEMY', 'E1', 3)], 3)
        self.assertEqual(len(items), 3)

    def test_apply_and_export(self):
        q = mp_quest()
        new = mpmerge.apply(q, 390, 507, 'Hungriger', 'E1', RETAIL_TILES,
                            group=3)
        self.assertEqual((new.id, new.giver, new.group), (390, 507, 3))
        self.assertFalse(new.retail)
        spk = new.speakers[0]
        self.assertEqual((spk['id'], spk['tile'], spk['marker'], spk['new'],
                          spk['party']), (507, 'E1', 507, True, 25))
        acts = [a for a in new.actions if a['kind'] == 'ACTION']
        self.assertEqual([a['args']['tile'] for a in acts], ['E1', 'E1', 'E1'])
        self.assertEqual([a['args']['marker'] for a in acts], [4, 4, 3])
        self.assertEqual([s['id'] for s in new.speakers], [507])
        self.assertEqual({n.get('speaker') for n in new.graph['nodes'].values()
                          if n.get('type') == 'npc'}, {507})
        todo = new.extra['markers_todo']
        self.assertEqual([(x['name'], x['num'], x['done']) for x in todo],
                         [('MARKER_QUEST_START', 507, False),
                          ('MARKER_QUEST_CREATE_OBJECT', 4, False),
                          ('MARKER_QUEST_CREATE_ENEMY', 3, False)])
        self.assertTrue(any(c.get('cond') == 'after'
                            for c in new.conditions_list()))
        # validation: open markers warn; giver id ok
        E, W = validate.validate_quest(new, _Idx(), Project('P'), None)
        self.assertFalse([m for m, _ in E if 'NPC_' in m])
        # checklist warnings name the markers as the editor does (Q_...)
        todo_w = [m for m, _ in W if m.startswith('warn.marker.todo')]
        self.assertEqual(len(todo_w), 3)
        self.assertTrue(any("'Q_Giver'" in m for m in todo_w))
        todo[0]['done'] = True
        _E, W = validate.validate_quest(new, _Idx(), Project('P'), None)
        self.assertEqual(sum(1 for m, _ in W
                             if m.startswith('warn.marker.todo')), 2)
        # export: NPC block with tile, marker and party, lines with tiles
        block = export.build_quest_block(new).emit()
        self.assertIn('ACTION OBJECT_CREATE ENABLE QITEM_040 4 E1', block)
        self.assertIn('ACTION ENEMY_CREATE TAKE ENEMY_ANIMAL 2 5 3 E1 20',
                      block)
        npc = export.npc_block(spk, _Idx())
        self.assertTrue(npc.startswith('NPC NPC_507 507 507 E1 0 (null) 25 '
                                       '(null) SMALL True CITIZEN_01_01'))
        # round trip through the project file keeps the checklist
        p = Project('P')
        p.quests.append(new)
        again = Project.from_json(p.to_json())
        self.assertEqual(again.quests[0].extra['markers_todo'][0]['done'],
                         True)

    def test_giver_limit_error(self):
        q = Quest(390, 'x')
        q.giver = 700
        q.add_speaker({'id': 700, 'name': 'n', 'lector': None, 'tile': 'E1',
                       'new': True})
        E, _W = validate.validate_quest(q, _Idx(), Project('P'), None)
        self.assertTrue(any('NPC_700' in m for m, _ in E))


if __name__ == '__main__':
    unittest.main()
