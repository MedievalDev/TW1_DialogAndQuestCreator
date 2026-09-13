import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import model  # noqa: E402
from questforge2.model import Quest, entry_id, PLAYER  # noqa: E402

E1 = entry_id('first')


def _chain(g, n, state='first'):
    """entry:first -> n1 -> n2 ... ; returns ids"""
    ids = []
    prev = E1
    for i in range(n):
        nid = model.add_node(g, model.make_node('npc', 0, 0, state, 3))
        g['nodes'][nid]['lines'][0]['text'] = f'N{i}'
        model.connect(g, prev, 0, nid)
        ids.append(nid)
        prev = nid
    return ids


class GraphOps(unittest.TestCase):
    def test_entries_exist_and_survive(self):
        q = Quest(390)
        for st in model.DEFAULT_STATES:
            self.assertIn(entry_id(st), q.graph['nodes'])
        model.remove_nodes(q.graph, [E1])
        self.assertIn(E1, q.graph['nodes'])
        self.assertEqual(q.node_count(), 0)
        self.assertEqual(q.states_present(), list(model.DEFAULT_STATES))
        model.add_node(q.graph, model.make_node('player', 0, 0, 'known'))
        self.assertIn('known', q.states_present())

    def test_connect_rules(self):
        g = model.new_graph()
        a = model.add_node(g, model.make_node('npc', 0, 0, 'first', 3))
        b = model.add_node(g, model.make_node('player', 0, 0, 'first'))
        c = model.add_node(g, model.make_node('comment', 0, 0))
        self.assertTrue(model.connect(g, E1, 0, a))
        self.assertTrue(model.connect(g, a, 0, b))
        self.assertFalse(model.connect(g, a, 1, b))      # only one line
        self.assertFalse(model.connect(g, a, 0, a))
        self.assertFalse(model.connect(g, a, 0, c))       # comment
        self.assertFalse(model.connect(g, c, 0, a))
        self.assertFalse(model.connect(g, b, 0, E1))
        # cross-level edges are allowed (plan 12.18)
        d = model.add_node(g, model.make_node('npc', 0, 0, 'solved', 3))
        self.assertTrue(model.connect(g, b, 0, d))
        # replacing the edge of a port
        self.assertTrue(model.connect(g, E1, 0, b))
        self.assertEqual(model.edge_from(g, E1, 0), [E1, 0, b])
        # several lines -> several ports
        g['nodes'][b]['kind'] = 'question'
        model.add_line(g, b)
        self.assertEqual(model.out_port_count(g['nodes'][b]), 2)
        self.assertTrue(model.connect(g, b, 1, a))
        self.assertEqual(model.successors(g, b), [d, a])

    def test_remove_line_renumbers_ports(self):
        g = model.new_graph()
        p = model.add_node(g, model.make_node('player', 0, 0))
        g['nodes'][p]['kind'] = 'question'
        model.add_line(g, p)
        model.add_line(g, p)
        t0 = model.add_node(g, model.make_node('npc', 0, 0, 'first', 3))
        t2 = model.add_node(g, model.make_node('npc', 0, 0, 'first', 3))
        model.connect(g, p, 0, t0)
        model.connect(g, p, 2, t2)
        self.assertTrue(model.remove_line(g, p, 1))
        self.assertEqual(sorted(e for e in g['edges'] if e[0] == p),
                         [[p, 0, t0], [p, 1, t2]])
        self.assertTrue(model.remove_line(g, p, 0))
        self.assertEqual([e for e in g['edges'] if e[0] == p], [[p, 0, t2]])
        self.assertFalse(model.remove_line(g, p, 0))      # last line stays

    def test_remove_and_disconnect(self):
        g = model.new_graph()
        ids = _chain(g, 3)
        cid = model.add_node(g, model.make_node('comment', 0, 0))
        g['nodes'][cid]['attached_to'] = ids[1]
        model.remove_nodes(g, [ids[1]])
        self.assertNotIn(ids[1], g['nodes'])
        self.assertEqual(len(g['edges']), 1)
        self.assertIsNone(g['nodes'][cid]['attached_to'])
        self.assertEqual(model.disconnect(g, E1, 0), 1)
        self.assertEqual(g['edges'], [])

    def test_copy_paste_duplicate(self):
        g = model.new_graph()
        ids = _chain(g, 3)
        clip = model.copy_nodes(g, ids[:2] + [E1])
        self.assertEqual(set(clip['nodes']), set(ids[:2]))
        self.assertEqual(len(clip['edges']), 1)           # n1 -> n2 only
        new = model.paste_nodes(g, clip)
        self.assertEqual(len(new), 2)
        self.assertEqual(len(g['edges']), 4)
        self.assertEqual(g['nodes'][new[0]]['x'], 30)
        dup = model.duplicate_nodes(g, [ids[2]])
        self.assertEqual(g['nodes'][dup[0]]['lines'][0]['text'], 'N2')
        self.assertEqual(len(g['edges']), 4)

    def test_auto_layout_bands(self):
        g = model.new_graph()
        a = model.add_node(g, model.make_node('npc', 0, 0, 'first', 3))
        b = model.add_node(g, model.make_node('player', 0, 0, 'first'))
        c = model.add_node(g, model.make_node('player', 0, 0, 'first'))
        r = model.add_node(g, model.make_node('npc', 0, 0, 'running', 3))
        loose = model.add_node(g, model.make_node('npc', 0, 0, 'first', 3))
        g['nodes'][a]['lines'].append(model.new_line('first'))
        model.connect(g, E1, 0, a)
        model.connect(g, a, 0, b)
        model.connect(g, a, 1, c)
        model.connect(g, entry_id('running'), 0, r)
        order = model.auto_layout(g)
        self.assertEqual(order[:4], [E1, a, b, c])
        n = g['nodes']
        self.assertLess(n[E1]['x'], n[a]['x'])
        self.assertLess(n[a]['x'], n[b]['x'])
        self.assertEqual(n[b]['x'], n[c]['x'])
        self.assertLess(n[b]['y'], n[c]['y'])
        # the running band starts below the whole first band
        self.assertGreater(n[entry_id('running')]['y'], n[c]['y'])
        self.assertEqual(n[r]['y'], n[entry_id('running')]['y'])
        self.assertGreater(n[loose]['y'], n[r]['y'])

    def test_undo_stack_and_snapshot(self):
        q = Quest(390)
        u = model.UndoStack(limit=3)
        u.push(q.snapshot(), 'add')
        a = model.add_node(q.graph, model.make_node('npc', 1, 2, 'first', 3))
        q.title = 'changed'
        self.assertTrue(u.can_undo())
        st = u.undo(q.snapshot())
        q.restore(st)
        self.assertNotIn(a, q.graph['nodes'])
        self.assertEqual(q.title, '')
        st2 = u.redo(q.snapshot())
        q.restore(st2)
        self.assertIn(a, q.graph['nodes'])
        self.assertEqual(q.title, 'changed')
        for i in range(5):
            u.push(q.snapshot(), str(i))
        self.assertEqual(len(u._undo), 3)
        self.assertFalse(u.can_redo())

    def test_node_size(self):
        n = model.make_node('npc', 0, 0, 'first', 3)
        self.assertEqual(model.node_size(n)[1],
                         model.HEADER_H + model.LINE_H + model.NODE_PAD)
        p = model.make_node('player', 0, 0)
        p['kind'] = 'question'
        p['lines'].append(model.new_line())
        self.assertEqual(model.out_port_count(p), 2)
        self.assertEqual(model.node_size(p)[1],
                         model.HEADER_H + 3 * model.LINE_H + model.NODE_PAD)
        self.assertEqual(model.node_size(model.make_node('comment', 0, 0)),
                         (200, 80))


