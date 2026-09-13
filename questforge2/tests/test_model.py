import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2.model import Project, Quest, ModelError, FORMAT  # noqa: E402


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


class ModelRoundTrip(unittest.TestCase):
    def _sample(self):
        p = Project('Testmod')
        p.target_archive = 'Testmod.wd'
        q = Quest(385, 'Der Schutzgelderpresser')
        q.group = 3
        q.journal = {'take': 'Tago bittet um Hilfe.', 'solve': 'Erledigt.',
                     'close': 'Belohnung erhalten.'}
        q.giver = 3
        q.speakers = [{'id': 3, 'name': 'Tago', 'lector': 4}]
        q.tabs['0.FT.AS']['nodes']['n1'] = {
            'type': 'npc', 'speaker': 3, 'text': 'Hallo!', 'x': 10, 'y': 20}
        q.tabs['0.FT.AS']['edges'].append(['entry', 0, 'n1'])
        q.task = {'type': 'BRING_GOLD', 'amount': 100}
        p.quests.append(q)
        return p

    def test_json_roundtrip_is_stable(self):
        p = self._sample()
        text = p.to_json()
        p2 = Project.from_json(text)
        self.assertEqual(p2.to_json(), text)
        self.assertEqual(p2.quests[0].id, 385)
        self.assertEqual(p2.quests[0].tabs['0.FT.AS']['nodes']['n1']['text'],
                         'Hallo!')
        self.assertEqual(p2.quests[0].node_count(), 1)
        self.assertTrue(text.endswith('\n'))
        self.assertIn('"format": %d' % FORMAT, text)

    def test_save_and_load_file(self):
        p = self._sample()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'test.tw1proj')
            p.save(path)
            self.assertFalse(p.dirty)
            raw = _read(path)
            self.assertNotIn(b'\r', raw)
            p2 = Project.load(path)
            self.assertEqual(p2.path, path)
            self.assertEqual(p2.to_json(), p.to_json())
            p2.save()
            self.assertEqual(_read(path), raw)

    def test_unknown_keys_survive(self):
        p = self._sample()
        d = p.to_dict()
        d['future_field'] = {'a': 1}
        d['quests'][0]['future_quest_field'] = [1, 2]
        p2 = Project.from_dict(d)
        d2 = p2.to_dict()
        self.assertEqual(d2['future_field'], {'a': 1})
        self.assertEqual(d2['quests'][0]['future_quest_field'], [1, 2])

    def test_rejects_newer_format(self):
        with self.assertRaises(ModelError):
            Project.from_dict({'format': FORMAT + 1})
        with self.assertRaises(ModelError):
            Project.from_json('not json')

    def test_missing_tabs_are_added(self):
        q = Quest.from_dict({'id': 390, 'tabs': {}})
        self.assertIn('0.QC', q.tabs)
        self.assertEqual(q.node_count(), 0)


if __name__ == '__main__':
    unittest.main()
