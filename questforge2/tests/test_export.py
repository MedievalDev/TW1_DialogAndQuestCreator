import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tw1_lan  # noqa: E402
from questforge2 import export, model  # noqa: E402
from questforge2.model import Quest, entry_id  # noqa: E402

BASE_LAN = os.path.join(ROOT, 'base', 'TwoWorldsQuests.lan')


class _Index:
    """Minimal stand-in for data.Index."""
    def __init__(self):
        self.lectors = {'326': [205], '123': [3]}
        self.npcs = {'205': {'name': 'Bote', 'tile': 'D3', 'lector': 326},
                     '3': {'name': 'Tago', 'tile': 'F5', 'lector': 123}}

    def npc(self, nid):
        return self.npcs.get(str(nid))

    def quest(self, qid):
        return {'giver': 205} if qid == 205 else None


def _tree_205():
    e = tw1_lan.DialogEntry
    L = 326
    tids = [f'translateDQ_205_0.FT.AS_{i}' for i in range(7)] + \
        ['translateDQ_205_0.QT_0']
    ents = [
        e(L, tids[0], 'CUE_0326_0001', [1], 0x20001, [2], 0, 0),
        e(1, tids[1], 'CUE_0001_0923', [2], 0x20001, [7], 0, 0),
        e(L, tids[2], 'CUE_0326_0002', [3], 0x20001, [2], 10, 10),
        e(1, tids[3], 'CUE_0001_0924', [4], 0x20001, [6], 17, 17),
        e(L, tids[4], 'CUE_0326_0003', [5], 0x20001, [2], 0, 0),
        e(1, tids[5], 'CUE_0001_0925', [6], 0x20001, [6], 10, 10),
        e(L, tids[6], 'CUE_0326_0004', [], 0x20001, [2], 0, 0),
        e(L, tids[7], 'CUE_0326_0005', [], 0x4, [1], 0, 0),
    ]
    tr = {tid: f'text {i}' for i, tid in enumerate(tids)}
    return tw1_lan.DialogTree('translateDQ_205', ents), tr


