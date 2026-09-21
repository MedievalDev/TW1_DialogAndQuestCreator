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



class OneWindow(unittest.TestCase):
    """4.3.0: everything on one page, the markers from the map, done."""

    def _placed(self, targets):
        spots = {mpmerge.GIVER_KEY: ('E1', 507),
                 ('MARKER_QUEST_CREATE_OBJECT', 1): ('E1', 9),
                 ('MARKER_QUEST_CREATE_ENEMY', 3): ('F1', 3)}
        for tg in targets:
            tile, num = spots[tg['key']]
            tg['placed'] = {'tile': tile, 'x': 100, 'y': 200, 'z': 300,
                            'num': num}

    def test_targets_group_the_lines(self):
        q = mp_quest()
        targets = mpmerge.marker_targets(q, 507, RETAIL_TILES)
        # giver first, both OBJECT_CREATE lines share one marker
        self.assertEqual([tg['key'] for tg in targets],
                         [mpmerge.GIVER_KEY,
                          ('MARKER_QUEST_CREATE_OBJECT', 1),
                          ('MARKER_QUEST_CREATE_ENEMY', 3)])
        self.assertEqual(targets[1]['refs'], [0, 1])
        self.assertEqual(targets[0]['num'], 507)
        self.assertFalse(any(mpmerge.target_ready(tg) for tg in targets))
        self._placed(targets)
        self.assertTrue(all(mpmerge.target_ready(tg) for tg in targets))
        giver, tiles, numbers = mpmerge.placement_settings(targets)
        self.assertEqual(giver, 'E1')
        self.assertEqual(tiles, {0: 'E1', 1: 'E1', 2: 'F1'})
        self.assertEqual(numbers, {0: 9, 1: 9, 2: 3})

    def test_a_line_on_a_game_marker_needs_nothing(self):
        q = mp_quest()
        a = next(a for a in q.actions if a['verb'] == 'OBJECT_CREATE')
        a['args']['tile'] = 'E1'          # E1 has object marker 1
        targets = mpmerge.marker_targets(q, 507, RETAIL_TILES)
        game = [tg for tg in targets if tg['exists']]
        self.assertEqual(len(game), 1)
        self.assertTrue(mpmerge.target_ready(game[0]))
        self.assertEqual((game[0]['tile'], game[0]['game_num']), ('E1', 1))

    def test_take_over_from_the_start(self):
        q = mp_quest()
        targets = mpmerge.marker_targets(q, 507, RETAIL_TILES)
        self._placed(targets)
        journal = {'take': 'a', 'solve': '', 'close': 'c'}
        self.assertEqual(mpmerge.default_journal(journal), ['solve'])
        self.assertTrue(journal['solve'])
        new = mpmerge.take_over(q, 385, 507, 'Kunibert', targets,
                                RETAIL_TILES, group=3, journal=journal,
                                title='Grosser Hunger')
        self.assertEqual((new.id, new.giver, new.giver_type), (385, 507,
                                                               'ACTIVE'))
        self.assertEqual(new.enable_level, 0)
        self.assertFalse([c for c in new.conditions_list()
                          if c.get('cond') == 'after'])
        self.assertEqual([c['level'] for c in new.conditions_list()
                          if c.get('cond') == 'level'], [0])
        self.assertEqual(new.journal['solve'], journal['solve'])
        acts = [a for a in new.actions if a['kind'] == 'ACTION']
        self.assertEqual([(a['args']['tile'], a['args']['marker'])
                          for a in acts], [('E1', 9), ('E1', 9), ('F1', 3)])
        self.assertEqual(new.speakers[0]['tile'], 'E1')
        block = export.build_quest_block(new).emit()
        self.assertIn('QUEST Q_385 0 3 ', block)
        self.assertIn('GIVER ACTIVE NPC_507', block)
        ct = mpmerge.commit_targets(targets)
        self.assertEqual([c['key'] for c in ct],
                         [('MARKER_QUEST_START', 'E1', 507),
                          ('MARKER_QUEST_CREATE_OBJECT', 'E1', 9),
                          ('MARKER_QUEST_CREATE_ENEMY', 'F1', 3)])

    def test_take_over_after_a_quest(self):
        q = mp_quest()
        targets = mpmerge.marker_targets(q, 507, RETAIL_TILES)
        self._placed(targets)
        new = mpmerge.take_over(q, 385, 507, 'K', targets, RETAIL_TILES,
                                active=False, availability=mpmerge.AFTER,
                                pred=12, event='CLOSE')
        self.assertEqual(new.giver_type, 'PASSIVE')
        self.assertEqual(new.enable_level, 1)
        after = [c for c in new.conditions_list() if c.get('cond') == 'after']
        self.assertEqual([(c['quest'], c['event']) for c in after],
                         [(12, 'CLOSE')])

    def test_default_project_path(self):
        import tempfile
        from questforge2 import data
        with tempfile.TemporaryDirectory() as d:
            p1 = data.default_project_path('Grosser: Hunger?', d)
            self.assertEqual(os.path.basename(p1), 'Grosser Hunger.tw1proj')
            open(p1, 'w').close()
            p2 = data.default_project_path('Grosser: Hunger?', d)
            self.assertEqual(os.path.basename(p2), 'Grosser Hunger 2.tw1proj')


if __name__ == '__main__':
    unittest.main()
