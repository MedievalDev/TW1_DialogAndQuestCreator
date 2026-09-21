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
        # 4.2.1: behind the last NPC, in front of the first QUEST - the
        # game swallows an NPC block that stands behind a quest
        self.assertIn('OBJECTS True\nEND\nNPC NPC_700 700 12 F5 0 123 25 '
                      '(null) SMALL True CHAR_05(15) 0\n  OBJECTS True\n'
                      'END\nQUEST Q_4 ', text)
        self.assertIn('NPC_700', export.engine_parse(text)[0])
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


def _after(q, pred, event='TAKE'):
    c = [n for n in q.conditions_list() if n['cond'] == 'after'][0]
    c['quest'], c['event'] = pred, event
    return q


class HookOrder(unittest.TestCase):
    """The unlock line of an own quest survives any order of the project
    quests (4.2.1: a changed game quest Q_4 written after Q_385 dropped
    the AOQ, Q_385 was never enabled and its giver never appeared)."""

    def _retail_q4(self):
        from questforge2 import retail
        q4 = Quest()
        m = export._find_block(QTX, 4)
        retail.import_block(q4, m.group(0))
        q4.actions[0]['args']['amount'] = '777'     # Marco changed it
        return q4

    def test_changed_game_quest_either_order(self):
        for order in ('own first', 'game quest first'):
            q, q4 = make_quest(), self._retail_q4()
            quests = [q, q4] if order == 'own first' else [q4, q]
            text, _ = export.patch_qtx(QTX, quests, _Index())
            b4 = export._find_block(text, 4).group(0)
            self.assertIn('  AOQ PROMOTE TAKE Q_390\n', b4, order)
            self.assertIn('REWARD GLD TAKE 777', b4, order)
            self.assertEqual(b4.count('Q_390'), 1, order)
            # a second export over the first result keeps exactly one
            text2, _ = export.patch_qtx(text, quests, _Index())
            self.assertEqual(text2, text, order)
            self.assertEqual(export.missing_hooks(text2, quests), [])

    def test_chain_of_own_quests_either_order(self):
        for order in (0, 1):
            a = make_quest(390)
            b = _after(make_quest(391), 390, 'CLOSE')
            quests = [a, b] if order else [b, a]
            text, _ = export.patch_qtx(QTX, quests, _Index())
            self.assertIn('  AOQ PROMOTE CLOSE Q_391\n',
                          export._find_block(text, 390).group(0), order)
            self.assertIn('  AOQ PROMOTE TAKE Q_390\n',
                          export._find_block(text, 4).group(0), order)
            text2, _ = export.patch_qtx(text, quests, _Index())
            self.assertEqual(text2, text, order)

    def test_own_link_stays(self):
        # 390 links to 391 itself, 391 has no condition on 390
        for order in (0, 1):
            a = make_quest(390)
            a.links.append({'type': 'PROMOTE', 'event': 'SOLVE',
                            'quest': 391})
            b = make_quest(391)
            quests = [a, b] if order else [b, a]
            text, _ = export.patch_qtx(QTX, quests, _Index())
            self.assertIn('  AOQ PROMOTE SOLVE Q_391\n',
                          export._find_block(text, 390).group(0), order)
            text2, _ = export.patch_qtx(text, quests, _Index())
            self.assertIn('  AOQ PROMOTE SOLVE Q_391\n',
                          export._find_block(text2, 390).group(0), order)

    def test_npc_behind_a_quest_is_moved(self):
        # what 4.2.0 wrote: the new NPC in front of its quest at the end
        q = make_quest(385)
        q.speakers.append({'id': 508, 'name': 'Kunibert', 'lector': None,
                           'tile': 'E1', 'new': True, 'marker': 508})
        rec = export.npc_block(q.speakers[-1], _Index())
        old = QTX + rec + 'QUEST Q_385 1 3 (null) 0 True\nEND\n'
        self.assertNotIn('NPC_508', export.engine_parse(old)[0])
        self.assertEqual(export.unread_npcs(old, [q]), ['NPC_508'])
        text, log = export.patch_qtx(old, [q], _Index())
        self.assertIn(('npc-update', 508), log)
        self.assertEqual(text.count('NPC NPC_508 '), 1)
        self.assertLess(text.index('NPC NPC_508 '), text.index('QUEST '))
        self.assertEqual(export.unread_npcs(text, [q]), [])
        again, log2 = export.patch_qtx(text, [q], _Index())
        self.assertEqual(again, text)
        self.assertNotIn(('npc-update', 508), log2)

    def test_engine_parse_retail(self):
        base = os.path.join(ROOT, 'base', 'TwoWorldsQuests.qtx')
        if not os.path.isfile(base):
            self.skipTest('base files not extracted')
        with open(base, 'rb') as f:
            text = f.read().decode('latin-1')
        npcs, quests = export.engine_parse(text)
        # every NPC of the file is read; the game drops 700+ itself
        self.assertEqual(len(npcs), 347)
        self.assertEqual(len([q for q in quests if q < 400]), 380)

    def test_missing_hooks(self):
        q = make_quest()
        self.assertEqual(export.missing_hooks(QTX, [q]),
                         ['Q_4: AOQ PROMOTE TAKE Q_390'])
        text, _ = export.patch_qtx(QTX, [q], _Index())
        self.assertEqual(export.missing_hooks(text, [q]), [])


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

    def test_dialog_template(self):
        """The standard giver dialog goes into an empty quest connected and
        into a quest with dialog beside it; the result builds a tree."""
        from questforge2 import data
        tpls = {tp['name']: tp for tp in data.builtin_templates('dialog')}
        # 4.3.0: five templates without TODO next to the standard giver
        self.assertEqual(len(tpls), 6)
        graph = tpls['dialog_standard_giver']['data']['graph']
        q = Quest(390, 'Leer')
        q.add_speaker({'id': 3, 'name': 'Tago', 'lector': 123, 'tile': 'E1',
                       'new': False})
        model.add_default_conditions(q)
        new, connected, skipped = model.insert_dialog(q, graph, 3)
        self.assertEqual(len(new), 7)
        self.assertEqual(sorted(connected),
                         ['closed', 'first', 'running', 'solved'])
        self.assertEqual(skipped, [])
        speakers = {q.graph['nodes'][n]['speaker'] for n in new
                    if q.graph['nodes'][n]['type'] == 'npc'}
        self.assertEqual(speakers, {3})
        tree, texts = export.quest_texts(q)
        self.assertGreaterEqual(len(tree.entries), 7)
        full = make_quest()
        before = max(n.get('x', 0) for n in full.graph['nodes'].values()
                     if n.get('type') in ('npc', 'player'))
        new2, connected2, skipped2 = model.insert_dialog(full, graph, 3)
        self.assertEqual(connected2, [])
        self.assertEqual(sorted(skipped2),
                         ['closed', 'first', 'running', 'solved'])
        self.assertTrue(all(full.graph['nodes'][n]['x'] > before
                            for n in new2))

    def test_dialog_templates_430(self):
        """The five dialog templates of 4.3.0: every line filled in (no
        TODO) in both languages, the quest validates, and a question menu
        comes back with only the question just asked negative - the pattern
        of every retail menu (DQ_4 entry 24, DQ_15 entry 47)."""
        from questforge2 import data, validate
        tpls = [tp for tp in data.builtin_templates('dialog')
                if tp['name'] != 'dialog_standard_giver']
        self.assertEqual(len(tpls), 5)
        for tp in tpls:
            for lang in ('de', 'en'):
                q = make_quest()
                g = q.graph
                model.remove_nodes(g, [n for n, v in g['nodes'].items()
                                       if v.get('type') in ('npc', 'player',
                                                            'action')])
                g['edges'] = [e for e in g['edges'] if e[0] in g['nodes']
                              and e[2] in g['nodes']]
                new, connected, _skipped = model.insert_dialog(
                    q, tp['data']['graph'], 3, lang)
                self.assertEqual(sorted(connected),
                                 ['closed', 'first', 'running', 'solved'])
                texts = [ln['text'] for n in new
                         for ln in g['nodes'][n]['lines']]
                self.assertTrue(all(isinstance(x, str) and x.strip()
                                    for x in texts), tp['name'])
                self.assertFalse(any('TODO' in x for x in texts))
                E, _W = validate.validate_quest(q, _Index())
                self.assertEqual(E, [], (tp['name'], lang))
                tree, _texts = export.graph_to_tree(q)
                for e in tree.entries:
                    self.assertLessEqual(sum(1 for x in e.next if x < 0), 1)
                if tp['name'] == 'dialog_01_test':
                    backs = [e.next for e in tree.entries
                             if any(x < 0 for x in e.next)]
                    self.assertEqual(len(backs), 2)       # two questions
                    self.assertEqual(len(tree.entries), 14)

    def test_test_dialog_quest_exports_at_once(self):
        """4.3.0: an empty quest with the test dialog (Tago, as the tool
        does it) has no error: title, journal, task and reward come with
        the template."""
        from questforge2 import data, validate
        tp = next(x for x in data.builtin_templates('dialog')
                  if x['name'] == 'dialog_01_test')
        for lang in ('de', 'en'):
            q = Quest(390)
            model.add_default_conditions(q)
            q.add_speaker({'id': 3, 'name': 'Tago', 'lector': 123,
                           'tile': 'E1', 'new': False})
            q.giver = 3
            model.insert_dialog(q, tp['data']['graph'], 3, lang)
            model.apply_template_quest(q, tp['data']['quest'], lang)
            E, _W = validate.validate_quest(q, _Index())
            self.assertEqual(E, [], lang)
            self.assertEqual(q.task()['fc'], 'BRING_GOLD')
            self.assertIn('REWARD GLD CLOSE 20',
                          export.build_quest_block(q).emit())
            # a filled title stays
            q.title = 'Mein Titel'
            model.apply_template_quest(q, tp['data']['quest'], lang)
            self.assertEqual(q.title, 'Mein Titel')

    def test_shipped_templates_build(self):
        """Every quest template validates, builds its block and packs into
        an archive; every enemy template fills a valid ENEMY_CREATE."""
        from questforge2 import data, validate
        from questforge2 import retail as rt
        quests = data.builtin_templates('quest')
        enemies = data.builtin_templates('enemy')
        self.assertGreaterEqual(len(quests), 4)
        self.assertGreaterEqual(len(enemies), 4)
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
            p = Project('Templates')
            for i, tp in enumerate(quests):
                raw = dict(tp['data'])
                raw.pop('template', None)
                q = rt.make_own(Quest.from_dict(raw), 390 + i)
                E, W = validate.validate_quest(q, _Index())
                self.assertEqual(E, [], tp['name'])
                self.assertIn('warn.todo', ' '.join(m for m, _ in W))
                self.assertIsNotNone(export.build_quest_block(q))
                p.quests.append(q)
            res = export.export_mod(p, game, base, _Index(), lambda m: None,
                                    register=False)
            qtx = {e.path: e.data for e in tw1_wd.read(res['archive'])}[
                export.INNER_QTX]
            for i in range(len(quests)):
                self.assertIn(b'QUEST Q_%d ' % (390 + i), qtx)
        for tp in enemies:
            args = dict(tp['data']['args'], marker=3, tile='E1')
            toks = model.op_tokens(
                model.ACTION_SPECS[('ACTION', 'ENEMY_CREATE')], args)
            self.assertEqual(len(toks), 6, tp['name'])
            self.assertIn(args['party'], model.PARTIES)

    def test_copy_references(self):
        q = make_quest(390)
        q.links = [{'type': 'PROMOTE', 'event': 'SOLVE', 'quest': 390},
                   {'type': 'DISABLE', 'event': 'TAKE', 'quest': 12}]
        foreign = model.copy_references(q, 390, 395)
        self.assertEqual(q.links[0]['quest'], 395)       # self reference
        self.assertEqual(q.links[1]['quest'], 12)        # stays
        kinds = sorted(k for k, _q, _t in foreign)
        self.assertEqual(kinds, ['condition', 'link'])   # Q_4 and Q_12

    def test_archive_name(self):
        p = Project('Meine Mod!')
        self.assertEqual(export.archive_name(p), 'MeineMod.wd')
        p.target_archive = 'Yamalin.wd'
        self.assertEqual(export.archive_name(p), 'Yamalin.wd')


if __name__ == '__main__':
    unittest.main()