class FlagsAndStates(unittest.TestCase):
    def test_line_flags_table(self):
        ln = model.new_line('first')
        self.assertEqual(model.line_flags('first', ln), 0x1)
        ln['take'] = True
        self.assertEqual(model.line_flags('first', ln), 0x20001)
        self.assertEqual(model.line_flags('running', ln), 0x20100)
        sol = model.new_line('solved')
        self.assertTrue(sol['close'])                  # default in solved
        self.assertEqual(model.line_flags('solved', sol), 0x40200)
        self.assertEqual(model.line_flags('closed', model.new_line()), 0x8)
        self.assertEqual(model.line_flags('known', model.new_line()), 0x2)
        self.assertEqual(model.line_flags('lowrep', model.new_line()), 0x21)
        self.assertEqual(model.line_flags('neutral', model.new_line()), 0x0)
        f = model.new_line()
        f['fight'] = True
        self.assertEqual(model.line_flags('running', f), 0x10100)

    def test_flags_to_state_roundtrip(self):
        for state in model.STATES:
            for take in (False, True):
                ln = dict(model.new_line(), take=take, close=False)
                got = model.flags_to_state(model.line_flags(state, ln))
                self.assertEqual(got, (state, take, False, False), state)
        self.assertEqual(model.flags_to_state(0x40200),
                         ('solved', False, True, False))
        self.assertEqual(model.flags_to_state(0x10000),
                         ('neutral', False, False, True))
        self.assertEqual(model.flags_to_state(0x104)[0], 'neutral')  # unknown mix

    def test_speakers(self):
        q = Quest(390)
        q.add_speaker({'id': 3, 'name': 'Tago', 'lector': 4, 'tile': 'F5',
                       'new': False})
        q.add_speaker({'id': 3, 'name': 'dup', 'lector': 4, 'tile': 'F5',
                       'new': False})
        self.assertEqual(len(q.speakers), 1)
        nid = model.add_node(q.graph, model.make_node('npc', 0, 0, 'first', 3))
        self.assertTrue(q.speaker_used(3))
        self.assertFalse(q.remove_speaker(3))
        model.remove_nodes(q.graph, [nid])
        self.assertTrue(q.remove_speaker(3))
        self.assertEqual(q.speakers, [])

    def test_legacy_tabs_migrate(self):
        d = {'id': 385, 'tabs': {
            '0.FT.AS': {'nodes': {'entry': {'type': 'entry', 'x': 1, 'y': 2},
                                  'n1': {'type': 'node', 'x': 5, 'y': 6,
                                         'title': 'T', 'lines': [{'text': 'hi'}]}},
                        'edges': [['entry', 0, 'n1']]},
            '0.QC': {'nodes': {'entry': {'type': 'entry', 'x': 1, 'y': 2}},
                     'edges': []}}}
        q = Quest.from_dict(d)
        g = q.graph
        self.assertIn(entry_id('first'), g['nodes'])
        self.assertIn(entry_id('closed'), g['nodes'])
        self.assertIn(entry_id('running'), g['nodes'])
        nodes = [n for n in g['nodes'].values() if n['type'] == 'npc']
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]['state'], 'first')
        self.assertEqual(nodes[0]['lines'][0]['text'], 'hi')
        self.assertEqual(len(g['edges']), 1)
        self.assertEqual(g['edges'][0][0], entry_id('first'))
        self.assertNotIn('tabs', q.to_dict())

    def test_player_node(self):
        p = model.make_node('player', 0, 0, 'first')
        self.assertEqual(p['speaker'], PLAYER)
        self.assertEqual(p['kind'], 'answer')


if __name__ == '__main__':
    unittest.main()
