import contextlib
import io
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tw1_lan  # noqa: E402
import tw1_qtx  # noqa: E402
import tw1_wd  # noqa: E402
import wdio  # noqa: E402
from questforge2 import export, model  # noqa: E402
from questforge2.model import Project, Quest, entry_id  # noqa: E402

QTX = """NPC NPC_3 3 3 E1 0 123 25 (null) SMALL True CHAR_05(15)#WP_MACE_0(4,0,6) 0
  OBJECTS True
END
QUEST Q_4 1 3 (null) 0 True
  GIVER ACTIVE NPC_3 AUTO_CLOSE_ON_SOLVE NONE
  FC TALK NPC_5
  REWARD GLD TAKE SMALL
END
QUEST Q_12 0 3 (null) 0 True
  FC TALK NPC_5
  AOQ PROMOTE CLOSE Q_13
END
"""


class _Index:
    def __init__(self):
        rec = 'NPC NPC_3 3 3 E1 0 123 25 (null) SMALL True CHAR_05(15) 0'
        self.npcs = {'3': {'name': 'Tago', 'tile': 'E1', 'lector': 123,
                           'record': rec, 'source': 'retail'}}
        self.lectors = {'123': [3]}
        self.groups = {'0': 'Test', '3': 'Kapitel'}
        self.quests = {'4': {'source': 'retail', 'giver': 3},
                       '12': {'source': 'retail', 'giver': None}}

    def npc(self, nid):
        return self.npcs.get(str(nid))

    def quest(self, qid):
        return self.quests.get(str(qid))


def make_quest(qid=390):
    q = Quest(qid, 'Testquest')
    q.journal = {'take': 'A', 'solve': 'B', 'close': 'C'}
    q.giver = 3
    q.add_speaker({'id': 3, 'name': 'Tago', 'lector': 123, 'tile': 'E1',
                   'new': False})
    g = q.graph
    model.add_default_conditions(q)
    model.set_task(g, 'BRING_GOLD')
    g['nodes'][model.TASK_ID]['args']['gold'] = 100
    n1 = model.add_node(g, model.make_node('npc', 0, 0, 'first', 3))
    g['nodes'][n1]['lines'][0].update(text='Hilf mir.', take=True)
    r = model.add_node(g, model.make_node('npc', 0, 0, 'running', 3))
    g['nodes'][r]['lines'][0]['text'] = 'Noch nicht?'
    s = model.add_node(g, model.make_node('npc', 0, 0, 'solved', 3))
    g['nodes'][s]['lines'][0]['text'] = 'Danke.'
    c = model.add_node(g, model.make_node('npc', 0, 0, 'closed', 3))
    g['nodes'][c]['lines'][0]['text'] = 'Danach.'
    for frm, to in ((entry_id('first'), n1), (entry_id('running'), r),
                    (entry_id('solved'), s), (entry_id('closed'), c)):
        model.connect(g, frm, 0, to)
    gold = model.add_node(g, model.make_action('REWARD', 'GLD', s))
    g['nodes'][gold]['args']['amount'] = '500'
    tele = model.add_node(g, model.make_action('ACTION', 'NPC_TELEPORT', n1))
    g['nodes'][tele]['args'].update(npc=3, marker=19, tile='h6', angle=128)
    model.restack(g)
    return q


