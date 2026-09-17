"""Voice line finder: ranking, speakers, ADPCM wrapper (no game needed)."""

import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import voicebank as vb  # noqa: E402

CUES = {
    'CUE_0001_0001': [1, 'Sag mir wo meine Schwester ist!', 'translateDQ_4'],
    'CUE_0001_0002': [1, 'Na gut. Wo ist meine Bezahlung?', 'translateDQ_4'],
    'CUE_0001_0003': [1, 'Danke.', 'translateDQ_7'],
    'CUE_0001_0004': [1, 'Nein, danke.', 'translateDQ_7'],
    'CUE_0001_0005': [1, "Ich werd's versuchen.", 'translateDQ_9'],
    'CUE_0001_0006': [1, 'Es war nicht einfach, zu dir zu kommen - ich '
                         'werde es versuchen, sagte ich mir.', 'translateDQ_9'],
    'CUE_0104_0001': [104, 'Danke.', 'translateDQ_12'],
    'CUE_0105_0001': [105, 'Wo ist meine Schwester?', ''],
}


class _Idx:
    cues = CUES
    lectors = {'104': [30]}
    npcs = {'30': {'name': 'Armin'}}


class Search(unittest.TestCase):
    def test_identical_first_and_hero_only(self):
        res = vb.search(CUES, 'Danke')
        self.assertEqual([r[1] for r in res[:2]],
                         ['CUE_0001_0003', 'CUE_0001_0004'])
        self.assertEqual(res[0][0], 1.0)
        self.assertTrue(all(r[2] == 1 for r in res))

    def test_all_speakers_and_filter(self):
        res = vb.search(CUES, 'Wo ist meine Schwester?', lector=None)
        self.assertEqual(res[0][1], 'CUE_0105_0001')
        self.assertEqual(vb.search(CUES, 'Danke', lector=104)[0][1],
                         'CUE_0104_0001')

    def test_short_close_line_beats_long_line(self):
        res = vb.search(CUES, 'Ich werde es versuchen')
        self.assertEqual(res[0][1], 'CUE_0001_0005')

    def test_similar_ranked(self):
        res = vb.search(CUES, 'Wo ist meine Schwester')
        self.assertEqual(res[0][1], 'CUE_0001_0001')
        self.assertGreater(res[0][0], res[1][0])

    def test_empty_query_lists_speaker(self):
        self.assertEqual(len(vb.search(CUES, '')), 6)
        self.assertEqual(vb.search(CUES, 'xyzzy qwrt'), [])

    def test_speakers_and_tree(self):
        sp = vb.speakers(_Idx)
        self.assertEqual(sp[0], (1, '', 6))
        self.assertIn((104, 'Armin', 1), sp)
        self.assertEqual(vb.tree_quest('translateDQ_15'), 15)
        self.assertIsNone(vb.tree_quest(''))


class Adpcm(unittest.TestCase):
    def test_header(self):
        raw = bytes(70 * 3 + 5)
        wav = vb.adpcm_wav(raw, 44100, 48)
        self.assertEqual(wav[:4], b'RIFF')
        self.assertEqual(struct.unpack_from('<I', wav, 4)[0], len(wav) - 8)
        tag, ch, rate, _avg, block, bits, _cb, spb = struct.unpack_from(
            '<HHIIHHHH', wav, 20)
        self.assertEqual((tag, ch, rate, block, bits, spb),
                         (2, 1, 44100, 70, 4, 128))
        self.assertTrue(wav.endswith(bytes(210)))
        self.assertIn(b'data' + struct.pack('<I', 210), wav)

    def test_missing_bank(self):
        ov = vb.OriginalVoices(os.path.join(ROOT, 'no_game_here'))
        self.assertFalse(ov.available())
        with self.assertRaises(vb.VoiceError):
            ov.wav_bytes('CUE_0001_0001')


if __name__ == '__main__':
    unittest.main()
