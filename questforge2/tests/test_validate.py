import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import model, validate  # noqa: E402
from questforge2.model import Project, entry_id  # noqa: E402
from questforge2.tests.test_quest_export import _Index, make_quest  # noqa: E402


def keys(items):
    return ' '.join(m for m, _ in items)


class Rules(unittest.TestCase):
    def setUp(self):
        self.idx = _Index()
        self.idx.cues = {'CUE_0123_0001': [123, 'Hallo Held.', 'translateDQ_4']}
        self.idx.locations = {'LOC_X': {'type': 10, 'radius': 0}}
        self.idx.quests['5'] = {'source': 'retail', 'giver': 3,
                                'fc': ['TALK', 'NPC_9']}

    def test_clean_quest(self):
        E, W = validate.validate_quest(make_quest(), self.idx)
        self.assertEqual(E, [])
        self.assertEqual(W, [])

    def test_errors_with_targets(self):
        q = make_quest()
        g = q.graph
        q.speakers.append({'id': 3, 'name': 'dup', 'lector': 1, 'new': True})
        q.speakers[-1]['id'] = 3
        q.speakers = [dict(q.speakers[0], new=True)]
        g['nodes']['bad'] = {'type': 'action', 'kind': 'ACTION',
                             'verb': 'FLY_AWAY', 'args': {},
                             'attached_to': None, 'x': 0, 'y': 0}
        c = [nid for nid, n in g['nodes'].items()
             if n.get('cond') == 'after'][0]
        g['nodes'][c]['quest'] = 9999
        n1 = model.edge_from(g, entry_id('first'), 0)[2]
        g['nodes'][n1]['lines'][0]['text'] = 'a\rb'
        E, W = validate.validate_quest(q, self.idx)
        k = keys(E)
        self.assertIn('val.speaker.taken', k)
        self.assertIn('val.opcode', k)
        self.assertIn('val.after.quest', k)
        self.assertIn('val.cr', k)
        self.assertIn(('val.after.quest ' + str({'id': 9999}), c), E)
        self.assertTrue(any(x == 'bad' for m, x in E if 'val.opcode' in m))
        self.assertTrue(any(x == n1 for m, x in E if 'val.cr' in m))

    def test_warnings(self):
        q = make_quest()
        g = q.graph
        # running and closed levels empty
        for st in ('running', 'closed'):
            model.disconnect(g, entry_id(st), 0)
        # question with one open line
        p = model.add_node(g, model.make_node('player', 0, 0, 'first'))
        g['nodes'][p]['kind'] = 'question'
        g['nodes'][p]['lines'] = [dict(model.new_line(), text='a'),
                                  dict(model.new_line(), text='b')]
        n1 = model.edge_from(g, entry_id('first'), 0)[2]
        model.connect(g, p, 0, n1)
        # cue mismatch
        g['nodes'][n1]['lines'][0]['cue'] = 'CUE_0123_0001'
        # NPC_GO on created NPC, SHOW_LOCATION on type 10 and not TAKE
        q.actions.append({'kind': 'ACTION', 'verb': 'NPC_CREATE',
                          'args': {'npc': 7}, 'when': 'ENABLE'})
        q.actions.append({'kind': 'ACTION', 'verb': 'NPC_GO',
                          'args': {'npc': 7, 'marker': 1}, 'when': 'SOLVE'})
        q.actions.append({'kind': 'ACTION', 'verb': 'SHOW_LOCATION',
                          'args': {'location': 'LOC_X'}, 'when': 'SOLVE'})
        E, W = validate.validate_quest(q, self.idx)
        self.assertEqual(E, [])
        k = keys(W)
        for key in ('warn.level.empty', 'warn.question.open', 'warn.cue.text',
                    'warn.npcgo.created', 'warn.showloc',
                    'warn.location.type10'):
            self.assertIn(key, k)
        self.assertTrue(any(x == 'qaction:1' for m, x in W
                            if 'warn.npcgo' in m))

    def test_talk_rules(self):
        q = make_quest()
        model.set_task(q.graph, 'TALK')
        q.task()['args']['npc'] = 9
        c = [n for n in q.conditions_list() if n['cond'] == 'after'][0]
        c['quest'] = 5
        E, W = validate.validate_quest(q, self.idx)
        self.assertIn('warn.talk.twice', keys(W))
        q.task()['args']['npc'] = 3
        E, W = validate.validate_quest(q, self.idx)
        self.assertIn('warn.talk.giver', keys(W))
        model.set_task(q.graph, 'KILL')
        q.task()['args']['npc'] = 3
        E, W = validate.validate_quest(q, self.idx)
        self.assertIn('warn.kill.questnpc', keys(W))

    def test_project(self):
        p = Project('x')
        a, b = make_quest(), make_quest()
        p.quests += [a, b]
        errors, warnings = validate.validate_project(p, self.idx)
        self.assertTrue(any('val.id.twice' in m for _, m, _ in errors))


if __name__ == '__main__':
    unittest.main()
