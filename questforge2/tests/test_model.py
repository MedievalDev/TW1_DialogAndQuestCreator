import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import model  # noqa: E402
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
        q.speakers = [{'id': 3, 'name': 'Tago', 'lector': 4, 'tile': 'F5',
                       'new': False}]
        n = model.make_node('npc', 10, 20, 'first', 3)
        n['lines'][0]['text'] = 'Hallo!'
        q.graph['nodes']['n1'] = n
        q.graph['edges'].append([model.entry_id('first'), 0, 'n1'])
        q.task = {'type': 'BRING_GOLD', 'amount': 100}
        p.quests.append(q)
        return p

    def test_json_roundtrip_is_stable(self):
        p = self._sample()
        text = p.to_json()
        p2 = Project.from_json(text)
        self.assertEqual(p2.to_json(), text)
        self.assertEqual(p2.quests[0].id, 385)
        self.assertEqual(
            p2.quests[0].graph['nodes']['n1']['lines'][0]['text'], 'Hallo!')
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

    def test_missing_entries_are_added(self):
        q = Quest.from_dict({'id': 390, 'graph': {'nodes': {}, 'edges': []}})
        self.assertIn(model.entry_id('closed'), q.graph['nodes'])
        self.assertEqual(q.node_count(), 0)


class Guidebook(unittest.TestCase):
    """Help > Guide (2.9.0): chapters in both languages, tables from the
    same source as the pickers, every "?" lands on a chapter."""

    def test_chapters(self):
        from questforge2 import guidebook, i18n
        ids = {c for c, _t, _f in guidebook.CHAPTERS}
        for lang in ('de', 'en'):
            i18n.set_lang(lang)
            for cid, titles, fn in guidebook.CHAPTERS:
                text = fn()
                self.assertTrue(text.startswith('# '), cid)
                self.assertNotIn('{', text.replace('{n}', ''), cid)
        i18n.set_lang('de')
        self.assertTrue(set(guidebook.HELP_CHAPTER.values()) <= ids)
        ref = guidebook.ch_reference()
        for name in model.NUMBER_LISTS:
            self.assertIn(name, ref)
        self.assertIn('ungeprueft', ref)
        tasks = guidebook.ch_tasks()
        for fc in model.FC_SPECS:
            self.assertIn(f'FC {fc}', tasks)
        self.assertIn('AOQ ENABLE', guidebook.ch_links())


class Colours(unittest.TestCase):
    """One colour per journal group in the timeline (2.7.0)."""

    def test_group_colour(self):
        from questforge2 import theme
        self.assertEqual(theme.group_color(3), theme.group_color(3))
        self.assertNotEqual(theme.group_color(3), theme.group_color(4))
        self.assertTrue(theme.group_color(999).startswith('#'))
        self.assertEqual(theme.mix('#000000', '#ffffff', 0.5), '#808080')
        self.assertEqual(theme.mix('#d2a044', '#000000', 1.0), '#d2a044')
        self.assertEqual(theme.mix('#d2a044', '#000000', 0.0), '#000000')


class Parties(unittest.TestCase):
    """Party numbers of the SDK in the picker (Discord question, 2.5.1)."""

    def test_labels_and_parsing(self):
        def t(key):
            return {'party.20': 'Bandits', 'party.21': 'Undead'}.get(key, key)
        self.assertEqual(model.party_label(20, t), '20  Bandits')
        self.assertEqual(model.party_label(99, t), '99')     # unknown number
        self.assertEqual(model.parse_party('20  Bandits'), 20)
        self.assertEqual(model.parse_party(' 25 '), 25)
        self.assertEqual(model.parse_party('(null)'), '(null)')
        self.assertEqual(model.PARTIES[0], 18)
        self.assertEqual(model.PARTIES[-1], 43)
        self.assertTrue(set(model.PARTY_FIGHT) < set(model.PARTIES))

    def test_guilds(self):
        def t(key):
            return {'guild.202': 'Warriors'}.get(key, key)
        self.assertEqual(model.guild_label('202', t), '202  Warriors')
        self.assertEqual(model.guild_label('(null)', t), '(null)')
        self.assertEqual(model.guild_label('', t), '(null)')
        self.assertEqual(model.guild_label('999', t), '999')
        self.assertEqual(model.parse_guild('204  Thieves'), '204')
        self.assertEqual(model.parse_guild('(null)'), '(null)')
        self.assertIn(201, model.GUILDS)
        self.assertNotIn(206, model.GUILDS)       # unused in the SDK


class ActionMenu(unittest.TestCase):
    """"+ New action": rewards as their own group on top, a hover text with
    input examples on every entry (Marco 2026-09-21, 4.3.1)."""

    def test_groups(self):
        self.assertEqual({k for k, _v in model.ACTION_REWARDS}, {'REWARD'})
        self.assertEqual(len(model.ACTION_REWARDS), 5)       # GLD EXP ITM REP SKL
        self.assertFalse([k for k in model.ACTION_MAIN + model.ACTION_MORE
                          if k[0] == 'REWARD'])
        # every opcode once, rewards first
        self.assertEqual(sorted(model.ACTION_ALL), sorted(model.ACTION_SPECS))
        self.assertEqual(len(set(model.ACTION_ALL)), len(model.ACTION_ALL))
        self.assertEqual(model.ACTION_ALL[:5], model.ACTION_REWARDS)

    def test_tips_in_both_languages(self):
        from questforge2 import i18n
        old = i18n.get_lang()
        try:
            for lang in ('de', 'en'):
                i18n.set_lang(lang)
                for k, v in model.ACTION_ALL:
                    tip = model.action_tip(k, v, i18n.t)
                    self.assertTrue(tip.strip(), (lang, k, v))
                    for raw in ('tip.op.', 'field.', 'example.'):
                        self.assertNotIn(raw, tip, (lang, k, v))
                # the rewards explain the words of the amount
                gold = model.action_tip('REWARD', 'GLD', i18n.t)
                for word in ('SMALL', 'MEDIUM', 'HIGH', '500'):
                    self.assertIn(word, gold)
                self.assertIn('-1', model.action_tip('REWARD', 'ITM', i18n.t))
                # the other actions list their fields with an example
                tp = model.action_tip('ACTION', 'NPC_TELEPORT', i18n.t)
                self.assertEqual(len(tp.splitlines()), 1 + 4)
                self.assertIn('NPC_3', tp)
        finally:
            i18n.set_lang(old)


if __name__ == '__main__':
    unittest.main()
