"""Own sound files and the voices in the game's sound bank (4.4.0)."""

import array
import math
import os
import struct
import sys
import tempfile
import unittest
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import adpcm, audioin, data, export, model, voicebuild  # noqa


def tone(seconds, rate=44100, freq=440.0, amp=8000, channels=1):
    out = array.array('h')
    for i in range(int(seconds * rate)):
        v = int(amp * math.sin(2 * math.pi * freq * i / rate))
        out.extend([v] * channels)
    return out.tobytes()


def write_wav(path, pcm, rate=44100, channels=1, width=2):
    with wave.open(path, 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)


class Adpcm(unittest.TestCase):
    def test_round_trip(self):
        pcm = tone(0.5)
        raw, blocks = adpcm.encode(pcm)
        self.assertEqual(len(raw), blocks * adpcm.BLOCK)
        self.assertEqual(blocks, -(-len(pcm) // 2 // adpcm.SAMPLES))
        back = array.array('h', adpcm.decode(raw))[:len(pcm) // 2]
        src = array.array('h', pcm)
        noise = sum((a - b) ** 2 for a, b in zip(src, back))
        signal = sum(a * a for a in src)
        self.assertGreater(10 * math.log10(signal / noise), 30)

    def test_format_word(self):
        # ADPCM, mono, 44100 Hz, alignment field 48 (as the retail entries)
        w = adpcm.format_word()
        self.assertEqual(w & 3, 2)
        self.assertEqual((w >> 2) & 7, 1)
        self.assertEqual((w >> 5) & 0x3FFFF, 44100)
        self.assertEqual((w >> 23) & 0xFF, 48)


class Import(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_fallback_wav(self):
        p = os.path.join(self.tmp.name, 'st.wav')
        write_wav(p, tone(1.0, rate=22050, channels=2), rate=22050,
                  channels=2)
        pcm = audioin.wav_pcm(p)
        self.assertAlmostEqual(len(pcm) / 2 / audioin.RATE, 1.0, places=2)

    def test_media_foundation(self):
        p = os.path.join(self.tmp.name, 'st.wav')
        write_wav(p, tone(1.5, rate=22050, channels=2), rate=22050,
                  channels=2)
        try:
            pcm = audioin.media_foundation_pcm(p)
        except audioin.AudioError as e:
            self.skipTest(f'no Media Foundation: {e}')
        self.assertAlmostEqual(len(pcm) / 2 / audioin.RATE, 1.5, places=2)

    def test_level(self):
        quiet = tone(0.5, amp=1500)
        out, note = audioin.level(quiet)
        s = array.array('h', out)
        rms = math.sqrt(sum(v * v for v in s) / len(s)) / 32768
        self.assertAlmostEqual(rms, audioin.TARGET_RMS, delta=0.03)
        loud, note = audioin.level(tone(0.5, amp=32000))
        self.assertLessEqual(max(abs(v) for v in array.array('h', loud)),
                             int(audioin.CAP * 32767) + 1)

    def test_too_short(self):
        p = os.path.join(self.tmp.name, 'short.wav')
        write_wav(p, tone(0.05))
        with self.assertRaises(audioin.AudioError):
            audioin.load(p)


def _game():
    g = data.find_game_dir()
    return g if g and voicebuild.available(g) else None


@unittest.skipIf(_game() is None, 'needs the game with its XACT banks')
class Bank(unittest.TestCase):
    """Against copies of the game's bank files; the wave bank keeps its real
    front part (header, metadata, gap) with a short wave region."""

    def setUp(self):
        import tw1_xwb
        self.tmp = tempfile.TemporaryDirectory()
        self.game = self.tmp.name
        src, dst = voicebuild.xact_dir(_game()), voicebuild.xact_dir(self.game)
        os.makedirs(dst)
        for n in voicebuild.SMALL:
            with open(os.path.join(src, n), 'rb') as f, \
                    open(os.path.join(dst, n), 'wb') as g:
                g.write(f.read())
        w = tw1_xwb.Xwb(os.path.join(src, voicebuild.XWB))
        wo = w.regionen['ENTRYWAVEDATA'][0]
        with open(os.path.join(src, voicebuild.XWB), 'rb') as f:
            head = bytearray(f.read(wo))
        struct.pack_into('<I', head, 12 + 4 * 8 + 4, 4096)
        with open(os.path.join(dst, voicebuild.XWB), 'wb') as g:
            g.write(head + b'\0' * 4096)
        self.orig = {n: self.read(n) for n in voicebuild.SMALL
                     + (voicebuild.XWB,)}
        self.takes = os.path.join(self.tmp.name, 'takes')
        os.makedirs(self.takes)
        self.lines = []
        for i, (secs, lec) in enumerate(((0.6, 1), (1.2, 25))):
            p = os.path.join(self.takes, f'Q385_n{i}_0.wav')
            write_wav(p, tone(secs, freq=300 + 100 * i))
            self.lines.append({'take': os.path.basename(p), 'path': p,
                               'lector': lec, 'quest': 385})

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, name):
        with open(os.path.join(voicebuild.xact_dir(self.game), name),
                  'rb') as f:
            return f.read()

    def banks(self):
        import tw1_xap
        import tw1_xsb
        import tw1_xwb
        d = voicebuild.xact_dir(self.game)
        return (tw1_xsb.Xsb(self.read('Sounds.xsb')),
                tw1_xap.Xap(self.read('sounds.xap.cued')).dauern(),
                tw1_xwb.Xwb(os.path.join(d, voicebuild.XWB)))

    def test_build_rebuild_remove(self):
        import tw1_xsb
        base = tw1_xsb.Xsb(self.orig['Sounds.xsb'])
        top = max(int(n[9:]) for n in base.namen
                  if n.startswith('CUE_0001_'))
        import tw1_xwb
        count0 = tw1_xwb.Xwb(os.path.join(voicebuild.xact_dir(self.game),
                                          voicebuild.XWB)).count
        logs = []
        cues = voicebuild.build(self.game, 'Test.wd', self.lines, logs.append)
        self.assertEqual(cues['Q385_n0_0.wav'], f'CUE_0001_{top + 1:04d}')
        self.assertTrue(cues['Q385_n1_0.wav'].startswith('CUE_0025_'))
        x, dur, w = self.banks()
        self.assertEqual(w.count, count0 + 2)
        for take, cue in cues.items():
            bank, idx = x.wave_of(cue)
            self.assertEqual(bank, 'UnitTalk')
            self.assertGreaterEqual(idx, w.count - 2)
        self.assertAlmostEqual(dur[cues['Q385_n1_0.wav']], 1.2, delta=0.01)
        self.assertEqual(w.pruefen(), [])
        size1 = len(self.read(voicebuild.XWB))
        # the same again: base restored and the lines back in, same names
        cues2 = voicebuild.build(self.game, 'Test.wd', self.lines,
                                 logs.append)
        self.assertEqual(cues2, cues)
        self.assertEqual(len(self.read(voicebuild.XWB)), size1)
        self.assertIn(('voice_restored',), logs)
        # a second mod: both in; the first goes, the second keeps its name
        other = [dict(self.lines[0], take='Q390_n0_0.wav', quest=390)]
        cues3 = voicebuild.build(self.game, 'Other.wd', other, logs.append)
        self.assertEqual(voicebuild.status(self.game)['sets'],
                         {'Test.wd': 2, 'Other.wd': 1})
        voicebuild.remove(self.game, 'Test.wd', logs.append)
        x, dur, w = self.banks()
        self.assertIsNotNone(x.wave_of(cues3['Q390_n0_0.wav']))
        self.assertIsNone(x.wave_of(cues['Q385_n1_0.wav']))
        # all out: every file exactly as before
        voicebuild.remove(self.game, None, logs.append)
        for n, blob in self.orig.items():
            self.assertEqual(self.read(n), blob, n)

    def test_partial_export_keeps_other_quests(self):
        quiet = lambda m: None                             # noqa: E731
        voicebuild.build(self.game, 'Test.wd', self.lines, quiet)
        extra = dict(self.lines[0], take='Q386_n0_0.wav', quest=386)
        cues = voicebuild.build(self.game, 'Test.wd', [extra], quiet,
                                partial_quests={386})
        self.assertEqual(set(cues), {'Q385_n0_0.wav', 'Q385_n1_0.wav',
                                     'Q386_n0_0.wav'})

    def test_changed_behind_our_back(self):
        cues = voicebuild.build(self.game, 'Test.wd', self.lines,
                                lambda m: None)
        # a campaign installer puts its own bank back
        with open(os.path.join(voicebuild.xact_dir(self.game), 'Sounds.xsb'),
                  'wb') as f:
            f.write(self.orig['Sounds.xsb'])
        with self.assertRaises(voicebuild.VoiceError):
            voicebuild.remove(self.game)
        logs = []
        again = voicebuild.build(self.game, 'Test.wd', self.lines, logs.append)
        self.assertIn(('voice_changed',), logs)
        x, _dur, _w = self.banks()
        for cue in again.values():
            self.assertIsNotNone(x.wave_of(cue))
        self.assertEqual(set(again), set(cues))

    def test_grow_gap(self):
        import tw1_xwb
        p = os.path.join(voicebuild.xact_dir(self.game), voicebuild.XWB)
        before = tw1_xwb.Xwb(p)
        voicebuild.grow_gap(p, 300, lambda m: None)
        after = tw1_xwb.Xwb(p)
        self.assertEqual(after.pruefen(), [])
        self.assertEqual(after.count, before.count)
        self.assertGreaterEqual(after.platz(), 300)
        mo, ml = before.regionen['ENTRYMETADATA']
        with open(p, 'rb') as f:
            f.seek(mo)
            self.assertEqual(f.read(ml), self.orig[voicebuild.XWB][mo:mo + ml])


class Project(unittest.TestCase):
    def quest(self):
        tpls = {tp['name']: tp for tp in data.builtin_templates('dialog')}
        q = model.Quest(390, 'Leer')
        q.add_speaker({'id': 3, 'name': 'Tago', 'lector': 123, 'tile': 'E1',
                       'new': False})
        model.add_default_conditions(q)
        model.insert_dialog(q, tpls['dialog_standard_giver']['data']['graph'],
                            3)
        return q

    def test_lines_of_the_project(self):
        q = self.quest()
        nodes = q.graph['nodes']
        npc = next(n for n in nodes.values() if n['type'] == 'npc')
        npc['lines'][0]['voice'] = 'Q390_a_0.wav'
        hero = next((n for n in nodes.values() if n['type'] == 'player'),
                    None)
        if hero:
            hero['lines'][0]['voice'] = 'Q390_b_0.wav'
        p = model.Project('T')
        p.quests.append(q)
        tmp = tempfile.mkdtemp()
        write_wav(os.path.join(tmp, 'Q390_a_0.wav'), tone(0.3))
        write_wav(os.path.join(tmp, 'Q390_b_0.wav'), tone(0.3))
        lines, skipped = voicebuild.project_lines(
            p, lambda project, ln: os.path.join(tmp, ln['voice']))
        self.assertEqual(skipped, [])
        want = [('Q390_a_0.wav', 123)] + ([('Q390_b_0.wav', 1)] if hero
                                          else [])
        self.assertEqual(sorted((ln['take'], ln['lector']) for ln in lines),
                         sorted(want))
        # a line with a take speaks its new cue, the others keep theirs
        tree, _texts = export.quest_texts(q, {'Q390_a_0.wav':
                                              'CUE_0123_0999'})
        self.assertIn('CUE_0123_0999', [e.cue for e in tree.entries])
        tree, _texts = export.quest_texts(q)
        self.assertNotIn('CUE_0123_0999', [e.cue for e in tree.entries])

    def test_speaker_without_lector_speaks_as_zero(self):
        q = self.quest()
        q.speakers[0]['lector'] = None       # an NPC from a multiplayer quest
        npc = next(n for n in q.graph['nodes'].values() if n['type'] == 'npc')
        npc['lines'][0]['voice'] = 'Q390_a_0.wav'
        npc['lines'].append(dict(npc['lines'][0], voice='Q390_gone.wav'))
        p = model.Project('T')
        p.quests.append(q)
        tmp = tempfile.mkdtemp()
        write_wav(os.path.join(tmp, 'Q390_a_0.wav'), tone(0.3))
        lines, skipped = voicebuild.project_lines(
            p, lambda project, ln: os.path.join(tmp, ln['voice']))
        self.assertEqual([(ln['take'], ln['lector']) for ln in lines],
                         [('Q390_a_0.wav', 0)])
        self.assertEqual(skipped, [(390, 'Q390_gone.wav')])


if __name__ == '__main__':
    unittest.main()
