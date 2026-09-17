"""Voice recorder helpers (no microphone needed)."""

import array
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import recorder  # noqa: E402
from questforge2.model import Project, Quest  # noqa: E402


class Helpers(unittest.TestCase):
    def test_wav_roundtrip_and_peak(self):
        a = array.array('h', [0, 16384, -32768, 100] * 11025)
        pcm = a.tobytes()
        self.assertAlmostEqual(recorder.peak(pcm), 1.0)
        self.assertEqual(recorder.peak(b''), 0.0)
        with tempfile.TemporaryDirectory() as d:
            path = recorder.write_wav(os.path.join(d, 'v', 'x.wav'), pcm)
            self.assertAlmostEqual(recorder.duration(path), 1.0)
            self.assertIsNone(recorder.duration(os.path.join(d, 'no.wav')))

    def test_paths(self):
        p = Project('P')
        q = Quest(390, 't')
        line = {'text': 'x', 'voice': 'Q390_n3_0.wav'}
        self.assertIsNone(recorder.voice_dir(p))
        self.assertIsNone(recorder.voice_path(p, line))
        p.path = os.path.join('C:' + os.sep, 'x', 'Mod.tw1proj')
        self.assertEqual(recorder.voice_dir(p),
                         os.path.join('C:' + os.sep, 'x', 'Mod_voice'))
        self.assertEqual(recorder.voice_path(p, line),
                         os.path.join('C:' + os.sep, 'x', 'Mod_voice',
                                      'Q390_n3_0.wav'))
        self.assertEqual(recorder.voice_name(q, 'n3', 1), 'Q390_n3_1.wav')
        self.assertEqual(recorder.voice_name(q, 'a/b:c', 0), 'Q390_abc_0.wav')
        self.assertIsNone(recorder.voice_path(p, {'text': 'x'}))

    def test_take_name_never_overwrites_other_lines(self):
        p = Project('P')
        q = Quest(390, 't')
        p.quests.append(q)
        a = {'text': 'a', 'voice': 'Q390_n3_0.wav'}
        b = {'text': 'b'}
        q.graph['nodes']['n3'] = {'type': 'npc', 'lines': [b, a]}
        with tempfile.TemporaryDirectory() as d:
            p.path = os.path.join(d, 'P.tw1proj')
            # b moved to index 0: base name belongs to a -> suffix
            self.assertEqual(recorder.take_name(p, p.quests, q, 'n3', 0, b),
                             'Q390_n3_0_2.wav')
            # a records again: its own file
            self.assertEqual(recorder.take_name(p, p.quests, q, 'n3', 1, a),
                             'Q390_n3_0.wav')
            # copied line shares the file: new name, not the shared one
            c = dict(a)
            q.graph['nodes']['n3']['lines'].append(c)
            self.assertEqual(recorder.take_name(p, p.quests, q, 'n3', 2, c),
                             'Q390_n3_2.wav')
            # file left on disk (undo removed the link) is not overwritten
            os.makedirs(recorder.voice_dir(p))
            open(os.path.join(recorder.voice_dir(p), 'Q390_n3_2.wav'),
                 'wb').close()
            self.assertEqual(recorder.take_name(p, p.quests, q, 'n3', 2, c),
                             'Q390_n3_2_2.wav')
            self.assertEqual(recorder.voice_refs(p.quests),
                             {'Q390_n3_0.wav'})
            self.assertEqual(recorder.voice_refs(p.quests, skip=a),
                             {'Q390_n3_0.wav'})

    def test_copy_takes(self):
        with tempfile.TemporaryDirectory() as d:
            old, new = os.path.join(d, 'A_voice'), os.path.join(d, 'B_voice')
            recorder.write_wav(os.path.join(old, 'x.wav'), b'\0\0' * 100)
            self.assertEqual(recorder.copy_takes(old, new,
                                                 {'x.wav', 'gone.wav'}), 1)
            self.assertTrue(os.path.isfile(os.path.join(new, 'x.wav')))
            self.assertEqual(recorder.copy_takes(old, new, {'x.wav'}), 0)
            self.assertEqual(recorder.copy_takes(old, old, {'x.wav'}), 0)
            self.assertEqual(recorder.copy_takes(None, new, {'x.wav'}), 0)

    def test_trim_detect_restore_library(self):
        rate = 1000
        quiet = array.array('h', [0] * 500)
        loud = array.array('h', [12000, -12000] * 300)
        pcm = (quiet + loud + quiet).tobytes()
        start, end = recorder.detect_trim(pcm, rate, pad=0.05)
        self.assertAlmostEqual(start, 0.45, places=2)
        self.assertAlmostEqual(end, 1.15, places=2)
        self.assertEqual(len(recorder.cut(pcm, rate, 0.5, 1.1)), 1200)
        self.assertEqual(len(recorder.peaks(pcm, 16)), 16)
        self.assertEqual(recorder.peaks(pcm, 16)[0], 0.0)
        with tempfile.TemporaryDirectory() as d:
            p = Project('P')
            p.path = os.path.join(d, 'P.tw1proj')
            q = Quest(390, 't')
            p.quests.append(q)
            vdir = recorder.voice_dir(p)
            path = recorder.write_wav(os.path.join(vdir, 'Q390_n3_0.wav'),
                                      pcm, rate)
            recorder.write_wav(os.path.join(vdir, 'spare.wav'), pcm, rate)
            q.graph['nodes']['n3'] = {'type': 'npc', 'lines': [
                {'text': 'Hallo', 'voice': 'Q390_n3_0.wav'},
                {'text': 'Weg', 'voice': 'gone.wav'}]}
            self.assertAlmostEqual(recorder.trim_file(path, start, end),
                                   end - start, places=2)
            self.assertAlmostEqual(recorder.duration(path), end - start,
                                   places=2)
            self.assertTrue(os.path.isfile(recorder.original_path(path)))
            # a second trim keeps the first original
            recorder.trim_file(path, 0.1, 0.5)
            self.assertAlmostEqual(recorder.duration(
                recorder.original_path(path)), 1.6, places=2)
            lib = {it['name']: it for it in recorder.library(p, p.quests)}
            self.assertEqual(sorted(lib, key=str.lower),
                             ['gone.wav', 'Q390_n3_0.wav', 'spare.wav'])
            self.assertTrue(lib['Q390_n3_0.wav']['trimmed'])
            self.assertEqual(lib['Q390_n3_0.wav']['uses'][0][1:],
                             ('n3', 0, 'Hallo'))
            self.assertFalse(lib['gone.wav']['exists'])
            self.assertEqual(lib['spare.wav']['uses'], [])
            self.assertNotIn('_original', lib)
            # save as brings the backup along
            other = os.path.join(d, 'other_voice')
            self.assertEqual(recorder.copy_takes(vdir, other,
                                                 {'Q390_n3_0.wav'}), 1)
            self.assertTrue(os.path.isfile(recorder.original_path(
                os.path.join(other, 'Q390_n3_0.wav'))))
            self.assertTrue(recorder.restore_original(path))
            self.assertAlmostEqual(recorder.duration(path), 1.6, places=2)
            self.assertFalse(recorder.restore_original(path))
            with self.assertRaises(ValueError):
                recorder.trim_file(path, 0.0, 0.05)
            recorder.trim_file(path, 0.1, 1.0)
            recorder.drop_original(path)
            self.assertFalse(os.path.exists(recorder.original_path(path)))
            recorder.drop_original(path)            # twice is fine

    def test_project_without_voice_unchanged(self):
        p = Project('P')
        q = Quest(390, 't')
        p.quests.append(q)
        self.assertNotIn('"voice"', p.to_json())


if __name__ == '__main__':
    unittest.main()
