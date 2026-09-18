"""3.8.0 bugfix round: engine rules the game fails on silently."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tw1_lan  # noqa: E402
from questforge2 import export, model, mods, mpmerge, retail  # noqa: E402
from questforge2.model import Project, Quest  # noqa: E402


class Ghosts(unittest.TestCase):
    def test_strip_quest_blocks_and_links(self):
        text = ('QUEST Q_4 1 3 (null) 0 True\n  AOQ PROMOTE TAKE Q_390\n'
                '  AOQ PROMOTE TAKE Q_5\nEND\n'
                'QUEST Q_390 1 3 (null) 0 True\n  FC TALK NPC_5\nEND\n'
                'QUEST Q_391 1 3 (null) 0 True\n  FC TALK NPC_5\nEND\n')
        self.assertEqual(export.quest_ids(text), {4, 390, 391})
        out = export.strip_quests(text, {390})
        self.assertNotIn('Q_390', out)
        self.assertIn('AOQ PROMOTE TAKE Q_5', out)
        self.assertIn('QUEST Q_391', out)

    def test_strip_texts(self):
        tree = tw1_lan.DialogTree('translateDQ_390', [])
        keep = tw1_lan.DialogTree('translateDQ_391', [])
        lan = tw1_lan.build({'translateQ_390': 'a', 'translateQ_390_QTD': 'b',
                             'translateDQ_390_1': 'c', 'translateQ_391': 'd',
                             'translateNPC_3': 'Tago'}, [],
                            tw1_lan.build_trees([tree, keep]))
        tr, _a, rest = tw1_lan.read(export.strip_texts(lan, {390}))
        self.assertEqual(sorted(tr), ['translateNPC_3', 'translateQ_391'])
        self.assertEqual([x.id for x in tw1_lan.parse_trees(rest)],
                         ['translateDQ_391'])


class Speakers(unittest.TestCase):
    def test_giver_and_targets_count_as_used(self):
        q = Quest(390, 't')
        q.speakers = [{'id': 600, 'name': 'A', 'new': True},
                      {'id': 601, 'name': 'B', 'new': True}]
        q.giver = 600
        self.assertTrue(q.speaker_used(600))
        self.assertFalse(q.speaker_used(601))
        q.actions.append({'kind': 'ACTION', 'verb': 'NPC_CREATE',
                          'args': {'npc': 601}, 'when': 'TAKE'})
        self.assertTrue(q.speaker_used(601))


class Mp(unittest.TestCase):
    def test_null_lines_come_back_with_own_markers(self):
        q = Quest(709, 'mp')
        q.extra['qtx'] = {'raw': [
            ['FC', ['CLEAR_AREA', '(null)', '(null)', '60', '21']],
            ['ACTION', ['ENEMY_CREATE', 'ENABLE', 'ENEMY_UNDEAD', '(null)',
                        '(null)', '(null)', '(null)', '21']],
            ['ACTION', ['ENEMY_CREATE', 'ENABLE', 'ENEMY_ORC', '(null)',
                        '(null)', '(null)', '(null)', '21']],
            ['AOQ', ['PROMOTE', 'SOLVE', 'Q_710']]]}
        self.assertEqual(mpmerge.recover_null_lines(q), 3)
        self.assertEqual(q.task()['fc'], 'CLEAR_AREA')
        self.assertEqual(len(q.actions), 2)
        self.assertEqual(q.extra['qtx']['raw'],
                         [['AOQ', ['PROMOTE', 'SOLVE', 'Q_710']]])
        items, mapping = mpmerge.plan(q, 508, 'E1', {})
        nums = [mapping[('line', i)] for i in range(3)]
        # the two enemy lines had no number: each gets a marker of its own
        self.assertEqual(len(set(nums[1:])), 2)
        self.assertEqual(items[0]['name'], mods.NPC_MARKER)

    def test_copy_keeps_links(self):
        q = Quest(15, 'game')
        q.retail = True
        q.extra['qtx'] = {'raw': [['AOQ', ['PROMOTE', 'SOLVE', 'Q_16']]],
                          'giver_remove': 'CLOSE', 'log': False}
        own = retail.make_own(q, 390)
        self.assertIn({'type': 'PROMOTE', 'event': 'SOLVE', 'quest': 16},
                      own.links)
        self.assertEqual(own.extra.get('giver_remove'), 'CLOSE')
        self.assertIs(own.extra.get('log'), False)

    def test_editor_names(self):
        self.assertEqual(mods.editor_name('MARKER_QUEST_START'), 'Q_Giver')
        self.assertEqual(mods.editor_name('MARKER_QUEST_CREATE_ENEMY'),
                         'Q_Action_Create_Enemy')


if __name__ == '__main__':
    unittest.main()