class RoundTrip(unittest.TestCase):
    def test_dq205_fixture_roundtrip(self):
        tree, tr = _tree_205()
        q = Quest(205)
        rep = export.tree_to_graph(q, tree, tr, _Index(), 205)
        self.assertEqual(rep.entries, 8)
        self.assertEqual(rep.lossy, [])
        self.assertEqual([s['id'] for s in q.speakers], [205])
        self.assertEqual(q.speakers[0]['lector'], 326)
        self.assertEqual(q.node_count(), 8)
        # levels and entries
        first = [n for n in q.graph['nodes'].values()
                 if n.get('state') == 'first' and n['type'] != 'entry']
        self.assertEqual(len(first), 7)
        self.assertTrue(all(n['lines'][0]['take'] for n in first))
        taken = [n for n in q.graph['nodes'].values()
                 if n.get('state') == 'taken' and n['type'] != 'entry']
        self.assertEqual(len(taken), 1)
        self.assertEqual(model.edge_from(q.graph, entry_id('first'), 0)[2],
                         [nid for nid, n in q.graph['nodes'].items()
                          if n['type'] == 'npc' and n['lines'][0]['order'] == 0][0])
        self.assertIn(entry_id('taken'), q.graph['nodes'])
        out, texts = export.graph_to_tree(q)
        self.assertEqual(tw1_lan.build_trees([out]),
                         tw1_lan.build_trees([tree]))
        self.assertEqual(texts, tr)

    def test_edit_changes_flags_only_where_edited(self):
        tree, tr = _tree_205()
        q = Quest(205)
        export.tree_to_graph(q, tree, tr, _Index(), 205)
        n0 = [nid for nid, n in q.graph['nodes'].items()
              if n['type'] == 'npc' and n['lines'][0].get('order') == 0][0]
        q.graph['nodes'][n0]['lines'][0]['text'] = 'neu'
        out, texts = export.graph_to_tree(q)
        self.assertEqual(texts['translateDQ_205_0.FT.AS_0'], 'neu')
        self.assertEqual([e.flags for e in out.entries],
                         [e.flags for e in tree.entries])

    def test_new_quest_export(self):
        q = Quest(390)
        q.add_speaker({'id': 3, 'name': 'Tago', 'lector': 123, 'tile': 'F5',
                       'new': False})
        g = q.graph
        n1 = model.add_node(g, model.make_node('npc', 0, 0, 'first', 3))
        g['nodes'][n1]['lines'][0]['text'] = 'Hilf mir.'
        p = model.add_node(g, model.make_node('player', 0, 0, 'first'))
        g['nodes'][p]['kind'] = 'question'
        g['nodes'][p]['lines'] = [dict(model.new_line('first'), text='Ja.',
                                       take=True),
                                  dict(model.new_line('first'), text='Nein.')]
        n2 = model.add_node(g, model.make_node('npc', 0, 0, 'first', 3))
        g['nodes'][n2]['lines'][0]['text'] = 'Danke.'
        r = model.add_node(g, model.make_node('npc', 0, 0, 'running', 3))
        g['nodes'][r]['lines'][0]['text'] = 'Noch nicht?'
        s = model.add_node(g, model.make_node('npc', 0, 0, 'solved', 3))
        g['nodes'][s]['lines'][0]['text'] = 'Belohnung.'
        c = model.add_node(g, model.make_node('npc', 0, 0, 'closed', 3))
        g['nodes'][c]['lines'][0]['text'] = 'Danach.'
        for frm, port, to in ((entry_id('first'), 0, n1), (n1, 0, p),
                              (p, 0, n2), (entry_id('running'), 0, r),
                              (entry_id('solved'), 0, s),
                              (entry_id('closed'), 0, c)):
            self.assertTrue(model.connect(g, frm, port, to))
        tree, texts = export.graph_to_tree(q)
        self.assertEqual(tree.id, 'translateDQ_390')
        ents = tree.entries
        self.assertEqual(len(ents), 7)
        # order: offer chain, then running, solved, closed
        self.assertEqual([e.flags for e in ents],
                         [0x1, 0x20001, 0x1, 0x20001, 0x100, 0x40200, 0x8])
        self.assertEqual(ents[0].next, [1, 2])          # the reply menu
        self.assertEqual(ents[1].next, [3])
        self.assertEqual(ents[2].next, [])
        self.assertEqual([e.lector for e in ents], [123, 1, 1, 123, 123, 123, 123])
        self.assertEqual(ents[0].cams, [2])
        self.assertEqual(ents[1].cams, [7])
        self.assertEqual(ents[0].tid, 'translateDQ_390_0.FT_0')
        self.assertEqual(ents[1].tid, 'translateDQ_390_0.FT.AS_0')
        self.assertEqual(ents[4].tid, 'translateDQ_390_0.QNS.AE_0')
        self.assertEqual(texts[ents[5].tid], 'Belohnung.')
        self.assertNotIn(b'\r', tw1_lan.build_trees([tree]))

    @unittest.skipUnless(os.path.isfile(BASE_LAN), 'base lan not extracted')
    def test_retail_trees_roundtrip(self):
        """Every retail quest tree must survive import + export unchanged
        unless the import reported a lossy menu."""
        from questforge2 import data
        with open(BASE_LAN, 'rb') as f:
            tr, _, rest = tw1_lan.read(f.read())
        trees = [t for t in tw1_lan.parse_trees(rest)
                 if t.id.startswith('translateDQ_')]
        cache = os.path.join(data.ROOT, 'cache', 'index.json')
        idx = None
        if os.path.isfile(cache):
            import json
            with open(cache, encoding='utf-8') as f:
                idx = data.Index(json.load(f))
        ok = lossy = broken = 0
        bad = []
        for t in trees:
            qid = int(t.id.split('_')[1])
            q = Quest(qid)
            rep = export.tree_to_graph(q, t, tr, idx, qid)
            out, texts = export.graph_to_tree(q)
            same = tw1_lan.build_trees([out]) == tw1_lan.build_trees([t])
            if same:
                ok += 1
            elif rep.lossy:
                lossy += 1
            else:
                broken += 1
                bad.append(t.id)
        print(f'\n  retail round trip: {ok} identical, {lossy} lossy menus, '
              f'{broken} broken {bad[:8]}')
        self.assertEqual(broken, 0, bad[:8])
        self.assertGreater(ok, len(trees) * 0.9)
        t205 = [t for t in trees if t.id == 'translateDQ_205'][0]
        q = Quest(205)
        export.tree_to_graph(q, t205, tr, idx, 205)
        out, _ = export.graph_to_tree(q)
        self.assertEqual(tw1_lan.build_trees([out]), tw1_lan.build_trees([t205]))


if __name__ == '__main__':
    unittest.main()
