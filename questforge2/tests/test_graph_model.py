import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import model  # noqa: E402
from questforge2.model import Quest, ENTRY_ID  # noqa: E402


def _chain(tab, n):
    """entry -> n1 -> n2 ... ; returns ids"""
    ids = []
    prev = ENTRY_ID
    for i in range(n):
        nid = model.add_node(tab, model.make_node('node', 0, 0, f'N{i}'))
        model.connect(tab, prev, 0, nid)
        ids.append(nid)
        prev = nid
    return ids


class GraphOps(unittest.TestCase):
    def test_entry_exists_and_survives(self):
        q = Quest(390)
        for tab in q.tabs.values():
            self.assertIn(ENTRY_ID, tab['nodes'])
        tab = q.tabs['0.FT.AS']
        model.remove_nodes(tab, [ENTRY_ID])
        self.assertIn(ENTRY_ID, tab['nodes'])
        self.assertEqual(q.node_count(), 0)

    def test_connect_rules(self):
        tab = model.new_tab()
        a = model.add_node(tab, model.make_node('node', 0, 0))
        b = model.add_node(tab, model.make_node('node', 0, 0))
        c = model.add_node(tab, model.make_node('comment', 0, 0))
        self.assertTrue(model.connect(tab, ENTRY_ID, 0, a))
        self.assertTrue(model.connect(tab, a, 0, b))
        self.assertFalse(model.connect(tab, a, 1, b))      # only one line
        self.assertFalse(model.connect(tab, a, 0, a))
        self.assertFalse(model.connect(tab, a, 0, c))       # comment
        self.assertFalse(model.connect(tab, c, 0, a))
        self.assertFalse(model.connect(tab, b, 0, ENTRY_ID))
        # replacing the edge of a port
        self.assertTrue(model.connect(tab, ENTRY_ID, 0, b))
        self.assertEqual(model.edge_from(tab, ENTRY_ID, 0), [ENTRY_ID, 0, b])
        self.assertEqual(len(tab['edges']), 2)
        # several lines -> several ports
        tab['nodes'][a]['lines'].append({'text': 'x'})
        self.assertTrue(model.connect(tab, a, 1, b))
        self.assertEqual(model.successors(tab, a), [b, b])

    def test_remove_and_disconnect(self):
        tab = model.new_tab()
        ids = _chain(tab, 3)
        cid = model.add_node(tab, model.make_node('comment', 0, 0))
        tab['nodes'][cid]['attached_to'] = ids[1]
        model.remove_nodes(tab, [ids[1]])
        self.assertNotIn(ids[1], tab['nodes'])
        self.assertEqual(len(tab['edges']), 1)
        self.assertIsNone(tab['nodes'][cid]['attached_to'])
        self.assertEqual(model.disconnect(tab, ENTRY_ID, 0), 1)
        self.assertEqual(tab['edges'], [])

    def test_copy_paste_duplicate(self):
        tab = model.new_tab()
        ids = _chain(tab, 3)
        clip = model.copy_nodes(tab, ids[:2] + [ENTRY_ID])
        self.assertEqual(set(clip['nodes']), set(ids[:2]))
        self.assertEqual(len(clip['edges']), 1)           # n1 -> n2 only
        new = model.paste_nodes(tab, clip)
        self.assertEqual(len(new), 2)
        self.assertEqual(len(tab['nodes']), 6)
        self.assertEqual(len(tab['edges']), 4)
        self.assertEqual(tab['nodes'][new[0]]['x'], 30)
        dup = model.duplicate_nodes(tab, [ids[2]])
        self.assertEqual(tab['nodes'][dup[0]]['title'], 'N2')
        self.assertEqual(len(tab['edges']), 4)

    def test_auto_layout(self):
        tab = model.new_tab()
        a = model.add_node(tab, model.make_node('node', 0, 0, 'A'))
        b = model.add_node(tab, model.make_node('node', 0, 0, 'B'))
        c = model.add_node(tab, model.make_node('node', 0, 0, 'C'))
        loose = model.add_node(tab, model.make_node('node', 0, 0, 'L'))
        tab['nodes'][a]['lines'].append({'text': 'second'})
        model.connect(tab, ENTRY_ID, 0, a)
        model.connect(tab, a, 0, b)
        model.connect(tab, a, 1, c)
        order = model.auto_layout(tab)
        self.assertEqual(order, [ENTRY_ID, a, b, c])
        n = tab['nodes']
        self.assertLess(n[ENTRY_ID]['x'], n[a]['x'])
        self.assertLess(n[a]['x'], n[b]['x'])
        self.assertEqual(n[b]['x'], n[c]['x'])
        self.assertLess(n[b]['y'], n[c]['y'])
        self.assertGreater(n[loose]['y'], n[c]['y'])

    def test_undo_stack(self):
        q = Quest(390)
        u = model.UndoStack(limit=3)
        tab = q.tabs['0.FT.AS']
        u.push(q.tabs, 'add')
        a = model.add_node(tab, model.make_node('node', 1, 2))
        self.assertTrue(u.can_undo())
        st = u.undo(q.tabs)
        self.assertNotIn(a, st['0.FT.AS']['nodes'])
        self.assertTrue(u.can_redo())
        st2 = u.redo(st)
        self.assertIn(a, st2['0.FT.AS']['nodes'])
        for i in range(5):
            u.push(q.tabs, str(i))
        self.assertEqual(len(u._undo), 3)
        self.assertFalse(u.can_redo())

    def test_node_size(self):
        n = model.make_node('node', 0, 0)
        self.assertEqual(model.node_size(n)[1],
                         model.HEADER_H + model.LINE_H + model.NODE_PAD)
        n['lines'].append({'text': ''})
        self.assertEqual(model.out_port_count(n), 2)
        self.assertEqual(model.node_size(model.make_node('comment', 0, 0)),
                         (200, 80))


if __name__ == '__main__':
    unittest.main()