class QtxBlock(unittest.TestCase):
    def test_block_and_validation(self):
        q = make_quest()
        E, W = export.validate_quest(q, _Index())
        self.assertEqual(E, [])
        blk = export.build_quest_block(q).emit()
        self.assertEqual(blk, (
            'QUEST Q_390 1 0 (null) 0 True\n'
            '  GIVER ACTIVE NPC_3 BACK_TO_GIVER_MAP_SIGN NONE\n'
            '  FC BRING_GOLD 100\n'
            '  ACTION NPC_TELEPORT TAKE NPC_3 19 H6 128\n'
            '  REWARD GLD CLOSE 500\n'
            'END\n'))
        # tw1_qtx parses its own output back
        self.assertEqual(tw1_qtx.parse_quest(blk.rstrip('\n')).emit(), blk)

    def test_action_level_rules(self):
        q = make_quest()
        g = q.graph
        run = [nid for nid, n in g['nodes'].items()
               if n.get('state') == 'running' and n['type'] == 'npc'][0]
        a = model.add_node(g, model.make_action('REWARD', 'EXP', run))
        E, _ = export.validate_quest(q, _Index())
        self.assertTrue(any(e[1] == a for e in E))
        g['nodes'][a]['attached_to'] = None
        g['nodes'].pop(a)
        solved = [nid for nid, n in g['nodes'].items()
                  if n.get('state') == 'solved' and n['type'] == 'npc'][0]
        gold = [nid for nid, n in g['nodes'].items() if n.get('type') == 'action'
                and n.get('attached_to') == solved][0]
        g['nodes'][gold]['when'] = 'SOLVE'
        self.assertIn('REWARD GLD SOLVE 500', export.build_quest_block(q).emit())

    def test_errors(self):
        q = make_quest()
        q.journal['solve'] = ''
        q.id = 400
        model.set_task(q.graph, 'KILL')
        E, _ = export.validate_quest(q, _Index())
        keys = ' '.join(e[0] for e in E)
        self.assertIn('val.id.limit', keys)  # above limit 400
        self.assertIn('val.journal.solve', keys)
        self.assertIn('val.task.field', keys)
        q.id = 390
        idx = _Index()
        idx.quests['390'] = {'source': 'Yamalin.wd', 'giver': 3}
        E, W = export.validate_quest(q, idx, archive='Testmod.wd')
        self.assertIn('val.id.taken', ' '.join(e[0] for e in E))
        E, W = export.validate_quest(q, idx, archive='Yamalin.wd')
        self.assertNotIn('val.id.taken', ' '.join(e[0] for e in E))
        self.assertIn('val.id.replace', ' '.join(w[0] for w in W))

    def test_patch_qtx(self):
        q = make_quest()
        q.speakers.append({'id': 700, 'name': 'Neu', 'lector': 123,
                           'tile': 'f5', 'new': True, 'marker': 12})
        text, log = export.patch_qtx(QTX, [q], _Index())
        self.assertIn('  AOQ PROMOTE TAKE Q_390\n', text)
        b4 = export._find_block(text, 4).group(0)
        self.assertEqual(b4.split('\n')[2], '  FC TALK NPC_5')
        self.assertEqual(b4.split('\n')[3], '  AOQ PROMOTE TAKE Q_390')
        self.assertIn('NPC NPC_700 700 12 F5 0 123 25 (null) SMALL True '
                      'CHAR_05(15) 0\n  OBJECTS True\nEND\nQUEST Q_390', text)
        # re-export: no duplicates, condition change moves the AOQ
        q.offered = False
        c = [n for n in q.conditions_list() if n['cond'] == 'after'][0]
        c['quest'], c['event'] = 12, 'CLOSE'
        text2, _ = export.patch_qtx(text, [q], _Index())
        self.assertEqual(text2.count('QUEST Q_390 '), 1)
        self.assertEqual(text2.count('NPC NPC_700 '), 1)
        self.assertNotIn('Q_390\n', export._find_block(text2, 4).group(0))
        b12 = export._find_block(text2, 12).group(0)
        self.assertIn('  AOQ PROMOTE CLOSE Q_13\n  AOQ TAKE CLOSE Q_390\n', b12)
        self.assertNotIn('\r', text2)

    def test_lan(self):
        q = make_quest()
        master = tw1_lan.build({'translateQ_4': 'Alt',
                                'translateDQ_390_0.X_9': 'stale'}, [],
                               tw1_lan.build_trees([]))
        full, overlay = export.build_lan(master, [q])
        tr, _, rest = tw1_lan.read(full)
        self.assertEqual(tr['translateQ_390'], 'Testquest')
        self.assertEqual(tr['translateQ_390_QSD'], 'B')
        self.assertNotIn('translateDQ_390_0.X_9', tr)
        self.assertEqual(tr['translateQ_4'], 'Alt')
        trees = tw1_lan.parse_trees(rest)
        self.assertEqual([t.id for t in trees], ['translateDQ_390'])
        self.assertEqual([hex(e.flags) for e in trees[0].entries],
                         ['0x20001', '0x100', '0x40200', '0x8'])
        otr, _, orest = tw1_lan.read(overlay)
        self.assertEqual(len(tw1_lan.parse_trees(orest)), 1)
        self.assertNotIn('translateQ_4', otr)


