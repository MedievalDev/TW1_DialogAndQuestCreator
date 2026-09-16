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

    def test_project_without_voice_unchanged(self):
        p = Project('P')
        q = Quest(390, 't')
        p.quests.append(q)
        self.assertNotIn('"voice"', p.to_json())


if __name__ == '__main__':
    unittest.main()
