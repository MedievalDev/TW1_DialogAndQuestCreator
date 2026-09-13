import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tw1_lan  # noqa: E402
import tw1_qtx  # noqa: E402
from questforge2 import export, model, retail  # noqa: E402
from questforge2.model import Project, Quest  # noqa: E402

BASE_QTX = os.path.join(ROOT, 'base', 'TwoWorldsQuests.qtx')
BASE_LAN = os.path.join(ROOT, 'base', 'TwoWorldsQuests.lan')

BLOCK = """QUEST Q_235 0 105 201 5 True
  GIVER PASSIVE NPC_235 BACK_TO_GIVER_MAP_SIGN CLOSE
  FC CLEAR_AREA 235 C6 60 21
  AOQ DISABLE TAKE Q_236
  ACTION ENEMY_CREATE ENABLE ENEMY_ORC 4 3 235 C6 21
  ACTION CHANGE_RELATIONS CLOSE 39 -1 AGGRESSIVE
  REWARD GLD CLOSE 400
  REWARD REP CLOSE 1 201
END
"""


class Block(unittest.TestCase):
    def test_import_and_unchanged(self):
        q = Quest()
        raw = retail.import_block(q, BLOCK)
        self.assertEqual(q.id, 235)
        self.assertEqual((q.giver, q.giver_type, q.map_sign),
                         (235, 'PASSIVE', 'BACK_TO_GIVER_MAP_SIGN'))
        self.assertEqual(q.task()['fc'], 'CLEAR_AREA')
        self.assertEqual(q.task()['args'], {'marker': 235, 'tile': 'C6',
                                            'range': 60, 'party': 21})
        self.assertEqual(len(q.actions), 3)
        self.assertEqual([r[0] for r in raw], ['AOQ', 'ACTION'])
        conds = {c['cond']: c for c in q.conditions_list()}
        self.assertEqual(conds['level']['level'], 0)
        self.assertEqual((conds['guild']['guild'], conds['guild']['min_rep']),
                         ('201', 5))
        self.assertFalse(retail.changed(q))
        self.assertEqual(retail.block_text(q), BLOCK)
        # survives the project file
        q2 = Quest.from_dict(Project.from_json(
            _proj(q).to_json()).quests[0].to_dict())
        self.assertEqual(retail.block_text(q2), BLOCK)

    def test_changed_rebuild(self):
        q = Quest()
        retail.import_block(q, BLOCK)
        q.actions[1]['args']['amount'] = '999'
        self.assertTrue(retail.changed(q))
        text = retail.block_text(q)
        self.assertIn('  REWARD GLD CLOSE 999\n', text)
        self.assertIn('  AOQ DISABLE TAKE Q_236\n', text)
        self.assertIn('  ACTION CHANGE_RELATIONS CLOSE 39 -1 AGGRESSIVE\n', text)
        self.assertEqual(text.split('\n')[0], 'QUEST Q_235 0 105 201 5 True')
        self.assertEqual(tw1_qtx.parse_quest(text.rstrip('\n')).emit(), text)

    def test_patch_and_make_own(self):
        base = 'QUEST Q_1 1 3 (null) 0 True\n  FC TALK NPC_5\nEND\n' + BLOCK
        q = Quest()
        retail.import_block(q, BLOCK)
        text, log = export.patch_qtx(base, [q])
        self.assertEqual(text, base)
        self.assertEqual(log, [])
        q.actions[0]['args']['count'] = 9
        text, log = export.patch_qtx(base, [q])
        self.assertEqual(log, [('replace', 235)])
        self.assertIn('ENEMY_ORC 9 3 235 C6 21', text)
        self.assertTrue(text.startswith('QUEST Q_1 1 3'))
        own = retail.make_own(q, 390)
        self.assertFalse(own.retail)
        self.assertNotIn('qtx', own.extra)
        self.assertEqual(own.id, 390)
        self.assertTrue(any(c['cond'] == 'after' for c in own.conditions_list()))


def _proj(q):
    p = Project('x')
    p.quests.append(q)
    return p


@unittest.skipUnless(os.path.isfile(BASE_QTX) and os.path.isfile(BASE_LAN),
                     'base files not extracted')
class AllRetail(unittest.TestCase):
    def test_all_blocks_unchanged(self):
        with open(BASE_QTX, 'rb') as f:
            text = f.read().decode('latin-1')
        blocks = [m.group(0) for m in re.finditer(
            r'^QUEST Q_\d+ [^\n]*\n.*?^END\n', text, re.M | re.S)]
        self.assertEqual(len(blocks), 500)
        quests, raw_total = [], 0
        for b in blocks:
            q = Quest()
            raw_total += len(retail.import_block(q, b))
            self.assertFalse(retail.changed(q), b[:20])
            self.assertEqual(retail.block_text(q), b)
            quests.append(q)
        out, log = export.patch_qtx(text, quests)
        self.assertEqual(out, text)
        self.assertEqual(log, [])
        # a rebuilt block (every quest touched) must parse and keep all
        # lines, possibly in a different order
        for q, b in zip(quests, blocks):
            q.extra['qtx']['sig'] = 'force rebuild'
            rebuilt = retail.block_text(q)
            self.assertEqual(sorted(rebuilt.split('\n')), sorted(b.split('\n')),
                             b[:20])
        print(f'\n  retail qtx: 500 blocks identical, {raw_total} raw lines')

    def test_lan_unchanged_retail_quest(self):
        with open(BASE_LAN, 'rb') as f:
            master = f.read()
        tr, _, rest = tw1_lan.read(master)
        tree = [t for t in tw1_lan.parse_trees(rest)
                if t.id == 'translateDQ_205'][0]
        q = Quest(205)
        q.retail = True
        q.title = tr.get('translateQ_205', '')
        q.journal = {'take': tr.get('translateQ_205_QTD', ''),
                     'solve': tr.get('translateQ_205_QSD', ''),
                     'close': tr.get('translateQ_205_QCD', '')}
        export.tree_to_graph(q, tree, tr, None, 205)
        full, overlay = export.build_lan(master, [q])
        self.assertEqual(full, master)

    def test_lan_all_retail_quests_unchanged(self):
        """Every retail quest with a tree: import and rebuild the master."""
        with open(BASE_LAN, 'rb') as f:
            master = f.read()
        tr, _, rest = tw1_lan.read(master)
        quests = []
        for tree in tw1_lan.parse_trees(rest):
            m = re.fullmatch(r'translateDQ_(\d+)', tree.id)
            if not m:
                continue
            qid = int(m.group(1))
            q = Quest(qid)
            q.retail = True
            q.title = tr.get(f'translateQ_{qid}', '')
            q.journal = {'take': tr.get(f'translateQ_{qid}_QTD', ''),
                         'solve': tr.get(f'translateQ_{qid}_QSD', ''),
                         'close': tr.get(f'translateQ_{qid}_QCD', '')}
            export.tree_to_graph(q, tree, tr, None, qid)
            quests.append(q)
        full, overlay = export.build_lan(master, quests)
        self.assertEqual(len(quests), 378)
        self.assertEqual(full, master)


if __name__ == '__main__':
    unittest.main()