class Packing(unittest.TestCase):
    def test_pack_new_and_merge(self):
        q = make_quest()
        p = Project('Testmod')
        p.quests.append(q)
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, 'base')
            os.makedirs(base)
            with open(os.path.join(base, 'TwoWorldsQuests.qtx'), 'wb') as f:
                f.write(QTX.encode('latin-1'))
            with open(os.path.join(base, 'TwoWorldsQuests.lan'), 'wb') as f:
                f.write(tw1_lan.build({'translateQ_4': 'Alt'}, [],
                                      tw1_lan.build_trees([])))
            game = os.path.join(d, 'game')
            os.makedirs(os.path.join(game, 'Mods'))
            # an existing archive with an unrelated file
            stage = os.path.join(d, 'stage')
            os.makedirs(os.path.join(stage, 'Parameters'))
            with open(os.path.join(stage, 'Parameters', 'X.txt'), 'wb') as f:
                f.write(b'keep me\n')
            arch = os.path.join(game, 'Mods', 'Testmod.wd')
            with contextlib.redirect_stdout(io.StringIO()):
                wdio.pack_single(stage, arch, 1, None)
            logs = []
            res = export.export_mod(p, game, base, _Index(), logs.append,
                                    register=False)
            self.assertEqual(res['archive'], arch)
            ents = {e.path: e.data for e in tw1_wd.read(arch)}
            self.assertEqual(ents['Parameters\\X.txt'], b'keep me\n')
            self.assertIn(b'QUEST Q_390', ents[export.INNER_QTX])
            self.assertIn('Language\\ZZ_QF_Testmod.lan', ents)
            self.assertTrue(os.path.isfile(arch + '.qf2backup'))
            self.assertIn(('verified', 4), logs)
            # second export reads the qtx from the archive, no duplicates
            export.export_mod(p, game, base, _Index(), logs.append,
                              register=False)
            ents = {e.path: e.data for e in tw1_wd.read(arch)}
            self.assertEqual(ents[export.INNER_QTX].count(b'QUEST Q_390 '), 1)
            self.assertEqual(ents[export.INNER_QTX].count(
                b'AOQ PROMOTE TAKE Q_390'), 1)
            # files only
            out = os.path.join(d, 'out')
            export.export_mod(p, game, base, _Index(), logs.append,
                              files_only=out)
            self.assertTrue(os.path.isfile(os.path.join(
                out, 'Scripts', 'Quests', 'TwoWorldsQuests.qtx')))

    def test_other_project_overlay_cleaned(self):
        """Exporting a quest id that another project already put into the
        same archive removes that project's stale texts (game test 4a/4b)."""
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, 'base')
            os.makedirs(base)
            with open(os.path.join(base, 'TwoWorldsQuests.qtx'), 'wb') as f:
                f.write(QTX.encode('latin-1'))
            with open(os.path.join(base, 'TwoWorldsQuests.lan'), 'wb') as f:
                f.write(tw1_lan.build({'translateQ_4': 'Alt'}, [],
                                      tw1_lan.build_trees([])))
            game = os.path.join(d, 'game')
            os.makedirs(os.path.join(game, 'Mods'))
            arch = os.path.join(game, 'Mods', 'Shared.wd')

            def project(name, *qids):
                p = Project(name)
                p.target_archive = 'Shared.wd'
                p.quests.extend(make_quest(q) for q in qids)
                return p

            # project A holds Q_390 and Q_391, project B only Q_392
            export.export_mod(project('A', 390, 391), game, base, _Index(),
                              lambda m: None, register=False)
            export.export_mod(project('B', 392), game, base, _Index(),
                              lambda m: None, register=False)
            # project C re-exports Q_390: A keeps only Q_391, B untouched
            logs = []
            export.export_mod(project('C', 390), game, base, _Index(),
                              logs.append, register=False)
            ents = {e.path: e.data for e in tw1_wd.read(arch)}
            tr_a, _, rest_a = tw1_lan.read(ents['Language\\ZZ_QF_A.lan'])
            self.assertFalse([k for k in tr_a if 'Q_390' in k])
            self.assertTrue([k for k in tr_a if 'Q_391' in k])
            self.assertEqual([t.id for t in tw1_lan.parse_trees(rest_a)],
                             ['translateDQ_391'])
            tr_b, _, _ = tw1_lan.read(ents['Language\\ZZ_QF_B.lan'])
            self.assertTrue([k for k in tr_b if 'Q_392' in k])
            self.assertIn(('overlay_cleaned', 'Language\\ZZ_QF_A.lan'), logs)
            # project D re-exports Q_391 and Q_392: A and B become empty
            export.export_mod(project('D', 391, 392), game, base, _Index(),
                              lambda m: None, register=False)
            ents = {e.path for e in tw1_wd.read(arch)}
            self.assertNotIn('Language\\ZZ_QF_A.lan', ents)
            self.assertNotIn('Language\\ZZ_QF_B.lan', ents)
            self.assertIn('Language\\ZZ_QF_C.lan', ents)
            self.assertIn('Language\\ZZ_QF_D.lan', ents)

    def test_archive_name(self):
        p = Project('Meine Mod!')
        self.assertEqual(export.archive_name(p), 'MeineMod.wd')
        p.target_archive = 'Yamalin.wd'
        self.assertEqual(export.archive_name(p), 'Yamalin.wd')


if __name__ == '__main__':
    unittest.main()
