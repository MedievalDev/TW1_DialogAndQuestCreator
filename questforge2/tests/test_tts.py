"""Placeholder voices (4.5.0): which lines get one, the mark, SSML."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import model, tts  # noqa: E402

VOICES = [
    {'id': 'onecore:Microsoft Katja', 'engine': 'onecore',
     'name': 'Microsoft Katja', 'lang': 'de-DE', 'gender': 'female'},
    {'id': 'onecore:Microsoft Stefan', 'engine': 'onecore',
     'name': 'Microsoft Stefan', 'lang': 'de-DE', 'gender': 'male'},
    {'id': 'sapi:Microsoft Zira Desktop', 'engine': 'sapi',
     'name': 'Microsoft Zira Desktop', 'lang': 'en-US', 'gender': 'female'},
    {'id': 'sapi:Microsoft David Desktop', 'engine': 'sapi',
     'name': 'Microsoft David Desktop', 'lang': 'en-US', 'gender': 'male'},
]


def quest():
    q = model.Quest(390, 'T')
    q.add_speaker({'id': 7, 'name': 'Tago', 'lector': 123, 'tile': 'E1',
                   'new': False})
    nodes = q.graph['nodes']

    def npc(nid, *texts, **extra):
        n = model.make_node('npc', 0, 0, speaker=7)
        n['lines'] = [dict(model.new_line(), text=tx, **extra)
                      for tx in texts]
        nodes[nid] = n
        return n
    npc('a', 'Hallo Fremder.')                         # new
    npc('b', 'Schon vertont.', cue='CUE_0123_0001')    # original actor
    npc('c', 'Eigene Aufnahme.', voice='own.wav')      # own take
    npc('d', '   ')                                    # nothing to say
    ph = npc('e', 'Neuer Text.', voice='ph.wav')       # outdated placeholder
    tts.mark(ph['lines'][0], 'onecore:Microsoft Stefan', -10, 0)
    ph['lines'][0]['text'] = 'Ganz neuer Text.'
    ok = npc('f', 'Gleicher Text.', voice='ok.wav')    # current placeholder
    tts.mark(ok['lines'][0], 'onecore:Microsoft Stefan', 0, 0)
    gone = npc('g', 'Datei fehlt.', voice='gone.wav')  # placeholder, no file
    tts.mark(gone['lines'][0], 'onecore:Microsoft Stefan', 0, 0)
    hero = model.make_node('player', 0, 0)
    hero['lines'][0]['text'] = 'Ich helfe dir.'
    nodes['h'] = hero
    choice = model.make_node('player', 0, 0)
    choice['kind'] = 'question'
    choice['lines'] = [dict(model.new_line(), text='Ja'),
                       dict(model.new_line(), text='Nein')]
    nodes['q'] = choice
    return q


def exists(line):
    return line.get('voice') in ('own.wav', 'ph.wav', 'ok.wav')


class Todo(unittest.TestCase):
    def picked(self, **kw):
        return sorted((nid, reason, key) for _q, nid, _i, _ln, key, reason
                      in tts.todo([quest()], exists, **kw))

    def test_default(self):
        self.assertEqual(self.picked(), [
            ('a', 'new', '7'), ('e', 'outdated', '7'), ('g', 'new', '7'),
            ('h', 'new', tts.HERO)])

    def test_keep_outdated(self):
        self.assertNotIn(('e', 'outdated', '7'),
                         self.picked(renew_outdated=False))

    def test_renew_all(self):
        got = self.picked(renew_all=True)
        self.assertIn(('f', 'renew', '7'), got)
        self.assertIn(('e', 'outdated', '7'), got)
        # never an own take, an original cue or a choice of the hero
        self.assertFalse({n for n, _r, _k in got} & {'b', 'c', 'd', 'q'})

    def test_placeholders_listed(self):
        got = sorted(nid for _q, nid, _i, _ln in tts.placeholders([quest()]))
        self.assertEqual(got, ['e', 'f', 'g'])


class Mark(unittest.TestCase):
    def test_mark_and_outdated(self):
        ln = dict(model.new_line(), text='Sei  gegruesst,\nFremder.',
                  voice='x.wav')
        tts.mark(ln, 'onecore:Microsoft Stefan', -10, 5)
        self.assertTrue(tts.is_placeholder(ln))
        self.assertFalse(tts.outdated(ln))
        ln['text'] = 'sei gegruesst, fremder.'      # case and spaces only
        self.assertFalse(tts.outdated(ln))
        ln['text'] = 'Sei gegruesst, Wanderer.'
        self.assertTrue(tts.outdated(ln))
        tts.unmark(ln)
        self.assertFalse(tts.is_placeholder(ln))

    def test_mark_without_take_is_no_placeholder(self):
        ln = dict(model.new_line(), text='x')
        tts.mark(ln, 'v', 0, 0)
        self.assertFalse(tts.is_placeholder(ln))


class Settings(unittest.TestCase):
    def test_pick_language_and_gender(self):
        self.assertEqual(tts.pick(VOICES, 'de')['name'], 'Microsoft Stefan')
        self.assertEqual(tts.pick(VOICES, 'en')['name'],
                         'Microsoft David Desktop')
        self.assertEqual(tts.pick(VOICES, 'fr')['name'], 'Microsoft Stefan')
        self.assertIsNone(tts.pick([], 'de'))

    def test_defaults_step_through_pitches(self):
        got = tts.defaults(VOICES, 'de', [tts.HERO, '7', '8'], {})
        self.assertEqual(got[tts.HERO]['pitch'], 0)
        self.assertEqual([got['7']['pitch'], got['8']['pitch']],
                         list(tts.PITCHES[:2]))
        # speakers already set are kept and counted
        more = tts.defaults(VOICES, 'de', ['7', '9'], {'7': got['7']})
        self.assertEqual(list(more), ['9'])
        self.assertEqual(more['9']['pitch'], tts.PITCHES[1])

    def test_ssml(self):
        s = tts.ssml('A < B & "C"\n  d', 'de-DE', -10, 5)
        self.assertIn("xml:lang='de-DE'", s)
        self.assertIn("<prosody pitch='-10%' rate='+5%'>", s)
        self.assertIn('A &lt; B &amp; &quot;C&quot; d', s)
        self.assertNotIn('prosody', tts.ssml('x', 'en-US'))


class Check(unittest.TestCase):
    """The check before the export (4.5.0)."""

    def run_check(self, q):
        import tempfile
        from questforge2 import validate
        tmp = tempfile.mkdtemp()
        p = model.Project('T')
        p.path = os.path.join(tmp, 'T.tw1proj')
        os.makedirs(os.path.join(tmp, 'T_voice'))
        for name in ('own.wav', 'ph.wav', 'ok.wav'):
            open(os.path.join(tmp, 'T_voice', name), 'wb').close()
        p.quests.append(q)
        _E, W = validate.validate_quest(q, None, p, 'T.wd',
                                        lambda key, **fmt: key)
        return [(str(m), x) for m, x in W if str(m).startswith(
            ('warn.voice', 'warn.teleport'))]

    def test_voices(self):
        got = self.run_check(quest())
        self.assertIn(('warn.voice.missing', 'g'), got)
        self.assertIn(('warn.voice.outdated', 'e'), got)
        self.assertIn(('warn.voice.placeholder', 'e'), got)
        # a (NPC) and h (the hero's answer) are silent; the choice q is not
        # counted, b speaks with its original cue
        self.assertIn(('warn.voice.silent', 'a'), got)

    def test_silent_alone_is_fine(self):
        q = model.Quest(391, 'T')
        n = model.make_node('npc', 0, 0, speaker=7)
        n['lines'][0]['text'] = 'Stumm.'
        q.graph['nodes']['a'] = n
        self.assertEqual(self.run_check(q), [])

    def test_teleport_on_solve(self):
        q = model.Quest(392, 'T')
        q.actions.append({'kind': 'ACTION', 'verb': 'HERO_TELEPORT_DELAYED',
                          'when': 'SOLVE', 'args': {'delay': 1, 'marker': 1,
                                                    'tile': 'E2', 'angle': 0}})
        self.assertIn('warn.teleport.solve', [m for m, _x in
                                              self.run_check(q)])
        q.actions[0]['when'] = 'CLOSE'
        self.assertNotIn('warn.teleport.solve', [m for m, _x in
                                                 self.run_check(q)])
        q.actions[0]['when'] = 'SOLVE'
        q.map_sign = 'AUTO_CLOSE_ON_SOLVE'
        self.assertNotIn('warn.teleport.solve', [m for m, _x in
                                                 self.run_check(q)])


if __name__ == '__main__':
    unittest.main()
