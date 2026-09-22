"""Mouth movement file (4.5.0)."""

import array
import math
import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from questforge2 import lipsync  # noqa: E402


def speech(parts, rate=44100):
    """(seconds, amplitude) pieces of a 180 Hz tone as 16 bit PCM."""
    out = array.array('h')
    for secs, amp in parts:
        for i in range(int(secs * rate)):
            out.append(int(amp * math.sin(2 * math.pi * 180 * i / rate)))
    return out.tobytes()


class File(unittest.TestCase):
    def test_round_trip(self):
        entries = {'CUE_0001_0002': struct.pack('<IIB', 0, 80, 23),
                   'CUE_0001_0001': struct.pack('<IIBIIB', 0, 40, 0, 40, 90,
                                                2)}
        blob = lipsync.build(entries)
        self.assertEqual(struct.unpack_from('<I', blob, 0)[0], 2)
        # sorted by name like the game's file
        self.assertEqual(blob[4:17], b'CUE_0001_0001')
        self.assertEqual(lipsync.parse(blob), entries)
        self.assertEqual(lipsync.build(lipsync.parse(blob)), blob)

    def test_bad_input(self):
        with self.assertRaises(lipsync.LipSyncError):
            lipsync.build({'CUE_0001_0001': b'x' * 10})
        with self.assertRaises(lipsync.LipSyncError):
            lipsync.parse(struct.pack('<I', 5))


class Generate(unittest.TestCase):
    def test_follows_the_loudness(self):
        pcm = speech([(0.3, 0), (0.5, 20000), (0.4, 0), (0.4, 4000)])
        recs = lipsync.records(lipsync.generate(pcm))
        self.assertEqual(recs[0][0], 0)
        # the first 0.3 s are a pause, loud speech opens the mouth
        self.assertEqual(recs[0][2], lipsync.PAUSE)
        loud = [i for a, b, i in recs if 300 <= a < 800]
        self.assertTrue(loud and all(i in lipsync.OPEN for i in loud))
        # the second pause is left out like in the game's entries
        self.assertFalse([r for r in recs[1:] if 800 <= r[0] < 1200])
        quiet = [i for a, b, i in recs if a >= 1200]
        self.assertTrue(quiet and all(i in lipsync.CLOSED for i in quiet))
        self.assertLessEqual(recs[-1][1], 1600)
        # consecutive records never repeat an id, they are merged
        self.assertTrue(all(x[2] != y[2] or x[1] != y[0]
                            for x, y in zip(recs, recs[1:])))

    def test_silence(self):
        self.assertEqual(lipsync.generate(speech([(0.5, 0)])), b'')


if __name__ == '__main__':
    unittest.main()
